# Sicherheit – Reachy Claude

Sprache steuert hier ein Programm, das **Dateien auf deinem PC ändern** kann.
Dieses Dokument beschreibt, wovor wir uns schützen, wie, und was bewusst
offen bleibt. Bei Änderungen an Bridge, Tool oder Profil bitte mitpflegen.

## Schützenswert

1. Dein PC und der Projektordner (Code, Geheimnisse in Dateien)
2. Das Bridge-Token
3. Deine Sprache/Gespräche (Privatsphäre)
4. Dein Claude-Konto (Kosten)

## Bedrohungen und Maßnahmen

| # | Bedrohung | Maßnahmen | Wo |
|---|---|---|---|
| T1 | Ein anderes Gerät im WLAN schickt Aufträge an die Bridge | Bridge lauscht standardmäßig nur auf `127.0.0.1` (SSH-Tunnel); IP-Allowlist (Pflicht, `/0` verboten); `0.0.0.0` nur mit ausdrücklichem Opt-in | `config.py`, `server.py` |
| T2 | Gefälschte oder manipulierte Anfragen | HMAC-SHA256 über Methode, Pfad, Zeitstempel, Nonce und Body; Token wird nie übertragen; Vergleich in konstanter Zeit | `signing.py` |
| T3 | Mitgeschnittene Anfrage wird erneut gesendet (Replay) | Zeitfenster ±60 s + Nonce-Speicher; Nonce wird erst **nach** gültiger Signatur gespeichert (kein Auffüllen durch Fremde) | `signing.py` |
| T4 | Untergeschobene Antwort, die Reachy vorliest | Antwort ist an die Nonce der Anfrage gebunden und signiert; Tool verwirft unsignierte/falsche Antworten | `ask_claude.py` |
| T5 | Mitlesen im WLAN | SSH-Tunnel (empfohlen) bzw. optional TLS ≥ 1.2 in der Bridge | `start-tunnel.ps1`, `server.py` |
| T6 | Fehlerkennung, fremde Stimmen (TV, Gäste), Prompt-Injection per Sprache | Weitergabe nur im Profil `claude_coder` und nur bei Ansprache von Claude; Claude darf **nie** Shell, Internet oder MCP; Rechtestufe `read` möglich; Projekt in Git → jede Änderung prüf-/rücknehmbar; Länge begrenzt | `profile.md`, `runner.py` |
| T7 | Claude richtet Schaden an | `--permission-mode dontAsk` + feste Allowlist (`Read, Grep, Glob, LS, TodoWrite` [+ `Edit, MultiEdit, Write`]); `Bash, WebFetch, WebSearch, NotebookEdit` immer verboten; `--strict-mcp-config`; festes Arbeitsverzeichnis; `--max-turns`; Timeout beendet den ganzen Prozessbaum; nur ein Auftrag gleichzeitig | `runner.py`, `server.py` |
| T8 | Shell-/Argument-Injection beim Start von `claude` | kein `shell=True`; Argumentliste ohne Nutzereingaben; Prompt nur über stdin; Session-ID per Regex geprüft; System-Prompt ohne `cmd.exe`-Sonderzeichen (Test), wichtig falls `claude` eine `.cmd`-Datei ist („BatBadBut“) | `runner.py`, `test_runner.py` |
| T9 | Claude liest das Bridge-Token | Token wird aus der Umgebung des Claude-Prozesses entfernt; Start wird verweigert, wenn die `.env` im Arbeitsordner liegt | `runner.py`, `config.py` |
| T10 | Überlastung / Kostenexplosion | Rate-Limit (Standard 10/min), Body ≤ 64 KB, Prompt ≤ 4000 Zeichen, Lese-Timeout 15 s, ein Auftrag gleichzeitig, `--max-turns` | `server.py`, `config.py` |
| T11 | Geheimnisse in Logs / Git | Prompts werden standardmäßig nicht geloggt; Token nie ausgegeben (Test); `.env`, `transcripts/`, `*.pem` in `.gitignore` | `server.py`, `.gitignore` |
| T12 | Sprachdaten verlassen das Haus | lokales Sprach-Backend; Cloud-Tools im Profil deaktiviert | `README.md` §2 |
| T13 | Supply-Chain | Bridge und Tool ohne Laufzeit-Abhängigkeiten (nur Standardbibliothek); Conversation-App auf geprüften Commit gepinnt | `pyproject.toml`, `README.md` |

## Bewusst offen / Restrisiken

- **Das speech-to-speech-Backend hat keine Authentifizierung.** Daher nur über
  den SSH-Tunnel bzw. auf `127.0.0.1` betreiben; im WLAN-Modus per
  Windows-Firewall auf Reachys IP beschränken.
- **Jeder Prozess auf dem Roboter** kann die Tunnel-Ports erreichen. Die Bridge
  ist durch das Token geschützt; das Token liegt in der `.env` der
  Conversation-App auf dem Roboter → Roboter-Zugang (SSH-Passwort!) absichern.
- **Prompt-Injection über Dateiinhalte**: Liest Claude präparierte Dateien im
  Projekt, könnte es sich zu ungewollten *Datei*änderungen verleiten lassen.
  Shell/Internet bleiben trotzdem gesperrt; Änderungen sind per Git sichtbar.
- `Write`/`Edit` sind auf Claude-Code-Ebene auf das Arbeitsverzeichnis
  begrenzt; diese Grenze setzt Claude Code durch, nicht die Bridge.
- **Kein Sprecher-Erkennung**: Wer im Raum spricht, kann Aufträge geben. Bei
  Bedarf Rechtestufe `read` nutzen oder Bridge nur bei Anwesenheit starten.
- Der Vorlesetext stammt von Claude und wird nur bereinigt, nicht geprüft.

## Token wechseln

```powershell
.\.venv\Scripts\python.exe -m claude_bridge gen-token
```
Neues Token in `bridge/.env` (PC) **und** in der `.env` der Conversation-App
(Roboter) eintragen, beides neu starten.
