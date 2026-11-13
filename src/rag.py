"""AIRA Layer 4 query, authorized retrieval, grounded generation, and citations."""

import logging
import os
import time
from typing import Any

from src.policy import check_access, get_user_role, ROLE_CLEARANCE
from src.sanitization import sanitize_and_mask
from src.vector_store import get_vector_store

logger = logging.getLogger(__name__)
GEMINI_CHAT_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.8-flash",
    "gemma-4-27b-it",
]


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

    api_key = os.getenv("SLACK_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("Gemini answer generation unavailable: set SLACK_API_KEY or GEMINI_API_KEY")
        raise RuntimeError("Gemini API key is missing")

    context = "\n\n".join(
        f"[{index}] {match['metadata'].get('title', 'Untitled')} "
        f"({match['metadata'].get('url', '')})\n{match['content']}"
        for index, match in enumerate(matches, start=1)
    )
    client = genai.Client(api_key=api_key)
    override_model = os.getenv("GEMINI_CHAT_MODEL", "").strip()
    models = ([override_model] if override_model else []) + [
        model for model in GEMINI_CHAT_MODELS if model != override_model
    ]
    failures: list[str] = []
    for model in models:
        try:
            response = client.models.generate_content(
                model=model,
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
            if response.text:
                logger.info("✅ SUCCESS: Gemini answer generated using model: %s", model)
                return response.text
            raise RuntimeError("Gemini returned an empty response")
        except Exception as exc:
            status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
            message = f"{model}: {type(exc).__name__} status={status} {exc}"
            failures.append(message)
            if status in (404, 503, "404", "503"):
                logger.warning("Gemini model %s unavailable (status %s); trying next fallback", model, status)
                if status in (503, "503"):
                    time.sleep(1.5)
                continue
            if status in (429, "429"):
                logger.warning("Gemini model %s rate limited (429); trying next fallback", model)
                continue
            logger.warning("Gemini model %s failed; trying next fallback: %s", model, message)
    logger.error("All Gemini answer models failed: %s", " | ".join(failures))
    raise RuntimeError("All configured Gemini answer models failed")


def check_gemini_connectivity() -> dict[str, str]:
    """Ping each configured answer model and report connectivity without exposing the key."""
    api_key = os.getenv("SLACK_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("Gemini connectivity check failed: SLACK_API_KEY and GEMINI_API_KEY are unset")
        return {model: "NO_API_KEY" for model in GEMINI_CHAT_MODELS}
    try:
        from google import genai
    except ImportError:
        logger.error("Gemini connectivity check failed: google-genai is not installed")
        return {model: "SDK_MISSING" for model in GEMINI_CHAT_MODELS}
    client = genai.Client(api_key=api_key)
    results: dict[str, str] = {}
    for model in GEMINI_CHAT_MODELS:
        try:
            response = client.models.generate_content(model=model, contents="Reply only: OK")
            results[model] = "CONNECTED" if response.text else "EMPTY_RESPONSE"
            logger.info("Gemini connectivity: model=%s status=%s", model, results[model])
        except Exception as exc:
            status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
            results[model] = f"ERROR status={status} {type(exc).__name__}"
            logger.warning("Gemini connectivity: model=%s status=%s error=%s", model, status, exc)
    return results


def answer_question(query: str, user_email: str) -> dict[str, Any]:
    clean_query = sanitize_and_mask(query)
    if not clean_query.strip():
        return {"answer": "Please include a question so I can search the knowledge base.", "sources": []}

    matches = retrieve(clean_query, top_k=3, user_email=user_email)
    if not matches:
        return {"answer": "I could not find any indexed documents to answer that question.", "sources": []}

    if os.getenv("SLACK_API_KEY") or os.getenv("GEMINI_API_KEY"):
        try:
            answer = _gemini_answer(clean_query, matches)
        except Exception:
            logger.exception("Gemini answer generation failed; returning safe extractive fallback")
            answer = _local_answer(matches)
    else:
        logger.warning("Neither SLACK_API_KEY nor GEMINI_API_KEY is set; using safe extractive fallback")
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


if __name__ == "__main__" and "--check" in os.sys.argv:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    logging.basicConfig(level=logging.INFO)
    outcomes = check_gemini_connectivity()
    for model_name, outcome in outcomes.items():
        print(f"{model_name}: {outcome}")
