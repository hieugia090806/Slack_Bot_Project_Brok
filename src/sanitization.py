# SUMMARY: Layer 1 Sanitization & PII Masking engine with local fallback.
"""Clean user and document text before it enters the retrieval pipeline."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser


class _TextExtractor(HTMLParser):
    """Collect visible HTML text while discarding script and style contents."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._hidden_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self._hidden_depth += 1
        elif tag.lower() in {"p", "div", "br", "li", "tr", "h1", "h2", "h3"} and not self._hidden_depth:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"} and self._hidden_depth:
            self._hidden_depth -= 1
        elif tag.lower() in {"p", "div", "br", "li", "tr", "h1", "h2", "h3"} and not self._hidden_depth:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._hidden_depth:
            self.parts.append(data)


def sanitize_and_mask(text: str) -> str:
    """Remove HTML and common page boilerplate, then redact common PII/secrets.

    The operation uses only the Python standard library. If malformed input
    causes a cleaning error, the original text is returned so ingestion or a
    Slack request can continue safely.
    """
    if not isinstance(text, str):
        return ""
    try:
        parser = _TextExtractor()
        parser.feed(text)
        clean = html.unescape(" ".join(parser.parts))
        clean = re.sub(r"(?im)^\s*(?:skip to content|cookie (?:settings|preferences)|accept all cookies|privacy policy|terms of use)\s*$", "", clean)
        clean = re.sub(r"[ \t]+", " ", clean)
        clean = re.sub(r"\n\s*\n\s*\n+", "\n\n", clean).strip()

        # Mask credentials before general numeric patterns.
        clean = re.sub(r"\b(?:xox[baprs]-[A-Za-z0-9-]{8,}|sk-[A-Za-z0-9_-]{12,}|Bearer\s+[A-Za-z0-9._~-]+)\b", "[REDACTED_SECRET]", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[REDACTED_EMAIL]", clean, flags=re.IGNORECASE)
        clean = re.sub(r"(?<!\w)(?:\+?\d[\d ().-]{7,}\d)(?!\w)", "[REDACTED_PHONE]", clean)
        return clean
    except Exception:
        return text
