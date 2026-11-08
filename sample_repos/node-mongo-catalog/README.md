# Catalog Service

Product catalogue and reviews for the mobile app (Tier 2).

- Read-heavy: up to 8k requests/s at peak, mostly product lookups.
- Data: dataset of about 120 GB of product and review documents.
- Availability target 99.9%; p99 read latency under 50 ms.
- Users globally (app stores in 40 countries).
- Search uses MongoDB text indexes; catalogue changes are streamed to Kafka for the search team.
