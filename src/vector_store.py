import hashlib
import json
import math
import os
import re
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any

VECTOR_DIMENSIONS = 384
EMBEDDING_MODEL = "text-embedding-3-small"


def _local_embedding(text: str) -> list[float]:
    vector = [0.0] * VECTOR_DIMENSIONS
    terms = re.findall(r"[\w'-]+", text.lower())
    features = terms + [f"{left}_{right}" for left, right in zip(terms, terms[1:])]
    for feature in features:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "little") % VECTOR_DIMENSIONS
        vector[index] += 1.0 if digest[4] & 1 else -1.0
    magnitude = math.sqrt(sum(value * value for value in vector))
    return [value / magnitude for value in vector] if magnitude else vector


def _embeddings(texts: list[str]) -> list[list[float]]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return [_local_embedding(text) for text in texts]

    from openai import OpenAI

    response = OpenAI(api_key=api_key).embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
        dimensions=VECTOR_DIMENSIONS,
    )
    return [item.embedding for item in response.data]


class SQLiteVectorStore:
    """Small persistent vector-store mock for local development and tests."""

    def __init__(self, path: str | Path | None = None):
        configured_path = path or os.getenv("VECTOR_DB_PATH", "data/brok_vectors.sqlite3")
        self.path = str(configured_path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.lock = RLock()
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                metadata TEXT NOT NULL,
                embedding TEXT NOT NULL
            )
            """
        )
        self.connection.commit()

    def upsert(self, chunks: list[dict[str, Any]]) -> int:
        if not chunks:
            return 0
        vectors = _embeddings([chunk["content"] for chunk in chunks])
        rows = []
        for chunk, vector in zip(chunks, vectors):
            rows.append(
                (
                    chunk["id"],
                    chunk["content"],
                    json.dumps(chunk["metadata"], ensure_ascii=False),
                    json.dumps(vector),
                )
            )
        with self.lock, self.connection:
            self.connection.executemany(
                """
                INSERT INTO documents (id, content, metadata, embedding)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    content = excluded.content,
                    metadata = excluded.metadata,
                    embedding = excluded.embedding
                """,
                rows,
            )
        return len(rows)

    def search(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        query_vector = _embeddings([query])[0]
        with self.lock, self.connection:
            rows = self.connection.execute(
                "SELECT content, metadata, embedding FROM documents"
            ).fetchall()

        matches = []
        for content, metadata_json, embedding_json in rows:
            embedding = json.loads(embedding_json)
            score = sum(left * right for left, right in zip(query_vector, embedding))
            matches.append(
                {
                    "content": content,
                    "metadata": json.loads(metadata_json),
                    "score": score,
                }
            )
        matches.sort(key=lambda result: result["score"], reverse=True)
        return matches[:top_k]


_default_store: SQLiteVectorStore | None = None


def get_vector_store() -> SQLiteVectorStore:
    global _default_store
    if _default_store is None:
        _default_store = SQLiteVectorStore()
    return _default_store