import logging
import os
from typing import Any

from src.policy import check_access, get_user_role, ROLE_CLEARANCE
from src.sanitization import sanitize_and_mask
from src.vector_store import get_vector_store

logger = logging.getLogger(__name__)


def retrieve(query: str, top_k: int = 3, user_email: str = "") -> list[dict[str, Any]]:
    """Sanitize a query, search the store, then apply the policy decision seam."""
    clean_query = sanitize_and_mask(query)
    matches = get_vector_store().search(clean_query, top_k=top_k)
    logger.info("Retrieval query=%r top_n=%d candidates=%d", clean_query, top_k, len(matches))
    allowed = []
    for match in matches:
        permitted = check_access(user_email, match.get("metadata", {}))
        logger.info("RBAC user=%s role=%s clearance=%d chunk=%s decision=%s", user_email, get_user_role(user_email), ROLE_CLEARANCE.get(get_user_role(user_email), 1), match.get("metadata", {}).get("page_id"), "allowed" if permitted else "filtered")
        if permitted:
            allowed.append(match)
    return allowed


def _source_label(metadata: dict[str, Any]) -> str:
    title = metadata.get("title", "Untitled")
    url = metadata.get("url") or metadata.get("source", "")
    if url.startswith(("https://", "http://")):
        return f"<{url}|{title}>"
    return f"{title} ({url})" if url else title


def _local_answer(matches: list[dict[str, Any]]) -> str:
    """Synthesize a concise response rather than returning a chopped excerpt."""
    points = []
    for match in matches[:3]:
        text = " ".join(match["content"].split())
        if text and text not in points:
            points.append(text)
    if not points:
        return "I couldn't find relevant information in the indexed pages."
    return "Here's what I found:\n" + "\n".join(f"• {point}" for point in points)


def _gemini_answer(query: str, matches: list[dict[str, Any]]) -> str:
    from google import genai
    from google.genai import types

    context = "\n\n".join(
        f"[{index}] {match['metadata'].get('title', 'Untitled')} "
        f"({match['metadata'].get('url', '')})\n{match['content']}"
        for index, match in enumerate(matches, start=1)
    )
    client = genai.Client(api_key=os.environ["SLACK_API_KEY"])
    logger.info("Gemini answer generation active with model gemini-2.5-flash")
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=f"Question: {query}\n\nAuthorized Confluence context:\n{context}",
        config=types.GenerateContentConfig(
            temperature=0.1,
            system_instruction=(
                "Answer only using facts explicitly stated in the provided Confluence context. "
                "If the answer is absent, state that clearly without guessing. Write a clean, "
                "conversational summary and use bullets where useful. Do not output citations."
            ),
        ),
    )
    return response.text or "I could not generate an answer."


def answer_question(query: str, user_email: str) -> dict[str, Any]:
    clean_query = sanitize_and_mask(query)
    if not clean_query.strip():
        return {"answer": "Please include a question so I can search the knowledge base.", "sources": []}

    matches = retrieve(clean_query, top_k=3, user_email=user_email)
    if not matches:
        return {"answer": "I could not find any indexed documents to answer that question.", "sources": []}

    if os.getenv("SLACK_API_KEY"):
        try:
            answer = _gemini_answer(clean_query, matches)
        except Exception:
            logger.exception("Gemini answer generation failed; returning safe extractive fallback")
            answer = _local_answer(matches)
    else:
        logger.info("SLACK_API_KEY missing; Gemini answer generation disabled, using safe extractive fallback")
        answer = _local_answer(matches)

    sources = []
    seen = set()
    for match in matches:
        metadata = match["metadata"]
        if metadata.get("title") == "Brok Assistant":
            continue
        key = metadata.get("page_id") or metadata.get("source")
        if key not in seen:
            seen.add(key)
            title = metadata.get("title", "Untitled")
            url = metadata.get("url", "")
            space = metadata.get("space_key", "COS40005")
            sources.append({"title": title, "url": url, "space": space})
    logger.info("Answer generated query=%r retrieved=%d citations=%s", clean_query, len(matches), [s["url"] for s in sources])
    return {"answer": answer, "sources": sources}
