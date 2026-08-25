"""Tests for the GCP/BigQuery local proof (partition-pruning cost model)."""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gcp" / "local_proof"))


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    os.chdir(tmp_path_factory.mktemp("gcp"))
    import build_bq_model
    return build_bq_model.main("results.json")


def test_model_and_mart_built(result):
    assert result["fact_rows"] == 500_000
    assert result["mart_rows"] > 0


def test_partition_pruning_reduces_scan(result):
    p = result["partition_pruning"]
    # partition-only scan is far smaller than the full table
    assert p["scanned_partition_only"] < p["scanned_without_optimization"] * 0.2
    # partition + cluster is smaller still
    assert p["scanned_partition_plus_cluster"] < p["scanned_partition_only"]


def test_cost_reduction_is_material(result):
    assert result["partition_pruning"]["cost_reduction_vs_full_scan_pct"] > 90


def test_mart_aggregates_valid(result):
    for r in result["top_mart_rows"]:
        assert r["ro_count"] > 0 and r["total_revenue"] > 0


def test_production_pyspark_beam_syntax():
    import py_compile
    py_compile.compile(str(ROOT / "gcp" / "beam" / "streaming_pipeline.py"), doraise=True)
