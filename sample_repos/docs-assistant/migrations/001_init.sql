CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE collections (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) UNIQUE NOT NULL,
    owner_team  VARCHAR(100) NOT NULL
);

CREATE TABLE documents (
    id             BIGSERIAL PRIMARY KEY,
    collection_id  INT NOT NULL REFERENCES collections(id),
    source_url     VARCHAR(500) UNIQUE NOT NULL,
    title          VARCHAR(300) NOT NULL,
    metadata_json  JSONB NOT NULL DEFAULT '{}',
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE chunks (
    id           BIGSERIAL PRIMARY KEY,
    document_id  BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    position     INT NOT NULL,
    content      TEXT NOT NULL,
    content_tsv  TSVECTOR NOT NULL,
    embedding    vector(1536) NOT NULL
);

CREATE INDEX ix_chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ix_chunks_tsv ON chunks USING gin (content_tsv);

CREATE TABLE feedback (
    id          BIGSERIAL PRIMARY KEY,
    question    TEXT NOT NULL,
    chunk_id    BIGINT REFERENCES chunks(id) ON DELETE SET NULL,
    helpful     BOOLEAN NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
