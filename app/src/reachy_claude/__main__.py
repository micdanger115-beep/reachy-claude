"""Kommandozeile: ``reachy-claude check-audio | say | listen``."""

from __future__ import annotations

import argparse
import logging
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from .check_audio import run_audio_check
from .robot import DEFAULT_ROBOT, RobotConnectionError, connect, wait_for_audio
from .tts import DEFAULT_VOICE, Speaker

if TYPE_CHECKING:
    from .assistant import Speaks
    from .settings import ClaudeSettings

logger = logging.getLogger("reachy_claude")

GREETING = "Hallo! Ich höre zu. Sag Claude und dann deinen Auftrag."
SAY_LINGER_S = 2.0  # Verbindung nach "say" offen halten, bis Reachy wirklich fertig gesprochen hat


def print_line(line: str) -> None:
    print(line, flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reachy-claude", description="Mit Reachy sprechen, Claude arbeitet."
    )
    parser.add_argument(
        "--robot", default=DEFAULT_ROBOT, help=f"Name oder IP von Reachy (Standard: {DEFAULT_ROBOT})"
    )
    parser.add_argument("--debug", action="store_true", help="ausfuehrliche Meldungen")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check-audio", help="Schritt 1: Mikrofon und Lautsprecher von Reachy testen")
    check.add_argument("--seconds", type=float, default=5.0, help="Aufnahmedauer in Sekunden (Standard: 5)")
    check.add_argument(
        "--save", type=Path, default=Path("aufnahmen") / f"audio-test-{time.strftime('%Y%m%d-%H%M%S')}.wav"
    )

    say = sub.add_parser("say", help="Schritt 3: Reachy einen Text sprechen lassen")
    say.add_argument("text", help="was Reachy sagen soll")
    say.add_argument("--voice", default=DEFAULT_VOICE, help=f"Piper-Stimme (Standard: {DEFAULT_VOICE})")

    listen = sub.add_parser(
        "listen", help="Zuhoeren: 'Claude, ...' geht an Claude Code, Reachy liest die Antwort vor"
    )
    listen.add_argument("--project", type=Path, help="Projektordner fuer Claude (wird gespeichert)")
    listen.add_argument(
        "--permission", choices=["read", "edit"], help="Rechte fuer Claude (wird gespeichert)"
    )
    listen.add_argument(
        "--no-claude", action="store_true", help="Test ohne Claude: Reachy wiederholt nur den Auftrag"
    )
    listen.add_argument(
        "--device", choices=["auto", "cuda", "cpu"], default="auto", help="Spracherkennung auf ..."
    )
    listen.add_argument("--model", help="Whisper-Modell (Standard: large-v3-turbo auf GPU, small auf CPU)")
    listen.add_argument("--voice", default=DEFAULT_VOICE, help=f"Piper-Stimme (Standard: {DEFAULT_VOICE})")
    listen.add_argument("--silent", action="store_true", help="Reachy antwortet nicht mit Stimme (nur Text)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    if args.command == "check-audio" and not 1.0 <= args.seconds <= 60.0:
        print("--seconds muss zwischen 1 und 60 liegen.")
        return 2

    try:
        if args.command == "listen":
            return run_listen(args)
        if args.command == "say":
            return run_say(args)
        print(f"Verbinde mit Reachy ({args.robot}) ...")
        with connect(args.robot, debug=args.debug) as mini:
            print("Verbunden.")
            result = run_audio_check(mini.media, print_line, seconds=args.seconds, save_to=args.save)
        return 0 if result.mic_ok else 1
    except RobotConnectionError as exc:
        print(f"FEHLER: {exc}")
        return 1
    except KeyboardInterrupt:
        print("Beendet.")
        return 0


def load_speaker(voice: str) -> Speaker | None:
    """Piper-Stimme laden (beim ersten Mal Download); ``None`` mit Meldung bei Fehler."""
    from .tts import PiperSpeaker, TtsConfig

    print("Lade Stimme (beim ersten Start einmaliger Download von Hugging Face, ca. 60 MB) ...")
    try:
        speaker = PiperSpeaker(TtsConfig(voice=voice))
    except Exception as exc:  # Download-, Datei- oder Modellfehler – alle gleich behandeln
        logger.debug("Stimme nicht ladbar", exc_info=True)
        print(f"FEHLER: Stimme '{voice}' konnte nicht geladen werden ({type(exc).__name__}: {exc}).")
        print("Beim ersten Start braucht der PC Internet, um die Stimme herunterzuladen.")
        return None
    print(f"Stimme bereit: {speaker.description}")
    return speaker


def run_say(args: argparse.Namespace) -> int:
    from .listener import Voice

    speaker = load_speaker(args.voice)
    if speaker is None:
        return 1
    print(f"Verbinde mit Reachy ({args.robot}) ...")
    with connect(args.robot, debug=args.debug) as mini:
        wait_for_audio(mini.media)
        Voice(speaker, mini.media, print_line).say(args.text)
        # Reachy spielt mit Verzoegerung ab; trennt man sofort, fehlt das Satzende.
        time.sleep(SAY_LINGER_S)
    return 0


def prepare_claude(args: argparse.Namespace) -> ClaudeSettings | None:
    """Einstellungen fuer Claude laden (und ggf. neuen Projektordner speichern)."""
    from .settings import SETTINGS_FILE, Permission, SettingsError, load_settings, save_settings

    try:
        if args.project is not None:
            settings = load_settings(SETTINGS_FILE, workdir_override=args.project)
            save_settings(SETTINGS_FILE, settings.workdir, Permission(args.permission or settings.permission))
        settings = load_settings(SETTINGS_FILE)
        if args.permission and settings.permission.value != args.permission:
            save_settings(SETTINGS_FILE, settings.workdir, Permission(args.permission))
            settings = load_settings(SETTINGS_FILE)
    except SettingsError as exc:
        print(f"FEHLER: {exc}")
        return None
    rights = "lesen + Dateien bearbeiten" if settings.permission.value == "edit" else "nur lesen"
    print(f"Claude arbeitet in: {settings.workdir}  (Rechte: {rights}; nie Shell, nie Internet)")
    return settings


def run_listen(args: argparse.Namespace) -> int:
    from .assistant import ClaudeAssistant, PrintOnly
    from .claude import ClaudeRunner
    from .listener import Voice, listen
    from .stt import SttConfig, WhisperTranscriber

    settings = None if args.no_claude else prepare_claude(args)
    if settings is None and not args.no_claude:
        return 1

    print("Lade Spracherkennung (beim ersten Start einmaliger Download von Hugging Face, bis ca. 1,5 GB) ...")
    try:
        transcriber = WhisperTranscriber(SttConfig(device=args.device, model=args.model))
    except RuntimeError as exc:
        print(f"FEHLER: {exc}")
        print("Beim ersten Start braucht der PC Internet, um das Sprachmodell herunterzuladen.")
        return 1
    print(f"Spracherkennung bereit: {transcriber.description}")

    speaker = None
    if not args.silent:
        speaker = load_speaker(args.voice)
        if speaker is None:
            return 1

    print(f"Verbinde mit Reachy ({args.robot}) ...")
    with connect(args.robot, debug=args.debug) as mini:
        wait_for_audio(mini.media)
        print('Verbunden. Sprich mit Reachy – Auftraege beginnen mit "Claude, ...". Beenden mit Strg+C.\n')
        voice: Speaks = (
            Voice(speaker, mini.media, print_line) if speaker is not None else PrintOnly(print_line)
        )

        if settings is None:

            def on_command(command: str) -> None:
                voice.say(f"Verstanden: {command}")  # Test ohne Claude

        else:
            assistant = ClaudeAssistant(
                ClaudeRunner(settings), voice, print_line, spoken_max_chars=settings.spoken_max_chars
            )
            on_command = assistant.handle

        voice.say(GREETING)
        stop = threading.Event()
        try:
            listen(mini.media, transcriber, print_line, on_command=on_command, stop=stop)
        except KeyboardInterrupt:
            stop.set()
            print("Beendet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
