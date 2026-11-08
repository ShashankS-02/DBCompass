# 05 — Scoring and Cost Model

Pipeline: **Filter → Score → Combine → Size → Price → Rank → Explain**

## 1. Filter (hard constraints)
A candidate is removed if any of these fail. Each removal is logged in the trace.
- Data shape family not compatible (via a family compatibility matrix in rules.yaml)
- Consistency requirement not met
- SLA requirement above the service's SLA for the requested topology
- Multi-region active-active required but not supported
- Residency regions not available for the service
- Compliance regime not supported
- Max storage below 3-year projected size (`current + growth × 36`)
- Excluded by user or CSP mandated elsewhere
- Single-region monthly cost of cheapest viable size > budget cap × 1.5 (soft margin)

## 2. Score (0–100 per dimension)
| Dimension | How it is computed |
|---|---|
| performance | latency_class vs target, write scaling vs write load, read replica headroom vs read load |
| cost | normalised inverse of Balanced tier monthly cost among survivors |
| reliability | SLA headroom, RPO/RTO capability vs need, multi-region support |
| ops | ops_complexity, managed_pref match, team skills match, DBA support |
| ecosystem | driver/ORM support for languages, CDC/vector/analytics needs, existing licenses |
| compliance | features: CMK, audit, private endpoint, IAM auth, masking/RLS |
| portability | engine openness, proprietary_lock_in vs pref.lock_in |

Weights come from priority sliders, normalised to sum 1. Defaults:
performance 0.20, cost 0.20, reliability 0.20, ops 0.15, ecosystem 0.10, compliance 0.10, portability 0.05.
Rule boosts and penalties are applied after weighting and clipped to 0–100.

## 3. Combine (polyglot)
Trigger a combination when more than one need exists:
| Need detected | Component added |
|---|---|
| p99 < 1 ms or read-heavy hot keys | in_memory cache |
| full-text query type | search engine (or Postgres FTS if light) |
| eco.analytics = warehouse or OLAP alongside OLTP | analytics store fed by CDC |
| eco.vector and primary lacks vector | vector-capable store |
| time-series high ingest | time-series store |
Rules: prefer same CSP for all components; add a cross-component cost line for CDC/ETL;
cap at 3 components for the MVP; a single DB that covers all needs "well enough" gets a
simplicity bonus so the engine does not over-engineer.

## 4. Size
1. Derive vCPU, memory, IOPS, throughput (doc 02 formulas) unless given.
2. Pick smallest instance in `hardware_profiles.yaml` matching the family that satisfies
   vCPU and memory with 30% headroom.
3. Pick storage tier whose IOPS/throughput ceiling covers the need at lowest cost.
4. HA layout from SLA/RPO/RTO: single instance → Multi-AZ standby → Multi-AZ + read replicas →
   cross-region replica → global/active-active service.

## 5. Price — three tiers
| Tier | Approach |
|---|---|
| Budget | Smallest viable size, minimum HA that still meets SLA, 3-year commitment if allowed |
| Balanced | Sized with headroom, recommended HA, 1-year commitment if allowed |
| Performance | One size up, extra replicas, highest storage tier, on-demand |

Monthly cost formula per component:
```
compute      = hourly_rate * 730 * node_count
storage      = provisioned_gb * gb_month_rate
iops         = max(0, provisioned_iops - included_iops) * iops_month_rate
backup       = max(0, backup_gb - free_backup_gb) * backup_gb_rate
egress       = estimated_egress_gb * egress_rate
licensing    = included in rate or BYOL adjustment
total        = sum of the above, per environment, times env multipliers (prod 1.0, DR, UAT, dev from input)
```

## Pricing sources
| CSP | Source | Notes |
|---|---|---|
| Azure | Azure Retail Prices REST API (`https://prices.azure.com/api/retail/prices`) | Public, no auth; filter with OData `$filter` by serviceName, armRegionName, skuName |
| AWS | AWS Price List Query API (GetProducts, needs IAM creds) or the public bulk offer JSON files | For hackathon: pre-download offer files for RDS, DynamoDB, ElastiCache, EC2, EBS and cache to `price_snapshots/` |
| GCP | Cloud Billing Catalog API (`services.skus.list`, needs API key) | For hackathon: snapshot to JSON |
All prices cached with `fetched_at`. UI shows "prices as of <date>, list price, excludes
enterprise discounts". The LLM never produces numbers.

### Pricing as implemented (M4)
- Snapshots: AWS bulk CSVs and Azure Retail Prices API built on 2026-11-07 for one region per
  geography (ap-south-1 / centralindia, eu-west-1 / westeurope, us-east-1 / eastus,
  ap-southeast-1 / southeastasia). GCP snapshot built 2026-11-08 from the Cloud Billing Catalog API
  (service account) for asia-south1, europe-west1, us-central1, asia-southeast1.
- 31 services priced, 23 marked `not_priced` with reasons (contract-priced Oracle@CSP, Spanner,
  Memorystore / Managed Redis node-type mapping, Cloud SQL for SQL Server licences, query-priced
  analytics and search).
- GCP prices vCPU and RAM separately (`vcpu_hour` + `memory_gb_hour`); Cloud SQL Zonal / Regional
  rates map to single-AZ / multi-AZ. Bigtable is node-priced: nodes = max(1, peak ops ÷ 10,000,
  data ÷ 5 TB) per cluster.
- Reserved prices become effective hourly rates (AWS: hourly + upfront ÷ term hours, preferring
  No Upfront; Azure: reservation total ÷ term hours).
- Pricing region: residency geography, else the first named user region, else `default_geo` (india).
- Not included (shown as notes): provisioned IOPS above baselines, Aurora / DocumentDB I/O requests,
  backup beyond free allowances, data egress, licences on BYOL / self-managed, discounts and taxes.
- When a tier's instance size is not sold (e.g. Aurora has no db.t4g.xlarge) the recommended size
  is priced and noted. A recommendation with an unpriced component shows a partial total (*).

## 6. Rank and explain
Rank by total score. Ties broken by Balanced cost. The explainer prompt receives:
user priorities, top 3 with dimension scores, rules fired, filtered-out list, assumptions.
System prompt: "Explain only using the data provided. Do not add services, prices or limits."

## Implementation notes (M3)
- Order is Filter → Size → Score → Combine → Rank: sizing runs before scoring so the cost dimension
  has something to compare (OPEN_QUESTIONS #3). Until M4 that is relative cost units
  (vCPU × license × deployment × service factor × nodes, see scoring.yaml), not dollars.
  The budget-cap filter waits for real prices.
- Dimension formulas live in `engine/scorer.py`; every number they use lives in `scoring.yaml`.
- Combination score = primary total − component_penalty × components − missing_component_penalty ×
  uncovered needs (+ simplicity_bonus when the primary covers every need), clipped to 0–100.
- HA topology: the lowest of single-AZ / multi-AZ / multi-region whose published SLA meets the target;
  zero RPO forces multi-AZ, active-active forces multi-region. Edition requirements (e.g. Cloud SQL
  Enterprise Plus for 99.99%) come from hardware_profiles.yaml.

## Test cases (tests/engine/)
Create 10 golden cases with the DBA team, for example:
1. Tier 1 OLTP, 2k TPS, strong consistency, heavy PL/SQL, India residency → Oracle-compatible managed option ranks first.
2. Global user profile store, 50k reads/s, eventual OK, key-value → DynamoDB / Cosmos DB / Bigtable class.
3. Internal tool, 10 TPS, Tier 3, tight budget → small managed PostgreSQL / MySQL, single AZ.
4. OLTP + BI dashboards → relational primary + warehouse via CDC.
Assert top-1 family and that eliminated services carry the expected rule id.
Implemented as `backend/tests/engine/golden/*.yaml` (10 cases: 4 from this doc, 6 drafts marked
`status: draft` for DBA review). Add a case by adding a YAML file; see the README there.
