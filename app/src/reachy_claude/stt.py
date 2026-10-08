"""Spracherkennung lokal auf dem PC mit faster-whisper (Grafikkarte, sonst Prozessor).

Modelle werden beim ersten Start einmalig von Hugging Face heruntergeladen und danach
nur noch lokal verwendet. Audio verlaesst den PC nicht.
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .audio import Audio, silence

logger = logging.getLogger(__name__)

GPU_MODEL = "large-v3-turbo"  # sehr gutes Deutsch, ~1,5 GB, passt locker in 8 GB VRAM
CPU_MODEL = "small"  # schneller Fallback ohne Grafikkarte
# Hilft Whisper, das Aktivierungswort richtig zu schreiben. Whisper uebernimmt die Schreibweise
# dieses Textes – deshalb mit echten Umlauten und typischen Programmier-Begriffen.
INITIAL_PROMPT = "Claude, schreib einen Test für die Login-Funktion in main.py. Claude, erkläre mir den Code."


class Transcriber(Protocol):
    """Audio (16 kHz mono) -> Text."""

    description: str

    def transcribe(self, audio: Audio) -> str: ...


@dataclass(frozen=True)
class SttConfig:
    """Auswahl von Geraet und Modell (``auto`` = Grafikkarte, falls nutzbar)."""

    device: str = "auto"  # auto | cuda | cpu
    model: str | None = None  # None = passend zum Geraet
    language: str = "de"


def _register_nvidia_dlls() -> None:
    """Unter Windows die CUDA-Bibliotheken aus den pip-Paketen nvidia-* auffindbar machen."""
    if sys.platform != "win32":
        return
    try:
        import nvidia
    except ImportError:
        return
    for base in getattr(nvidia, "__path__", []):
        for bin_dir in Path(base).glob("*/bin"):
            os.add_dll_directory(str(bin_dir))
            os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"


class WhisperTranscriber:
    """faster-whisper mit automatischem Rueckfall auf den Prozessor."""

    def __init__(self, config: SttConfig | None = None) -> None:
        config = config or SttConfig()
        _register_nvidia_dlls()
        from faster_whisper import WhisperModel

        self._language = config.language
        attempts: list[tuple[str, str, str]] = []
        if config.device in {"auto", "cuda"}:
            attempts.append(("cuda", "int8_float16", config.model or GPU_MODEL))
        if config.device in {"auto", "cpu"}:
            attempts.append(("cpu", "int8", config.model or CPU_MODEL))

        errors: list[str] = []
        for device, compute_type, model in attempts:
            try:
                self._model: Any = WhisperModel(model, device=device, compute_type=compute_type)
                # Einmal kurz rechnen: CUDA-Bibliotheksfehler zeigen sich erst hier.
                self._run(silence(1.0))
            except Exception as exc:  # ctranslate2/CUDA werfen unterschiedliche Typen
                logger.debug("Whisper auf %s nicht nutzbar", device, exc_info=True)
                errors.append(f"{device}: {type(exc).__name__}: {exc}")
                continue
            self.description = f"Whisper '{model}' auf {'Grafikkarte' if device == 'cuda' else 'Prozessor'}"
            return
        raise RuntimeError("Spracherkennung konnte nicht gestartet werden – " + " | ".join(errors))

    def _run(self, audio: Audio) -> str:
        segments, _ = self._model.transcribe(
            audio,
            language=self._language,
            beam_size=5,
            vad_filter=True,  # Silero: Nicht-Sprache verwerfen, verhindert erfundene Saetze
            condition_on_previous_text=False,
            initial_prompt=INITIAL_PROMPT,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()

    def transcribe(self, audio: Audio) -> str:
        """Satz erkennen; leerer Text, wenn nichts Verstaendliches dabei war."""
        return self._run(audio)
