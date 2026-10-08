"""Aktivierungswort "Claude" erkennen und den Auftrag abtrennen.

Die Spracherkennung schreibt "Claude" auf Deutsch nicht immer gleich (Cloud, Klod, Clot ...).
Deshalb wird die erste(n) Woerter tolerant verglichen. Optional davor: hey, hallo, ok(ay), hi.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum

WAKE_VARIANTS = frozenset(
    {
        "claude", "claud", "clod", "clode", "klod", "klode", "klaude", "klaud", "claudi",
        "cloud", "clowd", "kloud", "klout", "clot", "klot", "glod", "glaude",
    }
)  # fmt: skip
GREETINGS = frozenset({"hey", "hei", "hallo", "hi", "ok", "okay", "oh", "he", "ey", "na"})
_WORD_RE = re.compile(r"[\w']+", re.UNICODE)
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")


class Wake(Enum):
    """Ergebnis der Pruefung."""

    NONE = "none"  # kein Aktivierungswort -> ignorieren
    WAKE_ONLY = "wake_only"  # nur "Claude" -> auf den naechsten Satz warten
    COMMAND = "command"  # "Claude, <Auftrag>"


@dataclass(frozen=True)
class WakeResult:
    """Erkanntes Aktivierungswort und der Rest des Satzes."""

    kind: Wake
    command: str = ""


def clean_text(text: str) -> str:
    """Steuerzeichen entfernen, Leerraum normalisieren (Texte landen im Terminal)."""
    return " ".join(_CONTROL_RE.sub(" ", text).split())


def _normalize(word: str) -> str:
    decomposed = unicodedata.normalize("NFKD", word.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def parse_wake(text: str) -> WakeResult:
    """Pruefen, ob ``text`` mit dem Aktivierungswort beginnt."""
    text = clean_text(text)
    words = list(_WORD_RE.finditer(text))
    index = 0
    if words and _normalize(words[0].group()) in GREETINGS:
        index = 1
    if index >= len(words) or _normalize(words[index].group()) not in WAKE_VARIANTS:
        return WakeResult(Wake.NONE)
    rest = text[words[index].end() :].lstrip(" ,.;:!?-–—").strip()
    if not _WORD_RE.search(rest):
        return WakeResult(Wake.WAKE_ONLY)
    return WakeResult(Wake.COMMAND, rest)
