# Session Context (agents.local.md)

> Lokaler Kontext für AI-Agenten (Claude Code), damit spätere Sitzungen nahtlos weitermachen.

## Projekt
- **Reachy Claude**: Sprache → Claude Code auf dem Windows-PC des Nutzers, Reachy liest die Antwort vor.
- **v2 (aktuell):** eine PC-App `app/` (Paket `reachy_claude`), verbindet sich per Reachy-SDK
  (`reachy-mini~=1.11.0`, WebRTC) mit dem Roboter; auf Reachy wird nichts installiert.
  Aktivierungswort „Claude“. Umsetzung in 6 Schritten (siehe `plan.md` → Fortschritt).
- **v1 (Archiv):** `legacy/` – Conversation-App + claude-bridge; `runner.py`/`speech.py`
  von dort werden in Schritt 4 übernommen.
- Einstieg: `README.md`, `plan.md`, `SECURITY.md`.
- Hardware des Nutzers: RTX 4060 (8 GB VRAM), 32 GB RAM, Windows; will nicht plaudern,
  nur Aufträge an Claude geben.
- Herkunft: entstanden im Repo `micdanger115-beep/Reachy_` (Ordner `reachy_claude/`), dann ausgelagert.

## Roboter
- Reachy Mini **Wireless (CM4)**, Daemon `reachy-mini.local:8000`; Rechenlast auf den PC auslagern.

## Präferenzen des Nutzers
- Sprache: Deutsch
- PC: Windows; Reachy und PC im selben WLAN (umgesetzt mit SSH-Tunnel)
- Datensparsamkeit hat hohe Priorität (lokale Sprachverarbeitung)
- Immer: Tests ausführen, aktuelle Patterns, Sicherheitsaspekte prüfen, alles dokumentieren
- Vor nicht-trivialen Änderungen Plan in `plan.md` und Freigabe einholen
