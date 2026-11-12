# 09 — Guided intake and the org's supported list (M8)

## Why
Teams gave up on the Quick / Expert form: too many fields at once, no sense of progress, and the
same questions for a brand-new app and a 20-year-old Oracle estate. The intake at
`/assessments/new` asks one topic per screen, in the order a DBA would ask, and never needs more
than five minutes. The old Quick / Expert form was removed in M9 with the repo analyzer; its full
catalog lives on as the optional expert survey on the Priorities step.

## Flow
```
Start ─ app name, existing or new?
 ├─ Existing ─ Database (engine, version, platform, size bucket, tier, type)
 │            ─ Features (engine-specific checklist + stored procedures + data shape + notes)
 │            ─ Team (internal or vendor → vendor name (required) → will the vendor help? → readiness)
 │            ─ Application (languages, personal data, compliance, environments, network, proxy, egress)
 │            ─ Preference (database in mind → licences, cloud, user regions)
 └─ New ────── Origin (internal or vendor → vendor name (required) → certified database → licences)
              ─ Essentials (tier, type, data shape, size, traffic, regions, cloud, database in mind)
              ─ Application (as above)
Priorities ─ sliders + optional expert survey (only the questions not asked above)
Review ─ answers, validation, what will be assumed → Get recommendations
```
Rules of the intake:
- Buttons wherever possible; typing only for the name, the version, the notes and an exact size.
- Every step except the first (and the source engine) can be skipped: "I don't know, assume defaults".
  Skipped answers are filled from the criticality tier and listed as *assumed* on the review step.
- Drafts autosave in the browser (`localStorage` and `sessionStorage`, flushed when the tab is
  hidden) and survive tab switches, navigation, reloads and the sign-in redirect, until the assessment
  is submitted or "Start over" is pressed. The migration plan and request forms do the same
  (`hooks/useDraft.ts`).
- Metadata only. Questions never ask for row data, and every "How to check" query reads the
  engine's catalog (object names, counts, settings).

## Knowledge files
### `engine_features.yaml`
Per engine: `discovery_note` and a list of `{feature, label, how_to_check}`. `feature` is a value of
`data.special_features` (the cross-engine vocabulary), `label` is the engine's own name for it
("Linked servers" for SQL Server, "Foreign data wrappers" for PostgreSQL under `db_links`).
`sticky_features` are the ones that make staying on the same engine materially easier; rule
`R-FEAT-STICKY-001` boosts same-engine targets by 8 when any is ticked. The checker confirms every
feature is a catalog option.

### `org_support.yaml`
The engines the database team supports with a status:
- `strategic` — preferred; `supported` — fine as a target; `sunset` — accepted as a migration source
  only, not offered as a target (the three clouds have no managed Sybase, Informix or Vertica anyway).

Since M9 the service catalog only holds targets on supported engines, so there is nothing to pin and
no badge on the result. `special_cases` lists the three special-purpose kinds (caching, vector and
full-text search, analytics) with the answers under which such a service may be the main database;
the result's "If you need more than a database" panel lists the ones kept out.

## New catalog fields
M9: `eco.languages` (quick, twelve options), `sec.personal_data` (quick; customers / employees / both
/ none; turns `sec.cmk`, `sec.audit` and `sec.masking_rls` on by default and fires `R-PII-001`),
`sec.compliance` adds ISO 27001, `cost.egress_gb_month`, `cost.connection_proxy`, and
`app.vendor_name` is required when `app.origin` is vendor (`required_when` in questions.yaml).

M8: `app.name`, `app.origin`, `app.vendor_name`, `app.vendor_certified_db`, `app.vendor_migration_support`,
`app.notes`, `pref.licence_status`, `team.source_skills`, `team.target_skills`, `team.capacity`
(doc 02). Derived: `app.vendor_certified_engine`, used by `R-VENDOR-001` (+20 certified engine,
−15 others) and the *vendor_certified* justification reason.

## Team readiness (`engine/readiness.py`)
Only for an existing database. A vendor that will support the migration → *ready*. Otherwise the
three team answers score gaps (partial 1, no 2): any gap → *needs an SME*; no capacity or 4+ points →
*needs a migration partner*; unanswered → *unknown* with the next question to ask. The verdict is on
the result (`readiness`), in the fact sheet for the explainer, in the design document, and in the
migration plan as `plan.readiness`: phase `engage_partner` (15 days, before Plan) and risks
`RISK-TEAM-NEEDS-SME` / `RISK-TEAM-NEEDS-PARTNER`. The plan also raises
`RISK-VENDOR-UNSUPPORTED-TARGET` when the target is not the vendor-certified engine and
`RISK-SUNSET-SOURCE` for a sunset source.

## New sources
Couchbase, Sybase ASE, Informix and Vertica are engine options and `Engine` vocabulary values; the
tool matrix has rows for them (AWS SCT for SAP ASE / Informix, SSMA for Sybase, pgloader, the vendors'
export tools). Open questions 55–60 record what the DBA team still has to confirm.
