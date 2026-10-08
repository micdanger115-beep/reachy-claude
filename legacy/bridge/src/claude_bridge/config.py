"""Konfiguration aus Umgebungsvariablen bzw. ``.env`` – mit strenger Validierung.

Unsichere Einstellungen fuehren zu einem Startfehler statt zu einer Warnung.
"""

from __future__ import annotations

import ipaddress
import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

ENV_PREFIX = "CLAUDE_BRIDGE_"
MIN_TOKEN_LEN = 32
_WILDCARD_HOSTS = {"0.0.0.0", "::", ""}  # noqa: S104 - genau diese Werte wollen wir erkennen

IpNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


class ConfigError(ValueError):
    """Ungueltige oder unsichere Konfiguration."""


class PermissionLevel(StrEnum):
    """Was Claude auf dem PC per Sprachbefehl tun darf."""

    READ = "read"  # nur lesen und erklaeren
    EDIT = "edit"  # zusaetzlich Dateien im Arbeitsordner bearbeiten (keine Shell)


@dataclass(frozen=True)
class BridgeConfig:
    """Alle Einstellungen der Bridge (unveraenderlich nach dem Start)."""

    token: str
    host: str
    port: int
    allowed_clients: tuple[IpNetwork, ...]
    workdir: Path
    claude_bin: str
    permission_level: PermissionLevel
    timeout_s: float
    max_turns: int
    max_prompt_chars: int
    spoken_max_chars: int
    rate_limit_per_min: int
    transcript_dir: Path | None
    log_prompts: bool
    tls_cert: Path | None
    tls_key: Path | None

    def client_allowed(self, ip: str) -> bool:
        """Darf diese Client-IP die Bridge benutzen?"""
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
            addr = addr.ipv4_mapped
        return any(addr in net for net in self.allowed_clients)


def parse_env_file(path: Path) -> dict[str, str]:
    """Minimaler ``.env``-Parser (KEY=VALUE, Kommentare, optionale Anfuehrungszeichen)."""
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        key, sep, value = line.partition("=")
        if not sep:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def _get(env: Mapping[str, str], name: str, default: str | None = None) -> str:
    value = env.get(ENV_PREFIX + name, default)
    if value is None or value.strip() == "":
        raise ConfigError(f"{ENV_PREFIX}{name} fehlt.")
    return value.strip()


def _get_int(env: Mapping[str, str], name: str, default: int, lo: int, hi: int) -> int:
    raw = _get(env, name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{ENV_PREFIX}{name} muss eine ganze Zahl sein.") from exc
    if not lo <= value <= hi:
        raise ConfigError(f"{ENV_PREFIX}{name} muss zwischen {lo} und {hi} liegen.")
    return value


def _get_bool(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(ENV_PREFIX + name, "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "ja", "on"}:
        return True
    if raw in {"0", "false", "no", "nein", "off"}:
        return False
    raise ConfigError(f"{ENV_PREFIX}{name} muss true oder false sein.")


def _optional_path(env: Mapping[str, str], name: str) -> Path | None:
    raw = env.get(ENV_PREFIX + name, "").strip()
    return Path(raw).expanduser() if raw else None


def _is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def load_config(env: Mapping[str, str], env_file: Path | None = None) -> BridgeConfig:
    """Konfiguration laden und validieren. Wirft ``ConfigError`` bei Problemen."""
    token = _get(env, "TOKEN")
    if len(token) < MIN_TOKEN_LEN:
        raise ConfigError(
            f"{ENV_PREFIX}TOKEN ist zu kurz (min. {MIN_TOKEN_LEN} Zeichen). "
            "Neues Token: python -m claude_bridge gen-token"
        )

    host = _get(env, "HOST")
    if host in _WILDCARD_HOSTS and not _get_bool(env, "ALLOW_ALL_INTERFACES", False):
        raise ConfigError(
            f"{ENV_PREFIX}HOST={host!r} wuerde auf allen Netzwerkkarten lauschen. Trage die LAN-IP "
            f"des PCs ein oder setze {ENV_PREFIX}ALLOW_ALL_INTERFACES=true (nicht empfohlen)."
        )

    clients: list[IpNetwork] = []
    for part in _get(env, "ALLOWED_CLIENTS").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            clients.append(ipaddress.ip_network(part, strict=False))
        except ValueError as exc:
            raise ConfigError(f"Ungueltige Adresse in {ENV_PREFIX}ALLOWED_CLIENTS: {part!r}") from exc
    if not clients:
        raise ConfigError(f"{ENV_PREFIX}ALLOWED_CLIENTS ist leer.")
    if any(net.prefixlen == 0 for net in clients):
        raise ConfigError(f"{ENV_PREFIX}ALLOWED_CLIENTS darf nicht 'alle Adressen' (/0) enthalten.")

    workdir = Path(_get(env, "WORKDIR")).expanduser()
    if not workdir.is_dir():
        raise ConfigError(f"{ENV_PREFIX}WORKDIR existiert nicht: {workdir}")
    workdir = workdir.resolve()
    if env_file is not None and _is_relative_to(env_file, workdir):
        raise ConfigError(
            "Die .env der Bridge (mit dem Token) liegt im Arbeitsordner von Claude. "
            "Verschiebe die Bridge-Konfiguration ausserhalb von WORKDIR."
        )

    claude_bin_raw = env.get(ENV_PREFIX + "CLAUDE_BIN", "").strip() or "claude"
    claude_bin = shutil.which(claude_bin_raw)
    if claude_bin is None:
        raise ConfigError(
            f"Claude Code CLI nicht gefunden ({claude_bin_raw!r}). Installieren oder "
            f"{ENV_PREFIX}CLAUDE_BIN auf den vollen Pfad setzen."
        )

    try:
        level = PermissionLevel(_get(env, "PERMISSION_LEVEL", PermissionLevel.EDIT.value).lower())
    except ValueError as exc:
        raise ConfigError(f"{ENV_PREFIX}PERMISSION_LEVEL muss 'read' oder 'edit' sein.") from exc

    tls_cert = _optional_path(env, "TLS_CERT")
    tls_key = _optional_path(env, "TLS_KEY")
    if (tls_cert is None) != (tls_key is None):
        raise ConfigError(f"{ENV_PREFIX}TLS_CERT und {ENV_PREFIX}TLS_KEY nur gemeinsam setzen.")

    transcript_raw = env.get(ENV_PREFIX + "TRANSCRIPT_DIR", "transcripts").strip()
    transcript_dir = (
        None if transcript_raw.lower() in {"", "off", "none"} else Path(transcript_raw).expanduser()
    )

    return BridgeConfig(
        token=token,
        host=host,
        port=_get_int(env, "PORT", 8787, 1024, 65535),
        allowed_clients=tuple(clients),
        workdir=workdir,
        claude_bin=claude_bin,
        permission_level=level,
        timeout_s=float(_get_int(env, "TIMEOUT_S", 900, 10, 3600)),
        max_turns=_get_int(env, "MAX_TURNS", 30, 1, 200),
        max_prompt_chars=_get_int(env, "MAX_PROMPT_CHARS", 4000, 10, 20000),
        spoken_max_chars=_get_int(env, "SPOKEN_MAX_CHARS", 900, 100, 5000),
        rate_limit_per_min=_get_int(env, "RATE_LIMIT_PER_MIN", 10, 1, 120),
        transcript_dir=transcript_dir,
        log_prompts=_get_bool(env, "LOG_PROMPTS", False),
        tls_cert=tls_cert,
        tls_key=tls_key,
    )


def load_environment(env_file: Path | None) -> dict[str, str]:
    """``.env`` einlesen; echte Umgebungsvariablen haben Vorrang."""
    merged: dict[str, str] = {}
    if env_file is not None and env_file.is_file():
        merged.update(parse_env_file(env_file))
    merged.update({k: v for k, v in os.environ.items() if k.startswith(ENV_PREFIX)})
    return merged
