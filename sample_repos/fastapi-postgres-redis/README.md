# Orders API

Order capture and fulfilment API for the retail storefront (Tier 2).

- Peak load: about 1,500 requests per second during sales.
- Database size is around 300 GB.
- Availability target: 99.9% monthly.
- Users in India and Europe; GDPR and DPDP obligations apply to customer data.
- Product search uses PostgreSQL full-text search plus pgvector similarity for recommendations.
