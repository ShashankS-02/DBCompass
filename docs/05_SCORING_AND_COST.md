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
~~portability~~ removed in M10: teams stay on one cloud and options are limited to the org support list.

Weights come from three priority sliders (Performance, Cost, Reliability), which share 0.70 in
proportion to their positions; ops, ecosystem and compliance are fixed at 0.10 each (M10). Defaults:
performance 0.2333, cost 0.2333, reliability 0.2333, ops 0.10, ecosystem 0.10, compliance 0.10.
Saved inputs that still carry the retired Simplicity or Portability sliders are accepted and ignored.
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

### What the estimate covers (M9)
Every tier carries `components`: one entry per bill component with a status.

| Component | How it is priced | Status when not priced |
|---|---|---|
| Compute, storage, requests | Service price list (M4) | estimate incomplete |
| Licence | `licensing.yaml` (M6) | included when inside the service price |
| I/O and IOPS | Aurora I/O requests (avg TPS × `io_per_transaction`); RDS gp3 IOPS above 3,000 | included for services whose I/O is in the compute/storage price; not priced for VMs |
| Backup storage | (data × (1 + retention days × `backup_daily_change_fraction`)) − free allowance (100 % of provisioned storage) | not priced |
| HA standby, DR copy | Inside the compute and storage lines (sizing) | not needed when the layout has none |
| Egress | `cost.egress_gb_month` × first paid internet tier | not needed at 0 GB |
| Private endpoints | `private_endpoints_per_environment` × environments × hours, when `sec.network` is private | not needed for public access |
| Connection proxy | RDS Proxy per vCPU-hour when `cost.connection_proxy`; built-in pooler (Azure PostgreSQL) is included | not priced where no managed proxy exists |
| Customer-managed key | One key per environment when `sec.cmk` | included (platform keys) |
| Audit logging | avg TPS × `audit_kb_per_transaction` ingested into CloudWatch / Log Analytics | not needed without `sec.audit`; marked *estimated* |
| Environments | `environment_multipliers` | production only |

The extra components (backup to audit logging) are added to the total when priced but never make an
estimate incomplete. CSP-wide prices live in `pricing.yaml` `shared_components` and in the snapshot
under the pseudo service `<csp>.shared`. GCP shared components wait for catalog credentials
(OPEN_QUESTIONS #62).

### Price difference against staying on the current engine (M9)
On-prem costs are rarely known, so the comparison is cloud to cloud. For an existing database,
`engine/baseline.py` prices every managed service on each recommended cloud that runs the source
engine, at the Balanced tier with the same answers, and keeps the cheapest on compute + licence
lines. When no managed one has a list price (Oracle Database@Azure) a self-managed VM with
licences is used and the note says so. Each recommendation's `versus_baseline.delta_usd` is its own
Balanced compute + licence total minus the baseline's. Storage, backup and network are left out of the
difference because they would be about the same for both.

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
- Licences (M6, licensing.yaml): services whose CSP price excludes the database licence (RDS for
  Oracle BYOL, EC2 / Azure VM / Compute Engine self-managed, Bare Metal Solution) get licence lines
  in every tier: Oracle Processor licences = ceil(instance vCPUs ÷ 2) × licensed nodes (primary,
  standby, replicas, DR), purchase ÷ 36 months plus 22 % support a year; SQL Server core-pack
  subscriptions (4-core minimum per instance). They count in the cost score, the budget filter
  and every total, and the UI shows "incl. $X licence" per tier.
- Cost score for an unpriced candidate: it is scored as if it cost the highest known price in its
  group, so a missing price can never win on cost (an infrastructure-only or absent price usually
  understates the real bill). When nothing in the group is priced, cost falls back to relative units.

## 6. Rank and explain
Rank by total score. Ties broken by Balanced cost. The explainer prompt receives:
user priorities, top 3 with dimension scores, rules fired, filtered-out list, assumptions.
System prompt: "Explain only using the data provided. Do not add services, prices or limits."

As implemented (M7):
- The fact sheet (`app/explain/facts.py`) holds priorities, the top 3 options (components, HA layout,
  dimension scores, tier prices with licence share, why lines), rules fired with their messages, up to 15
  other candidates that passed the filters (score and rule adjustments), the first reason for every
  filtered service (up to 60) and up to 12 assumed answers. Prompts and limits live in
  `knowledge_base/explainer.yaml`.
- Fact check (`app/explain/grounding.py`): every number in the prose must be within 2 % (or 0.6) of a
  number in the fact sheet, or be 1, 2, 3 or 100; every service or engine name it uses must appear in
  the fact sheet. A failing draft is retried once with the problems listed, then replaced by the
  rule-based explanation. Unpriced options are written as "not priced", never "$0".
- What-if (`app/engine/whatif.py`) re-runs the same deterministic pipeline on the merged input and
  diffs the two traces; no LLM is involved. The Results page no longer shows it (M10); the API stays.

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


## Multi-engine services and the data shape

A self-managed VM can run several engines. `scoring.yaml` `engine_shapes` lists the data shapes each
engine can be the primary for. Such a service passes the shape filter only through an engine that
fits, its engine list is narrowed to the fitting engines before rules and scores run (so the vendor
bonus follows the engine that will actually run), and the engine is chosen among them. The
like-for-like baseline and the justification price pin the named engine instead.

When the vendor-certified or requested engine does not suit the chosen shape, the result carries a
notice telling the team to fix the data shape. "We already own enough licences"
(`pref.licence_status = owned`) adds the matching `eco.licenses` option for that engine, so the
licence purchase is dropped and support continues.
