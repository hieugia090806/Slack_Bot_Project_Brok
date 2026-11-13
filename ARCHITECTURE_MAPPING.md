# Brok architecture mapping

This document maps the current implementation to the requested MemTrust,
Stäbler et al., and AIRA (Appendix A, Fig. A1) concepts. “Inspired by” indicates
an application-level correspondence, not a claim of reproducing a research
system or security property.

| Layer / reference | Modules | Current implementation | Alignment limits / gaps |
| --- | --- | --- | --- |
| **Layer 1 — MemTrust ingestion and sanitization** | `src/ingestion.py`, `src/sanitization.py` | Ingestion fetches Confluence REST v2 pages from `COS40005`, follows cursor pagination, sanitizes storage bodies, masks common email, phone, and credential patterns, and attaches page ID, title, URL, space, and security metadata. | RA-TLS is not implemented. HTML and common Confluence macro cleanup are best-effort; PII masking is pattern-based and is not comprehensive. |
| **Layer 2 — Stäbler et al. chunking and embeddings** | `src/embedding.py` | Sentence-boundary chunking targets approximately 512 tokens with sentence-level overlap up to approximately 200 tokens. Gemini `gemini-embedding-001` dense embeddings are used when configured; deterministic feature-hash embeddings preserve zero-config local operation. | Token counts are approximate, not a tokenizer-backed `SentenceSplitter`. BGE-M3 is not implemented. A sparse term-vector helper exists but is not integrated into store ranking; storage/search are currently dense-only. |
| **Layer 3 — MemTrust storage and access control** | `src/vector_store.py`, `src/policy.py` | PostgreSQL with pgvector stores dense vectors and JSONB provenance metadata and searches by cosine distance. When unavailable or unset, an empty process-local in-memory store with local embeddings is used. RAG applies role clearance checks against `public`, `internal`, `confidential`, and `restricted` classifications before answer generation. | No sealed-segment design or OPA service/policy stub is present. The in-memory fallback is process-local and non-persistent. RBAC role mappings are application configuration, not an enterprise identity provider. |
| **Layer 4 — AIRA query processing and citations** | `src/rag.py`, `src/slack_app.py`, `src/formatter.py`, `src/main.py` | Slack mention/DM events enter the threaded response path. Queries are sanitized and embedded for dense top-N retrieval; RBAC filters retrieved chunks before grounded Gemini generation. Retrieved metadata supplies page title, space, and URL citations rendered in Slack Block Kit. FastAPI serves health and Slack event endpoints; ingestion runs in a background thread during lifespan startup. | Citation rendering is source-link attribution, not a complete APA bibliographic citation (author/date fields are not currently stored). LLM generation falls back to a local extractive response when Gemini is unavailable. Retrieval is top-N dense cosine, without integrated sparse/dense fusion. |

## Startup and local fallback behavior

The FastAPI lifespan schedules Confluence ingestion with `asyncio.to_thread`,
so the event loop can start serving health checks while indexing proceeds.
Missing external services do not seed mock files: the no-database fallback is
empty until live ingestion adds content. Local embeddings remain available when
Gemini credentials or the SDK are absent.

## Verification scope

The mapping describes code behavior, not a formal security certification or a
claim that the cited papers' full algorithms and guarantees are reproduced.
