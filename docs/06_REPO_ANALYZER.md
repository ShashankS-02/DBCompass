# 06 — Repo Analyzer (removed in M9)

The repo analyzer read a GitHub repository, extracted drivers, ORM models, SQL and infrastructure
files, and sent redacted excerpts to the LLM to pre-fill the requirements form.

It was removed on 2026-11-12. Giving anything related to internal application code to an AI is a
security violation under the organisation's policy, even with secret redaction. The code, the
`analyzer.yaml` patterns, the `repo_scans` table, the `/api/repo/*` endpoints, the demo repos and
the Repo page are gone. Git history keeps them for reference.

What replaced it:
- The guided intake (docs/09) asks the same questions in plain language.
- The engine-specific feature checklist gives DBAs catalog queries that return metadata only.
- A team that has reviewed its own code can still type a refactor estimate into the migration plan.

The LLM is now used only for explanations and follow-up answers, grounded in the engine's result.
