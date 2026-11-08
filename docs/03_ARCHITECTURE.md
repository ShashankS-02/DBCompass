# 03 — Architecture

## Component view
```
[React UI] --(Entra ID JWT)--> [FastAPI backend]
                                   |
   +---------------+---------------+----------------+-----------------+
   |               |               |                |                 |
[Assessment API] [Repo Analyzer] [Recommendation  [Pricing module]  [Migration Planner]
                   |              Engine]           |                 |
                   |               |                |                 |
              [LLM extractor] [Knowledge Base YAML] [Price cache]  [Tool matrix YAML]
                   \               |                                  /
                    \------> [Explainer (LLM, grounded in trace)] <--/
                                   |
                            [App DB: PostgreSQL]
```

## Request flow (assessment)
1. UI posts `RequirementsInput` (or a repo URL first, which returns `InferredRequirements`).
2. `defaults.apply_tier_defaults()` fills unknowns and records `assumed_fields`.
3. `engine.filters` removes ineligible candidates and records reasons.
4. `engine.scorer` scores survivors on 7 dimensions, weighted by user priorities.
5. `engine.combiner` builds polyglot combinations when multiple data shapes / query types exist.
6. `engine.sizer` maps each option to instance class, storage tier, HA layout.
7. `pricing.estimator` prices each option in Budget / Balanced / Performance tiers.
8. `explain.writer` asks the LLM to turn the trace into prose. Prompt includes ONLY trace data.
9. Result stored and returned as `AssessmentResult`.

## Repo layout
```
dbcompass/
  CLAUDE.md
  docs/
  docker-compose.yml
  backend/
    requirements.txt
    app/
      main.py
      config.py
      auth/entra.py
      api/
        routes_health.py     # /api/health, /api/me
        routes_questions.py  # /api/questions
        routes_assessment.py # /api/requirements/validate (M1), /api/assessments (M3)
        routes_repo.py
        routes_migration.py
        routes_export.py
      models/
        questions.py         # QuestionCatalog, Question, QuestionSchema
        knowledge.py         # ServiceEntry, RuleSet, RegionCatalog, SizingConstants
        requirements.py      # RequirementsInput, ValidationReport
        results.py           # AssessmentResult, Recommendation, Trace, SizingResult
        migration.py         # MigrationInput, MigrationPlan
        pricing.py           # PricingConfig (pricing.yaml), PricePoint, PriceSnapshot
      engine/
        defaults.py
        weights.py           # priority sliders -> dimension weights
        validation.py        # builds ValidationReport
        rules.py             # condition / predicate evaluation
        assess.py            # runs the pipeline, ranks, builds AssessmentOutcome
        costing.py           # tier sizing, budget filter, recommendation cost tiers
        filters.py
        scorer.py
        combiner.py
        sizer.py
        explain.py
      analyzer/
        repo_fetch.py        # shallow clone or GitHub API, size limits
        secret_redactor.py
        dependency_scanner.py
        schema_extractor.py
        sql_profiler.py
        infra_scanner.py     # docker-compose, Terraform, k8s manifests
        llm_extractor.py
        mapper.py            # signals -> InferredRequirements
      pricing/
        azure_retail.py      # Retail Prices API (no auth), with retry/backoff
        aws_pricelist.py     # public bulk CSV per offer/region; reserved -> effective hourly
        gcp_catalog.py       # Cloud Billing Catalog API (needs GCP_BILLING_API_KEY)
        matching.py          # pricing.yaml matchers -> PricePoints
        snapshot.py          # `python -m app.pricing.snapshot <csp>`
        price_cache.py       # snapshot files + PriceIndex lookup
        estimator.py         # monthly cost lines per service and tier
      migration/
        strategy.py          # 7 Rs selection
        method.py            # offline / physical / CDC selection
        tools_matrix.py
        transfer_time.py
        runbook.py
      knowledge/loader.py, knowledge/catalog.py   # YAML loading; answer validation
      knowledge/check.py   # `python -m app.knowledge.check` cross-checks the KB
      db/session.py, db/tables.py, db/assessments.py
    tests/                 # pytest suite, run from backend/; tests/engine/golden/*.yaml = golden cases
  knowledge_base/
    databases/aws_*.yaml, gcp_*.yaml, azure_*.yaml
    questions.yaml           # requirements catalog (machine-readable doc 02)
    rules.yaml
    regions.yaml             # geography -> region ids per CSP
    sizing.yaml
    scoring.yaml             # scoring tables, relative cost, combination settings
    hardware_profiles.yaml
    design_patterns.yaml
    migration_tools.yaml
    pricing.yaml             # how to find each service's prices; tiers; not_priced reasons
    price_snapshots/         # aws.json, azure.json (gcp.json once a key is set)
  frontend/
    src/pages/ (NewAssessment, RepoInput, Results, MigrationPlan, History)
    src/components/ (QuestionCard, PrioritySliders, ScoreRadar, CostTiers, WhyPanel, RunbookView)
  sample_repos/              # small demo repos for the analyzer
```

## API contracts
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | /api/assessments | RequirementsInput | AssessmentResult (201); 422 with ValidationReport in `detail` when input is invalid |
| GET | /api/assessments | ?limit=1..100 | list[AssessmentSummary] — caller's own, newest first |
| GET | /api/assessments/{id} | | AssessmentResult; 404 if missing or not the caller's (dba_admin can read all) |
| POST | /api/assessments/{id}/whatif | partial RequirementsInput | AssessmentResult (not stored) |
| POST | /api/repo/analyze | {repo_url, branch?, token?} | InferredRequirements |
| POST | /api/migrations/plan | MigrationInput | MigrationPlan |
| GET | /api/assessments/{id}/export?format=md\|pdf | | file |
| GET | /api/pricing/status | | snapshot date, regions, price count and unmatched components per CSP; priced / not-priced service counts; INR rate |
| POST | /api/pricing/refresh/{csp} | | dba_admin only; `azure` only (AWS and GCP via the CLI). Rebuilds and saves the snapshot |
| GET | /api/questions?mode=quick\|expert | | QuestionSchema {mode, sections[questions], priority_sliders, fixed_dimension_weights, default_tier} |
| POST | /api/requirements/validate | RequirementsInput | ValidationReport {valid, errors, normalised, unanswered_quick_fields, assumed_fields, ignored_fields, dimension_weights} |
| GET | /api/health | | HealthResponse {status, version, database} (no auth) |
| GET | /api/me | | CurrentUser {user_id, name, email, roles, auth_mode} |

The form is rendered from `/api/questions`, generated from `knowledge_base/questions.yaml`,
so adding a field in the catalog does not require frontend or backend model changes.

`RequirementsInput` is `{mode, migrating, answers: {field_id: value}, priorities: {slider_id: 0–100}}`.
Answers are checked against the catalog by `knowledge/catalog.py`; a missing or null answer means
"unknown". `/api/requirements/validate` always returns 200 with `valid` and per-field `errors`;
only a malformed body returns 422. Migration fields are ignored unless `migrating` is true.

## Key models (Pydantic, abbreviated)
```python
class Recommendation(BaseModel):
    rank: int
    components: list[ServiceChoice]          # 1 for single DB, >1 for polyglot
    csp: Literal["aws", "gcp", "azure"]
    total_score: float
    dimension_scores: dict[str, float]       # performance, cost, reliability, ops, ecosystem, compliance, portability
    cost_tiers: dict[str, CostEstimate]      # budget, balanced, performance
    ha_topology: str
    design_guidance: list[str]
    explanation: str

class ServiceChoice(BaseModel):
    service_id: str                          # e.g. "aws.aurora_postgresql"
    role: str                                # primary_oltp, cache, search, analytics, vector
    engine_version: str | None
    instance_class: str
    storage_tier: str
    replicas: int

class Trace(BaseModel):
    filtered_out: list[FilterReason]         # service_id, rule_id, message
    rules_fired: list[str]
    assumed_fields: list[str]
```

## Engine as implemented (M3)
`engine/assess.py::run_assessment` is a pure function (no clock, randomness or LLM):
1. Validate against the catalog; invalid input raises and the API returns 422.
2. `defaults.resolve_requirements`: answers → tier defaults → app-type defaults (sizing.yaml) →
   derived fields. Everything filled is listed in `trace.assumed_fields`.
3. `rules.fired_rules` evaluates `when` on the resolved values.
4. `filters.filter_services` twice: primaries (shape filter + every fired rule) and add-on
   components (only `scope: all_components` rules). Every removal is a `FilterReason`.
5. `sizer.size_service` for every service, once as primary and once as component (an in-memory
   primary holds the whole dataset; a cache holds the working set).
6. `costing.apply_budget_filter` drops primaries whose Budget tier exceeds cap × 1.5 (unpriced pass, noted).
   `scorer.score_all`: 7 dimensions, weighted, plus rule boosts/penalties, clipped to 0–100.
   Cost = Balanced-tier monthly USD (unpriced services score neutral 50; relative units only if nothing is priced).
7. `combiner.build_combination` for the best `primaries_considered` primaries.
8. Rank by score, then lower monthly cost, then service id. Top 3 become `Recommendation`s, each with
   `cost_tiers` (budget / balanced / performance `CostEstimate`s whose `lines` carry SKU, region,
   term, quantity and unit price) and the result carries `pricing` (snapshot dates, INR rate).

`Trace` holds `rules_fired`, `filtered_out` (service, rule id, message — every service not
scored has at least one), `assumed_fields`, `dimension_weights`, `scores` (per-dimension
breakdown and adjustments for every scored primary) and `combination_notes`.

## Persistence (app DB)
Tables: users, assessments (input JSON, result JSON, created_by, created_at),
repo_scans (repo_url, commit_sha, signals JSON), migration_plans, feedback
(assessment_id, accepted_option, comment). Feedback is used later to tune weights.

## Security
- Entra ID SSO; role claims: `user`, `dba_admin` (can edit KB via UI later).
- GitHub tokens are used once and never stored.
- Repo clones go to a temp dir, max 200 MB, deleted after scan.
- Secret redaction runs before any LLM call.
- LLM calls go through Azure AI Foundry inside the corporate tenant.
