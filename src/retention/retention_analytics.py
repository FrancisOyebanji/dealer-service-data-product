"""Service Retention analytics: predictive model, KPIs, and prescriptive actions.

  - retention_model : predict whether a customer returns for service; surface the
    retention DRIVERS (feature importances) — the "insights and recommendations
    around Service Retention and related KPIs" the role centers on.
  - service_retention_kpis : retention rate overall and by segment (dealer region,
    warranty status, model), plus the at-risk population.
  - prescriptive_actions : recommend a targeted retention action per at-risk
    customer, ranked by churn risk x customer value.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import train_test_split

FEATURES = ["vehicle_age", "in_warranty", "prior_visits", "months_since_last_service",
            "avg_satisfaction", "avg_wait_days", "repeat_repair_rate",
            "customer_pay_share", "distance_to_dealer_mi", "total_service_spend", "had_recall"]


def load(path="data/retention/customer_service_history.csv") -> list[dict]:
    rows = list(csv.DictReader(open(path)))
    for r in rows:
        for k in FEATURES + ["retained_next_period"]:
            r[k] = float(r[k])
    return rows


# ---------- predictive model ----------
def retention_model(rows) -> dict:
    X = np.array([[r[f] for f in FEATURES] for r in rows])
    y = np.array([1 - r["retained_next_period"] for r in rows])   # model CHURN (1 = did not return)
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)
    m = GradientBoostingClassifier(random_state=42, n_estimators=250, max_depth=3, learning_rate=0.06)
    m.fit(Xtr, ytr)
    p = m.predict_proba(Xte)[:, 1]
    # lift at top-10% churn-risk on the held-out set (where outreach is targeted)
    idx = np.argsort(-p)[:max(1, len(p) // 10)]
    lift = float(yte[idx].mean() / yte.mean())
    drivers = dict(sorted(zip(FEATURES, m.feature_importances_.round(4)), key=lambda kv: -kv[1]))
    # score ALL customers for KPIs/prescription
    churn_all = m.predict_proba(X)[:, 1]
    return {"model": m, "churn_scores": churn_all,
            "metrics": {"churn_roc_auc": round(float(roc_auc_score(yte, p)), 4),
                        "churn_pr_auc": round(float(average_precision_score(yte, p)), 4),
                        "lift_at_10pct": round(lift, 2)},
            "retention_drivers": drivers}


# ---------- KPIs ----------
def service_retention_kpis(rows) -> dict:
    def rate(subset): return round(100 * np.mean([r["retained_next_period"] for r in subset]), 1) if subset else 0.0

    by_warranty = {("in_warranty" if int(r["in_warranty"]) else "out_of_warranty"): None for r in rows}
    kpis = {
        "overall_retention_rate_pct": rate(rows),
        "by_warranty": {k: rate([r for r in rows if ("in_warranty" if int(r["in_warranty"]) else "out_of_warranty") == k])
                        for k in by_warranty},
        "by_region": {reg: rate([r for r in rows if r["region"] == reg])
                      for reg in sorted({r["region"] for r in rows})},
        "by_model": dict(sorted({m: rate([r for r in rows if r["model"] == m])
                                 for m in {r["model"] for r in rows}}.items(),
                                key=lambda kv: kv[1])),
    }
    return kpis


# ---------- prescriptive ----------
ACTIONS = {
    "lapsed_maintenance_reminder": {"applies": lambda r: r["months_since_last_service"] > 8, "value": 3},
    "warranty_expiry_offer":       {"applies": lambda r: r["in_warranty"] and r["vehicle_age"] >= 3, "value": 4},
    "service_recovery_outreach":   {"applies": lambda r: r["avg_satisfaction"] < 3.5 or r["repeat_repair_rate"] > 0.25, "value": 5},
    "loyalty_discount":            {"applies": lambda r: r["customer_pay_share"] > 0.6, "value": 2},
    "recall_completion_followup":  {"applies": lambda r: r["had_recall"] == 1, "value": 3},
}


def prescriptive_actions(rows, churn_scores, top_pct: float = 0.15) -> dict:
    scored = sorted(zip(rows, churn_scores), key=lambda t: -t[1])
    n = int(len(rows) * top_pct)
    at_risk = scored[:n]
    recs = []
    for r, churn in at_risk:
        # eligible actions ranked by action value x churn risk
        options = [(a, cfg["value"]) for a, cfg in ACTIONS.items() if cfg["applies"](r)]
        if not options:
            action = "personalized_service_reminder"
        else:
            action = max(options, key=lambda o: o[1])[0]
        recs.append({"customer_key": r["customer_key"], "churn_risk": round(float(churn), 3),
                     "recommended_action": action,
                     "expected_value": round(float(churn) * ACTIONS.get(action, {"value": 1})["value"], 3)})
    from collections import Counter
    return {"at_risk_customers": n,
            "action_mix": dict(Counter(x["recommended_action"] for x in recs)),
            "top_recommendations": recs[:20]}


def run(out_path="reports/retention_report.json") -> dict:
    rows = load()
    model = retention_model(rows)
    kpis = service_retention_kpis(rows)
    rx = prescriptive_actions(rows, model["churn_scores"])
    result = {"model_metrics": model["metrics"], "retention_drivers": model["retention_drivers"],
              "service_retention_kpis": kpis, "prescriptive": {k: v for k, v in rx.items()
                                                               if k != "top_recommendations"},
              "sample_recommendations": rx["top_recommendations"][:10]}
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    r = run()
    print("Churn model AUC:", r["model_metrics"]["churn_roc_auc"],
          "| lift@10%:", r["model_metrics"]["lift_at_10pct"])
    print("Overall service retention rate:", r["service_retention_kpis"]["overall_retention_rate_pct"], "%")
    print("Top retention drivers:", list(r["retention_drivers"])[:4])
    print("At-risk action mix:", r["prescriptive"]["action_mix"])
