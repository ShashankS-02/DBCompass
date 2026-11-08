"""Nightly re-ingestion of changed documents (Celery beat)."""

from celery import Celery
from celery.schedules import crontab
from sqlalchemy import text

from app.db import SessionLocal
from app.embeddings import embed

celery_app = Celery("ingest", broker="redis://broker:6379/0")
celery_app.conf.beat_schedule = {"nightly-reindex": {"task": "app.ingest.reindex_changed", "schedule": crontab(hour=2, minute=0)}}

CHUNK_SIZE = 1200


def split_text(content: str) -> list[str]:
    chunks = []
    for start in range(0, len(content), CHUNK_SIZE):
        chunks.append(content[start:start + CHUNK_SIZE])
    return chunks


@celery_app.task
def reindex_changed() -> int:
    with SessionLocal() as session:
        changed = session.execute(
            text("SELECT id, body FROM document_sources WHERE updated_at > now() - interval '1 day'")
        ).all()
        for document_id, body in changed:
            session.execute(text("DELETE FROM chunks WHERE document_id = :id"), {"id": document_id})
            for position, piece in enumerate(split_text(body)):
                session.execute(
                    text(
                        "INSERT INTO chunks (document_id, position, content, content_tsv, embedding) "
                        "VALUES (:id, :position, :content, to_tsvector('english', :content), CAST(:embedding AS vector))"
                    ),
                    {"id": document_id, "position": position, "content": piece, "embedding": str(embed(piece))},
                )
        session.commit()
        return len(changed)
