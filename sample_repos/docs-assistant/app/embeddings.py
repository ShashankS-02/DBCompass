"""Calls the internal embedding service."""

import os

import httpx

EMBEDDING_ENDPOINT = os.environ.get("EMBEDDING_ENDPOINT", "")


def embed(text: str) -> list[float]:
    response = httpx.post(f"{EMBEDDING_ENDPOINT}/embeddings", json={"input": text}, timeout=10)
    response.raise_for_status()
    return response.json()["data"][0]["embedding"]
