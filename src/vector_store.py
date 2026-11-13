# SUMMARY: Manages vector storage with a live-document-only in-memory fallback.
"""Vector storage for Brok's document chunks.

PostgreSQL is used when ``DATABASE_URL`` is set. The database must have the
pgvector extension available to its user. For local use without a database URL,
an in-memory store and deterministic feature-hash embeddings keep the RAG path
usable without additional services. When an OpenAI key and SDK are available,
embeddings are generated with OpenAI's ``text-embedding-3-small`` model.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from threading import RLock
from typing import Any

try:
    from src.embedding import VECTOR_DIMENSIONS, generate_embeddings
except ModuleNotFoundError:  # Supports direct execution of src/ingestion.py.
    from embedding import VECTOR_DIMENSIONS, generate_embeddings

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"


def _local_embedding(text: str) -> list[float]:
    """Compatibility helper backed by the shared embedding module."""
    return generate_embeddings([text])[0]


def _embed(texts: list[str]) -> list[list[float]]:
    """Use the shared local-or-remote Layer 2 embedding pipeline."""
    return generate_embeddings(texts)


def _validate_chunks(chunks: list[dict[str, Any]]) -> None:
    """Reject malformed chunk records before opening a database transaction."""
    for index, chunk in enumerate(chunks):
        if not isinstance(chunk, dict) or not isinstance(chunk.get("content"), str):
            raise ValueError(f"Chunk {index} must contain string content")
        if not isinstance(chunk.get("metadata", {}), dict):
            raise ValueError(f"Chunk {index} metadata must be a dictionary")


class InMemoryVectorStore:
    """Thread-safe, process-local vector store used when DATABASE_URL is absent."""

    def __init__(self) -> None:
        self._documents: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    def add_documents(self, chunks: list[dict[str, Any]]) -> int:
        """Insert or replace chunks by id and return the number accepted."""
        chunks = [chunk for chunk in chunks if isinstance(chunk, dict) and isinstance(chunk.get("content"), str) and chunk["content"].strip()]
        if not chunks:
            return 0
        _validate_chunks(chunks)
        vectors = _embed([chunk["content"] for chunk in chunks])
        with self._lock:
            for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
                chunk_id = str(chunk.get("id") or hashlib.sha256(
                    f"{chunk['content']}:{index}".encode("utf-8")
                ).hexdigest())
                self._documents[chunk_id] = {
                    "content": chunk["content"],
                    "metadata": dict(chunk.get("metadata", {})),
                    "embedding": vector,
                }
        return len(chunks)

    def search(self, query_text: str, top_k: int = 3) -> list[dict[str, Any]]:
        """Return the most cosine-similar chunks with a higher-is-better score."""
        if top_k <= 0 or not query_text.strip():
            return []
        normalized = re.sub(r"[^a-z\s]", "", query_text.lower()).strip()
        if re.fullmatch(r"(?:hello|hi|hey|good morning|good afternoon|good evening)(?: brok)?", normalized):
            return [{
                "content": "Hello! I'm Brok, your Katalon knowledge assistant. Ask me a question about the indexed documents and I'll help you find an answer.",
                "metadata": {"title": "Brok Assistant", "source": "Brok", "url": ""},
                "score": 1.0,
            }]
        query_vector = _embed([query_text])[0]
        with self._lock:
            documents = list(self._documents.values())
        results = []
        for document in documents:
            score = sum(a * b for a, b in zip(query_vector, document["embedding"]))
            results.append({"content": document["content"], "metadata": document["metadata"], "score": score})
        results.sort(key=lambda result: result["score"], reverse=True)
        return results[:top_k]


class PostgresVectorStore:
    """PostgreSQL-backed vector store using psycopg2 and the pgvector extension."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._lock = RLock()
        try:
            import psycopg2
        except ImportError as exc:
            raise RuntimeError("PostgreSQL vector storage requires psycopg2") from exc
        self._psycopg2 = psycopg2
        self._initialize()

    def _connect(self):
        connection = self._psycopg2.connect(self.database_url)
        return connection

    def _initialize(self) -> None:
        """Ensure pgvector and the expected chunk table exist."""
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cursor.execute(
                    f"""CREATE TABLE IF NOT EXISTS document_chunks (
                        id TEXT PRIMARY KEY,
                        content TEXT NOT NULL,
                        metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                        embedding vector({VECTOR_DIMENSIONS}) NOT NULL
                    )"""
                )

    def add_documents(self, chunks: list[dict[str, Any]]) -> int:
        """Upsert chunks and embeddings in one transaction; return inserted count."""
        chunks = [chunk for chunk in chunks if isinstance(chunk, dict) and isinstance(chunk.get("content"), str) and chunk["content"].strip()]
        if not chunks:
            return 0
        _validate_chunks(chunks)
        vectors = _embed([chunk["content"] for chunk in chunks])
        from psycopg2.extras import Json

        rows = []
        for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
            chunk_id = str(chunk.get("id") or hashlib.sha256(
                f"{chunk['content']}:{index}".encode("utf-8")
            ).hexdigest())
            vector_literal = "[" + ",".join(str(value) for value in vector) + "]"
            rows.append((chunk_id, chunk["content"], Json(chunk.get("metadata", {})), vector_literal))

        try:
            with self._lock, self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.executemany(
                        """INSERT INTO document_chunks (id, content, metadata, embedding)
                           VALUES (%s, %s, %s, %s::vector)
                           ON CONFLICT (id) DO UPDATE SET
                               content = EXCLUDED.content,
                               metadata = EXCLUDED.metadata,
                               embedding = EXCLUDED.embedding""",
                        rows,
                    )
        except Exception as exc:
            logger.exception("PostgreSQL insert failed; using the process-local empty/live index")
            return _switch_to_fallback().add_documents(chunks)
        return len(rows)

    def search(self, query_text: str, top_k: int = 3) -> list[dict[str, Any]]:
        """Search by pgvector cosine distance and return normalized result records."""
        if top_k <= 0 or not query_text.strip():
            return []
        normalized = re.sub(r"[^a-z\s]", "", query_text.lower()).strip()
        if re.fullmatch(r"(?:hello|hi|hey|good morning|good afternoon|good evening)(?: brok)?", normalized):
            return [{
                "content": "Hello! I'm Brok, your Katalon knowledge assistant. Ask me a question about the indexed documents and I'll help you find an answer.",
                "metadata": {"title": "Brok Assistant", "source": "Brok", "url": ""},
                "score": 1.0,
            }]
        vector = "[" + ",".join(str(value) for value in _embed([query_text])[0]) + "]"
        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """SELECT content, metadata, 1 - (embedding <=> %s::vector) AS score
                           FROM document_chunks
                           ORDER BY embedding <=> %s::vector
                           LIMIT %s""",
                        (vector, vector, int(top_k)),
                    )
                    rows = cursor.fetchall()
        except Exception as exc:
            logger.warning("PostgreSQL search failed; using process-local indexed documents: %s", exc)
            return _switch_to_fallback().search(query_text, top_k)
        return [
            {"content": content, "metadata": metadata if isinstance(metadata, dict) else json.loads(metadata), "score": float(score)}
            for content, metadata, score in rows
        ]


_default_store: PostgresVectorStore | InMemoryVectorStore | None = None
_store_lock = RLock()


def _build_fallback_store() -> InMemoryVectorStore:
    """Create an empty process-local store; only ingestion can add live pages."""
    return InMemoryVectorStore()


def _switch_to_fallback() -> InMemoryVectorStore:
    """Replace an unavailable database with an empty process-local store."""
    global _default_store
    with _store_lock:
        if not isinstance(_default_store, InMemoryVectorStore):
            _default_store = _build_fallback_store()
        return _default_store


def get_vector_store() -> PostgresVectorStore | InMemoryVectorStore:
    """Return the process-wide store, falling back when DATABASE_URL is unset."""
    global _default_store
    with _store_lock:
        if _default_store is None:
            database_url = os.getenv("DATABASE_URL")
            if database_url:
                try:
                    _default_store = PostgresVectorStore(database_url)
                except Exception as exc:
                    logger.warning("PostgreSQL unavailable; using an empty in-memory store: %s", exc)
                    _default_store = _build_fallback_store()
            else:
                logger.info("DATABASE_URL is unset; using empty in-memory vector store")
                _default_store = _build_fallback_store()
        return _default_store
