# 06 — Repo Analyzer

Goal: turn a GitHub repo into `InferredRequirements`, where every field has a value,
a confidence (0–1) and evidence (file path + line). The user confirms before scoring.

## Pipeline
1. **Fetch**: GitHub REST API or shallow clone (`--depth 1`), max 200 MB, skip binaries,
   node_modules, vendor, build dirs. Never run any code from the repo.
2. **Redact**: regex + entropy scan for secrets, connection strings, passwords; replace with
   `<REDACTED>` before anything is logged or sent to the LLM.
3. **Static scanners** (deterministic, fast, no LLM).
4. **LLM extractor** for fuzzy signals (only on small, selected snippets).
5. **Mapper** merges signals into requirement fields.

## Static signals
| File / pattern | Signal | Maps to |
|---|---|---|
| requirements.txt, pyproject.toml | psycopg2/asyncpg → PostgreSQL; oracledb/cx_Oracle → Oracle; pymysql → MySQL; pyodbc → SQL Server; pymongo/motor → MongoDB; redis → cache; elasticsearch/opensearch-py → search; neo4j → graph; pgvector/faiss/chromadb → vector | app.existing_db, data.shape, eco.vector |
| package.json | pg, mysql2, oracledb, mssql, mongoose, ioredis, prisma, typeorm, sequelize | same |
| pom.xml, build.gradle | ojdbc, postgresql, mysql-connector, mssql-jdbc, spring-data-jpa, spring-data-mongodb, hibernate | same, eco.languages |
| *.csproj | EntityFrameworkCore providers | same |
| go.mod | pgx, go-ora, mongo-driver | same |
| ORM models (SQLAlchemy, Django, JPA @Entity, Prisma schema) | entity count, relationship count, JSON columns | data.joins, data.shape, data.schema_volatility |
| Migrations (Alembic, Flyway, Liquibase, Django migrations) | migration frequency over git history | data.schema_volatility |
| *.sql, *.pks, *.pkb | PL/SQL packages, triggers, CONNECT BY, ROWNUM, MERGE, sequences, DB links (`@dblink`), hints, partitioning DDL | data.proc_code, data.special_features |
| SQL in code | count of JOINs, GROUP BY, LIKE '%x%', window functions, SELECT FOR UPDATE | wl.query_types, wl.pattern |
| docker-compose.yml, k8s manifests | DB images and versions, replica counts, cache/queue containers | app.existing_db, eco.cdc |
| Terraform / Bicep / CloudFormation | provider, regions, existing DB resources | geo.app_location, pref.csp, geo.user_regions |
| Kafka / Debezium / Celery / cron configs | streaming, batch | eco.cdc, wl.batch_windows |
| README, docs | stated scale, SLAs | LLM extractor |

## Oracle compatibility sub-report (high value for this org)
For Oracle sources, count and classify features into effort buckets, similar in spirit to
AWS Schema Conversion Tool complexity reports:
| Feature | Effort to PostgreSQL |
|---|---|
| Plain tables, indexes, views | Low |
| Sequences, simple triggers, MERGE | Low–Medium |
| PL/SQL packages with state, autonomous transactions | High |
| CONNECT BY, ROWNUM, (+) joins | Medium (rewrite) |
| DB links | Medium–High (replace with FDW / app integration) |
| DBMS_* packages (DBMS_JOB, DBMS_SCHEDULER, UTL_FILE) | High |
Output: `estimated_refactor_person_days` with a range, used by the migration planner to
compare "Replatform to Oracle on cloud" vs "Refactor to PostgreSQL".

## LLM extractor
Input: redacted README excerpts, top N SQL snippets, ORM model summaries (not whole files).
Output: strict JSON matching a schema of optional fields with confidence and evidence.
Validate with Pydantic; drop anything that fails validation.

## Output example
```json
{
  "app.existing_db": {"value": "oracle 19c", "confidence": 0.95, "evidence": ["pom.xml:42 ojdbc11"]},
  "data.proc_code": {"value": "heavy", "confidence": 0.8, "evidence": ["db/pkg_billing.pkb (1,240 lines)"]},
  "data.special_features": {"value": ["db_links", "sequences"], "confidence": 0.9, "evidence": ["db/views.sql:88 @REMOTE_DB"]},
  "wl.read_write_ratio": {"value": null, "confidence": 0.0, "evidence": []}
}
```
Fields with confidence < 0.5 are shown empty with a hint, not pre-filled.

## Demo repos
Keep 3 small repos in `sample_repos/`: a Spring Boot + Oracle app with PL/SQL,
a FastAPI + Postgres + Redis app, a Node + MongoDB app.

## Implementation notes (M5)
- Fetch: GitHub tarball API (no `git clone`, so no hooks or submodules); archive capped at 200 MB,
  files over 1 MB and skipped folders ignored; only regular files are read (no symlinks, absolute
  paths or `..`); nothing is written to disk. `/tree/<branch>/<folder>` URLs analyse one folder.
  Tokens travel in a header, are used once, and are never logged or stored.
- All patterns live in `knowledge_base/analyzer.yaml` (checked by `python -m app.knowledge.check`).
- Signals carry a source: `static` (code and config), `readme` (plainly stated facts in README /
  docs, e.g. "99.95%", "2,000 TPS", "1.5 TB") or `llm`. Merge order on ties: static, readme, llm.
- Oracle report person-days come from `oracle_features.person_days_per_item` plus
  `plsql_person_days_per_100_lines`; heuristics for the DBA team to tune.
- The LLM step runs only when all four `AZURE_OPENAI_*` settings are present. It may fill only
  `llm_fields` that static scanning left empty, must cite a file that exists, values are validated
  against the catalog, and confidence is capped at 0.7.
- Demo repos: `sample_repos/spring-oracle-billing`, `fastapi-postgres-redis`, `node-mongo-catalog`
  pre-fill 80%, 80% and 73% of Quick fields without an LLM (doc 01 target: 60%).
