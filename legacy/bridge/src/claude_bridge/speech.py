"""Aus Claudes Antwort einen kurzen, vorlesbaren Text machen.

Claude wird per System-Prompt gebeten, die Antwort mit einer Zeile
``SPRECHTEXT: ...`` zu beenden (bewusst ohne ``<``/``>``, siehe runner.py).
Fehlt sie, wird die ganze Antwort von Markdown, Code und URLs befreit.
In jedem Fall wird auf eine Satzgrenze gekuerzt.
"""

from __future__ import annotations

import re

SPOKEN_MARKER_RE = re.compile(r"^[\s>*_#]*SPRECHTEXT[*_]*\s*:[*_]*\s*", re.IGNORECASE | re.MULTILINE)
_FENCED_CODE_RE = re.compile(r"```.*?(```|$)", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`\n]*)`")
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_URL_RE = re.compile(r"https?://\S+")
_TABLE_LINE_RE = re.compile(r"^\s*\|.*\|\s*$", re.MULTILINE)
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s*", re.MULTILINE)
_LIST_MARK_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+", re.MULTILINE)
_EMPHASIS_RE = re.compile(r"(\*\*|\*|~~)(?=\S)(.+?)(?<=\S)\1")
_UNDERSCORE_EMPHASIS_RE = re.compile(r"(?<!\w)(__|_)(?=\S)(.+?)(?<=\S)\1(?!\w)")
_HTML_TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")
_WHITESPACE_RE = re.compile(r"\s+")
_SENTENCE_END_RE = re.compile(r"[.!?…](?=\s|$)")

CODE_PLACEHOLDER = " (Code siehe PC) "
TRUNCATION_SUFFIX = " Den Rest findest du auf dem PC."
EMPTY_FALLBACK = "Claude ist fertig, hat aber keinen vorlesbaren Text geliefert. Details stehen auf dem PC."


def strip_markdown(text: str) -> str:
    """Markdown, Code, Tabellen und URLs entfernen, Whitespace normalisieren."""
    text = _FENCED_CODE_RE.sub(CODE_PLACEHOLDER, text)
    text = _TABLE_LINE_RE.sub(" ", text)
    text = _MD_LINK_RE.sub(r"\1", text)
    text = _URL_RE.sub("(Link siehe PC)", text)
    text = _INLINE_CODE_RE.sub(r"\1", text)
    text = _HEADING_RE.sub("", text)
    text = _LIST_MARK_RE.sub("", text)
    text = _EMPHASIS_RE.sub(r"\2", text)
    text = _UNDERSCORE_EMPHASIS_RE.sub(r"\2", text)
    text = _HTML_TAG_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    # Mehrere Platzhalter hintereinander zusammenfassen.
    placeholder = CODE_PLACEHOLDER.strip()
    while f"{placeholder} {placeholder}" in text:
        text = text.replace(f"{placeholder} {placeholder}", placeholder)
    return text


def truncate_at_sentence(text: str, max_chars: int) -> str:
    """Auf hoechstens ``max_chars`` kuerzen, moeglichst an einem Satzende."""
    if len(text) <= max_chars:
        return text
    budget = max(0, max_chars - len(TRUNCATION_SUFFIX))
    head = text[:budget]
    ends = [m.end() for m in _SENTENCE_END_RE.finditer(head)]
    if ends and ends[-1] >= budget // 3:
        head = head[: ends[-1]]
    else:
        head = head.rsplit(" ", 1)[0].rstrip(",;:") + " …"
    return head.strip() + TRUNCATION_SUFFIX


def make_spoken_text(result: str, max_chars: int) -> str:
    """Vorlesetext aus Claudes Ergebnis erzeugen."""
    markers = list(SPOKEN_MARKER_RE.finditer(result))
    source = result[markers[-1].end() :] if markers else result
    spoken = strip_markdown(source)
    if not spoken:
        return EMPTY_FALLBACK
    return truncate_at_sentence(spoken, max_chars)
