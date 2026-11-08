CREATE TABLE document_sources (
    id          BIGINT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    body        TEXT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_document_sources_updated ON document_sources (updated_at);
