"""UAT-style acceptance tests for the data product.

These encode the acceptance criteria a business stakeholder signs off on —
run after every ETL execution, before the dashboard is considered publishable.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import etl
import generate_sources


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    work = tmp_path_factory.mktemp("wh")
    src = work / "sources"
    generate_sources.main(str(src))
    db = work / "warehouse.db"
    etl.run(str(src), str(db))
    return sqlite3.connect(db)


def one(conn, sql):
    return conn.execute(sql).fetchone()[0]


# --- AC1: referential integrity — every fact row resolves to all dimensions ---
def test_no_orphan_fact_rows(conn):
    orphans = one(conn, """
        SELECT COUNT(*) FROM fact_repair_orders f
        LEFT JOIN dim_dealer  dd ON dd.dealer_key  = f.dealer_key
        LEFT JOIN dim_vehicle dv ON dv.vehicle_key = f.vehicle_key
        LEFT JOIN dim_date    d  ON d.date_key     = f.open_date_key
        WHERE dd.dealer_key IS NULL OR dv.vehicle_key IS NULL OR d.date_key IS NULL""")
    assert orphans == 0


# --- AC2: DQ gates actually reject bad rows, and reconciliation balances ---
def test_reconciliation_extract_equals_load_plus_rejects(conn):
    extracted = one(conn, "SELECT row_count FROM etl_audit WHERE stage='extract' AND entity='orders'")
    loaded = one(conn, "SELECT row_count FROM etl_audit WHERE stage='load' AND entity='fact_repair_orders'")
    rejected = one(conn, "SELECT row_count FROM etl_audit WHERE stage='validate' AND entity='orders_rejected'")
    assert extracted == loaded + rejected
    assert rejected > 0  # the seeded DQ issues must be caught, not slip through


def test_rejects_have_documented_reasons(conn):
    unreasoned = one(conn, "SELECT COUNT(*) FROM dq_rejects WHERE reason IS NULL OR reason = ''")
    assert unreasoned == 0


# --- AC3: no negative or null financial measures in the fact table ---
def test_fact_measures_are_valid(conn):
    bad = one(conn, """SELECT COUNT(*) FROM fact_repair_orders
                       WHERE labor_amount < 0 OR parts_amount < 0
                          OR total_amount IS NULL
                          OR ABS(total_amount - labor_amount - parts_amount) > 0.01""")
    assert bad == 0


# --- AC4: uniqueness at declared grain ---
def test_ro_number_unique_at_grain(conn):
    dupes = one(conn, """SELECT COUNT(*) FROM
        (SELECT ro_number FROM fact_repair_orders GROUP BY ro_number HAVING COUNT(*) > 1)""")
    assert dupes == 0


# --- AC5: privacy by design — no raw PII anywhere in the warehouse ---
def test_no_raw_pii_in_warehouse(conn):
    # email_hash must be hex digests, never contain '@'
    assert one(conn, "SELECT COUNT(*) FROM dim_customer WHERE email_hash LIKE '%@%'") == 0
    # phone_last4 must be exactly 4 chars
    assert one(conn, "SELECT COUNT(*) FROM dim_customer WHERE LENGTH(phone_last4) != 4") == 0
    # and no table may carry a raw email/phone column at all
    for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        cols = [c[1] for c in conn.execute(f"PRAGMA table_info({table})")]
        assert "customer_email" not in cols and "customer_phone" not in cols, table


# --- AC6: survey coverage lands in the expected band (join sanity) ---
def test_survey_join_coverage(conn):
    pct = one(conn, """SELECT 100.0 * SUM(satisfaction_score IS NOT NULL) / COUNT(*)
                       FROM fact_repair_orders""")
    assert 25 <= pct <= 45  # sources generate ~35% survey response
