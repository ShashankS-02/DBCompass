# 02 — Requirements Catalog

Every input the engine can use. Each field has an `id` used by rules in
`knowledge_base/rules.yaml`. Fields marked **Q** appear in Quick mode.
Unknown values are filled from tier defaults (bottom of this doc) and flagged as assumed.

### Machine-readable catalog
`knowledge_base/questions.yaml` is the machine-readable form of this document: it holds option
values (stable snake_case ids such as `lt_1ms`, `tier_1`, `pci_dss`), labels, number ranges,
Quick flags, tier defaults and the priority sliders. `GET /api/questions` serves it, and
`backend/tests/test_questions_catalog.py` fails if the two drift apart. Deliberate differences:
- `vol.retention` is split into `vol.retention_period` (<1 y, 1–3 y, 3–7 y, >7 y) and `vol.archive_allowed` (yes/no).
- `eco.cdc` stays yes/no; the target moves to its own field `eco.cdc_target`.
- `cost.priority` is not a form field; it is the Cost priority slider (see OPEN_QUESTIONS #2).

## A. Application context
| id | Question | Type / options | Why it matters |
|---|---|---|---|
| app.tier **Q** | Business criticality | Tier 0 (mission critical) / 1 / 2 / 3 (internal, low impact) | Drives default SLA, RPO, RTO, HA layout |
| app.type **Q** | Application type | Web/API, Batch, Analytics/BI, Event/IoT, ML/AI, Internal tool | Seeds workload defaults |
| app.env | Environments needed | Prod, DR, UAT, Dev (multi) | Multiplies cost |
| app.lifecycle | Expected lifespan | <1 yr, 1–3 yr, 3+ yr | Commitment discounts, refactor worth |
| app.existing_db | Current database (if any) | engine + version | Compatibility, migration path |
| app.requested_engine **Q** | Database you have in mind (if any) | engine + version | Compared with DBCompass's ranking; licensed engines (Oracle, SQL Server, Db2) need a justification before approval (M6) |

## B. Data model
| id | Question | Type / options | Why it matters |
|---|---|---|---|
| data.shape **Q** | Primary data shape | Relational, Document/JSON, Key-value, Wide-column, Graph, Time-series, Vector embeddings, Full-text search (multi) | First-pass filter on DB families |
| data.joins | Join complexity | None, Simple (1–2 tables), Complex (3+ tables, reporting) | Relational vs NoSQL |
| data.schema_volatility | How often schema changes | Rarely, Monthly, Constantly | Schemaless options |
| data.proc_code | Stored procedures / PL/SQL / T-SQL dependency | None, Light, Heavy | Engine lock-in, refactor cost |
| data.special_features | Uses engine-specific features | DB links, sequences, hierarchical queries, materialized views, partitioning, RAC, spatial (multi) | Compatibility scoring |

## C. Workload
| id | Question | Type / options | Why it matters |
|---|---|---|---|
| wl.pattern **Q** | Workload pattern | OLTP, OLAP, HTAP (both), Mixed with batch | Row vs column store, separation |
| wl.read_write_ratio **Q** | Read : write ratio | 90:10, 70:30, 50:50, Write heavy | Replicas, caching, write scaling |
| wl.peak_tps **Q** | Peak transactions or queries per second | number | Instance sizing, horizontal scale need |
| wl.avg_tps | Average TPS | number | Serverless vs provisioned economics |
| wl.burstiness | Traffic shape | Steady, Daily peaks, Spiky/unpredictable | Autoscaling, serverless |
| wl.latency_p99_ms **Q** | Target p99 read latency | <1 ms, <10 ms, <100 ms, Seconds OK | In-memory cache, storage tier |
| wl.query_types | Query types | Point lookup, Range scan, Aggregation, Full-text, Geospatial, Vector similarity (multi) | Secondary engines in combo |
| wl.connections | Max concurrent connections | number | Pooling, proxy (RDS Proxy, PgBouncer) |
| wl.batch_windows | Batch/ETL windows | none / nightly / continuous | IO headroom, read replica for batch |

## D. Data volume
| id | Question | Type / options | Why it matters |
|---|---|---|---|
| vol.current_gb **Q** | Current data size (GB) | number | Storage cost, migration time |
| vol.growth_gb_month | Growth per month (GB) | number | 3-year projection, max storage limits |
| vol.retention | Retention requirement | months/years, archive tier allowed? | Tiering, partitioning, lifecycle |
| vol.item_size | Typical row/document size | <1 KB, 1–100 KB, >100 KB, LOBs | NoSQL item limits, LOB handling |

## E. Consistency and transactions
| id | Question | Type / options | Why it matters |
|---|---|---|---|
| tx.consistency **Q** | Consistency needed | Strong, Read-your-writes, Eventual OK | Filters eventually consistent stores |
| tx.acid_scope | ACID scope | Single row, Multi-row single table, Multi-table, Cross-region | Distributed SQL vs regular RDBMS |

## F. Availability and DR
| id | Question | Type / options | Why it matters |
|---|---|---|---|
| ha.sla **Q** | Availability target | 99.5, 99.9, 99.95, 99.99, 99.999 | Multi-AZ, multi-region, service eligibility |
| ha.rpo | Max data loss (RPO) | 0, <1 min, <15 min, <24 h | Sync vs async replication |
| ha.rto | Max downtime to recover (RTO) | <1 min, <15 min, <4 h, <24 h | Automatic failover, standby type |
| ha.multi_region | Multi-region needs | None, DR only (active-passive), Active-active | Global DBs |
| ha.maintenance_tolerance | Planned downtime tolerance | None, Short monthly window, Flexible | Zero-downtime patching options |
| ha.backup_retention_days | Backup retention | number | PITR window, cost |

## G. Geography and users
| id | Question | Type / options | Why it matters |
|---|---|---|---|
| geo.user_regions **Q** | Where are users | India, US, EU, APAC, Global (multi) | Region choice, latency, replicas |
| geo.residency | Data residency constraints | None, India (DPDP), EU (GDPR), US only, custom | Region filter |
| geo.app_location | Where app compute runs | On-prem DC, AWS, GCP, Azure, Undecided | Co-location, egress, hybrid connectivity |

## H. Security and compliance
| id | Question | Type / options | Why it matters |
|---|---|---|---|
| sec.compliance **Q** | Compliance regimes | SOX, PCI-DSS, HIPAA, GDPR, DPDP, None (multi) | Audit logging, encryption, service eligibility |
| sec.cmk | Customer managed encryption keys | Yes/No | KMS / Key Vault / Cloud KMS integration |
| sec.network | Network exposure | Private only, Private + VPN, Public with allowlist | Private endpoints / PrivateLink / PSC |
| sec.identity | Auth integration | DB users, Entra ID, IAM, LDAP | Native IAM auth support |
| sec.audit | DB-level auditing needed | Yes/No | Audit feature availability and cost |
| sec.masking_rls | Data masking / row-level security | Yes/No | Feature availability |

## I. Integration and ecosystem
| id | Question | Type / options | Why it matters |
|---|---|---|---|
| eco.languages | Languages / frameworks | Python, Java, .NET, Node, Go (multi) | Driver & ORM support |
| eco.cdc | Needs change data capture / streaming | Yes/No, target (Kafka, analytics) | Combo designs, logical replication |
| eco.analytics | Downstream analytics/BI | None, BI dashboards, Data lake/warehouse | Add warehouse to combo |
| eco.vector | Needs vector search for AI | Yes/No | pgvector, vector-capable services |
| eco.licenses | Existing licenses | Oracle BYOL, SQL Server (Hybrid Benefit), None | Cost model, Oracle@CSP path |

## J. Operations and team
| id | Question | Type / options | Why it matters |
|---|---|---|---|
| ops.skills **Q** | Team's strongest DB skills | Oracle, SQL Server, PostgreSQL, MySQL, MongoDB, None (multi) | Ops burden and learning curve score |
| ops.managed_pref | Management preference | Fully managed / serverless, Managed, Self-managed on VMs OK | IaaS vs PaaS |
| ops.dba_support | DBA support available | 24x7, Business hours, None | Penalise complex self-managed options |
| ops.iac | IaC tool | Terraform, Bicep, CloudFormation, Deployment Manager, None | Export templates |

## K. Budget and commercial
| id | Question | Type / options | Why it matters |
|---|---|---|---|
| cost.monthly_cap **Q** | Monthly budget cap (USD or INR) | number / unknown | Hard filter on tiers |
| cost.commitment | Willing to commit | On-demand only, 1-year, 3-year | Reserved / Savings Plans / CUDs pricing |
| cost.egress_sensitivity | Heavy data egress expected | Yes/No | Cross-cloud and hybrid penalties |
| cost.priority | Cost vs performance priority | Slider 0–100 | Score weights |

## L. Hardware (used for IaaS / self-managed and sizing hints)
| id | Question | Type / options | Why it matters |
|---|---|---|---|
| hw.vcpu | Known vCPU need | number / derive | Instance family |
| hw.memory_gb | Known memory need | number / derive | Memory optimised families |
| hw.iops | Required IOPS | number / derive | Storage tier (gp3/io2, Premium SSD v2/Ultra, Hyperdisk/PD-SSD) |
| hw.throughput_mbps | Required throughput | number / derive | Storage tier |

## M. Preferences and constraints
| id | Question | Type / options | Why it matters |
|---|---|---|---|
| pref.csp **Q** | Preferred CSP | AWS, GCP, Azure, No preference | Soft boost, or hard filter if "mandated" |
| pref.csp_mandated | Is the CSP mandated by org | Yes/No | Hard filter |
| pref.lock_in | Vendor lock-in tolerance | Low, Medium, High | Penalise proprietary services when low |
| pref.open_source | Prefer open-source engines | Yes/No | Score boost |
| pref.excluded | Services to exclude | list | Hard filter |

## N. Migration (only when migrating)
| id | Question | Type / options | Why it matters |
|---|---|---|---|
| mig.source_platform | Source | On-prem, AWS, GCP, Azure | Tool matrix |
| mig.source_engine | Source engine + version | e.g. Oracle 19c | Homogeneous vs heterogeneous |
| mig.size_gb | Database size | number | Transfer time, method |
| mig.change_rate_gb_day | Redo / WAL / change volume per day | number | CDC sizing |
| mig.downtime_minutes | Allowed cutover downtime | number | Offline vs online method |
| mig.bandwidth_mbps | Available network bandwidth to target | number | Transfer time, offline appliance decision |
| mig.dependencies | DB links, external apps, ETL jobs, schedulers | list | Wave grouping, cutover order |
| mig.charset | Character set | e.g. AL32UTF8, WE8ISO8859P1 | Conversion risk |
| mig.target_choice | Target known? | Use recommendation / specify | Planner input |

## Tier defaults (applied when a field is unknown)
| Field | Tier 0 | Tier 1 | Tier 2 | Tier 3 |
|---|---|---|---|---|
| ha.sla | 99.99 | 99.95 | 99.9 | 99.5 |
| ha.rpo | 0 | <1 min | <15 min | <24 h |
| ha.rto | <1 min | <15 min | <4 h | <24 h |
| ha.multi_region | DR active-passive | DR active-passive | None | None |
| ha.backup_retention_days | 35 | 30 | 14 | 7 |
| sec.audit | Yes | Yes | No | No |

## Derivation rules for hardware when not given
- `hw.iops ≈ peak_tps × (reads_per_txn × cache_miss_ratio + writes_per_txn × write_amplification)`
  with defaults reads_per_txn=4, writes_per_txn=2, cache_miss_ratio=0.2, write_amplification=3.
- `hw.memory_gb ≈ working_set_gb × 1.3`, where `working_set_gb` defaults to 20% of current size.
- `hw.vcpu ≈ ceil(peak_tps / tps_per_vcpu)` with `tps_per_vcpu` from the engine's KB entry.
All constants live in `knowledge_base/sizing.yaml` so DBAs can tune them.
