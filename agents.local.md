# Session Context (agents.local.md)

> Lokaler Kontext für AI-Agenten (Claude Code), damit spätere Sitzungen nahtlos weitermachen.

## Projekt
- **Reachy Claude**: Sprache → Claude Code auf dem Windows-PC des Nutzers, Reachy liest die Antwort vor.
- **v2 (aktuell):** eine PC-App `app/` (Paket `reachy_claude`), verbindet sich per Reachy-SDK
  (`reachy-mini~=1.11.0`, WebRTC) mit dem Roboter; auf Reachy wird nichts installiert.
  Aktivierungswort „Claude“. Alle 6 Schritte umgesetzt, danach Prüfrunde mit 4 Agents (Pakete A–D);
  Stand und offene Punkte: `plan.md` → Fortschritt.
- **Start:** Doppelklick `Reachy-Claude.cmd` (→ `reachy-claude.ps1` → `app/python-env.ps1` → `python -m reachy_claude`);
  `pruefen` = Startprüfung. Gemerkte Einstellungen: `app/einstellungen.toml` (`[claude]`, `[reachy]`, gitignored).
- **Arbeitsweise:** Entwicklung auf Branch `claude/serene-planck-k50f54` (nicht `main`; Merge nur mit Zustimmung).
  Tests: `cd app && .venv/bin/python -m pytest -q` (+ ruff, mypy); CI Ubuntu + Windows.
- **Sicherheitskern:** `claude.py` `build_argv` (`--restricted --tools …`, Sperrlisten) – Änderungen dort immer
  gegen die echte CLI prüfen (siehe plan.md → Erkenntnisse Paket A).
- **v1 (Archiv):** `legacy/` – Conversation-App + claude-bridge (Teile davon in `claude.py`/`spoken.py` übernommen).
- Einstieg: `README.md`, `plan.md`, `SECURITY.md`.
- Hardware des Nutzers: RTX 4060 (8 GB VRAM), 32 GB RAM, Windows; will nicht plaudern,
  nur Aufträge an Claude geben.
- Herkunft: entstanden im Repo `micdanger115-beep/Reachy_` (Ordner `reachy_claude/`), dann ausgelagert.

## Roboter
- Reachy Mini **Wireless (CM4)**, Daemon `reachy-mini.local:8000`; Rechenlast auf den PC auslagern.

## Präferenzen des Nutzers
- Sprache: Deutsch
- PC: Windows; Reachy und PC im selben WLAN/LAN (v2: direkte Verbindung per Reachy-SDK/WebRTC)
- Datensparsamkeit hat hohe Priorität (lokale Sprachverarbeitung)
- Immer: Tests ausführen, aktuelle Patterns, Sicherheitsaspekte prüfen, alles dokumentieren
- Vor nicht-trivialen Änderungen Plan in `plan.md` und Freigabe einholen
