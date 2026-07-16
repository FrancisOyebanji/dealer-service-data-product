"""One-command build of the entire data product:
sources -> ETL with DQ gates -> KPI checks -> dashboard.
"""
import subprocess
import sys

import build_dashboard
import etl
import generate_sources


def main() -> None:
    print("=== 1/3 Generating source systems ===")
    generate_sources.main()
    print("=== 2/3 Running ETL with data quality gates ===")
    s = etl.run()
    print(f"Extracted {s['extracted']:,} | loaded {s['loaded']:,} | rejected {s['rejected']:,} "
          f"({', '.join(f'{k}:{v}' for k, v in s['reject_reasons'].items())})")
    print("=== 3/3 Building dashboard ===")
    build_dashboard.main()
    print("\nRun acceptance tests with: python -m pytest tests/ -q")


if __name__ == "__main__":
    main()
