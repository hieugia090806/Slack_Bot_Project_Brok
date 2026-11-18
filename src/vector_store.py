# SUMMARY: Manages vector storage with a live-document-only in-memory fallback.
"""MemTrust-inspired Layer 3 storage for chunks and provenance metadata.

PostgreSQL is used when ``DATABASE_URL`` is set. Hybrid retrieval is delegated
to ``public.match_documents_hybrid`` with authorized space keys. For local use
without a database URL, an in-memory store and deterministic feature-hash
embeddings keep the RAG path usable without additional services.
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

EMBEDDING_MODEL = "gemini-embedding-001"


def _title_match_boost(query_text: str, title: str) -> float:
    """Give exact or strong title matches a small, backend-independent lift."""
    stop_words = {"a", "an", "and", "are", "for", "in", "is", "of", "the", "to", "what", "who"}
    query_terms = set(re.findall(r"[a-z0-9]+", query_text.lower())) - stop_words
    title_terms = set(re.findall(r"[a-z0-9]+", str(title).lower()))
    if not query_terms or not title_terms:
        return 0.0
    overlap = len(query_terms & title_terms) / len(query_terms)
    if overlap >= 0.3:
        return 0.5
    if overlap >= 0.2:
        return 0.25
    return 0.0


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

    @property
    def document_count(self) -> int:
        with self._lock:
            return len(self._documents)

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

    def sync_space_documents(self, chunks: list[dict[str, Any]], space_key: str) -> int:
        """Replace one space's local snapshot after a complete source fetch."""
        chunks = [chunk for chunk in chunks if isinstance(chunk, dict) and isinstance(chunk.get("content"), str) and chunk["content"].strip()]
        _validate_chunks(chunks)
        vectors = _embed([chunk["content"] for chunk in chunks])
        replacements = {}
        for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
            chunk_id = str(chunk.get("id") or hashlib.sha256(f"{chunk['content']}:{index}".encode("utf-8")).hexdigest())
            replacements[chunk_id] = {"content": chunk["content"], "metadata": dict(chunk.get("metadata", {})), "embedding": vector}
        with self._lock:
            self._documents = {
                chunk_id: document for chunk_id, document in self._documents.items()
                if document["metadata"].get("space_key") != space_key
            }
            self._documents.update(replacements)
        return len(replacements)

    def search(
        self, query_text: str, top_k: int = 7, allowed_spaces: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Return the most cosine-similar chunks with a higher-is-better score."""
        if top_k <= 0 or not query_text.strip():
            return []
        if allowed_spaces is not None and not allowed_spaces:
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
            if allowed_spaces is not None and document["metadata"].get("space_key") not in allowed_spaces:
                continue
            score = sum(a * b for a, b in zip(query_vector, document["embedding"]))
            score += _title_match_boost(query_text, document["metadata"].get("title", ""))
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

    def sync_space_documents(self, chunks: list[dict[str, Any]], space_key: str) -> int:
        """Atomically replace one space's rows with a complete fetched snapshot."""
        chunks = [chunk for chunk in chunks if isinstance(chunk, dict) and isinstance(chunk.get("content"), str) and chunk["content"].strip()]
        _validate_chunks(chunks)
        from psycopg2.extras import Json

        try:
            with self._lock, self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT id, content, embedding::text FROM public.document_chunks WHERE metadata->>'space_key' = %s",
                        (space_key,),
                    )
                    existing = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}

                    identified_chunks = []
                    for index, chunk in enumerate(chunks):
                        chunk_id = str(chunk.get("id") or hashlib.sha256(f"{chunk['content']}:{index}".encode("utf-8")).hexdigest())
                        identified_chunks.append((chunk_id, chunk))

                    changed = [
                        chunk for chunk_id, chunk in identified_chunks
                        if chunk_id not in existing or existing[chunk_id][0] != chunk["content"]
                    ]
                    changed_vectors = iter(_embed([chunk["content"] for chunk in changed]))
                    rows = []
                    active_page_ids = {
                        str(chunk.get("metadata", {}).get("page_id"))
                        for chunk in chunks
                        if chunk.get("metadata", {}).get("page_id") is not None
                    }
                    active_chunk_ids = [chunk_id for chunk_id, _ in identified_chunks]
                    for chunk_id, chunk in identified_chunks:
                        if chunk_id in existing and existing[chunk_id][0] == chunk["content"]:
                            vector_literal = existing[chunk_id][1]
                        else:
                            vector = next(changed_vectors)
                            vector_literal = "[" + ",".join(str(value) for value in vector) + "]"
                        rows.append((chunk_id, chunk["content"], Json(chunk.get("metadata", {})), vector_literal))

                    # The fetched snapshot is complete, so remove stale page IDs
                    # explicitly before replacing the active space snapshot.
                    if active_page_ids:
                        cursor.execute(
                            "DELETE FROM public.document_chunks WHERE metadata->>'space_key' = %s AND (metadata->>'page_id' IS NULL OR metadata->>'page_id' <> ALL(%s))",
                            (space_key, list(active_page_ids)),
                        )
                    else:
                        # A completed empty fetch means all pages in this space
                        # were removed; incomplete fetches are rejected upstream.
                        cursor.execute(
                            "DELETE FROM public.document_chunks WHERE metadata->>'space_key' = %s",
                            (space_key,),
                        )
                    # Prune old chunk IDs for active pages that were re-chunked.
                    if active_chunk_ids:
                        cursor.execute(
                            "DELETE FROM public.document_chunks WHERE metadata->>'space_key' = %s AND id <> ALL(%s)",
                            (space_key, active_chunk_ids),
                        )
                    elif active_page_ids:
                        cursor.execute(
                            "DELETE FROM public.document_chunks WHERE metadata->>'space_key' = %s",
                            (space_key,),
                        )
                    if rows:
                        cursor.executemany(
                            """INSERT INTO public.document_chunks (id, content, metadata, embedding)
                               VALUES (%s, %s, %s, %s::vector)
                               ON CONFLICT (id) DO UPDATE SET
                                   content = EXCLUDED.content,
                                   metadata = EXCLUDED.metadata,
                                   embedding = EXCLUDED.embedding""",
                            rows,
                        )
        except Exception:
            logger.exception("PostgreSQL space sync failed; prior snapshot retained")
            raise
        return len(rows)

    def search(
        self, query_text: str, top_k: int = 7, allowed_spaces: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Search through the hybrid RPC, with inline SQL fallback if absent."""
        if top_k <= 0 or not query_text.strip():
            return []
        spaces = list(allowed_spaces or [])
        if not spaces:
            return []
        logger.info("Vector search received query=%r top_k=%d allowed_spaces=%s", query_text, top_k, spaces)
        normalized = re.sub(r"[^a-z\s]", "", query_text.lower()).strip()
        if re.fullmatch(r"(?:hello|hi|hey|good morning|good afternoon|good evening)(?: brok)?", normalized):
            return [{
                "content": "Hello! I'm Brok, your Katalon knowledge assistant. Ask me a question about the indexed documents and I'll help you find an answer.",
                "metadata": {"title": "Brok Assistant", "source": "Brok", "url": ""},
                "score": 1.0,
            }]
        vector = _embed([query_text])[0]
        logger.info("Query embedding generated dimension=%d", len(vector))
        if len(vector) != VECTOR_DIMENSIONS:
            logger.error(
                "Query embedding dimension mismatch: expected=%d actual=%d",
                VECTOR_DIMENSIONS, len(vector),
            )
            return self._local_search(query_text, top_k, spaces)
        vector_literal = "[" + ",".join(str(value) for value in vector) + "]"
        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """SELECT content, metadata, score
                           FROM public.match_documents_hybrid(
                               %s::vector, %s::text, %s::integer, %s::text[]
                           )""",
                        (vector_literal, query_text, int(top_k), spaces),
                    )
                    rows = cursor.fetchall()
                    logger.info("Hybrid RPC returned %d rows", len(rows))
        except Exception as exc:
            sqlstate = getattr(exc, "pgcode", None)
            missing_rpc = (
                sqlstate == "42883"
                or ("match_documents_hybrid" in str(exc) and "does not exist" in str(exc))
            )
            if not missing_rpc:
                logger.warning("PostgreSQL hybrid RPC search failed: %s", exc)
                return self._local_search(query_text, top_k, spaces)
            logger.warning("Hybrid RPC is missing; using inline hybrid SQL against public.document_chunks: %s", exc)
            try:
                with self._connect() as connection:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """SELECT content, metadata,
                                      (1 - (embedding <=> %s::vector)) AS score
                               FROM public.document_chunks
                               WHERE metadata->>'space_key' = ANY(%s::text[])
                               ORDER BY
                                 (CASE WHEN to_tsvector('english', coalesce(metadata->>'title', ''))
                                            @@ plainto_tsquery('english', %s)
                                       THEN 0.5 ELSE 0.0 END
                                  + 2.0 * ts_rank_cd(
                                     to_tsvector('english', coalesce(metadata->>'title', '')),
                                     plainto_tsquery('english', %s)
                                  ) + 0.25 * ts_rank_cd(
                                     to_tsvector('english', content),
                                     plainto_tsquery('english', %s)
                                  )) DESC,
                                 embedding <=> %s::vector
                               LIMIT %s""",
                            (vector_literal, spaces, query_text, query_text, query_text, vector_literal, int(top_k)),
                        )
                        rows = cursor.fetchall()
                        logger.info("Inline hybrid SQL returned %d rows", len(rows))
            except Exception as fallback_exc:
                logger.warning("PostgreSQL inline hybrid SQL failed; using process-local indexed documents: %s", fallback_exc)
                return self._local_search(query_text, top_k, spaces)
        return [
            {"content": content, "metadata": metadata if isinstance(metadata, dict) else json.loads(metadata), "score": float(score)}
            for content, metadata, score in rows
        ]

    @staticmethod
    def _local_search(query_text: str, top_k: int, spaces: list[str]) -> list[dict[str, Any]]:
        """Search the populated process-local fallback without replacing it."""
        fallback = _switch_to_fallback()
        logger.warning("Using process-local fallback; indexed document count=%d", fallback.document_count)
        results = fallback.search(query_text, top_k, spaces)
        logger.info("Process-local vector search returned %d rows", len(results))
        return results


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
