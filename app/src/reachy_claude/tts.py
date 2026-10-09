"""Sprachausgabe lokal auf dem PC mit Piper (deutsche Stimme, laeuft auf dem Prozessor).

Die Stimme wird beim ersten Start einmalig von Hugging Face (``rhasspy/piper-voices``)
heruntergeladen und in ``app/voices`` abgelegt; danach wird nur noch lokal gerechnet.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from .audio import SAMPLE_RATE, Audio

logger = logging.getLogger(__name__)

DEFAULT_VOICE = "de_DE-thorsten-medium"
# Alle deutschen Piper-Stimmen (Quelle: rhasspy/piper VOICES.md). Qualitaet: x_low < low < medium < high.
GERMAN_VOICES: dict[str, str] = {
    "de_DE-thorsten-medium": "Thorsten, maennlich, klar (Standard)",
    "de_DE-thorsten-high": "Thorsten, maennlich, beste Qualitaet (groesser, etwas langsamer)",
    "de_DE-thorsten-low": "Thorsten, maennlich, einfache Qualitaet (klein, schnell)",
    "de_DE-thorsten_emotional-medium": "Thorsten mit Gefuehlslagen (mehrere Sprecher, Auswahl mit -Sprecher)",
    "de_DE-kerstin-low": "Kerstin, weiblich",
    "de_DE-ramona-low": "Ramona, weiblich",
    "de_DE-eva_k-x_low": "Eva K., weiblich, sehr einfache Qualitaet",
    "de_DE-karlsson-low": "Karlsson, maennlich",
    "de_DE-pavoque-low": "Pavoque, maennlich",
    "de_DE-mls-medium": "MLS, viele verschiedene Sprecher (Auswahl mit -Sprecher)",
}
# Sprache_Land-Name-Qualitaet; nichts, was als Pfad etwas anderes bedeuten koennte ("..", "/")
VOICE_NAME_RE = re.compile(r"^[A-Za-z]{2}_[A-Za-z]{2}-[A-Za-z0-9_]+-[a-z_]+$")
VOICES_REPO = "rhasspy/piper-voices"
DEFAULT_VOICE_DIR = Path("voices")
TARGET_PEAK = 0.8  # etwas Luft nach oben, damit Reachys Lautsprecher nicht uebersteuert
PRONUNCIATION_FILE = Path("aussprache.txt")
# Eigene Ergaenzungen (nicht in Git, damit "git pull" nicht mit deinen Aenderungen kollidiert)
OWN_PRONUNCIATION_NAME = "aussprache-eigene.txt"
# Englische Namen spricht die deutsche Stimme sonst "deutsch" aus (Re-ach-ue).
DEFAULT_PRONUNCIATIONS = {"Reachy": "Rietschi", "Claude": "Klohd"}


class Speaker(Protocol):
    """Text -> Audio (16 kHz mono)."""

    description: str

    def synthesize(self, text: str) -> Audio: ...


@dataclass(frozen=True)
class TtsConfig:
    """Stimme und Sprechtempo (``length_scale`` > 1 = langsamer)."""

    voice: str = DEFAULT_VOICE
    voice_dir: Path = DEFAULT_VOICE_DIR
    length_scale: float = 1.0
    pronunciation_file: Path | None = PRONUNCIATION_FILE
    speaker: str | None = None  # bei Stimmen mit mehreren Sprechern: Name oder Nummer


def load_pronunciations(path: Path | None) -> dict[str, str]:
    """Standard-Aussprachen plus ``aussprache.txt`` plus ``aussprache-eigene.txt`` (``Wort = Lautschrift``).

    Spaetere Eintraege gewinnen – deine eigene Datei also vor der mitgelieferten.
    """
    table = dict(DEFAULT_PRONUNCIATIONS)
    if path is None:
        return table
    for file in (path, path.with_name(OWN_PRONUNCIATION_NAME)):
        if file.is_file():
            table = _read_pronunciations(file, table)
    return table


def _read_pronunciations(path: Path, table: dict[str, str]) -> dict[str, str]:
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        word, sep, spoken = line.partition("=")
        if not sep or not word.strip() or not spoken.strip():
            logger.warning("%s Zeile %d ignoriert (Format: Wort = Lautschrift): %r", path, number, raw)
            continue
        table = {k: v for k, v in table.items() if k.lower() != word.strip().lower()}
        table[word.strip()] = spoken.strip()
    return table


def apply_pronunciations(text: str, table: dict[str, str]) -> str:
    """Ganze Woerter (ohne Ruecksicht auf Gross-/Kleinschreibung) durch ihre Lautschrift ersetzen."""
    for word in sorted(table, key=len, reverse=True):
        text = re.sub(rf"(?<!\w){re.escape(word)}(?!\w)", table[word], text, flags=re.IGNORECASE)
    return text


def voice_repo_path(voice: str) -> str:
    """Pfad im Repo ``rhasspy/piper-voices``, z. B. ``de/de_DE/thorsten/medium``."""
    if not VOICE_NAME_RE.fullmatch(voice):
        raise ValueError(f"Ungueltiger Stimmenname: {voice!r} (Beispiel: {DEFAULT_VOICE})")
    locale, name, quality = voice.split("-")
    return f"{locale.split('_')[0]}/{locale}/{name}/{quality}"


def ensure_voice(config: TtsConfig) -> Path:
    """Stimme lokal bereitstellen (einmaliger Download); gibt den Pfad zur .onnx-Datei zurueck."""
    model = config.voice_dir / f"{config.voice}.onnx"
    if model.is_file() and model.with_suffix(".onnx.json").is_file():
        return model
    from huggingface_hub import hf_hub_download

    config.voice_dir.mkdir(parents=True, exist_ok=True)
    base = voice_repo_path(config.voice)
    for suffix in (".onnx", ".onnx.json"):
        downloaded = hf_hub_download(
            VOICES_REPO, f"{base}/{config.voice}{suffix}", local_dir=config.voice_dir
        )
        Path(downloaded).replace(config.voice_dir / f"{config.voice}{suffix}")
    return model


def resample(samples: Audio, rate_in: int, rate_out: int = SAMPLE_RATE) -> Audio:
    """Einfaches lineares Umrechnen der Abtastrate (fuer Sprache ausreichend)."""
    if rate_in == rate_out or samples.size == 0:
        return samples.astype(np.float32, copy=False)
    duration = samples.size / rate_in
    n_out = max(1, round(duration * rate_out))
    x_out = np.arange(n_out, dtype=np.float64) / rate_out
    x_in = np.arange(samples.size, dtype=np.float64) / rate_in
    return np.interp(x_out, x_in, samples).astype(np.float32)


def normalize(samples: Audio, peak: float = TARGET_PEAK) -> Audio:
    """Lautstaerke auf einen festen Spitzenwert bringen."""
    current = float(np.max(np.abs(samples))) if samples.size else 0.0
    if current <= 1e-6:
        return samples
    return (samples * (peak / current)).astype(np.float32)


class PiperSpeaker:
    """Piper-Stimme; liefert 16-kHz-Audio passend zu Reachys Lautsprecher."""

    def __init__(self, config: TtsConfig | None = None, voice: Any = None) -> None:
        self._config = config or TtsConfig()
        if voice is None:
            from piper import PiperVoice

            voice = PiperVoice.load(ensure_voice(self._config))
        self._voice = voice
        self._pronunciations = load_pronunciations(self._config.pronunciation_file)
        self._speaker_id = resolve_speaker(self._config.speaker, speaker_map(voice))
        self.description = f"Piper '{self._config.voice}'"
        speakers = speaker_map(voice)
        if speakers:
            chosen = next((name for name, sid in speakers.items() if sid == self._speaker_id), None)
            self.description += (
                f", Sprecher '{chosen or self._speaker_id or 0}' (verfuegbar: {', '.join(speakers)})"
            )

    def synthesize(self, text: str) -> Audio:
        """Text sprechen; leerer Text ergibt leeres Audio."""
        if not text.strip():
            return np.zeros(0, dtype=np.float32)
        from piper import SynthesisConfig

        spoken = apply_pronunciations(text, self._pronunciations)
        config = SynthesisConfig(length_scale=self._config.length_scale, speaker_id=self._speaker_id)
        chunks = list(self._voice.synthesize(spoken, config))
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        audio = np.concatenate([np.asarray(c.audio_float_array, dtype=np.float32) for c in chunks])
        return normalize(resample(audio, int(chunks[0].sample_rate)))


def speaker_map(voice: Any) -> dict[str, int]:
    """Sprecher einer Stimme (Name -> Nummer); leer bei Stimmen mit nur einem Sprecher."""
    config = getattr(voice, "config", None)
    mapping = getattr(config, "speaker_id_map", None) or {}
    return {str(name): int(sid) for name, sid in dict(mapping).items()}


def resolve_speaker(speaker: str | None, speakers: dict[str, int]) -> int | None:
    """Sprecher-Name oder -Nummer in eine Nummer uebersetzen (``None`` = Standard der Stimme)."""
    if speaker is None or speaker == "":
        return None
    if speaker.isdigit():
        number = int(speaker)
        if speakers and number not in speakers.values():
            raise ValueError(f"Sprecher {number} gibt es nicht. Verfuegbar: {', '.join(speakers)}")
        return number
    for name, number in speakers.items():
        if name.lower() == speaker.lower():
            return number
    available = ", ".join(speakers) if speakers else "keine (Stimme hat nur einen Sprecher)"
    raise ValueError(f"Sprecher '{speaker}' gibt es nicht. Verfuegbar: {available}")
