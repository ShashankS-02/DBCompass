"""Docs Assistant API."""

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.embeddings import embed
from app.search import get_document, search_chunks

app = FastAPI(title="Docs Assistant")


class AskRequest(BaseModel):
    question: str
    collection_ids: list[int]


def get_session():
    with SessionLocal() as session:
        yield session


@app.post("/ask")
def ask(request: AskRequest, session: Session = Depends(get_session)) -> dict:
    query_embedding = embed(request.question)
    chunks = search_chunks(session, request.question, query_embedding, request.collection_ids)
    return {"question": request.question, "sources": chunks}


@app.get("/documents/{document_id}")
def document(document_id: int, session: Session = Depends(get_session)) -> dict:
    found = get_document(session, document_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Not found")
    return found
