# BigQuery Cost Optimization & Governance

The performance/cost and security design decisions a Data Architect documents and
defends. Values are illustrative; the [local proof](local_proof/) quantifies the
partition/cluster savings on 500k rows.

## Cost optimization

| Lever | Decision | Impact |
|---|---|---|
| **Partitioning** | Partition the fact by `service_date` | Date-filtered queries scan one partition, not the table — **~94% fewer rows scanned** in the proof |
| **Clustering** | Cluster by `dealer_key, service_type` | Within a partition, dealer/type filters read only the relevant blocks — **99.95% reduction** combined with partitioning |
| **`require_partition_filter`** | Enforced `true` | Prevents accidental full-table scans (a common cost blowout) |
| **Materialized views** | `mv_monthly_dealer_revenue` | Dashboards hit a small pre-aggregate; BigQuery auto-routes and keeps it fresh incrementally |
| **BI Engine** | Reserve for dashboard datasets | Sub-second, in-memory BI without repeated scan cost |
| **Storage** | `partition_expiration_days` + long-term storage tier | Old partitions auto-expire; untouched data drops to cheaper storage automatically |
| **Compute** | Slot reservations for predictable workloads; on-demand for spiky | Predictable spend vs elasticity tradeoff |

Rule of thumb communicated to clients: **on-demand BigQuery bills by bytes scanned**, so partition + cluster design is the single biggest cost lever — model it deliberately, and enforce it with `require_partition_filter`.

## Governance & security

| Control | Mechanism |
|---|---|
| **Least-privilege access** | IAM at dataset level; analysts get `dataViewer` on gold only, never the raw fact |
| **Column-level security** | Data Catalog **policy tags** on PII columns (e.g., `customer_pii`); only tagged principals can read |
| **Row/column governance** | **Authorized views** expose a curated projection without granting base-table access |
| **Encryption** | CMEK (customer-managed keys) on sensitive datasets |
| **Network isolation** | VPC Service Controls perimeter around the analytics project |
| **Lineage & quality** | Dataplex profiling + Dataform assertions (uniqueness, non-null, domain checks) as CI gates |
| **Data classification** | Sensitivity labels drive masking and retention policy per column |
| **Auditability** | BigQuery audit logs + Data Catalog record every access and schema change |

## Migration cost & risk notes

- Land raw cheaply in Cloud Storage before any transformation — decouples cutover from re-modeling.
- Reconcile legacy vs BigQuery outputs (row counts → aggregates → field-level) before decommissioning, so cutover is evidence-based.
- Right-size slot reservations only after observing steady-state query patterns; start on-demand.
