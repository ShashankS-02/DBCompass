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
sample_repos/     Demo repos for the analyzer (Oracle, Postgres+Redis, Mongo, SQL Server→Azure, pgvector RAG on GCP)
docs/             Product and design docs; OPEN_QUESTIONS.md tracks undecided points
```
