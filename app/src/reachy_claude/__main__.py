"""Kommandozeile: ``reachy-claude check-audio | listen`` (weitere Befehle folgen schrittweise)."""

from __future__ import annotations

import argparse
import logging
import sys
import threading
import time
from pathlib import Path

from .check_audio import run_audio_check
from .robot import DEFAULT_ROBOT, RobotConnectionError, connect

logger = logging.getLogger("reachy_claude")


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

    listen = sub.add_parser("listen", help="Schritt 2: zuhoeren, erkennen, Auftraege fuer Claude anzeigen")
    listen.add_argument(
        "--device", choices=["auto", "cuda", "cpu"], default="auto", help="Spracherkennung auf ..."
    )
    listen.add_argument("--model", help="Whisper-Modell (Standard: large-v3-turbo auf GPU, small auf CPU)")
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


def run_listen(args: argparse.Namespace) -> int:
    from .listener import listen
    from .stt import SttConfig, WhisperTranscriber

    print("Lade Spracherkennung (beim ersten Start einmaliger Download von Hugging Face, bis ca. 1,5 GB) ...")
    try:
        transcriber = WhisperTranscriber(SttConfig(device=args.device, model=args.model))
    except RuntimeError as exc:
        print(f"FEHLER: {exc}")
        print("Beim ersten Start braucht der PC Internet, um das Sprachmodell herunterzuladen.")
        return 1
    print(f"Spracherkennung bereit: {transcriber.description}")

    print(f"Verbinde mit Reachy ({args.robot}) ...")
    with connect(args.robot, debug=args.debug) as mini:
        print('Verbunden. Sprich mit Reachy – Auftraege beginnen mit "Claude, ...". Beenden mit Strg+C.\n')
        stop = threading.Event()
        try:
            listen(mini.media, transcriber, print_line, on_command=lambda command: None, stop=stop)
        except KeyboardInterrupt:
            stop.set()
            print("Beendet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
