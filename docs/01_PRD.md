# 01 — Product Requirements: DBCompass

## Problem
Application teams pick databases by habit ("we always use Oracle") or by whatever the last
project used. Result: over-provisioned on-prem boxes, wrong data models, surprise cloud bills,
and migrations planned on spreadsheets. The DBA team answers the same questions repeatedly.

## Goal
Give any application team a defensible, explainable answer to:
1. Which database(s) should this application use?
2. On which CSP (AWS / GCP / Azure), which service, what size, what HA topology?
3. What will it cost per month, and what are the trade-offs?
4. If we are moving, how do we migrate, with which tools, and what are the risks?

## Users
| Persona | Need |
|---|---|
| App developer / tech lead | Quick, trustworthy recommendation without DB expertise |
| Solution architect | Compare options, export a design document for review boards |
| DBA team | Fewer repetitive consultations; consistent standards; migration runbooks |
| Engineering manager | Cost estimate and risk view for budgeting and approval |

## Core user flows
### Flow A — Form based assessment
Login (Entra ID) → New Assessment → choose Quick or Expert mode → answer questions
(with tooltips explaining why each matters) → set priority sliders (Performance / Cost /
Reliability; operations effort, ecosystem and compliance carry fixed weights) → Results page.

### Flow B — Repo based assessment (removed in M9)
Removed: sending internal application code to an AI is a security violation. The guided intake
(docs/09) and its metadata-only feature checklists replace it.

### Flow C — Migration planning
From any assessment, or standalone: describe source (on-prem / CSP, engine, version, size,
change rate, downtime tolerance, dependencies like DB links) → pick or accept target →
Migration Plan page.

## Results page contents
1. Top 3 recommendations, each either a single DB or a polyglot combination.
2. Per recommendation: CSP, service, engine/version, instance class, storage tier, HA layout,
   estimated monthly cost (Budget / Balanced / Performance tiers), score radar chart.
3. "Why this" panel built from the rule trace. "Why not X" for eliminated candidates.
4. Design guidance: schema/data modelling notes, indexing, partitioning, caching,
   read replicas, connection pooling, backup/PITR, encryption.
5. Assumptions list (fields that were defaulted).
6. Your answers (the Review step) on the results page, and per option "About this service":
   what the cloud provider runs and what the team runs (managed, serverless or self-managed).
7. Export: Markdown / PDF design document.

## MVP (hackathon, 2 weeks)
- Quick + Expert form, priority sliders
- Knowledge base covering the main managed DB services on AWS, GCP, Azure (see doc 04)
- Deterministic engine: filter → score → combine → size → price
- Live pricing from Azure Retail Prices API; cached price snapshots for AWS and GCP
- Migration planner with strategy selection, tool matrix, phase runbook, transfer time estimate
- LLM explanations grounded in trace
- Export to Markdown/PDF

## Stretch
- AWR / OEM report upload for Oracle sources to size targets from real metrics
- Oracle feature compatibility scanner with effort estimate in person-days
- Fleet view: DB link dependency graph → migration waves
- Terraform generation for the recommended target
- 3-year TCO: on-prem vs each CSP, including licensing (BYOL, Azure Hybrid Benefit)
- Network path advice: private connectivity (Direct Connect / ExpressRoute / Cloud Interconnect),
  latency between app region and DB region

## Non-goals
- Any CSP other than AWS, GCP, Azure
- Actually provisioning resources or running migrations
- Real-time cost tracking of existing deployments

## Success metrics
- Assessment completed in under 5 minutes (Quick mode)
- DBA team agrees with top recommendation on at least 8 of 10 historical test cases
