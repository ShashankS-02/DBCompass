# 04 — Knowledge Base

The KB is a folder of YAML files, one per service. It is the only place service capabilities
live. DBAs review it. Every entry needs `last_verified` and `source_url`.
**Before the demo, verify limits, SLAs and engine versions against current CSP docs; the
lists below are a starting point, not ground truth.**

## Entry schema
```yaml
id: aws.aurora_postgresql
csp: aws
name: Amazon Aurora PostgreSQL-Compatible
family: relational            # relational | document | key_value | wide_column | graph |
                              # time_series | in_memory | search | analytics | vector | distributed_sql
engines: [postgresql]
deployment: managed           # serverless | managed | iaas
consistency: [strong]
max_storage_gb: 131072
horizontal_write_scaling: false
read_replicas_max: 15
multi_az: true
multi_region: active_passive  # none | active_passive | active_active
sla_percent: 99.99
rpo_capability_seconds: 0     # within region
latency_class: low_ms         # sub_ms | low_ms | tens_ms | seconds
supports:
  json: true
  full_text: basic
  vector: true                # pgvector
  geospatial: true            # PostGIS
  stored_procedures: plpgsql
  cdc: true
  iam_auth: true
  cmk_encryption: true
  private_endpoint: true
compliance: [sox, pci_dss, hipaa, gdpr]
proprietary_lock_in: medium   # low | medium | high
ops_complexity: low           # low | medium | high
tps_per_vcpu: 800             # sizing heuristic, tune with DBAs
pricing_ref:
  provider_api: aws_pricelist
  service_code: AmazonRDS
  filters: {databaseEngine: "Aurora PostgreSQL"}
instance_families: [db.r7g, db.r6g, db.t4g]
storage_options: [aurora_standard, aurora_io_optimized]
good_for: [oltp, htap_light, saas_backends]
avoid_when: [heavy_plsql_without_refactor, petabyte_analytics]
last_verified: 2026-11-07
source_url: https://aws.amazon.com/rds/aurora/
```

### Schema as implemented (M2)
`backend/app/models/knowledge.py` is the authoritative schema; the example above is the original
sketch. Differences:
- `sla_percent` → `sla_by_topology: {single_az, multi_az, multi_region}` (null = not offered or
  not published). Rules compare against `best_sla_percent`, the highest of the three.
- `supports.json` → `supports.json_documents` (name clash with Pydantic). New flags: `graph`,
  `audit`, `masking_rls`, `sql_agent` (SQL Server Agent available; default false).
- New: `secondary_families` (e.g. Aurora PostgreSQL also serves `vector` via pgvector),
  `regions` (ids from `regions.yaml`, only the India / EU / US / APAC geographies),
  `lifecycle` (`active | not_for_new_projects | retiring`) with `status_note`.
- `host_label` (optional, self-managed only): what the engine is installed on, e.g. `Amazon EC2 + EBS`.
  Results title the service "<engine> on <host_label> (self-managed)".
- `special_case` (M9, optional): `caching | vector_search | analytics`. Marks a service kept only for
  one job. It is filtered out as the main database (filter id `SPECIAL-CASE`) unless the answers meet
  `org_support.yaml` `special_cases.<kind>.primary_when`; it can always be an add-on component. The
  checker rejects any service without `special_case` whose engine is not a supported target.
- Verification: `review_status` (`draft` until a DBA signs the entry off), `last_verified`
  (date of the last check) and `verification: {verified_fields, sources, notes}` listing exactly
  which fields were checked against which official pages. Fields not listed are drafts.
- `engines` use the catalog's engine values plus `valkey, memcached, influxdb, opensearch,
  gremlin, proprietary`. `compliance` uses `sec.compliance` values.

### Status of the M2 entries (54 services, checked 2026-11-07)
SLAs were checked for every managed service except Oracle Database@AWS / @Google Cloud / @Azure,
Bare Metal Solution, Cosmos DB for MongoDB vCore and the self-managed VM entries. Storage and
replica limits were checked where the official limits pages state them. Notable findings:
- Amazon Timestream for LiveAnalytics carries an end-of-support notice → `not_for_new_projects`;
  Timestream for InfluxDB is the AWS time-series entry.
- Azure Cosmos DB for PostgreSQL is "on a retirement path" → `not_for_new_projects`; Azure Database
  for PostgreSQL elastic clusters is the replacement.
- Azure Cache for Redis retires (Basic/Standard/Premium 30 Sep 2028, Enterprise 31 Mar 2027);
  only Azure Managed Redis is in the KB.
- Vertex AI Search is being renamed Agent Search.
- Spanner Graph is a Spanner feature (Enterprise editions), so it is `supports.graph` on Spanner.
- AWS and Redshift / OpenSearch SLA pages state credit thresholds rather than a commitment
  sentence; the top threshold is recorded and noted per entry.
Open items are tracked in `docs/OPEN_QUESTIONS.md` (#14 onwards).

### Checking the KB
After editing any YAML, run from `backend/`:
```
python -m app.knowledge.check
```
It validates every file and cross-checks them: rule fields and option values exist in
`questions.yaml`, service fields used by rules exist, regions are known, sources are official
CSP / Oracle documentation URLs, file names match ids, and coverage minimums are met. The same
checks run in `pytest`.

## Service list to populate (AWS / GCP / Azure only)
| Family | AWS | GCP | Azure |
|---|---|---|---|
| Relational (open source) | RDS PostgreSQL, RDS MySQL, RDS MariaDB, Aurora PostgreSQL, Aurora MySQL | Cloud SQL PostgreSQL, Cloud SQL MySQL, AlloyDB for PostgreSQL | Azure Database for PostgreSQL Flexible Server, Azure Database for MySQL Flexible Server |
| Relational (commercial) | RDS Oracle, RDS SQL Server, RDS Db2, Oracle Database@AWS | Cloud SQL SQL Server, Oracle Database@Google Cloud, Bare Metal Solution (Oracle) | Azure SQL Database, Azure SQL Managed Instance, SQL Server on Azure VMs, Oracle Database@Azure |
| Distributed SQL | Aurora DSQL | Spanner | Cosmos DB for PostgreSQL |
| Document | DocumentDB | Firestore | Cosmos DB (NoSQL API, MongoDB vCore/RU) |
| Key-value / wide-column | DynamoDB, Keyspaces | Bigtable | Cosmos DB (Table, Cassandra API), Managed Instance for Apache Cassandra |
| In-memory | ElastiCache (Valkey/Redis OSS/Memcached), MemoryDB | Memorystore (Valkey/Redis/Memcached) | Azure Managed Redis / Azure Cache for Redis |
| Graph | Neptune | Spanner Graph | Cosmos DB for Gremlin |
| Time-series | Timestream | Bigtable (pattern) | Azure Data Explorer |
| Search | OpenSearch Service | Vertex AI Search / self-managed on GKE | Azure AI Search |
| Analytics / warehouse | Redshift | BigQuery | Synapse Analytics / Microsoft Fabric |
| Self-managed (IaaS) | EC2 + EBS | Compute Engine + Hyperdisk/PD | Azure VMs + Managed Disks |

## Other KB files
### rules.yaml
Declarative rules. Each rule: `id` (`R-AREA-NNN`), `when` (conditions on requirement fields,
ANDed; empty = always), `effects`, `message`. Implemented grammar:
```yaml
- id: R-COMP-001
  when:
    - {field: sec.compliance, op: not_contains, value: none}   # eq ne in not_in contains not_contains
  effects:                                                     # contains_any gte lte gt lt is_set excludes
    exclude_where:                                             # service predicates, ANDed
      - {field: compliance, op: missing_any_of, value_from: sec.compliance}
  message: "Service is not listed as eligible for every required compliance regime."
```
- Conditions on a field with no value (neither answered nor assumed) never match.
- Service predicates use dotted paths (`supports.vector`) and compare with a literal `value` or a
  requirement field via `value_from`. Ops add `missing_any_of`, `is_null`, `not_null`. A null
  service value never matches a comparison (so an unpublished SLA does not exclude a service).
- Effects: `exclude_where`, `boost` / `penalise` (`{where, by}`), `require_component`
  (`{role, family, satisfied_by_primary}`), `add_guidance`, `region_filter: {geo}`.
- Derived requirement fields: `vol.projected_3y_gb`, `ha.sla_percent`, `mig.source_engine_family`.
- `scope: primary` (default) rules judge the primary only; `scope: all_components` rules (lifecycle,
  residency, compliance, mandated CSP, exclusions, CMK, private network) also filter add-on components.
  Without this, e.g. the strong-consistency rule would remove every cache.
- `family_compatibility` maps each `data.shape` option to the families that can be the primary store.
The doc's original shorthand (`engines_contains: oracle`) is written in this explicit form.
### regions.yaml
Geography (india, eu, us, apac) → region ids per CSP. Used by `region_filter` and by service
`regions`.
### sizing.yaml
Constants for the derivation formulas in doc 02 (tps_per_vcpu defaults, cache miss ratio, etc.)
and `app_type_defaults`: workload values assumed per `app.type` when unanswered (OPEN_QUESTIONS #7).
### scoring.yaml
Tables behind the 7 score dimensions (latency fit, write share, RPO seconds, management fit, …),
the engine choice per data shape for multi-engine entries, relative cost factors used until M4
pricing, and combination settings (component penalty, simplicity bonus, max components).
### hardware_profiles.yaml
Instance families per CSP grouped as general / memory-optimised / compute / burstable, with
vCPU, memory and network; storage tiers with IOPS/throughput ceilings
(EBS gp3/io2 Block Express, Azure Premium SSD v2/Ultra Disk, GCP Hyperdisk Balanced/Extreme).
### design_patterns.yaml
Guidance snippets keyed by condition: read replicas, CQRS, cache-aside, partitioning by date,
connection pooling, outbox pattern for CDC, multi-region write conflict handling.
### pricing.yaml
How to find each service's prices in the CSP price lists: per component (compute, storage,
reads/writes, throughput, zone redundancy) a matcher on price-list fields (`equals`, `regex` with
named groups for dimensions like `vcpu`, `exclude`, `dims`, Azure-only `odata` narrowing), the
billing `basis`, and how HA standbys are billed (`multi_az_rate`). Also the three cost tiers,
commitment → allowed terms, environment multipliers and request-unit constants. Every service
is either in `services` or in `not_priced` with a reason (checked).
### price_snapshots/
Built by `python -m app.pricing.snapshot <csp>`; never edited by hand. Each price keeps its SKU,
unit, region, term and `fetched_at`.
### migration_tools.yaml
Planner settings (deadline 2028-12-31, link utilisation, thresholds, team size, day rate), strategy
effort ranges, the tool matrix (each tool links to its docs), methods with rollback, the 8 phases with
tasks and go / no-go checks, risk rules (rules.yaml condition grammar plus `plan.*` facts) and
validation checks. See doc 07.

### licensing.yaml (M6)
Vendor list prices for licences the CSP price does not include: Oracle EE / SE2 per Processor
(perpetual, spread over 36 months, plus annual support) and SQL Server Enterprise / Standard
subscriptions per 2-core pack; Oracle's cloud counting rule (2 vCPUs = 1 Processor licence on
AWS / Azure / GCP); which services need which product per engine (BYOL and self-managed only;
licence-included services are not listed); `org_discount_fraction` per vendor; and the
`commercial_engines` the justification gate covers. Owned licences (`eco.licenses`) drop the purchase
line; Oracle support continues. Entries marked `verified: false` await the vendor's own document.

### justification.yaml (M6)
Reasons a team can give for a licensed engine, each with a weight, an optional evidence prompt and
optional `verify` / `contradict` conditions over the requirements; thresholds for "justified" and
"needs review"; reasons that can never justify on their own; and the saving above which an architect
review is needed unless a strong reason (vendor certification, performance test) is backed.

### Catalog cut (M9)
Removed because the database team does not support their engines: DynamoDB, Neptune, Timestream
(both), Aurora DSQL, RDS for MariaDB, Cosmos DB for NoSQL / Table / Gremlin, Azure Data Explorer,
Synapse Analytics, Bigtable, Firestore and Spanner. MariaDB was dropped from the self-managed VM
entries. Every remaining entry lists `iso_27001` under `compliance` (all three clouds hold ISO/IEC
27001 certification for these services).

### org_support.yaml (M8)
The engines the database team supports: `engines.<id>: {status: strategic|supported|sunset, label, note?}`,
`pin_supported_at` (where the best supported option is shown when #1 is unsupported) and the
`messages` the UI prints. Presentation only — scores never change. See docs/09_GUIDED_INTAKE.md.

### engine_features.yaml (M8)
Per-engine checklist for the intake: `engines.<id>.features[] = {feature, label, how_to_check}` where
`feature` is a `data.special_features` option and `how_to_check` is a catalog query that returns
metadata only. `sticky_features` feeds rule R-FEAT-STICKY-001. The checker verifies every feature id.


## service_models.yaml (M10)

Plain-language description of each deployment model (`managed`, `serverless`, `iaas`): a title, a
summary, what the cloud provider handles and what the team handles. Shown on every recommendation as
"About this service", together with facts from the service entry (SLA for the chosen layout, storage
limit, read replicas, cross-region option, operating effort, own licences on VMs). `csp_sources`
links each cloud's shared responsibility model. The knowledge check fails if a service uses a
deployment model the file does not describe.


## setup_guide.yaml (M10)

Basic steps to stand up a recommended option for a NEW application, in phases: cloud foundation,
create the database, secure access, connect the application, schema, add-ons (cache, vector,
search, analytics, time series) and go-live. Each step is a template with `{placeholders}` and
optional filters: `deployments`, `engines`, `needs` (an add-on role, `replicas` or
`vector_in_primary`) and `when` (answer conditions in the rules.yaml grammar). Lookups fill the
placeholders: `csp_terms` (secrets store, KMS, monitoring, private access), `engine_terms` (pooler,
HA tooling, backup tool, schema migration tool, vector step), `service_terms` (per-service
overrides such as RDS Proxy) and `drivers` (engine x eco.languages). A step whose placeholder has
no value is dropped, never guessed. The knowledge check rejects unknown placeholders, services,
languages and condition fields.
