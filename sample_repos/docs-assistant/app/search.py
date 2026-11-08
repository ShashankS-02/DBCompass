"""Hybrid retrieval: pgvector cosine similarity plus PostgreSQL full-text rank."""

from sqlalchemy import text
from sqlalchemy.orm import Session

HYBRID_QUERY = text(
    """
    SELECT c.id, c.content, d.title, d.source_url,
           1 - (c.embedding <=> CAST(:query_embedding AS vector)) AS similarity,
           ts_rank(c.content_tsv, plainto_tsquery('english', :question)) AS text_rank
    FROM chunks c
    JOIN documents d ON d.id = c.document_id
    WHERE d.collection_id = ANY(:collection_ids)
    ORDER BY c.embedding <=> CAST(:query_embedding AS vector)
    LIMIT :candidate_count
    """
)


def search_chunks(session: Session, question: str, query_embedding: list[float], collection_ids: list[int], limit: int = 8) -> list[dict]:
    """Top chunks by vector similarity, re-ranked with the full-text score."""
    rows = session.execute(
        HYBRID_QUERY,
        {"query_embedding": str(query_embedding), "question": question, "collection_ids": collection_ids, "candidate_count": limit * 4},
    ).mappings().all()
    ranked = sorted(rows, key=lambda row: 0.8 * row["similarity"] + 0.2 * row["text_rank"], reverse=True)
    return [dict(row) for row in ranked[:limit]]


def get_document(session: Session, document_id: int) -> dict | None:
    """One document by id."""
    row = session.execute(text("SELECT id, title, source_url FROM documents WHERE id = :id"), {"id": document_id}).mappings().first()
    return dict(row) if row else None
