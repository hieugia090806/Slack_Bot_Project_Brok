# SUMMARY: Scans Confluence REST API for knowledge files, parses them into searchable chunks, and populates the vector store.
"""Load Confluence knowledge files and add their chunks to the vector store."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any
import requests
from requests.auth import HTTPBasicAuth

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from src.vector_store import InMemoryVectorStore, PostgresVectorStore, get_vector_store
    from src.embedding import chunk_text
    from src.sanitization import sanitize_and_mask
except ModuleNotFoundError:
    from vector_store import InMemoryVectorStore, PostgresVectorStore, get_vector_store
    from embedding import chunk_text
    from sanitization import sanitize_and_mask


def fetch_confluence_pages() -> list[dict[str, Any]]:
    """Fetch pages from the Confluence REST API v2 using environment secrets."""
    domain = os.environ.get("CONFLUENCE_URL")
    email = os.environ.get("CONFLUENCE_USERNAME")
    api_token = os.environ.get("CONFLUENCE_API_TOKEN")

    if not domain or not email or not api_token:
        print("Confluence credentials not fully set. Skipping remote Confluence ingestion.")
        return []

    base_url = domain.rstrip("/")
    url = f"{base_url}/api/v2/pages?body-format=storage"
    auth = HTTPBasicAuth(email, api_token)
    headers = {"Accept": "application/json"}

    pages = []
    try:
        response = requests.get(url, auth=auth, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            for item in data.get("results", []):
                title = item.get("title")
                page_id = item.get("id")
                body = item.get("body", {}).get("storage", {}).get("value", "")
                
                cleaned_body = sanitize_and_mask(body)
                source_url = f"{base_url}/spaces/COS40005/pages/{page_id}"

                pages.append({
                    "text": cleaned_body,
                    "metadata": {
                        "page_id": str(page_id),
                        "title": title,
                        "url": source_url,
                        "source": "confluence"
                    }
                })
            print(f"Successfully fetched {len(pages)} pages from Confluence.")
        else:
            print(f"Failed to fetch Confluence pages: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error connecting to Confluence API: {e}")

    return pages


def split_text(text: str, chunk_size: int = 512, chunk_overlap: int = 64) -> list[str]:
    return chunk_text(text, chunk_size=chunk_size, overlap=chunk_overlap)


def chunk_documents(
    pages: list[dict[str, Any]], chunk_size: int = 512, chunk_overlap: int = 64
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for page in pages:
        metadata = dict(page.get("metadata", {}))
        page_id = str(metadata.get("page_id") or "document")
        for index, content in enumerate(split_text(page.get("text", ""), chunk_size, chunk_overlap)):
            chunk_id = hashlib.sha256(f"{page_id}:{index}".encode("utf-8")).hexdigest()
            chunks.append(
                {"id": chunk_id, "content": content, "metadata": {**metadata, "chunk_index": index}}
            )
    return chunks


def ingest_local_docs(
    store: PostgresVectorStore | InMemoryVectorStore | None = None,
) -> int:
    """Read, chunk, and add live Confluence documents; return chunks added."""
    all_pages = fetch_confluence_pages()
    chunks = chunk_documents(all_pages)
    if not chunks:
        return 0
    return (store or get_vector_store()).add_documents(chunks)


if __name__ == "__main__":
    print("Loading documents from Confluence workspace...")
    added = ingest_local_docs()
    print(f"Successfully added {added} chunks to the vector store.")