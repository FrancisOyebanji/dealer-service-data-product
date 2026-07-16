"""ETL: heterogeneous sources -> validated star schema.

Pipeline stages:
  Extract   : CSV (DMS, vehicle master, dealer ref) + nested JSON (surveys)
  Validate  : data quality gates BEFORE load; rejects quarantined with reasons
  Transform : PII minimization (hash email, truncate phone), survey flattening,
              surrogate keys, conformed date dimension
  Load      : SQLite star schema (BigQuery DDL in sql/schema_bigquery.sql)

Every stage logs row counts to etl_audit — reconciliation is a query, not a hope.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = "data/warehouse.db"

SCHEMA = """
DROP TABLE IF EXISTS dim_dealer;   DROP TABLE IF EXISTS dim_vehicle;
DROP TABLE IF EXISTS dim_customer; DROP TABLE IF EXISTS dim_date;
DROP TABLE IF EXISTS fact_repair_orders; DROP TABLE IF EXISTS etl_audit;
DROP TABLE IF EXISTS dq_rejects;

CREATE TABLE dim_dealer (dealer_key INTEGER PRIMARY KEY, dealer_id TEXT UNIQUE, dealer_name TEXT,
                         region TEXT, service_bays INTEGER);
CREATE TABLE dim_vehicle (vehicle_key INTEGER PRIMARY KEY, vin TEXT UNIQUE, model TEXT,
                          model_year INTEGER, warranty_months INTEGER, in_service_date TEXT);
CREATE TABLE dim_customer (customer_key INTEGER PRIMARY KEY, email_hash TEXT UNIQUE,
                           phone_last4 TEXT, consent_status TEXT);
CREATE TABLE dim_date (date_key INTEGER PRIMARY KEY, full_date TEXT, year INTEGER, quarter INTEGER,
                       month INTEGER, month_name TEXT, is_weekend INTEGER);
CREATE TABLE fact_repair_orders (
    ro_key INTEGER PRIMARY KEY, ro_number TEXT UNIQUE, dealer_key INTEGER, vehicle_key INTEGER,
    customer_key INTEGER, open_date_key INTEGER, service_type TEXT, pay_type TEXT,
    days_to_close INTEGER, labor_amount REAL, parts_amount REAL, total_amount REAL,
    repeat_repair_flag INTEGER, satisfaction_score INTEGER, would_recommend INTEGER);
CREATE INDEX idx_fact_dealer ON fact_repair_orders(dealer_key);
CREATE INDEX idx_fact_date   ON fact_repair_orders(open_date_key);
CREATE INDEX idx_fact_type   ON fact_repair_orders(service_type);

CREATE TABLE etl_audit (stage TEXT, entity TEXT, row_count INTEGER, logged_at TEXT);
CREATE TABLE dq_rejects (ro_number TEXT, reason TEXT, raw_row TEXT);
"""

MONTHS = ["", "January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


def _audit(conn, stage, entity, n):
    conn.execute("INSERT INTO etl_audit VALUES (?,?,?,?)",
                 (stage, entity, n, datetime.now(timezone.utc).isoformat(timespec="seconds")))


def _hash_email(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


def validate_orders(rows: list[dict], conn) -> list[dict]:
    """DQ gates: reject rows that would corrupt the fact table; quarantine with reasons."""
    seen, clean = set(), []
    for r in rows:
        reasons = []
        if not r["vin"]:
            reasons.append("missing_vin")
        if float(r["labor_amount"]) < 0 or float(r["parts_amount"]) < 0:
            reasons.append("negative_amount")
        if r["ro_number"] in seen:
            reasons.append("duplicate_ro_number")
        if r["service_type"] not in ("scheduled_maintenance", "warranty_repair",
                                     "customer_pay_repair", "recall", "diagnostic"):
            reasons.append("invalid_service_type")
        if reasons:
            conn.execute("INSERT INTO dq_rejects VALUES (?,?,?)",
                         (r["ro_number"], ",".join(reasons), json.dumps(r)))
        else:
            seen.add(r["ro_number"])
            clean.append(r)
    return clean


def run(source_dir: str = "data/sources", db_path: str = DB_PATH) -> dict:
    src = Path(source_dir)
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)

    # ---------- Extract ----------
    orders = list(csv.DictReader(open(src / "dms_repair_orders.csv")))
    vehicles = list(csv.DictReader(open(src / "vehicle_master.csv")))
    dealers = list(csv.DictReader(open(src / "dealer_reference.csv")))
    surveys = json.loads((src / "customer_surveys.json").read_text())
    for name, rows in [("orders", orders), ("vehicles", vehicles),
                       ("dealers", dealers), ("surveys", surveys)]:
        _audit(conn, "extract", name, len(rows))

    # ---------- Validate ----------
    clean = validate_orders(orders, conn)
    _audit(conn, "validate", "orders_clean", len(clean))
    _audit(conn, "validate", "orders_rejected", len(orders) - len(clean))

    # ---------- Transform + Load dims ----------
    for d in dealers:
        conn.execute("INSERT INTO dim_dealer (dealer_id, dealer_name, region, service_bays) VALUES (?,?,?,?)",
                     (d["dealer_id"], d["dealer_name"], d["region"], int(d["service_bays"])))
    for v in vehicles:
        conn.execute("INSERT INTO dim_vehicle (vin, model, model_year, warranty_months, in_service_date) "
                     "VALUES (?,?,?,?,?)",
                     (v["vin"], v["model"], int(v["model_year"]), int(v["warranty_months"]), v["in_service_date"]))

    # Customers: PII minimized at transform time — raw email/phone never loaded
    cust_keys: dict[str, int] = {}
    for r in clean:
        h = _hash_email(r["customer_email"])
        if h not in cust_keys:
            cur = conn.execute("INSERT INTO dim_customer (email_hash, phone_last4, consent_status) VALUES (?,?,?)",
                               (h, r["customer_phone"][-4:], "consented"))
            cust_keys[h] = cur.lastrowid

    # Date dimension from observed dates
    for ds in sorted({r["open_date"] for r in clean}):
        dt = datetime.strptime(ds, "%Y-%m-%d")
        conn.execute("INSERT OR IGNORE INTO dim_date VALUES (?,?,?,?,?,?,?)",
                     (int(ds.replace("-", "")), ds, dt.year, (dt.month - 1) // 3 + 1,
                      dt.month, MONTHS[dt.month], int(dt.weekday() >= 5)))

    # Survey lookup: ro_number -> (satisfaction, recommend)
    survey_by_ro = {s["ro_number"]: (s["response"]["satisfaction"], int(s["response"]["would_recommend"]))
                    for s in surveys}

    dealer_keys = dict(conn.execute("SELECT dealer_id, dealer_key FROM dim_dealer"))
    vehicle_keys = dict(conn.execute("SELECT vin, vehicle_key FROM dim_vehicle"))

    # ---------- Load fact ----------
    n_fact = 0
    for r in clean:
        sat, rec = survey_by_ro.get(r["ro_number"], (None, None))
        labor, parts = float(r["labor_amount"]), float(r["parts_amount"])
        conn.execute(
            "INSERT INTO fact_repair_orders (ro_number, dealer_key, vehicle_key, customer_key, "
            "open_date_key, service_type, pay_type, days_to_close, labor_amount, parts_amount, "
            "total_amount, repeat_repair_flag, satisfaction_score, would_recommend) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (r["ro_number"], dealer_keys[r["dealer_id"]], vehicle_keys[r["vin"]],
             cust_keys[_hash_email(r["customer_email"])], int(r["open_date"].replace("-", "")),
             r["service_type"], r["pay_type"], int(r["days_to_close"]), labor, parts,
             round(labor + parts, 2), int(r["repeat_repair_flag"]), sat, rec))
        n_fact += 1
    _audit(conn, "load", "fact_repair_orders", n_fact)
    conn.commit()

    stats = {
        "extracted": len(orders), "loaded": n_fact,
        "rejected": len(orders) - len(clean),
        "reject_reasons": dict(conn.execute(
            "SELECT reason, COUNT(*) FROM dq_rejects GROUP BY reason ORDER BY 2 DESC")),
    }
    conn.close()
    return stats


if __name__ == "__main__":
    s = run()
    print(f"Extracted {s['extracted']:,} | loaded {s['loaded']:,} | rejected {s['rejected']:,}")
    for reason, n in s["reject_reasons"].items():
        print(f"  reject: {reason}: {n}")
