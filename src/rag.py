import logging
import os
from typing import Any

from src.vector_store import get_vector_store

logger = logging.getLogger(__name__)


def retrieve(query: str, top_k: int = 3) -> list[dict[str, Any]]:
    return get_vector_store().search(query, top_k=top_k)


def _source_label(metadata: dict[str, Any]) -> str:
    title = metadata.get("title", "Untitled")
    url = metadata.get("url") or metadata.get("source", "")
    if url.startswith(("https://", "http://")):
        return f"<{url}|{title}>"
    return f"{title} ({url})" if url else title


def _local_answer(matches: list[dict[str, Any]]) -> str:
    excerpt = matches[0]["content"].strip()
    title = matches[0]["metadata"].get("title", "Untitled")
    return (
        f"From the indexed documents, the relevant information is:\n> {excerpt}\n\n"
        f"({title}, n.d.)"
    )


def _openai_answer(query: str, matches: list[dict[str, Any]]) -> str:
    from openai import OpenAI

    context = "\n\n".join(
        f"[{index}] {match['metadata'].get('title', 'Untitled')} "
        f"({match['metadata'].get('url', '')})\n{match['content']}"
        for index, match in enumerate(matches, start=1)
    )
    response = OpenAI().chat.completions.create(
        model=os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    "Answer strictly from the supplied context. If it does not contain "
                    "the answer, say so plainly. Cite claims in APA-style using the "
                    "document title and n.d. when no publication date is available. "
                    "Do not invent sources or facts."
                ),
            },
            {"role": "user", "content": f"Question: {query}\n\nContext:\n{context}"},
        ],
    )
    return response.choices[0].message.content or "I could not generate an answer."


def answer_question(query: str, user_email: str) -> str:
    del user_email  # The prototype does not apply per-user document permissions.
    if not query.strip():
        return "Please include a question so I can search the knowledge base."

    matches = retrieve(query, top_k=3)
    if not matches:
        return "I could not find any indexed documents to answer that question."

    if os.getenv("OPENAI_API_KEY"):
        try:
            answer = _openai_answer(query, matches)
        except Exception:
            logger.exception("OpenAI answer generation failed; returning retrieved text")
            answer = _local_answer(matches)
    else:
        answer = _local_answer(matches)

    sources = []
    seen = set()
    for match in matches:
        metadata = match["metadata"]
        key = metadata.get("page_id") or metadata.get("source")
        if key not in seen:
            seen.add(key)
            sources.append(_source_label(metadata))
    if sources:
        answer += "\n\nSources: " + "; ".join(sources)
    return answer