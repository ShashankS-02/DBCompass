# Billing Service

Invoicing and payment allocation for the enterprise payments platform.

## Service profile
- Criticality: Tier 1 (business critical). Availability target 99.95%.
- Traffic: handles about 2,000 TPS at month-end peak.
- Data: the database size is about 1.5 TB and grows ~40 GB per month.
- Latency: p99 read latency must stay under 10 ms for invoice lookups.
- Users in India (all business units); PCI-DSS applies to stored card references.

## Stack
Spring Boot 3, Spring Data JPA, Oracle Database 19c. Most rating and allocation logic lives in
PL/SQL packages under `db/plsql`. Ledger balances are read from the finance ledger database over
a database link.
