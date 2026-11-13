# 03 — Architecture

## Component view
```
[React UI] --(Entra ID JWT)--> [FastAPI backend]
                                   |
   +---------------+---------------+----------------+-----------------+
   |               |               |                |                 |
[Assessment API] [Guided intake] [Recommendation  [Pricing module]  [Migration Planner]
                                  Engine]           |                 |
                                   |                |                 |
                         [Knowledge Base YAML] [Price cache]  [Tool matrix YAML]
                                   |                                  /
                          [Explainer (LLM, grounded in trace)] <-----/
                                   |
                            [App DB: PostgreSQL]
```

## Request flow (assessment)
1. UI posts `RequirementsInput` from the guided intake. No application code is read anywhere (M9: the repo analyzer was removed because sending internal code to an LLM is a security violation).
2. `defaults.apply_tier_defaults()` fills unknowns and records `assumed_fields`.
3. `engine.filters` removes ineligible candidates and records reasons.
4. `engine.scorer` scores survivors on 7 dimensions, weighted by user priorities.
5. `engine.combiner` builds polyglot combinations when multiple data shapes / query types exist.
6. `engine.sizer` maps each option to instance class, storage tier, HA layout.
7. `pricing.estimator` prices each option in Budget / Balanced / Performance tiers.
8. Result stored and returned as `AssessmentResult`.
9. On request (M7), `explain.writer` asks the LLM to turn a fact sheet built from the stored result into
   prose. The prompt includes ONLY that fact sheet; the text is fact-checked before it is shown or saved.

## Repo layout
```
dbcompass/
  CONTRIBUTING.md
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
        whatif.py            # re-run with changed answers / priorities; deterministic diff (M7)
      explain/               # M7
        facts.py             # fact sheet from a stored result; vocabulary of service / engine names
        grounding.py         # fact check: numbers and product names must come from the fact sheet
        writer.py            # LLM explanation (checked, one retry) or rule-based paragraphs
        qa.py                # one grounded answer per question; refuses rather than guesses
      export/                # M7 design document
        document.py          # one outline (headings, paragraphs, bullets, tables)
        markdown.py
        pdf.py               # reportlab, Helvetica (Latin-1; arrows and the rupee sign are written out)
      llm/
        client.py            # shared Azure OpenAI client (JSON mode), used by the explainer only
      pricing/
        azure_retail.py      # Retail Prices API (no auth), with retry/backoff
        aws_pricelist.py     # public bulk CSV per offer/region; reserved -> effective hourly
        gcp_catalog.py       # Cloud Billing Catalog API (needs GCP_BILLING_API_KEY)
        matching.py          # pricing.yaml matchers -> PricePoints
        snapshot.py          # `python -m app.pricing.snapshot <csp>`
        price_cache.py       # snapshot files + PriceIndex lookup
        estimator.py         # monthly cost lines per service and tier
        components.py        # M9: backup, I/O, proxy, egress, private endpoints, keys, audit logs; component summary
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
    org_support.yaml         # engines the DBA team supports; special-purpose services (caching, search, analytics)
    engine_features.yaml     # per-engine feature checklist with metadata-only discovery queries
    price_snapshots/         # aws.json, azure.json (gcp.json once a key is set)
  frontend/
    src/pages/ (Intake, Results, MigrationPlan, JustificationForm, History)
    src/hooks/useDraft.ts    # keeps form drafts in the browser until submitted (M9)
    src/components/ (QuestionCard, PrioritySliders, ScoreRadar, CostTiers, WhyPanel, RunbookView)
```

## API contracts
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | /api/assessments | RequirementsInput | AssessmentResult (201); 422 with ValidationReport in `detail` when input is invalid. M9: each `CostEstimate` has `components` [{id, label, status: priced\|included\|estimated\|not_priced\|not_applicable, monthly_usd, note, service}]; for an existing database the result has `baselines` {csp: Baseline} and each recommendation `versus_baseline` (compute + licence difference against staying on the current engine). Baselines carry `core_lines` and `environment_multiplier`, and each `versus_baseline` carries `recommendation_core_lines` and `recommendation_environment_multiplier` (M11), so the UI shows the working. Results also carry `notices` [string]: input conflicts to fix, e.g. a vendor-certified or requested engine that does not suit the chosen data shape. Self-managed components are titled with their engine ("Oracle on Amazon EC2 + EBS (self-managed)") |
| GET | /api/assessments | ?limit=1..100 | list[AssessmentSummary] — caller's own, newest first |
| GET | /api/assessments/{id} | | AssessmentResult; 404 if missing or not the caller's (dba_admin can read all) |
| POST | /api/assessments/{id}/whatif | WhatIfRequest {answers (null clears a field), priorities} | WhatIfResult {base_assessment_id, input (merged), outcome (AssessmentOutcome), changes {changed_fields, top_changed, rank_moves, newly_filtered, no_longer_filtered, rules_added, rules_removed, summary}}; not stored; 422 invalid answers |
| GET | /api/assessments/{id}/explanation | | Explanation or null: the saved LLM explanation for the current prompt version |
| POST | /api/assessments/{id}/explanation | ?refresh=true | Explanation {paragraphs, source: llm\|rules, model, prompt_version, generated_at, notes}. LLM text only if it passes the fact check (else rule-based); only LLM text is saved |
| POST | /api/assessments/{id}/ask | {question} | AnswerOut {question, answer, answerable, source: llm\|unavailable, notes}; grounded in the result, nothing stored |
| POST | /api/migrations/plan | MigrationPlanRequest {assessment_id?, answers (override / add mig.* etc.), target_service_id?, refactor_person_days? [low, high], team_size?, start_date?} | MigrationPlan (201, stored): source, strategies (Rehost / Replatform / Refactor priced over 3 years incl. licences), considered (Retire / Retain / Relocate / Repurchase), recommended strategy, two_step, method + transfer estimate, tools, 8 phases, deadline fit, risks, rollback, validation, assumptions; 404 unknown assessment, 400 no source engine / unknown target, 422 invalid answers |
| GET | /api/migrations/{id} | | MigrationPlan (owner, dba_admin, db_approver) |
| GET | /api/justification/reasons | | JustificationConfig (reasons, weights, thresholds) |
| POST | /api/justification/evaluate | JustificationInput {kind, application_name, requested_engine, assessment_id, migration_plan_id?, reasons [{reason_id, evidence?}], justification_text, alternatives_considered, refactor_person_days?} | JustificationEvaluation (advisory verdict, reason statuses, requested vs best licence-free option, net saving, break-even, problems); nothing stored |
| POST | /api/requests | JustificationInput | DbRequest (201, draft, evaluated) |
| PUT | /api/requests/{id} | JustificationInput | DbRequest (owner; draft or sent_back only, else 409; re-evaluated) |
| POST | /api/requests/{id}/submit | | DbRequest (owner; 409 while the justification has problems) |
| POST | /api/requests/{id}/decision | {decision: approve\|reject\|send_back, note?} | DbRequest (db_approver, never on own request outside dev bypass → 403; reject / send back / approving a needs_review or not_justified verdict need a note → 409) |
| GET | /api/requests | ?scope=mine\|review\|all&limit | list[DbRequestSummary] (review / all for db_approver) |
| GET | /api/requests/{id} | | DbRequest with audit events (owner, db_approver, dba_admin) |
| GET | /api/requests/{id}/export | | text/markdown justification packet |
| GET | /api/assessments/{id}/export?format=md\|pdf | | design document file (attachment): summary, requirements (answered / assumed), options with sizing and cost lines, explanation, services ruled out, latest migration plan, prices, rule trace |
| GET | /api/pricing/status | | snapshot date, regions, price count and unmatched components per CSP; priced / not-priced service counts; INR rate |
| POST | /api/pricing/refresh/{csp} | | dba_admin only; `azure` only (AWS and GCP via the CLI). Rebuilds and saves the snapshot |
| GET | /api/questions?mode=quick\|expert | | QuestionSchema {mode, sections[questions], priority_sliders, fixed_dimension_weights, default_tier} |
| GET | /api/intake | | IntakeConfig {org_support (statuses, engines, special_cases), engine_features (per-engine checklist with metadata-only `how_to_check` queries), commercial_engines} — what the guided intake needs beyond the catalog (M8) ; engine entries also list `discovery` queries (version, size, load) shown in Help (M11) |
| GET | /api/help/guides | | [{slug, title, summary}]: the Help guides (M11) |
| GET | /api/help/guides/{slug} | | {slug, title, summary, markdown}: one guide, read from `DOCS_DIR` (default `docs/`); only listed guides can be read (M11) |
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
    dimension_scores: dict[str, float]       # performance, cost, reliability, ops, ecosystem, compliance (portability dropped in M10)
    cost_tiers: dict[str, CostEstimate]      # budget, balanced, performance
    ha_topology: str
    design_guidance: list[str]
    explanation: str
    setup_guide: list[SetupPhase]           # M10, new applications only: [{id, title, steps: [str]}]

class ServiceChoice(BaseModel):
    service_id: str                          # e.g. "aws.aurora_postgresql"
    role: str                                # primary_oltp, cache, search, analytics, vector
    engine_version: str | None
    instance_class: str
    storage_tier: str
    replicas: int
    about: ServiceAbout | None               # M10: deployment model, provider vs team duties, service facts

class ServiceAbout(BaseModel):               # from knowledge_base/service_models.yaml + the service entry
    deployment: str                          # managed | serverless | iaas
    title: str
    summary: str
    provider_handles: list[str]
    team_handles: list[str]
    facts: list[str]                         # SLA for the chosen layout, storage limit, replicas, licences
    source_url: str | None                   # the cloud's shared responsibility page

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
migration_plans (assessment_id?, request JSON, plan JSON, created_by), db_requests (status, input JSON,
evaluation JSON, created_by, timestamps), request_events (request_id, actor, action, note, at: the audit trail),
explanations (assessment_id, prompt_version, explanation JSON: fact-checked LLM text only),
feedback (assessment_id, accepted_option, comment). Feedback is used later to tune weights.

Roles (Entra app roles): `user`, `dba_admin` (pricing refresh, reads everything), `db_approver` (decides
database requests; cannot decide their own). The dev bypass user has all three.

## Security
- Entra ID SSO; role claims: `user`, `dba_admin` (can edit KB via UI later).
- DBCompass never reads application code. The LLM receives only questionnaire answers and the engine's own result (M9).
- Feature checklists ask for catalog metadata only; no query reads table rows.
- LLM calls go through Azure AI Foundry inside the corporate tenant.
