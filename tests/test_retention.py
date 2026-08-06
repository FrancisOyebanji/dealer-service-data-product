"""Tests for the Service Retention analytics layer."""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    os.chdir(tmp_path_factory.mktemp("ret"))
    from retention import generate_service_history, retention_analytics
    generate_service_history.generate()
    return retention_analytics.run()


def test_churn_model_has_signal(report):
    assert report["model_metrics"]["churn_roc_auc"] > 0.65
    assert report["model_metrics"]["lift_at_10pct"] > 1.2      # top-risk decile churns more


def test_recovers_known_retention_drivers(report):
    # DGP makes recency (months_since_last) and warranty the strongest drivers.
    top4 = list(report["retention_drivers"])[:4]
    assert "months_since_last_service" in top4
    assert "in_warranty" in top4


def test_retention_kpis_bounded_and_segmented(report):
    k = report["service_retention_kpis"]
    assert 0 <= k["overall_retention_rate_pct"] <= 100
    assert k["by_region"] and k["by_warranty"]
    # in-warranty customers retain better than out-of-warranty (a known driver)
    assert k["by_warranty"]["in_warranty"] > k["by_warranty"]["out_of_warranty"]


def test_prescriptive_targets_at_risk(report):
    p = report["prescriptive"]
    assert p["at_risk_customers"] > 0
    assert sum(p["action_mix"].values()) == p["at_risk_customers"]
    # every sample recommendation has a churn risk and an action
    for rec in report["sample_recommendations"]:
        assert 0 <= rec["churn_risk"] <= 1
        assert rec["recommended_action"]
