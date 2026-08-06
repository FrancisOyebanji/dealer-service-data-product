"""Synthetic customer service-visit history for Service Retention modeling.

Extends the dealer-service data product with a customer-level, multi-visit
history designed for retention analytics. Each customer owns a vehicle and has a
sequence of service visits over an observation window; a KNOWN churn process
governs whether they return for service in the outcome window, driven by
realistic Service Retention drivers:

  - recency / frequency of prior service
  - vehicle age & warranty status (in-warranty customers return more)
  - service experience (satisfaction, wait time, repeat repairs)
  - distance to dealer, customer-pay vs warranty mix, recall touchpoints

The true churn label is constructed so the retention model can be graded on
whether it recovers the drivers. All data is synthetic; no real customer data.
"""
from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path

import numpy as np

SEED = 41
N_CUSTOMERS = 15000
OBS_START = date(2023, 1, 1)
FEATURE_CUTOFF = date(2024, 7, 1)     # features use visits before this
OUTCOME_END = date(2025, 1, 1)        # retained if a visit occurs in [cutoff, end]

MODELS = ["Altima", "Rogue", "Sentra", "Pathfinder", "Frontier", "Kicks", "Murano"]
REGIONS = ["Northeast", "Southeast", "Midwest", "Southwest", "West"]
SERVICE_TYPES = ["scheduled_maintenance", "warranty_repair", "customer_pay_repair", "recall"]


def _sigmoid(z): return 1 / (1 + np.exp(-z))


def generate(out_dir: str = "data/retention") -> None:
    rng = np.random.default_rng(SEED)
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)

    model_year = rng.integers(2016, 2024, N_CUSTOMERS)
    vehicle_age = 2024 - model_year
    in_warranty = (vehicle_age <= 3).astype(int)
    dealer_id = rng.integers(1, 61, N_CUSTOMERS)
    region = rng.choice(REGIONS, N_CUSTOMERS)
    model = rng.choice(MODELS, N_CUSTOMERS)
    distance_mi = np.round(rng.gamma(2.0, 6.0, N_CUSTOMERS), 1)

    # Prior service behavior (feature window)
    prior_visits = rng.poisson(np.clip(3.5 - 0.25 * vehicle_age, 0.5, None), N_CUSTOMERS)
    months_since_last = np.clip(rng.exponential(6, N_CUSTOMERS) + 0.5 * vehicle_age, 0.2, 36).round(1)
    avg_satisfaction = np.clip(rng.normal(4.1 - 0.05 * vehicle_age, 0.7, N_CUSTOMERS), 1, 5).round(1)
    avg_wait_days = np.clip(rng.normal(1.8 + 0.1 * vehicle_age, 0.8, N_CUSTOMERS), 0.2, 10).round(1)
    repeat_repair_rate = np.clip(rng.beta(1.5, 8, N_CUSTOMERS), 0, 1).round(3)
    customer_pay_share = np.clip(rng.beta(2, 2, N_CUSTOMERS), 0, 1).round(3)
    total_spend = np.round(prior_visits * rng.uniform(120, 650, N_CUSTOMERS), 2)
    had_recall = rng.integers(0, 2, N_CUSTOMERS)

    # KNOWN retention (return-for-service) propensity
    z = (0.9
         + 0.9 * in_warranty                       # warranty is the top driver
         - 0.10 * months_since_last                # recency: stale customers churn
         + 0.18 * prior_visits                      # frequency/loyalty
         + 0.35 * (avg_satisfaction - 4)            # experience
         - 0.12 * avg_wait_days
         - 1.4 * repeat_repair_rate                 # comebacks erode trust
         - 0.03 * distance_mi
         + 0.25 * had_recall                        # recall brings them in
         + rng.normal(0, 0.5, N_CUSTOMERS))
    p_retain = _sigmoid(z)
    retained = (rng.random(N_CUSTOMERS) < p_retain).astype(int)

    rows = []
    for i in range(N_CUSTOMERS):
        rows.append({
            "customer_key": f"CU{i:06d}", "dealer_id": f"D{dealer_id[i]:03d}",
            "region": region[i], "model": model[i], "model_year": int(model_year[i]),
            "vehicle_age": int(vehicle_age[i]), "in_warranty": int(in_warranty[i]),
            "prior_visits": int(prior_visits[i]),
            "months_since_last_service": float(months_since_last[i]),
            "avg_satisfaction": float(avg_satisfaction[i]),
            "avg_wait_days": float(avg_wait_days[i]),
            "repeat_repair_rate": float(repeat_repair_rate[i]),
            "customer_pay_share": float(customer_pay_share[i]),
            "distance_to_dealer_mi": float(distance_mi[i]),
            "total_service_spend": float(total_spend[i]),
            "had_recall": int(had_recall[i]),
            "retained_next_period": int(retained[i]),
        })

    with open(out / "customer_service_history.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    rate = np.mean(retained)
    print(f"Wrote {N_CUSTOMERS:,} customers to {out}/customer_service_history.csv "
          f"(service retention rate {rate:.1%})")


if __name__ == "__main__":
    generate()
