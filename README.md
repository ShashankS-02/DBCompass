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

## Auth
- Local dev: `DEV_AUTH_BYPASS=true` (backend) and `VITE_DEV_AUTH_BYPASS=true` (frontend). Every
  request runs as a fixed dev user. Never enable in a shared environment.
- Real sign-in: set the `ENTRA_*` variables in `.env` and the `VITE_ENTRA_*` variables in
  `frontend/.env.local`, and turn both bypass flags off. The backend accepts Entra ID v2 access
  tokens whose audience is the API app registration.

## Layout
```
backend/          FastAPI app (app/) and pytest suite (tests/)
frontend/         React + Vite + Tailwind
knowledge_base/   Service catalog YAML, rules, sizing constants, price snapshots (M2+)
sample_repos/     Demo repos for the analyzer (M5)
docs/             Product and design docs; OPEN_QUESTIONS.md tracks undecided points
```
