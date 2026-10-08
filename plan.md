# plan.md — Reachy ↔ Claude Sprachsteuerung ("Reachy Claude")

Status: **FREIGEGEBEN & umgesetzt** (v0.1, 2026-10-02) – Details/Stand siehe `README.md` §9

### Entscheidungen des Nutzers (2026-10-02)
1. Sprach-Backend: **lokal auf dem PC** (speech-to-speech) → Audio bleibt im Heimnetz.
2. Rechte für Claude: **Dateien bearbeiten**, keine Shell, kein Internet.
3. PC: **Windows**.
4. Verbindung: **gleiches WLAN** → umgesetzt als SSH-Rückwärtstunnel (verschlüsselt,
   nichts im WLAN offen); direkter WLAN-Modus mit IP-Allowlist/TLS als Alternative.

### Stufenweise Inbetriebnahme (Wunsch des Nutzers, 2026-10-08)
- **Stufe 1 `claude-bridge listen`**: nur mit Reachy verbinden und das Gespräch als Text
  anzeigen (du / Reachy). Quelle: JSON-RPC-WebSocket der Conversation-App
  (`ws://<roboter>:7860/rpc`, Benachrichtigungen `conversation.transcript` {role, text, final}
  und `conversation.turn`; Statusabfrage `conversation.status`). Am Roboter keine Änderung.
  Entscheidungen: Bibliothek `websockets` statt Eigenbau; Änderung auf eigenem Branch.
- **Stufe 2 `serve`**: Claude anbinden (Profil + Tool + Bridge).
- **Stufe 3**: Sprache lokal (speech-to-speech) statt HF-Cloud.

### Erkenntnisse bei der Umsetzung
- Claude Code CLI 2.1.287 kennt `--permission-mode default` nicht mehr; verwendet
  wird `dontAsk` (alles Nicht-Erlaubte wird ohne Rückfrage verweigert).
- Antwort-Markierung `SPRECHTEXT:` statt `<spoken>`-Tag, weil `<`/`>` in Argumenten
  für `cmd.exe` (claude als `.cmd`) gefährlich sind.
- speech-to-speech unterstützt offiziell Linux/NVIDIA und macOS → unter Windows via WSL2.

## 1. Ziel (mein Verständnis)

- Ich rede mit Reachy. Reachy wacht auf und wirkt beim Zuhören lebendig
  (Kopf + Antennen bewegen sich).
- Was ich sage, geht als **Befehl/Anfrage an Claude Code auf meinem PC**
  (programmieren per Sprache, Fragen stellen).
- Erklärenden Text aus Claudes Antwort **liest Reachy vor**.
- **Möglichst wenig Daten ins Netz.**
- Immer Tests, aktuelle Patterns, Sicherheit, vollständige Doku.

## 2. Prüfung: Kann die bestehende Conversation-App genutzt werden?

Geprüft: `pollen-robotics/reachy_mini_conversation_app` (v1.0.1, Python,
Stand main vom 2026-09-30).

**Ergebnis: Ja – ohne Fork, über den offiziellen Erweiterungsweg.**

| Bedarf | Was die App schon kann | Fundstelle |
|---|---|---|
| Aufwachen | `wake_up_if_sleeping()` beim Start, `go_to_sleep`-Tool | `app_lifecycle.py`, `main.py` |
| Zuhören / Spracherkennung / Sprechen | Realtime-Backend (Server-VAD, Transkription, TTS) | `huggingface_realtime.py` |
| Lebendig wirken | Idle-„Atmen“, Sprech-Wackeln, Gesichtsverfolgung, Emotionen | `moves.py`, Tools `head_tracking`, `play_emotion` |
| Eigene Funktion anbinden | **Externe Tools** (`REACHY_MINI_EXTERNAL_TOOLS_DIRECTORY`) + **externe Profile** (`profile.md` mit `default_tools`) | README „External profiles and tools“ |
| Lange Aufgaben (Claude braucht Minuten) | Tools laufen im `BackgroundToolManager` (max. 1 Tag), Ergebnis wird **automatisch angesagt**, `task_status`/`task_cancel` | `tools/background_tool_manager.py` |
| Datensparsam | `HF_REALTIME_CONNECTION_MODE=local` → eigenes Sprach-Backend (`huggingface/speech-to-speech`) auf dem PC statt HF-Cloud | README „Connection Modes“ |

**Eine Lücke:** Während des Zuhörens werden die Antennen absichtlich
**eingefroren** und das Atmen pausiert (`MovementManager.set_listening`,
`_calculate_blended_antennas`). Für „Antennen bewegen beim Zuhören“ braucht
es eine kleine Änderung in der Conversation-App selbst. Vorschlag: als
sauberer Upstream-PR („listening wiggle“), bis dahin optional als
dokumentierter Patch. Kopfbewegung beim Zuhören (Gesichtsverfolgung) geht
schon heute.

## 3. Architektur

```
 Ich ──Sprache──► Reachy Mini (Wireless, CM4)
                  └─ conversation_app (unverändert)
                       ├─ Profil "claude_coder"     (unser profile.md)
                       └─ Tool  "ask_claude"         (unser externes Tool)
                                │  HTTPS/HTTP im LAN/WireGuard
                                │  Bearer-Token + HMAC, nur Text
                                ▼
                  PC: claude-bridge (unser Dienst, Python, nur stdlib)
                       └─ ruft `claude -p … --output-format json` auf
                          (Claude Code CLI, im konfigurierten Projektordner)
                                │
                                ▼
                       Anthropic API  (einziger Weg ins Internet)

 Optional/empfohlen: Sprach-Backend (speech-to-speech) ebenfalls auf dem PC
 → Audio verlässt das Heimnetz nie.
```

Ablauf einer Anfrage:
1. Ich sage z. B. „Frag Claude: schreib einen Test für die Login-Funktion“.
2. Realtime-Modell erkennt die Absicht → ruft `ask_claude(prompt=…)`.
   Reachy bestätigt kurz („Ich gebe das an Claude weiter“) + Emotion.
3. Tool sendet den Text an die Bridge. Die Bridge startet Claude Code
   headless, setzt die Sitzung fort (`--resume <session_id>`), damit
   Folgefragen Kontext haben.
4. Claude antwortet. Die Bridge trennt **Vorlesetext** (Erklärung, ohne
   Code/Diffs/Pfade-Listen, gekürzt) von Rohausgabe (bleibt nur im PC-Log).
5. Tool liefert `{spoken_text, …}` zurück → Reachy liest es vor.

## 4. Datensparsamkeit

| Datenstrom | Standard-Conversation-App | Unser Ziel-Setup |
|---|---|---|
| Mikrofon-Audio | HF-Cloud | **lokal** (speech-to-speech auf PC) |
| Transkript/Antworten | HF-Cloud | **lokal** |
| Claude-Anfrage + Projekt-Kontext | – | Anthropic (unvermeidbar für Claude) |
| Robot ↔ Bridge | – | nur LAN/WireGuard, nur Text |
| Emotions-/Tanz-Datensätze, MCP-Spaces (Wetter/Suche) | HF | im Profil **deaktiviert** |

## 5. Sicherheit (Sprache → Code-Ausführung ist heikel!)

Bedrohungen & Maßnahmen:
- **Fremde im Netz schicken Befehle an die Bridge** → Bridge bindet nur an
  konfigurierte IP (WireGuard/LAN), Pflicht-Token (≥32 Byte, `secrets`),
  HMAC-Signatur mit Zeitstempel + Nonce (Replay-Schutz), Rate-Limit,
  Body-Limit, Allowlist der Client-IPs, konstante Vergleichszeit.
- **Fehlerkennung / Fremde Stimmen / Prompt-Injection über Audio**
  (TV, Gäste) → Tool nur im Profil `claude_coder`; Rechte-Stufen für Claude
  (siehe Frage 2); gefährliche Werkzeuge per `--disallowedTools` gesperrt;
  optional Bestätigung „Soll ich das wirklich an Claude senden?“.
- **Claude macht Schaden auf dem PC** → festes Arbeitsverzeichnis,
  `--permission-mode` + `--allowedTools`, kein `--dangerously-skip-permissions`,
  Timeout, ein Auftrag gleichzeitig, Git als Sicherheitsnetz.
- **Shell-Injection in der Bridge** → Prozessstart nur mit Argumentliste
  (`asyncio.create_subprocess_exec`, nie `shell=True`), Prompt per stdin.
- **Geheimnisse** → Token nur in `.env` (gitignored), nie im Log;
  Log ohne Prompt-Volltexte (optional).

## 6. Lieferumfang (nach Freigabe)

```
reachy-claude/
  plan.md
  README.md                 Installation, Betrieb, Sicherheit, Weiterarbeit
  SECURITY.md               Bedrohungsmodell
  bridge/                   PC-Dienst (Python ≥3.11, nur stdlib → keine Supply-Chain)
    claude_bridge/…         HTTP-Server, Auth, Claude-Runner, Vorlesetext-Filter
    tests/…                 pytest (Auth, Replay, Limits, Runner mit Fake-CLI)
    .env.example
  robot/
    external_tools/ask_claude.py      Tool für die Conversation-App
    external_profiles/claude_coder/profile.md
    tests/…                 pytest (Tool mit Fake-Bridge)
  patches/listening_motion.patch      optional (Antennen beim Zuhören)
.github/workflows/reachy-claude-tests.yml   CI: ruff + mypy + pytest
```

## 7. Offene Fragen (beantwortet, siehe oben)

1. Sprach-Backend: lokal auf dem PC (datensparsam, braucht ordentliche
   CPU/GPU) oder HF-Cloud (einfach, Audio geht zu HF)?
2. Rechte für Claude per Sprache: nur lesen/erklären · Dateien bearbeiten ·
   auch Befehle ausführen?
3. Betriebssystem des PCs (Windows/macOS/Linux)?
4. Verbindung Reachy ↔ PC: gleiches WLAN oder WireGuard?
