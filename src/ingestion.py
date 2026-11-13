"""Fetch and index live pages from the COS40005 Confluence space."""

from __future__ import annotations

import hashlib
import os
from typing import Any
from urllib.parse import urljoin

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

SPACE_KEY = "COS40005"
TIMEOUT_SECONDS = 20


def _credentials() -> tuple[str, str, str] | None:
    url = os.environ.get("CONFLUENCE_URL", "").strip().rstrip("/")
    # CONFLUENCE_EMAIL is the key used by this project's .env; keep the
    # username alias for deployments configured with the newer example file.
    username = (
        os.environ.get("CONFLUENCE_EMAIL", "").strip()
        or os.environ.get("CONFLUENCE_USERNAME", "").strip()
    )
    token = os.environ.get("CONFLUENCE_API_TOKEN", "").strip()
    if not all((url, username, token)):
        print("WARNING: Missing CONFLUENCE_URL, CONFLUENCE_EMAIL (or CONFLUENCE_USERNAME), or CONFLUENCE_API_TOKEN.")
        return None
    return url, username, token


def _get_space_id(session: requests.Session, base_url: str, auth: HTTPBasicAuth) -> tuple[str | None, int]:
    response = session.get(
        f"{base_url}/api/v2/spaces", params={"keys": SPACE_KEY, "limit": 1},
        auth=auth, headers={"Accept": "application/json"}, timeout=TIMEOUT_SECONDS,
    )
    if response.status_code != 200:
        if response.status_code in (401, 403):
            print(f"WARNING: Confluence returned {response.status_code}; check API credentials and space permissions.")
        else:
            print(f"Confluence space lookup failed: HTTP {response.status_code} - {response.text}")
        return None, response.status_code
    spaces = response.json().get("results", [])
    return (str(spaces[0]["id"]) if spaces and spaces[0].get("id") else None), response.status_code


def _fetch_pages(session: requests.Session, base_url: str, auth: HTTPBasicAuth) -> tuple[list[dict[str, Any]], int | None]:
    space_id, space_status = _get_space_id(session, base_url, auth)
    if not space_id:
        if space_status == 200:
            print(f"WARNING: Confluence space {SPACE_KEY} was not found or is not visible to this account.")
        return [], space_status

    url = f"{base_url}/api/v2/pages"
    params: dict[str, Any] | None = {"space-id": space_id, "body-format": "storage", "limit": 100}
    pages: list[dict[str, Any]] = []
    status_code: int | None = None
    while url:
        response = session.get(
            url, params=params, auth=auth, headers={"Accept": "application/json"},
            timeout=TIMEOUT_SECONDS,
        )
        status_code = response.status_code
        if status_code != 200:
            if status_code in (401, 403):
                print(f"WARNING: Confluence returned {status_code}; check API credentials and space permissions.")
            else:
                print(f"Confluence page fetch failed: HTTP {status_code} - {response.text}")
            return pages, status_code

        data = response.json()
        for item in data.get("results", []):
            page_id = item.get("id")
            if not page_id:
                continue
            body = item.get("body", {}).get("storage", {}).get("value", "")
            text = sanitize_and_mask(body)
            pages.append({
                "text": text,
                "metadata": {
                    "page_id": str(page_id),
                    "title": item.get("title") or "Untitled",
                    "url": f"{base_url}/spaces/{SPACE_KEY}/pages/{page_id}",
                    "source": "confluence",
                    "space_key": SPACE_KEY,
                    "security_level": "internal",
                },
            })
        next_url = data.get("_links", {}).get("next")
        if not next_url:
            links = response.links
            next_url = links.get("next", {}).get("url")
        url = urljoin(base_url + "/", next_url) if next_url else ""
        params = None  # Cursor is encoded in the next URL.
    return pages, status_code


def fetch_confluence_pages() -> list[dict[str, Any]]:
    """Fetch every page in COS40005 through the Confluence REST API v2."""
    credentials = _credentials()
    if not credentials:
        return []
    base_url, username, token = credentials
    try:
        pages, _ = _fetch_pages(requests.Session(), base_url, HTTPBasicAuth(username, token))
        print(f"Successfully discovered {len(pages)} pages in Confluence space {SPACE_KEY}.")
        return pages
    except (requests.RequestException, ValueError, KeyError) as exc:
        print(f"Error connecting to Confluence API: {exc}")
        return []


def test_confluence_connection() -> dict[str, Any]:
    """Print a diagnostic status and page count for the configured live space."""
    credentials = _credentials()
    if not credentials:
        print("Confluence diagnostic: credentials missing; cannot connect.")
        return {"status_code": None, "page_count": 0, "ok": False}
    base_url, username, token = credentials
    try:
        pages, status_code = _fetch_pages(requests.Session(), base_url, HTTPBasicAuth(username, token))
    except (requests.RequestException, ValueError, KeyError) as exc:
        print(f"Confluence diagnostic connection error: {exc}")
        return {"status_code": None, "page_count": 0, "ok": False}
    print(f"Confluence HTTP status: {status_code}")
    print(f"Pages discovered in {SPACE_KEY}: {len(pages)}")
    if status_code in (401, 403):
        print(f"WARNING: HTTP {status_code} Unauthorized/Forbidden. Check credentials and access to {SPACE_KEY}.")
    return {"status_code": status_code, "page_count": len(pages), "ok": status_code == 200}


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
            chunks.append({"id": chunk_id, "content": content, "metadata": {**metadata, "chunk_index": index}})
    return chunks


def ingest_local_docs(
    store: PostgresVectorStore | InMemoryVectorStore | None = None,
) -> int:
    """Fetch only live COS40005 pages, then add non-empty chunks to the store."""
    chunks = chunk_documents(fetch_confluence_pages())
    if not chunks:
        return 0
    return (store or get_vector_store()).add_documents(chunks)


if __name__ == "__main__":
    import sys

    if "--check" in sys.argv:
        test_confluence_connection()
    else:
        print(f"Loading documents exclusively from Confluence space {SPACE_KEY}...")
        print(f"Successfully added {ingest_local_docs()} chunks to the vector store.")
