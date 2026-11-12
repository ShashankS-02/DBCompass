# DBCompass

Internal portal that recommends databases, cloud provider (AWS / GCP / Azure), sizing and design
for an application, and plans migrations. See `CLAUDE.md` and `docs/` for the full picture.

## Run everything
```
cp .env.example .env
docker compose up --build
```
- Frontend: http://localhost:5173
- API: http://localhost:8000/api/health (OpenAPI docs at http://localhost:8000/docs)

## Backend only
```
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
DEV_AUTH_BYPASS=true uvicorn app.main:app --reload --port 8000
pytest -q
```
Without `DATABASE_URL` the backend uses a local SQLite file (`backend/dbcompass.db`).

## Frontend only
```
cd frontend
cp .env.example .env.local
npm install && npm run dev
```

## Knowledge base
Service entries, rules and sizing constants live in `knowledge_base/` (see docs/04). After editing
any YAML, run `python -m app.knowledge.check` from `backend/` (with the venv active).
Golden recommendation cases live in `backend/tests/engine/golden/` — add one YAML file per case.

## Prices
Monthly costs come from price snapshots in `knowledge_base/price_snapshots/`, built from the
official price lists (no prices are hand-entered). Rebuild from the repo root:
```
cd backend && .venv/bin/python -m app.pricing.snapshot azure   # Retail Prices API; a few minutes (rate-limited)
cd backend && .venv/bin/python -m app.pricing.snapshot aws     # public bulk CSVs; ~10 minutes (EC2 files are large)
cd backend && .venv/bin/python -m app.pricing.snapshot gcp     # Cloud Billing Catalog API; needs GCP credentials
```
GCP needs `GCP_SERVICE_ACCOUNT_FILE` (path to a service-account JSON key, kept outside the repo)
or `GCP_BILLING_API_KEY` in `.env`. A `dba_admin` can refresh Azure live with
`POST /api/pricing/refresh/azure`.

## Migration planning and database requests (M6)
- **Licences**: Oracle (BYOL / self-managed) and SQL Server on VMs carry licence lines in every cost
  tier, from `knowledge_base/licensing.yaml`. Set the org discount there once the licence team confirms it.
- **Migration plan** (Results → Plan migration): Rehost, Replatform and Refactor compared over three
  years including licences, checked against the 2028-12-31 on-prem exit, with method, tools,
  runbook, risks and rollback. Settings in `knowledge_base/migration_tools.yaml`.
- **Database requests** (Requests page): a team asking for, or keeping, Oracle / SQL Server / Db2
  gives reasons; DBCompass checks them against the assessment, compares the cost with the best
  licence-free option and gives an advisory verdict. A user with the `db_approver` Entra app role
  approves, sends back or rejects; every step is in the audit trail and the packet exports as Markdown.

## Supported engines, application questions and price difference (M9)

- **Supported engines only.** The service catalog holds managed services for Oracle, PostgreSQL,
  SQL Server, MongoDB, Cassandra, Db2 and MySQL on the three clouds, plus self-managed VMs. Ten
  special-purpose services stay for one job each: caching (ElastiCache, MemoryDB, Azure Managed Redis,
  Memorystore), vector and full-text search (OpenSearch, Azure AI Search, Vertex AI Search) and
  analytics (Redshift, BigQuery, Fabric Warehouse). They are only the main database for an analytics
  or search application; otherwise they appear as add-ons. The support badges are gone.
- **Repo analyzer removed.** DBCompass never reads application code (docs/06).
- **Drafts kept.** The intake, the migration plan form and the request form keep what you entered in
  the browser until you submit, across tab switches, reloads and sign-in.
- **Application step.** Languages, personal data (customers / employees), compliance including
  ISO 27001, environments, network access, connection proxy and monthly egress. A vendor
  application must name the vendor.
- **What the estimate covers.** Every cost tier lists compute, licence, storage, I/O, backup, HA
  standby, DR copy, egress, private endpoints, connection proxy, customer-managed keys, audit logging
  and environments, each marked priced, estimated, included, not priced or not needed.
- **Price difference.** For an existing database, each option shows its monthly difference from
  staying on the current engine on the same cloud (compute and licences only; storage, backup and
  network would be the same). Partial snapshot rebuild:
  `python -m app.pricing.snapshot aws --sources AmazonRDS AWSDataTransfer`.

## Guided intake and the org's supported list (M8)

`/assessments/new` is a step-by-step intake (about five minutes, buttons wherever possible, an
"I don't know" on every step, drafts kept in the browser). It branches on *existing* vs *new*
application: an existing database gets an engine-specific feature checklist
(`knowledge_base/engine_features.yaml`, each item with a catalog query that returns metadata only),
an ownership check (internal or vendor; will the vendor help?) and a three-question team readiness
check; a new application asks who builds it and which database the vendor certifies. The old form
is gone (M9).

`knowledge_base/org_support.yaml` lists the engines the database team supports (strategic,
supported, sunset). Every recommendation carries a support badge; when the top option is not on the
list, the best-ranked supported option is pinned at #2 as the "supported alternative". The result
also shows a team-readiness verdict, and the migration plan adds an "engage a migration partner"
phase and the matching risks when the team cannot do it alone. Sybase ASE, Informix, Vertica and
Couchbase are accepted as migration sources.

## Explain, what-if and export (M7)
- **Explain this result** (Results page): plain-English explanation. With Azure OpenAI configured
  the model writes it from a fact sheet of the result, and DBCompass checks every number and
  service name against that sheet before showing it; otherwise it is built from the rule trace.
  **Ask about this result** answers follow-up questions the same way, and says so when the result
  does not contain the answer.
- **What-if**: change peak traffic, availability, user regions, budget cap or priorities and the
  ranking re-runs straight away, with what moved and why. Save a scenario as a new assessment.
- **Export**: design document as Markdown or PDF (requirements, options, costs, explanation, services
  ruled out, the latest migration plan, prices and the rule trace).

## Auth
- Local dev: `DEV_AUTH_BYPASS=true` (backend) and `VITE_DEV_AUTH_BYPASS=true` (frontend). Every
  request runs as a fixed dev user. Never enable in a shared environment.
- Real sign-in: set the `ENTRA_*` variables in `.env` and the `VITE_ENTRA_*` variables in
  `frontend/.env.local`, and turn both bypass flags off. The backend accepts Entra ID v2 access
  tokens whose audience is the API app registration. App roles: `dba_admin`, `db_approver`.

## Layout
```
backend/          FastAPI app (app/) and pytest suite (tests/)
frontend/         React + Vite + Tailwind
knowledge_base/   Service catalog YAML, rules, sizing constants, price snapshots (M2+)
docs/             Product and design docs; OPEN_QUESTIONS.md tracks undecided points
```
