# Docs Assistant

Docs Assistant answers employee questions about internal policies, runbooks and product documentation.
Documents are split into chunks, embedded, and stored in PostgreSQL with the pgvector extension; a
question is answered from the most similar chunks (retrieval-augmented generation).

## Service profile

- Criticality: **Tier 2** (important internal tool). Target availability **99.9%**.
- Users: employees in India (Bengaluru, Hyderabad, Pune offices).
- Compliance: DPDP. Employee data must stay in India.
- Dataset: about 150 GB today (documents, chunks and 1536-dimension embeddings), growing ~10 GB per month.
- Load: up to 300 requests/s at the start of the working day; mostly reads.
- Latency target: p99 under 100 ms for the similarity search.
- Deployment target is Google Cloud, Mumbai region (`infra/`).

## Stack

- FastAPI service (`app/`), SQLAlchemy, psycopg 3, pgvector.
- Background ingestion with Celery: new and changed documents are re-chunked and re-embedded nightly.
- Full-text search on chunk text is combined with vector similarity (hybrid retrieval).

## Running locally

```bash
docker compose up -d db
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Configuration comes from environment variables (see `.env.example`).
