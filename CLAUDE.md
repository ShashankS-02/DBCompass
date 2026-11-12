# CLAUDE.md — DBCompass

## What this project is
DBCompass is an internal portal that helps application teams choose the right database
(or combination of databases), cloud provider, hardware and design for their application,
and plans migrations between on-prem and AWS / GCP / Azure or between those clouds.

Inputs come from the guided intake (docs/09): one topic per screen, an optional expert survey for
the full catalog. The repo analyzer was removed in M9: internal application code must never be
given to an AI.

Outputs:
- Ranked database recommendations (single DB or polyglot combinations) with a score breakdown.
- Target CSP, managed service, instance class, storage tier and HA topology.
- Monthly cost estimate in three tiers: Budget, Balanced, Performance.
- Design guidance (indexing, partitioning, caching, read replicas, connection pooling).
- Migration plan: strategy (7 Rs), method, tools, phases, runbook, risks, rollback.

## Scope rules (hard)
- Cloud providers: AWS, GCP, Azure ONLY. Do not add or mention any other provider.
- On-prem is allowed only as a migration SOURCE or as a "retain" option.
- Oracle-on-cloud offerings (Oracle Database@AWS, @Azure, @Google Cloud) are in scope
  because they run inside those three CSPs.

## Read these docs before writing code (in order)
1. docs/01_PRD.md                 — product scope, users, MVP vs stretch
2. docs/02_REQUIREMENTS_CATALOG.md — every input field, type, defaults, why it matters
3. docs/03_ARCHITECTURE.md         — components, data flow, API contracts, repo layout
4. docs/04_KNOWLEDGE_BASE.md       — database service catalog schema and service list
5. docs/05_SCORING_AND_COST.md     — filter, score, combine, size, price algorithm
6. docs/06_REPO_ANALYZER.md        — why the repo analyzer was removed (M9)
7. docs/07_MIGRATION_PLANNER.md    — migration strategy logic and tool matrix
8. docs/08_BUILD_PLAN.md           — milestones, owners, demo script

## Tech stack
- Backend: Python 3.11+, FastAPI, Uvicorn, Pydantic v2, SQLAlchemy 2.x
- App database: PostgreSQL (SQLite allowed for local dev)
- LLM: Azure AI Foundry (GPT-4o class model) via the `openai` SDK Azure client
- Frontend: React + Vite + TypeScript + Tailwind, Recharts for charts
- Auth: Microsoft Entra ID SSO (MSAL on frontend, JWT validation on backend). Dev mode bypass flag.
- Packaging: Docker + docker-compose
- Tests: pytest, httpx TestClient

## Architecture principles (non negotiable)
1. The recommendation engine is DETERMINISTIC. Same inputs give the same ranking.
   The LLM is used only for (a) writing human explanations from the engine's rule trace and
   (b) answering follow-up questions grounded in the result. It never sees application code.
2. The LLM never invents prices, SLAs, limits or service names. These come from
   `knowledge_base/` YAML files and the pricing module.
3. Every recommendation carries a `trace`: which rules fired, which filters removed which
   candidates, and the score per dimension. The UI must be able to show "why".
4. Knowledge base YAML is the single source of truth for service capabilities. Each entry has
   `last_verified` date and `source_url`.
5. Unknown inputs get defaults derived from the application's criticality tier, and the
   result marks those fields as "assumed".
6. Never read or ask for application code or customer data. Discovery queries return metadata only.
7. Recommend only engines on the org support list (`org_support.yaml`); caching, search and
   analytics services are kept as special-purpose add-ons.

## Python coding conventions
- Explicit, readable code. No clever one-liners, no nested comprehensions.
- Clear descriptive variable names (`monthly_compute_cost`, not `mcc`).
- Standard `for` loops over comprehensions when logic is non-trivial.
- Type hints on every function. Docstring on every public function.
- Small functions, one responsibility each. Max ~40 lines per function.
- Pydantic models for every request and response body.
- No bare `except`. Log with the `logging` module, not print.
- Config through environment variables loaded in `app/config.py`. Never hardcode secrets.

## Commands
```
# backend
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
pytest -q

# frontend
cd frontend && npm install && npm run dev

# everything
docker compose up --build
```

## Definition of done for any task
- Code follows the conventions above.
- Unit tests added or updated and passing.
- New knowledge base entries include `last_verified` and `source_url`.
- API changes reflected in docs/03_ARCHITECTURE.md.
- No secrets committed.

## How to work in this repo
- Before a large change, write a short plan and list files you will touch.
- Prefer extending YAML rules over hardcoding logic in Python.
- When unsure about a cloud service capability, add it to `docs/OPEN_QUESTIONS.md`
  instead of guessing.
