# Reachy Claude 🤖🎙️ → 💻

Mit Reachy Mini **sprechen** und dabei **Claude Code auf dem eigenen PC** steuern:
programmieren per Sprache, Fragen zum Projekt stellen – Reachy liest Claudes
Erklärung anschließend vor.

- Reachy wacht auf, folgt deinem Gesicht und bewegt beim Zuhören Kopf und Antennen.
- „Frag Claude: …“ → der Auftrag geht an Claude Code auf deinem Windows-PC.
- Claude arbeitet im festgelegten Projektordner; Reachy liest die Zusammenfassung vor.
- **Datensparsam:** Sprache wird lokal verarbeitet, nur der Auftrag an Claude geht ins Internet.

> Stand: siehe [Abschnitt 9 „Stand & nächste Schritte“](#9-stand--nächste-schritte).
> Plan und Entscheidungen: [`plan.md`](plan.md) · Sicherheit: [`SECURITY.md`](SECURITY.md)

---

## Schnellstart – Stufe 1: Gespräch mit Reachy als Text sehen

Bevor Claude ins Spiel kommt, prüfen wir nur eins: **Versteht Reachy dich, und
was antwortet er?** Dafür brauchst du weder Token noch Claude, Tunnel oder
Sprach-Backend auf dem PC – am Roboter wird nichts verändert.

**Auf Reachy:** Die **Conversation-App** ganz normal im Reachy-Dashboard
installieren und starten (Standard-Einstellungen, Sprache über Hugging Face).

**Auf dem Windows-PC** (Python ≥ 3.11, im selben WLAN wie Reachy):

```powershell
git clone https://github.com/micdanger115-beep/reachy-claude.git
cd reachy-claude\bridge
powershell -ExecutionPolicy Bypass -File .\listen.ps1
```

Beim ersten Start richtet das Skript alles selbst ein. Danach siehst du:

```
Verbunden mit ws://reachy-mini.local:7860/rpc
10:15:00  Sprachdienst verbunden (Hugging-Face-Cloud). Sprich mit Reachy!
10:15:02  Du:     Hallo Reachy, wie geht's?
10:15:04  Reachy: Mir geht's prima! Was kann ich für dich tun?
```

Das Gespräch wird zusätzlich in `bridge\transcripts\gespraech-<Datum>.md`
gespeichert. Beenden mit **Strg+C**.

| Option | Wirkung |
|---|---|
| `-Robot 192.168.1.30` | Reachy per IP ansprechen, falls `reachy-mini.local` nicht gefunden wird |
| `-ShowTurns` | zusätzlich anzeigen, ob Reachy gerade zuhört, nachdenkt oder spricht |

Ohne Skript (z. B. Linux/macOS): `claude-bridge listen --robot reachy-mini.local --save gespraech.md`

| Meldung | Bedeutung / Lösung |
|---|---|
| „Reachy nicht erreichbar … Neuer Versuch“ | Conversation-App läuft nicht, oder Name/IP falsch → im Dashboard starten bzw. `-Robot <IP>` |
| „Sprachdienst ist nicht verbunden“ | Reachy erreicht seinen Sprachdienst nicht (Internet/Hugging-Face-Login am Roboter prüfen) |
| Verbunden, aber keine Zeilen | Mikrofon stumm? In der Weboberfläche der App (`http://reachy-mini.local:7860`) prüfen |

> **Datenschutz/Sicherheit in Stufe 1:** Sprache geht hier noch über die
> Hugging-Face-Cloud (Standard der App). Die Schnittstelle der App
> (Port 7860) ist im WLAN ohne Passwort erreichbar – das ist so in der
> Pollen-App angelegt; `listen` liest nur mit. Details: [`SECURITY.md`](SECURITY.md).

**Stufe 2** (Claude anbinden) und **Stufe 3** (Sprache lokal statt Cloud)
beschreiben die Abschnitte 4–6.

---

## Inhalt

0. [Schnellstart – Stufe 1](#schnellstart--stufe-1-gespräch-mit-reachy-als-text-sehen)
1. [Wie es funktioniert](#1-wie-es-funktioniert)
2. [Welche Daten wohin gehen](#2-welche-daten-wohin-gehen)
3. [Voraussetzungen](#3-voraussetzungen)
4. [PC einrichten (Windows)](#4-pc-einrichten-windows)
5. [Roboter einrichten](#5-roboter-einrichten)
6. [Starten & benutzen](#6-starten--benutzen)
7. [Fehlersuche](#7-fehlersuche)
8. [Entwicklung & Tests](#8-entwicklung--tests)
9. [Stand & nächste Schritte](#9-stand--nächste-schritte)

---

## 1. Wie es funktioniert

Wir nutzen die **offizielle Conversation-App** von Pollen Robotics
([`reachy_mini_conversation_app`](https://github.com/pollen-robotics/reachy_mini_conversation_app))
**ohne sie zu forken** – über ihre vorgesehenen Erweiterungspunkte:

| Baustein | Wo | Was es tut |
|---|---|---|
| Conversation-App | Roboter | Aufwachen, Zuhören (VAD), Spracherkennung, Sprechen, Bewegungen |
| Profil `claude_coder` | Roboter (`robot/external_profiles/`) | Persönlichkeit/Regeln: Deutsch, wann an Claude weitergeben, vorlesen |
| Tool `ask_claude` | Roboter (`robot/external_tools/`) | Schickt den Auftrag signiert an die Bridge, gibt den Vorlesetext zurück |
| `claude-bridge` | PC (`bridge/`) | Nimmt Aufträge an, startet `claude -p`, macht aus der Antwort Vorlesetext |
| Sprach-Backend | PC (`speech-to-speech`) | Spracherkennung + Sprachausgabe + kleines lokales LLM |
| Patch „Zuhör-Bewegung“ | Roboter (optional, `patches/`) | Antennen wippen und Kopf neigt sich beim Zuhören |

```
 Du ──Sprache──► Reachy Mini (Wireless)
                 └─ Conversation-App + Profil claude_coder + Tool ask_claude
                        │  Audio            │  Auftrag (Text, HMAC-signiert)
                        ▼                   ▼
            ┌──────────── SSH-Tunnel (verschlüsselt) ────────────┐
                        ▼                   ▼
 Windows-PC:  speech-to-speech :8765    claude-bridge :8787
              (STT · LLM · TTS lokal)    └─ claude -p (Claude Code CLI)
                                              │  im Projektordner
                                              ▼
                                         Anthropic API  ← einziger Weg ins Internet
```

**Ablauf einer Anfrage**

1. Du: „Frag Claude, schreib einen Test für die Login-Funktion.“
2. Das lokale Sprachmodell erkennt die Absicht und ruft `ask_claude` auf;
   Reachy sagt kurz „Ich gebe das an Claude weiter.“
3. Das Tool läuft **im Hintergrund** (die App bleibt ansprechbar) und schickt
   den Text signiert an die Bridge.
4. Die Bridge startet Claude Code headless im Projektordner. Folgefragen
   setzen dieselbe Claude-Sitzung fort (`--resume`).
5. Claude beendet jede Antwort mit einer Zeile `SPRECHTEXT: …`. Die Bridge
   schickt **nur diesen kurzen Text** zurück; Code/Diffs bleiben auf dem PC
   (Mitschrift unter `bridge/transcripts/JJJJ-MM-TT.md`).
6. Reachy liest den Text vor.

## 2. Welche Daten wohin gehen

| Daten | Ziel | Bemerkung |
|---|---|---|
| Mikrofon-Audio, Transkript, Reachys Antworten | **nur Heimnetz** (Roboter ↔ PC) | Sprach-Backend lokal statt HF-Cloud |
| Dein Auftrag + benötigter Projekt-Kontext | Anthropic (Claude) | unvermeidbar, damit Claude arbeiten kann |
| Vollständige Claude-Antwort | bleibt auf dem PC | `transcripts/`, abschaltbar |
| Websuche, Wetter, Emotions-Datensätze (HF) | – | im Profil **nicht** aktiviert |

Einmalig beim Einrichten werden Modelle/Pakete heruntergeladen (pip, Hugging Face).

## 3. Voraussetzungen

- **Reachy Mini Wireless** mit aktueller Software, per SSH erreichbar
  (`reachy-mini.local`). Benutzername laut Pollen-Doku (in den Beispielen `pollen`).
- **Windows-PC** im selben WLAN mit
  - Python ≥ 3.11 (`py -3 --version`)
  - **Claude Code** installiert und angemeldet (`claude --version`, einmal `claude` starten und einloggen)
  - OpenSSH-Client (bei Windows 10/11 dabei: `ssh -V`)
  - für das lokale Sprach-Backend: **NVIDIA-GPU** (ca. 8–24 GB VRAM je nach Modell) und **WSL2** (siehe 4.3)
- Ein Projektordner, in dem Claude arbeiten soll – am besten ein **Git-Repository**
  (dann kannst du jede Änderung mit `git diff` prüfen und zurücknehmen).

## 4. PC einrichten (Windows)

### 4.1 Repository holen

```powershell
git clone https://github.com/micdanger115-beep/reachy-claude.git
cd reachy-claude
```

> Wichtig: Dieses Repository **nicht** als Claude-Arbeitsordner verwenden – die
> Bridge-`.env` mit dem Token läge sonst in Claudes Reichweite (die Bridge
> verweigert dann den Start).

### 4.2 claude-bridge

```powershell
cd bridge
copy .env.example .env
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m claude_bridge gen-token     # Token kopieren
notepad .env                                               # Token + WORKDIR eintragen
.\.venv\Scripts\python.exe -m claude_bridge --env-file .env check
```

`check` zeigt die Einstellungen und den genauen Claude-Aufruf (ohne Token).
Wichtige Einstellungen (alle in `.env.example` erklärt):

| Variable | Standard | Bedeutung |
|---|---|---|
| `CLAUDE_BRIDGE_TOKEN` | – (Pflicht) | gemeinsames Geheimnis mit Reachy, ≥ 32 Zeichen |
| `CLAUDE_BRIDGE_HOST` / `_PORT` | `127.0.0.1` / `8787` | wo die Bridge lauscht (mit SSH-Tunnel: Loopback) |
| `CLAUDE_BRIDGE_ALLOWED_CLIENTS` | – (Pflicht) | erlaubte Client-IPs/Netze |
| `CLAUDE_BRIDGE_WORKDIR` | – (Pflicht) | Projektordner für Claude |
| `CLAUDE_BRIDGE_PERMISSION_LEVEL` | `edit` | `read` = nur lesen/erklären, `edit` = Dateien bearbeiten |
| `CLAUDE_BRIDGE_TIMEOUT_S` | `900` | Abbruch nach 15 min |
| `CLAUDE_BRIDGE_SPOKEN_MAX_CHARS` | `900` | Länge des Vorlesetexts |
| `CLAUDE_BRIDGE_TRANSCRIPT_DIR` | `transcripts` | lokale Mitschrift (`off` = aus) |

Starten: `powershell -ExecutionPolicy Bypass -File .\start-bridge.ps1`

**Was Claude darf** (fest eingebaut, nicht per `.env` aufweichbar):

| | `read` | `edit` |
|---|---|---|
| Dateien lesen/suchen | ✅ | ✅ |
| Dateien im Projektordner ändern/anlegen | ❌ | ✅ |
| Shell-Befehle (`Bash`) | ❌ | ❌ |
| Internet (`WebFetch`, `WebSearch`) | ❌ | ❌ |
| MCP-Server | ❌ | ❌ |
| Rückfragen | – | – (`--permission-mode dontAsk`: alles Nicht-Erlaubte wird verweigert) |

### 4.3 Lokales Sprach-Backend (speech-to-speech)

Die Conversation-App spricht das OpenAI-Realtime-Protokoll; Hugging Faces
[`speech-to-speech`](https://github.com/huggingface/speech-to-speech) stellt
genau diesen Server lokal bereit (Spracherkennung, ein kleines LLM für das
Gespräch und die Tool-Auswahl, Sprachausgabe).

Offiziell unterstützt sind Linux/NVIDIA und Apple Silicon, daher unter
Windows über **WSL2 (Ubuntu 24.04)** mit NVIDIA-Treiber:

```bash
# in WSL2 (Ubuntu)
sudo apt-get install -y libportaudio2 libsndfile1
python3 -m venv ~/s2s && source ~/s2s/bin/activate
pip install speech-to-speech

speech-to-speech serve \
    --device cuda \
    --stt parakeet-tdt \
    --llm_backend transformers \
    --model_name Qwen/Qwen3-4B-Instruct-2507 \
    --llm_torch_dtype float16 \
    --tts qwen3 --qwen3_tts_backend ggml \
    --qwen3_tts_language german \
    --enable_lang_prompt
```

`serve` lauscht standardmäßig nur auf `127.0.0.1:8765` – gut so, der
SSH-Tunnel holt es zum Roboter. Damit Windows den WSL-Port auf
`127.0.0.1` sieht, in `%UserProfile%\.wslconfig` eintragen:

```ini
[wsl2]
networkingMode=mirrored
```

> Hinweis: Das lokale LLM entscheidet, wann `ask_claude` aufgerufen wird.
> Ein 4B-Modell ist dafür knapp; wenn Aufträge nicht zuverlässig weitergegeben
> werden, ein größeres Modell wählen (siehe speech-to-speech-README, z. B. über
> llama.cpp). Alternative ohne GPU: Standard-HF-Cloud-Backend
> (`HF_REALTIME_CONNECTION_MODE=deployed`) – dann geht Audio aber zu Hugging Face.

### 4.4 SSH-Tunnel zum Roboter (empfohlen)

```powershell
cd reachy-claude
powershell -ExecutionPolicy Bypass -File .\start-tunnel.ps1 -Robot reachy-mini.local -User pollen
```

Der Tunnel macht auf dem **Roboter** `127.0.0.1:8765` (Sprache) und
`127.0.0.1:8787` (Bridge) verfügbar. Vorteile: alles verschlüsselt, keiner der
Dienste ist im WLAN offen, keine Firewall-Regeln nötig. Für dauerhaften Betrieb
SSH-Schlüssel einrichten (`ssh-keygen`, `ssh-copy-id`-Äquivalent) statt Passwort.

**Alternative „direkt im WLAN“** (ohne Tunnel): `CLAUDE_BRIDGE_HOST` = LAN-IP des
PCs, `CLAUDE_BRIDGE_ALLOWED_CLIENTS` = IP von Reachy, Windows-Firewall-Regel nur
für Reachys IP, am besten mit `CLAUDE_BRIDGE_TLS_CERT/_KEY` (HTTPS). Das
speech-to-speech-Backend hat **keine Authentifizierung** – im WLAN-Modus
unbedingt per Firewall auf Reachys IP beschränken.

## 5. Roboter einrichten

> Die Conversation-App läuft auf dem Roboter. Wir starten sie per SSH aus einem
> eigenen Ordner, damit unsere `.env` gilt.

```bash
# vom PC aus (im Ordner reachy-claude): Roboter-Teil und Patch kopieren
ssh pollen@reachy-mini.local "mkdir -p ~/reachy_claude"
scp -r robot patches pollen@reachy-mini.local:~/reachy_claude/

# auf dem Roboter
ssh pollen@reachy-mini.local
git clone https://github.com/pollen-robotics/reachy_mini_conversation_app.git
cd reachy_mini_conversation_app
git checkout 5eb39ed1c96790390363cca85d4088ff27a0fdff          # getesteter Stand
git apply ~/reachy_claude/patches/listening_motion.patch       # optional, siehe unten
pip install -e .            # in die Python-Umgebung des Roboters (oder "uv sync")
cp ~/reachy_claude/robot/.env.example .env
nano .env                   # CLAUDE_BRIDGE_TOKEN = Token aus der PC-.env
```

Die `.env` (Vorlage `robot/.env.example`) setzt:

- `HF_REALTIME_CONNECTION_MODE=local`, `HF_REALTIME_WS_URL=ws://127.0.0.1:8765/v1/realtime`
- `REALTIME_TRANSCRIPTION_LANGUAGE=de`
- externe Profile/Tools + `REACHY_MINI_CUSTOM_PROFILE=claude_coder`
- `CLAUDE_BRIDGE_URL=http://127.0.0.1:8787` und `CLAUDE_BRIDGE_TOKEN`

### Patch „Zuhör-Bewegung“ (`patches/listening_motion.patch`)

Die Conversation-App **friert** beim Zuhören die Antennen ein und stoppt das
„Atmen“. Der Patch ersetzt das durch eine kleine, weich ein- und ausgeblendete
Bewegung: Antennen wippen gegenläufig (±7°), der Kopf neigt sich leicht (6°)
und nickt minimal (±2°). Er ändert nur `moves.py` (+ Tests) und wurde gegen die
Upstream-Testsuite geprüft (siehe 8). Ohne Patch funktioniert alles andere
genauso – Reachy folgt dann beim Zuhören nur deinem Gesicht.

Langfristig sinnvoll: als Pull Request bei Pollen einreichen, damit der Patch
nicht bei jedem Update neu angewendet werden muss.

## 6. Starten & benutzen

Reihenfolge:

1. PC: Sprach-Backend starten (WSL2, 4.3)
2. PC: `start-bridge.ps1`
3. PC: `start-tunnel.ps1`
4. Roboter (SSH): `cd ~/reachy_mini_conversation_app && reachy-mini-conversation-app`
   (mit `--ui` zusätzlich Weboberfläche auf Port 7860)

Reachy wacht auf und begrüßt dich. Beispiele:

| Du sagst | Ergebnis |
|---|---|
| „Frag Claude, was die Funktion `login` in `auth.py` macht.“ | Claude liest Code, Reachy erklärt |
| „Claude soll in `calc.py` eine Funktion zum Subtrahieren ergänzen.“ | Datei wird geändert, Reachy fasst zusammen |
| „Was hast du gerade geändert?“ | gleiche Claude-Sitzung, Kontext bleibt |
| „Fang mit Claude ein neues Thema an: …“ | neue Claude-Sitzung |
| „Ist Claude schon fertig?“ | Reachy prüft den Hintergrund-Auftrag (`task_status`) |
| „Geh schlafen.“ | Reachy legt sich hin, App endet |

Änderungen prüfen: im Projektordner `git diff`. Die vollständigen Antworten
(mit Code) stehen in `bridge/transcripts/`. Eine Sitzung kannst du am PC mit
`claude --resume <Session-ID aus der Mitschrift>` weiterführen.

## 7. Fehlersuche

| Reachy sagt / Symptom | Ursache & Lösung |
|---|---|
| „Ich erreiche Claude auf dem PC gerade nicht.“ | Bridge oder Tunnel läuft nicht → `start-bridge.ps1`, `start-tunnel.ps1` |
| „… hat die Anfrage abgelehnt …“ | Token ungleich, Uhrzeit von PC/Roboter > 60 s verschieden, oder IP nicht in `ALLOWED_CLIENTS` |
| „Claude arbeitet noch am vorigen Auftrag.“ | Es läuft immer nur ein Auftrag gleichzeitig – warten oder `task_cancel` |
| „Claude hat nach 15 Minuten nicht geantwortet …“ | `CLAUDE_BRIDGE_TIMEOUT_S` erhöhen oder Auftrag aufteilen |
| „Claude Code ist mit einem Fehler beendet worden.“ | Bridge-Konsole lesen; oft: nicht eingeloggt → am PC einmal `claude` starten |
| Bridge startet nicht | `claude_bridge check` – die Meldung nennt die Einstellung |
| Reachy gibt Aufträge nicht weiter | Profil aktiv? (`REACHY_MINI_CUSTOM_PROFILE=claude_coder`); lokales LLM ggf. zu klein (4.3) |
| `TimeoutError` beim Start der App | Reachy-Daemon läuft nicht |

## 8. Entwicklung & Tests

Struktur:

```
reachy-claude/
├── plan.md                 Plan, Entscheidungen, Recherche
├── README.md               diese Datei
├── SECURITY.md             Bedrohungsmodell & Maßnahmen
├── start-tunnel.ps1        SSH-Tunnel (Windows)
├── bridge/                 PC-Dienst (Python ≥3.11, einzige Abhängigkeit: websockets)
│   ├── src/claude_bridge/
│   │   ├── listen.py       Stufe 1: Gespräch von Reachy mitlesen (WebSocket /rpc)
│   │   ├── config.py       .env laden + strenge Validierung
│   │   ├── signing.py      HMAC-Protokoll v1, Replay-Schutz
│   │   ├── runner.py       claude -p sicher aufrufen, Sitzungen, Timeout
│   │   ├── speech.py       Vorlesetext aus der Antwort
│   │   ├── server.py       HTTP-Server (IP-Allowlist, Limits, ein Auftrag gleichzeitig)
│   │   └── __main__.py     CLI: listen | serve | check | gen-token
│   ├── tests/              pytest inkl. Fake-Claude-CLI (auch als .cmd unter Windows)
│   ├── .env.example
│   ├── listen.ps1          Stufe 1 starten (Windows)
│   └── start-bridge.ps1    Stufe 2 starten (Windows)
├── robot/
│   ├── external_tools/ask_claude.py           Tool (Einzeldatei, nur stdlib)
│   ├── external_profiles/claude_coder/profile.md
│   ├── tests/              Tool-Tests, End-to-End mit echter Bridge, Integration mit echter App
│   └── .env.example
└── patches/listening_motion.patch            Zuhör-Bewegung für die Conversation-App
```

Tests ausführen:

```bash
# Bridge (Windows: .venv\Scripts\python -m ...)
cd reachy-claude/bridge
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy && .venv/bin/pytest -q

# Roboter-Tool (nutzt die Bridge aus ../bridge/src)
cd ../robot
../bridge/.venv/bin/pytest -q
```

Der Integrationstest `robot/tests/test_conversation_app_integration.py` lädt
Tool und Profil mit dem **echten Loader** der Conversation-App; er läuft nur,
wenn die App installiert ist (sonst „skipped“). Lokal:
`<conversation-app-venv>/bin/python -m pytest -q` im Ordner `robot/`.

Patch testen: im Klon der Conversation-App `git apply …/listening_motion.patch`
und deren Suite laufen lassen (`pytest tests/test_moves.py`).

CI: `.github/workflows/tests.yml` (Bridge auf Ubuntu **und
Windows**, Roboter-Tool auf Ubuntu).

Design-Entscheidungen:

- **Minimale Abhängigkeiten**: Roboter-Tool nur Standardbibliothek; Bridge nur `websockets`
  (für `listen`, selbst ohne weitere Abhängigkeiten) → kleine Angriffsfläche.
- **Stufenweise Inbetriebnahme**: `listen` (nur mitlesen) → `serve` (Claude) → lokale Sprache.
- **Dependency Injection**: Der Server kennt nur das `AskService`-Protokoll;
  Tests ersetzen Claude durch Fakes.
- **Unveränderliche Konfiguration** (`frozen` Dataclass), „fail fast“ bei unsicheren Werten.
- **Kein Fork** der Conversation-App: nur offizielle Erweiterungspunkte + kleiner, optionaler Patch.
- **Protokoll v1** (HMAC) ist in Bridge und Tool doppelt implementiert, weil
  externe Tools Einzeldateien sind; ein Test stellt sicher, dass beide gleich rechnen.

## 9. Stand & nächste Schritte

**Verifiziert (2026-10-08) – Stufe 1 `listen`**

- 19 neue Tests mit nachgebautem Reachy (Anzeige, Mitschrift, Neuverbinden, Steuerzeichen-Filter) ✅
- Lauf gegen den **echten** JSON-RPC-Server aus dem Reachy-SDK (`reachy_mini.apps.jsonrpc_server`,
  so wie ihn die Conversation-App `5eb39ed` einbindet) ✅
- Noch nicht am echten Reachy getestet

**Verifiziert (2026-10-02)**

- Bridge: 80 Tests (inkl. `listen`), ruff, mypy `--strict` ✅
- Roboter-Tool: 16 Tests inkl. Integration mit Conversation-App `5eb39ed` ✅
- Patch: Upstream-Suite 459 ✅ (3 Avatar-Tests schlagen dort auch ohne Patch fehl – Umgebungsthema der Upstream-Suite)
- **Echter End-to-End-Lauf** Tool → Bridge → Claude Code CLI 2.1.287:
  Datei geändert ✅, Folgefrage mit fortgesetzter Sitzung ✅, Shell-Befehl verweigert ✅

**Noch nicht auf echter Hardware getestet**

- Conversation-App auf dem Reachy Mini Wireless mit unserem Profil/Tool
- speech-to-speech unter WSL2 auf deinem PC (deutsche Spracherkennung/-ausgabe, Tool-Aufrufe durch das lokale LLM)
- Zuhör-Bewegung am echten Roboter (Amplituden ggf. in `moves.py` anpassen: `LISTENING_*`)
- SSH-Benutzername/Pfade auf dem Roboter (Beispiele nutzen `pollen`)

**Ideen für später**

- Bridge als Windows-Autostart (Aufgabenplanung) einrichten
- Sprachliche Bestätigung vor riskanten Aufträgen („Soll ich das wirklich …?“)
- Optionale Rechtestufe „Tests ausführen“ mit eng begrenzter Bash-Allowlist (z. B. `Bash(npm test)`)
- Zuhör-Bewegung als Pull Request bei Pollen einreichen
- Kosten pro Auftrag (`total_cost_usd`) in der Mitschrift anzeigen
