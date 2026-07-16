"""Synthetic heterogeneous source systems for the dealer service data product.

Simulates three real-world-shaped sources that must be integrated:
  1. DMS repair orders   -> CSV   (dealer management system extract)
  2. Customer survey API -> JSON  (post-service satisfaction, nested payloads)
  3. Vehicle master      -> CSV   (VIN registry with model/warranty attributes)

All data is synthetic. Customer PII fields exist deliberately — the governance
layer's masking and retention policies need something real-shaped to govern.
"""
from __future__ import annotations

import csv
import json
import random
from pathlib import Path

SEED = 11
N_DEALERS = 40
N_VEHICLES = 3000
N_ORDERS = 12000

MODELS = ["F-150", "Escape", "Explorer", "Bronco", "Mustang", "Maverick", "Edge", "Transit"]
SERVICE_TYPES = ["scheduled_maintenance", "warranty_repair", "customer_pay_repair", "recall", "diagnostic"]
PAY_TYPE = {"scheduled_maintenance": "customer", "customer_pay_repair": "customer",
            "warranty_repair": "warranty", "recall": "warranty", "diagnostic": "customer"}
REGIONS = ["Northeast", "Southeast", "Midwest", "Southwest", "West"]
FIRST = ["Alex", "Jordan", "Sam", "Taylor", "Morgan", "Casey", "Riley", "Devon"]
LAST = ["Rivera", "Chen", "Okafor", "Nguyen", "Smith", "Garcia", "Kim", "Patel"]


def main(out_dir: str = "data/sources") -> None:
    rng = random.Random(SEED)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # --- Vehicle master (CSV) ---
    vehicles = []
    for i in range(N_VEHICLES):
        vin = f"1FTSYN{i:011d}"
        vehicles.append({
            "vin": vin,
            "model": rng.choice(MODELS),
            "model_year": rng.randint(2019, 2026),
            "warranty_months": rng.choice([36, 36, 60]),
            "in_service_date": f"{rng.randint(2019, 2024)}-{rng.randint(1,12):02d}-01",
        })
    with open(out / "vehicle_master.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=vehicles[0].keys())
        w.writeheader(); w.writerows(vehicles)

    # --- DMS repair orders (CSV) — includes deliberate quality issues ---
    orders = []
    for i in range(N_ORDERS):
        v = rng.choice(vehicles)
        st = rng.choice(SERVICE_TYPES)
        dealer_n = rng.randint(1, N_DEALERS)
        labor = round(rng.uniform(60, 900), 2)
        parts = round(rng.uniform(0, 1400), 2)
        row = {
            "ro_number": f"RO{i:07d}",
            "dealer_id": f"D{dealer_n:03d}",
            "vin": v["vin"],
            "service_type": st,
            "open_date": f"2025-{rng.randint(1,12):02d}-{rng.randint(1,28):02d}",
            "days_to_close": rng.choices([1, 2, 3, 5, 8], weights=[50, 25, 12, 8, 5])[0],
            "labor_amount": labor,
            "parts_amount": parts,
            "pay_type": PAY_TYPE[st],
            "customer_email": f"{rng.choice(FIRST).lower()}.{rng.choice(LAST).lower()}{rng.randint(1,999)}@example.test",
            "customer_phone": f"555-{rng.randint(200,999)}-{rng.randint(1000,9999)}",
            "repeat_repair_flag": rng.choices([0, 1], weights=[85, 15])[0],
        }
        # Deliberate DQ issues the pipeline must catch (~2%)
        roll = rng.random()
        if roll < 0.008:
            row["vin"] = ""                      # missing key
        elif roll < 0.014:
            row["labor_amount"] = -abs(labor)    # negative amount
        elif roll < 0.02:
            row["ro_number"] = orders[-1]["ro_number"] if orders else row["ro_number"]  # duplicate
        orders.append(row)
    with open(out / "dms_repair_orders.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=orders[0].keys())
        w.writeheader(); w.writerows(orders)

    # --- Customer surveys (JSON, nested) ---
    surveys = []
    for row in rng.sample(orders, k=int(N_ORDERS * 0.35)):
        surveys.append({
            "survey_id": f"S{rng.randrange(10**8):08d}",
            "ro_number": row["ro_number"],
            "response": {
                "satisfaction": rng.choices([5, 4, 3, 2, 1], weights=[38, 30, 16, 10, 6])[0],
                "would_recommend": rng.choice([True, True, True, False]),
                "comments_present": rng.choice([True, False]),
            },
            "channel": rng.choice(["email", "sms", "app"]),
        })
    (out / "customer_surveys.json").write_text(json.dumps(surveys, indent=1))

    # --- Dealer reference (CSV) ---
    with open(out / "dealer_reference.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["dealer_id", "dealer_name", "region", "service_bays"])
        for n in range(1, N_DEALERS + 1):
            w.writerow([f"D{n:03d}", f"Dealer {n:03d}", rng.choice(REGIONS), rng.randint(4, 24)])

    print(f"Sources written to {out}/: {N_ORDERS:,} repair orders, {len(surveys):,} surveys, "
          f"{N_VEHICLES:,} vehicles, {N_DEALERS} dealers")


if __name__ == "__main__":
    main()
