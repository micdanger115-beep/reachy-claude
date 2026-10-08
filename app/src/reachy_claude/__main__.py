"""Kommandozeile: ``reachy-claude check-audio`` (weitere Befehle folgen schrittweise)."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from .check_audio import run_audio_check
from .robot import DEFAULT_ROBOT, RobotConnectionError, connect

logger = logging.getLogger("reachy_claude")


def main(argv: list[str] | None = None) -> int:
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
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    if not 1.0 <= args.seconds <= 60.0:
        print("--seconds muss zwischen 1 und 60 liegen.")
        return 2

    print(f"Verbinde mit Reachy ({args.robot}) ...")
    try:
        with connect(args.robot, debug=args.debug) as mini:
            print("Verbunden.")
            result = run_audio_check(
                mini.media, lambda line: print(line, flush=True), seconds=args.seconds, save_to=args.save
            )
    except RobotConnectionError as exc:
        print(f"FEHLER: {exc}")
        return 1
    except KeyboardInterrupt:
        print("Abgebrochen.")
        return 130
    return 0 if result.mic_ok else 1


if __name__ == "__main__":
    sys.exit(main())
