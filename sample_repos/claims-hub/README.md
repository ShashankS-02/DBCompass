# Claims Hub

Claims Hub is the motor and home insurance claims platform used by adjusters and the customer portal.
It runs today on an on-premises SQL Server 2019 cluster in our Frankfurt data centre and is being
moved to Azure as part of the data centre exit.

## Service profile

- Criticality: **Tier 1** (business critical). Target availability **99.99%**.
- Users: policy holders and adjusters in Europe (Germany, France, Netherlands).
- Compliance: GDPR. Claim and customer data must stay in the EU.
- Database size is about 900 GB, growing roughly 25 GB per month.
- Peak load is around 1,200 TPS during storm events; normal load is ~300 TPS.
- Latency target: p99 under 20 ms for claim lookups.
- Strong consistency: payments and reserve changes are ACID transactions across several tables.

## Architecture

- ASP.NET Core 8 Web API (`src/ClaimsHub`) using Entity Framework Core with SQL Server.
- Business rules for reserves, fraud scoring and settlement live in T-SQL stored procedures
  (`database/procedures`), called from the API.
- SQL Server Agent runs nightly jobs for reserve recalculation and the regulator export (`database/jobs`).
- Target landing zone in Azure West Europe is defined in `infra/` (Terraform).

## Running locally

```bash
docker compose up -d sqlserver
dotnet run --project src/ClaimsHub
```

Connection strings come from environment variables; nothing secret is stored in this repository.
