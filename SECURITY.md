# Sicherheit – Reachy Claude (v2)

Sprache steuert ein Programm, das Dateien auf deinem PC ändern kann (ab Schritt 4).
Dieses Dokument hält fest, wovor wir uns schützen und was bewusst offen bleibt.
Bei jeder Änderung mitpflegen. (v1-Bedrohungsmodell: [`legacy/SECURITY.md`](legacy/SECURITY.md))

## Schützenswert
1. Dein PC und der Projektordner  2. Deine Sprache/Gespräche  3. Dein Claude-Konto (Kosten)

## Maßnahmen

| # | Bedrohung | Maßnahme | Stand |
|---|---|---|---|
| S1 | Fremde im Netz greifen auf den PC zu | Die App öffnet **keinen Port**; sie verbindet sich selbst zum Roboter | ✅ |
| S2 | Sprache verlässt das Haus | Spracherkennung (Whisper) und -ausgabe lokal auf dem PC; Audio nur im Heimnetz (WebRTC, Signalisierung auf dem Roboter); Modelle nur einmalig heruntergeladen | ✅ |
| S3 | Versehentliche Aufträge (Fernseher, Gäste, Fehlerkennung) | Nur Sätze mit Aktivierungswort „Claude“ (am Satzanfang) gehen weiter; „Claude“ allein öffnet nur 8 s lang; ein Auftrag gleichzeitig; Claude ist angewiesen, bei Unklarheit nachzufragen | ✅ |
| S4 | Claude richtet Schaden an | `--restricted --tools Read,Grep,Glob,Edit,Write`: nur Datei-Werkzeuge und **nur im Projektordner** (gegen die echte CLI geprüft; **bis 2026-10-09 fehlte das – Claude konnte per `../` überall lesen und schreiben**, gefunden von der Prüfrunde), keine Shell (auch nicht PowerShell), kein Internet, keine Subagenten/Skills/MCP-Server, keine Einstellungsdateien oder Hooks (weder aus dem Projekt noch aus deiner normalen Claude-Konfiguration); zusätzlich `--permission-mode dontAsk` + Sperrlisten; Dateien, die später andere Programme ausführen/auswerten (`.git/`, `.github/`, `.husky/`, `.githooks/`, `.vscode/`, `.idea/`, `.claude/`, `CLAUDE.md`), sind nie bearbeitbar; Timeout beendet den Prozessbaum; Prompt nur über stdin; Projektordner darf nicht das Laufwerk, dein Benutzerordner (oder darüber), AppData oder der Ordner dieser App sein; `claude_programm` nur `claude`/`claude.exe`/`claude.cmd`, nie aus dem aktuellen Ordner | ✅ |
| S12 | Gemerkte Einstellungen (`app/einstellungen.toml`) mit unsinnigen/gefährlichen Werten | Roboter-Adresse nur Hostname/IP (keine URL-Teile), Stimmenname streng geprüft (kein `..`/`/`, landet in Dateipfaden), Fehler werden vor dem Speichern erkannt – die Datei bleibt dann unverändert | ✅ |
| S13 | Claude macht etwas Ungewolltes und läuft lange | „Claude, stopp“ beendet den laufenden Auftrag sofort (ganzer Prozessbaum) – auch wenn er gerade erst startet; im Nachlauf verwirft „stopp“ den diktierten Auftrag, statt ihn mitzuschicken (Fund der Prüfrunde). Reachy sagt ehrlich, dass schon ein Teil erledigt sein kann. Beim Beenden der App (Strg+C) wird ein laufender oder startender Auftrag still abgebrochen – kein Claude-Prozess läuft weiter | ✅ |
| S14 | Veraltete Reachy-Software unbemerkt | Startprüfung fragt Reachys Version im Heimnetz ab und warnt bei bekannten Lücken (S10) | ✅ |
| S5 | Manipulierte Texte im Terminal (Steuerzeichen) | Erkannte Texte werden vor Anzeige/Weitergabe bereinigt | ✅ |
| S6 | Supply-Chain | wenige, verbreitete Abhängigkeiten; Reachy-SDK auf `~=1.11.0` begrenzt | ✅ |
| S7 | Aufnahmen/Mitschriften auf der Festplatte | Audio-Test-WAV in `app/aufnahmen/`, Claude-Mitschriften in `app/mitschriften/` – nur lokal, nicht in Git | ✅ |
| S9 | Bewegungen | Kleine, geglättete Bewegungen; harte Grenzen (Kopf ±15°, ±10 mm, Antennen 0–60°); Netzfehler beim Senden brechen nicht ab; beim Beenden weich in Grundstellung, dann Schlafhaltung | ✅ |
| S10 | Bekannte Lücken in Reachys eigenem Dienst (Pollen, Stand 2026-10-08) | Betreffen die Software **auf dem Roboter**, nicht unser PC-Paket. Datei-Upload ohne Anmeldung (CVE-2026-55419): behoben ab 1.8.2 → Reachy über das Dashboard aktuell halten. Bluetooth-PIN-Umgehung (GHSA-993g-hgjh-whmf): behoben in 1.12.0, noch nicht veröffentlicht. Pfad-Trick in Bluetooth-Befehlen (CVE-2026-62661, hoch): noch kein Fix → Bluetooth nur koppeln, wenn nötig; Fremdgeräte ins Gäste-WLAN. Sobald 1.12 erscheint: Roboter updaten, dann `reachy-mini`-Version der App anheben | ⚠️ |
| S11 | Angriffe über GitHub (KI-Workflows) | Keine KI-Agenten in GitHub Actions; CI führt nur Tests aus, Rechte `contents: read`, keine Secrets | ✅ |
| S8 | Daten an Anthropic | Nur der Auftrag und die Projektdateien (nur aus dem Projektordner, S4), die Claude für den Auftrag liest; Telemetrie der Claude CLI und von Hugging Face abgeschaltet. Projektordner bewusst wählen (keine Geheimnisse darin) | ✅ |

## Bewusst offen / Restrisiken
- **Reachys eigene Dienste** (Daemon-API Port 8000, WebRTC-Signalisierung Port 8443,
  Dashboard) sind im WLAN **ohne Passwort** erreichbar. Das ist das Design von Pollen,
  nicht unser Code. Wer im Heimnetz ist, kann Reachy steuern bzw. mithören.
  Empfehlung: Gäste-WLAN für fremde Geräte.
- Der WebRTC-Ton zwischen Reachy und PC ist verschlüsselt (WebRTC/DTLS); die
  Signalisierung (`ws://`, Port 8443) nicht.
- Was Claude im Projektordner ändert, wird später oft ausgeführt (dein eigener Code, Build-Skripte).
  Änderungen deshalb vor dem Ausführen ansehen (z. B. `git diff`).
- Keine Sprechererkennung: Jeder im Raum kann „Claude, …“ sagen – und auch „Claude, stopp“.
- Während Reachy spricht, hört er nicht zu (sonst Selbstgespräch): „stopp“ in einer Sprechpause sagen.
- **Kamerabild:** Die WebRTC-Verbindung des SDK überträgt fest auch Reachys Kamerabild an den PC
  (mehr Netzlast im Heimnetz). Es wird weder gespeichert noch ausgewertet. Ein „nur Audio“-Modus
  existiert im SDK (1.11 und main) nicht; Entscheidung des Nutzers (2026-10-08): **so lassen**.
