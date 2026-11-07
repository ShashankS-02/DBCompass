# 08 — Build Plan (2 weeks, 5 people, 3 with Claude Code)

## Roles
| Person | Area | Claude Code? |
|---|---|---|
| P1 | Backend core: models, engine (filters, scorer, combiner, sizer) | Yes |
| P2 | Repo analyzer + LLM integration + explainer | Yes |
| P3 | Frontend: form renderer, results, migration page | Yes |
| P4 | Knowledge base YAML + rules + golden test cases (DBA expertise) | No |
| P5 | Pricing snapshots, migration tool matrix, demo data, pitch deck | No |

## Milestones (do them in this order)
| Day | Milestone | Done when |
|---|---|---|
| 1 | M0 Skeleton | Repo layout, FastAPI health, React shell, docker compose up works, Entra dev bypass |
| 2–3 | M1 Catalog + form | `/api/questions` from catalog; Quick and Expert forms render; RequirementsInput validated |
| 2–4 | M2 Knowledge base | 25+ service YAML entries across the 3 CSPs, rules.yaml with 20+ rules |
| 4–6 | M3 Engine | Filter → score → combine → size works on golden cases; trace returned |
| 5–7 | M4 Pricing | Azure live, AWS + GCP snapshots, 3 cost tiers on results |
| 5–9 | M5 Repo analyzer | 3 sample repos produce pre-filled forms with evidence |
| 7–10 | M6 Migration planner | Strategy, method, tools, transfer time, runbook, risks |
| 9–11 | M7 Explainer + what-if + export | LLM explanation grounded in trace; sliders re-rank; MD/PDF export |
| 11–12 | M8 Stretch pick ONE | AWR upload sizing OR DB link wave planner |
| 13 | Polish | Loading states, empty states, error handling, demo seed data |
| 14 | Rehearse | Timed demo twice, backup video recorded |

## Kick-off prompt for each Claude Code session
```
Read CLAUDE.md and every file in docs/ in order. Then summarise in 10 lines what you understood,
list anything ambiguous, and propose a plan for milestone <Mx> listing the files you will create.
Do not write code until I approve the plan.
```

## Demo script (7 minutes)
1. Problem in one slide: cost of wrong DB choices and manual migration planning (use real anonymised numbers from the DBA team).
2. Paste the Spring Boot + Oracle sample repo URL → analyzer finds Oracle 19c, heavy PL/SQL, DB links.
3. Confirm form, set priorities (cost high) → top 3 results with radar charts and cost tiers.
4. Click "Why not Aurora PostgreSQL?" → trace shows refactor effort penalty and person-day estimate.
5. Drag what-if slider: 10× traffic → ranking shifts; explain why.
6. Open Migration Plan → strategy comparison, ZDM / DMS tool path, transfer time, runbook, rollback.
7. Export PDF design doc. Close with stretch feature and roadmap.

## Risks for the team
- Scope creep: cut hardware recommendations for IaaS before cutting explainability.
- KB accuracy: P4 verifies every entry; judges from the DBA world will spot wrong limits.
- LLM latency in demo: cache explanations for demo cases.
