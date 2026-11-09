# 07 — Migration Planner

Input: `MigrationInput` (doc 02 section N) plus an optional target from an assessment.
Output: `MigrationPlan` = strategy, method, tools, phases, runbook, transfer estimate,
risks, rollback plan, validation plan.

## Step 1 — Strategy (7 Rs)
| Strategy | Choose when |
|---|---|
| Retire | No active users / replaced by another system |
| Retain | Hard dependencies, licensing or latency keep it on-prem for now |
| Rehost (lift and shift to VMs) | Need speed, unsupported features, minimal change; same engine on IaaS |
| Relocate | Moving a VMware estate as-is (Azure VMware Solution, Google Cloud VMware Engine, VMware Cloud on AWS) |
| Replatform | Same engine, move to managed service (Oracle → RDS Oracle / Oracle Database@CSP; SQL Server → Azure SQL MI) |
| Repurchase | Move to a SaaS product |
| Refactor | Change engine (Oracle → PostgreSQL) to cut licensing or modernise; justified when refactor effort is acceptable and app lifespan is long |

Decision inputs: app.lifecycle, data.proc_code, Oracle compatibility sub-report effort,
licensing (BYOL), downtime tolerance, team skills, target from assessment.
Show at least two strategies side by side with effort, cost and risk.

## Step 2 — Method
| Method | Use when | Examples |
|---|---|---|
| Offline logical (export/import) | Small DB, downtime of hours OK | Oracle Data Pump, pg_dump/pg_restore, mysqldump, BACPAC |
| Offline physical | Same engine, large DB, downtime OK | RMAN backup/restore, native SQL Server backup to URL/S3 |
| Online physical replication | Same engine, near-zero downtime | Oracle Data Guard, SQL Server log shipping / distributed AG, PostgreSQL streaming replication |
| Online logical / CDC | Heterogeneous or cross-version, near-zero downtime | AWS DMS, Google Database Migration Service, Azure Database Migration Service, Oracle GoldenGate, Debezium |
| Offline device | Network too slow for the size | AWS Snowball, Azure Data Box, Google Transfer Appliance |

Transfer time estimate:
```
transfer_hours = (size_gb * 8 * 1024) / (bandwidth_mbps * 0.7 * 3600)   # 70% effective link use
if transfer_hours > 7 * 24: suggest offline device + CDC catch-up
CDC feasibility: change_rate_gb_day must be well below daily effective bandwidth
```

## Step 3 — Tool matrix (seed for migration_tools.yaml; verify each before demo)
| Source → Target | Assessment | Schema conversion | Data movement | Validation |
|---|---|---|---|---|
| On-prem Oracle → Oracle on AWS (RDS Oracle / Oracle Database@AWS / EC2) | AWS Migration Hub / DMS Fleet Advisor style discovery, AWR | Not needed | Data Pump, RMAN, Data Guard, GoldenGate, Oracle ZDM, AWS DMS | Row counts, DMS validation, checksums |
| On-prem Oracle → Aurora/RDS PostgreSQL | AWS SCT / DMS Schema Conversion | AWS SCT, Ora2Pg | AWS DMS (full load + CDC) | DMS validation |
| On-prem Oracle → Oracle on Azure (Oracle Database@Azure / VMs) | Azure Migrate, AWR | Not needed | Oracle ZDM, Data Guard, RMAN, GoldenGate | Checksums |
| On-prem Oracle → Azure Database for PostgreSQL | Ora2Pg assessment | Ora2Pg | Ora2Pg / GoldenGate / Debezium | Row counts, checksums |
| On-prem Oracle → Oracle on GCP (Oracle Database@Google Cloud / Bare Metal Solution) | Google Migration Center, AWR | Not needed | Oracle ZDM, Data Guard, RMAN | Checksums |
| On-prem Oracle → AlloyDB / Cloud SQL PostgreSQL | Google Database Migration Assessment | Google Database Migration Service conversion workspace, Ora2Pg | Google Database Migration Service | Google Data Validation Tool (DVT) |
| SQL Server → Azure SQL DB / MI | Azure Migrate, Data Migration Assistant style assessment | Minor | Azure DMS, log replay, distributed AG | Row counts |
| MySQL / PostgreSQL → any CSP managed | Native | Not needed | AWS DMS / Google DMS / Azure DMS, native replication | Row counts, checksums |
| MongoDB → DocumentDB / Cosmos DB for MongoDB / Firestore | Compatibility checkers | Minor | AWS DMS, Azure DMS, mongodump/restore | Doc counts |
| CSP A → CSP B (any) | Target CSP's discovery tool | Per engine pairs above | Target CSP's DMS or engine-native replication over VPN / interconnect | As above |
Supporting: network (VPN, AWS Direct Connect, Azure ExpressRoute, Google Cloud Interconnect),
secrets (Secrets Manager / Key Vault / Secret Manager), IaC (Terraform), monitoring.

## Step 4 — Phases and runbook
1. **Discover & assess**: inventory, dependencies (DB links, ETL, schedulers, consumers), AWR baselines.
2. **Plan**: strategy, target sizing, network, security, wave assignment, rollback criteria.
3. **Build target**: landing zone, IaC, parameter groups, users/roles, encryption.
4. **Schema migrate & convert**: run conversion, fix manual items, unit test procedures.
5. **Data migrate**: full load, start CDC, monitor lag.
6. **Validate**: row counts, checksums, sample queries, performance test against AWR baseline.
7. **Cutover**: freeze, drain CDC lag to zero, switch connection strings / DNS, smoke tests.
8. **Hypercare & optimise**: monitoring, right-size after 2–4 weeks, decommission source.
Runbook generator outputs each phase with tasks, owner role, tool, estimated duration, and
go/no-go checks.

## Step 5 — Risks and rollback
Auto-generated risk list from inputs, e.g.:
- Charset conversion (non-AL32UTF8 source) → data corruption risk → test with full copy.
- DB links → broken cross-DB queries after move → map every link, plan wave together.
- High change rate vs bandwidth → CDC lag → bigger link or offline seed.
- Heavy PL/SQL in refactor path → schedule slip → pilot one package first.
Rollback: keep reverse replication (GoldenGate / DMS reverse task / Data Guard switchback)
until hypercare ends; define rollback trigger metrics.

## As implemented (M6)
- `POST /api/migrations/plan` re-runs the engine on the assessment's answers (plus overrides), then
  prices the best-ranked target for each of Rehost (same engine, IaaS), Replatform (same engine,
  managed) and Refactor (different engine): Balanced monthly cost including licences × 36 months +
  effort mid-point × day rate. Effort = strategy base + code refactor (repo analyzer's Oracle report
  when given, else by `data.proc_code`).
- Duration = the runbook's total for that strategy (phase base days + dependencies + code refactor
  ÷ team + transfer days + CDC soak + validation per TB), so the table and the runbook agree.
- Recommended = cheapest 3-year total among options that finish by the deadline (2028-12-31,
  migration_tools.yaml); none on time → the fastest. When Refactor is cheapest but late, the plan
  suggests a two-step move (replatform first, refactor after the exit).
- Retire / Retain / Relocate / Repurchase are listed with whether they apply; Retain conflicts with
  the on-prem exit for on-prem sources.
- Method follows step 2; tools come from the first matching tool-matrix row (`csp:dms` resolves to the
  target CSP's DMS); risks are YAML rules over requirements plus `plan.*` facts; rollback follows the
  method.
- A plan that keeps a licensed engine links to the justification gate (doc 01 non-goal untouched:
  DBCompass never runs a migration).

## Stretch: wave planning for a fleet
Ingest a CSV of databases + DB link inventory → build dependency graph →
connected components become candidate waves → order waves by risk and criticality.
