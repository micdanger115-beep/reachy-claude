"""Kommandozeile: ``claude-bridge listen`` | ``serve`` | ``check`` | ``gen-token``."""

from __future__ import annotations

import argparse
import asyncio
import logging
import secrets
import sys
from pathlib import Path

from .config import ConfigError, load_config, load_environment
from .listen import DEFAULT_PORT, build_url, listen
from .runner import ClaudeRunner, build_argv
from .server import BridgeServer

logger = logging.getLogger("claude_bridge")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="claude-bridge", description="Reachy Mini -> Claude Code Bruecke")
    parser.add_argument(
        "--env-file", type=Path, default=Path(".env"), help="Pfad zur .env (Standard: ./.env)"
    )
    parser.add_argument("--debug", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    listen_parser = sub.add_parser("listen", help="Stufe 1: Gespraech mit Reachy als Text anzeigen")
    listen_parser.add_argument(
        "--robot",
        default="reachy-mini.local",
        help="Name/IP von Reachy oder ws://-Adresse (Standard: reachy-mini.local)",
    )
    listen_parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT, help=f"Port der Conversation-App (Standard: {DEFAULT_PORT})"
    )
    listen_parser.add_argument("--save", type=Path, help="Gespraech zusaetzlich in diese Datei schreiben")
    listen_parser.add_argument(
        "--show-turns", action="store_true", help="Auch Zustaende anzeigen (hoert zu, denkt nach, spricht)"
    )
    sub.add_parser("serve", help="Stufe 2: Bridge fuer Claude starten")
    sub.add_parser("check", help="Konfiguration pruefen und Claude-Aufruf anzeigen")
    sub.add_parser("gen-token", help="Neues zufaelliges Token ausgeben")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.command == "gen-token":
        print(secrets.token_urlsafe(48))
        return 0

    if args.command == "listen":
        return run_listen(args)

    env_file = args.env_file.resolve()
    try:
        config = load_config(load_environment(env_file), env_file=env_file)
    except ConfigError as exc:
        logger.error("Konfiguration ungueltig: %s", exc)
        return 2

    if args.command == "check":
        shown = build_argv(config, None)
        print("Konfiguration OK.")
        print(f"  Lauscht auf:   {config.host}:{config.port} ({'TLS' if config.tls_cert else 'HTTP'})")
        print(f"  Erlaubt:       {', '.join(str(n) for n in config.allowed_clients)}")
        print(f"  Arbeitsordner: {config.workdir}")
        print(f"  Rechte:        {config.permission_level.value}")
        print(f"  Aufruf:        {' '.join(shown[:-2])} --append-system-prompt <...>")
        return 0

    server = BridgeServer(config, ClaudeRunner(config))
    logger.info(
        "claude-bridge laeuft auf %s:%s (Rechte: %s, Ordner: %s)",
        config.host,
        config.port,
        config.permission_level.value,
        config.workdir,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Beendet.")
    finally:
        server.server_close()
    return 0


def run_listen(args: argparse.Namespace) -> int:
    """Stufe 1: nur mitlesen, braucht weder Token noch Claude."""
    try:
        url = build_url(args.robot, args.port)
    except ValueError as exc:
        logger.error("%s", exc)
        return 2
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # alte Windows-Konsolen ohne UTF-8
    print(f"Verbinde mit Reachy ({url}) … Beenden mit Strg+C.")
    try:
        asyncio.run(
            listen(
                url,
                lambda line: print(line, flush=True),
                show_turns=args.show_turns,
                transcript_file=args.save,
            )
        )
    except KeyboardInterrupt:
        print("Beendet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
