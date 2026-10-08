# Session Context (agents.local.md)

> Lokaler Kontext für AI-Agenten (Claude Code), damit spätere Sitzungen nahtlos weitermachen.

## Projekt
- **Reachy Claude**: Sprache → Claude Code auf dem Windows-PC des Nutzers, Reachy liest die Erklärung vor.
- Nutzt die offizielle Python-Conversation-App von Pollen (externes Profil + externes Tool, kein Fork),
  PC-Dienst `bridge/` (claude-bridge), optionaler Patch `patches/listening_motion.patch`.
- Einstieg: `README.md` (§9 = Stand & nächste Schritte), `plan.md`, `SECURITY.md`.
- Herkunft: entstanden im Repo `micdanger115-beep/Reachy_` (Ordner `reachy_claude/`), dann ausgelagert.

## Roboter
- Reachy Mini **Wireless (CM4)**, Daemon `reachy-mini.local:8000`; Rechenlast auf den PC auslagern.

## Präferenzen des Nutzers
- Sprache: Deutsch
- PC: Windows; Reachy und PC im selben WLAN (umgesetzt mit SSH-Tunnel)
- Datensparsamkeit hat hohe Priorität (lokale Sprachverarbeitung)
- Immer: Tests ausführen, aktuelle Patterns, Sicherheitsaspekte prüfen, alles dokumentieren
- Vor nicht-trivialen Änderungen Plan in `plan.md` und Freigabe einholen
