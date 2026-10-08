# plan.md — Reachy ↔ Claude Sprachsteuerung ("Reachy Claude")

## v2 (FREIGEGEBEN 2026-10-08, in Umsetzung): schlanke PC-App ohne Conversation-App

### Entscheidungen des Nutzers (2026-10-08)
1. Aktivierungswort **„Claude“**.
2. v1-Teile nach **`legacy/`** verschoben.
3. Umsetzung schrittweise; jeder Schritt wird am echten Reachy getestet.

### Fortschritt
- [x] Schritt 1: Audio-Test `reachy-claude check-audio` – **am Reachy erfolgreich** (Sprache −14…−18 dB, Raum ~−40 dB)
- [x] Schritt 2: Spracherkennung + Aktivierungswort `reachy-claude listen` – **am Reachy erfolgreich** (GPU, „Claude“ zuverlässig)
- [x] Schritt 3: Sprachausgabe `reachy-claude say` / Antworten in `listen` – wartet auf Test am Reachy
- [x] Schritt 3 am Reachy bestaetigt (Satz vollstaendig, Aussprache passt)
- [x] Schritt 4: Claude anbinden (`listen -Projekt …`) – echter CLI-Durchlauf ok; wartet auf Test am Reachy
- [x] Schritt 4 am Reachy bestaetigt
- [x] Schritt 5: Bewegungen + Stimmenauswahl – **am Reachy bestaetigt** („fuers Erste okay“)
- [x] Sicherheits-Nachbesserung (vor Schritt 6, freigegeben 2026-10-08): Projekt-Einstellungen/Hooks ignoriert,
      Steuer-Ordner gesperrt; Reachy-Luecken in SECURITY.md (S10)
- [x] Schritt 6: Doppelklick-Start, Startpruefung, alles merken, „stopp“/„wiederhole“ – wartet auf Test am Reachy
- [x] Nachbesserung lange Auftraege (Schnitt nach 20 s / Denkpausen / mitwandernde Schwelle) – wartet auf Test am Reachy
- [ ] Danach: Branch nach `main` (nur mit Zustimmung)

### Plan Nachbesserung „lange Auftraege“ (freigegeben 2026-10-08, Variante „Nachlauf 2 s“; umgesetzt)
Fehlerbild (Nutzer): Bei laengeren gesprochenen Prompts bricht die Aufnahme ab und ggf. geht nur der
halbe Prompt an Claude. Ursachen (mit synthetischer Sprache nachgestellt):
1. harte Grenze `max_speech_s = 20` → 25 s Sprache wird zu [20 s, 6 s]; der Rest ohne „Claude“ wird ignoriert
2. `end_silence_s = 0.8` → jede Denkpause > 0,8 s beendet den Satz
3. Grundrauschen wird auch *waehrend* des Sprechens nachgefuehrt → Schwelle steigt, leise Woerter
   gelten als Stille → Schnitt mitten im fluessigen Sprechen (z. B. nach 10,9 von 15 s)
Massnahmen:
- A: Grundrauschen waehrend eines Satzes einfrieren; im Satz Hysterese (weiter = 3 dB ueber Rauschen,
  Start bleibt 6 dB) → leise Woerter halten den Satz offen
- B: Hoechstlaenge 20 s → 120 s (Whisper verarbeitet lange Aufnahmen in Abschnitten)
- C: Satzende nach 1,2 s Pause (statt 0,8 s)
- D: „Nachlauf“ nur fuer Auftraege: nach einem „Claude, …“-Satz noch 2 s warten; sprichst du weiter,
  wird der naechste Satz angehaengt (beliebig oft). Terminal zeigt „(hoere weiter zu …)“.
  Folge: ca. 3 s nach deinem letzten Wort geht der Auftrag los (bisher ca. 1 s).
- Tests: die drei Faelle oben als Regressionstests (vorher rot, nachher gruen), echte Testaufnahme
  muss weiterhin 4 Saetze liefern; Nachlauf-Test mit Simulation.

### Plan Schritt 6 (freigegeben 2026-10-08: alle vier Teile)
Ziel: Starten ohne Tippen von Parametern, verstaendliche Fehler vorab, sauberer Abschluss.
1. **Doppelklick-Start** `Reachy-Claude.cmd` im Hauptordner: startet `listen` ohne ExecutionPolicy-Getippe;
   Fenster bleibt bei Fehlern offen. Befehl `verknuepfung` legt eine Desktop-Verknuepfung an.
   Standardbefehl des Startskripts wird `listen` (statt `check-audio`).
2. **Alles merken:** Roboter-Adresse, Stimme/Sprecher, Bewegung an/aus in `app/einstellungen.toml`
   (wie Projektordner/Rechte heute) – einmal mit Parameter setzen, danach nie wieder noetig.
3. **Startpruefung** `pruefen` (laeuft auch kurz vor jedem `listen`): Python-Umgebung, GPU, Claude CLI
   installiert/angemeldet, Projektordner gesetzt, Reachy erreichbar (Ports 8000/8443), **Reachy-Version**
   ueber `GET /api/daemon/status` → Warnung bei bekannten Luecken (S10, < 1.8.2). Jede Meldung mit
   konkretem „So behebst du es“.
4. **Sprachbefehle Feinschliff:** „Claude, stopp/abbrechen“ bricht einen laufenden Auftrag ab (Prozessbaum
   beenden, Reachy sagt „Abgebrochen.“); „Claude, wiederhole“ liest die letzte Antwort nochmal vor.
5. Tests (Startpruefung mit Fakes, Einstellungen, Sprachbefehle), README als Kurzanleitung
   „Installation → Doppelklick → sprechen“, SECURITY/plan pflegen, CI gruen.
6. Nach deinem Test am Reachy: Branch nach `main` uebernehmen (nur mit deiner Zustimmung).

### Entscheidung Netzlast (2026-10-08)
- Nutzer bemerkte mehr Ethernet-Last bei laufender App. Ursache: `GstWebRTCClient` empfängt fest
  Kamera-Video (H.264) + Audio; kein „nur Audio“-Modus im SDK. Optionen: so lassen / Video-Transceiver
  per SDK-Interna inaktiv setzen / Feature-Wunsch bei Pollen. **Entscheidung: so lassen.**

### Erkenntnisse lange Auftraege (2026-10-08)
- Satzerkennung: Schwelle im Satz eingefroren (Rauschen beim Satzbeginn + 4 dB statt aktuell + 6 dB),
  Schaetzung laeuft weiter. Satzende 1,2 s, Hoechstlaenge 120 s, 0,5 s Einmessen nach dem Start
  (ohne: Schaetzung aus 6 Messwerten → ganze Testaufnahme als ein Satz).
- Risiko des Einfrierens: anspringender Luefter = endloser „Satz“. Loesung: gleichmaessig lautes
  Fenster (10 %..90 % < 3 dB, und selbst die leisen Anteile ueber der Satzschwelle) beendet den Satz.
  Erst 6 dB gewaehlt → hat lauten synthetischen Sprecher (Ton mit nur 3,7 dB Schwankung) verworfen.
  Daher 3 dB und solche Abschnitte **nicht verwerfen**, sondern an Whisper geben (filtert selbst).
- Nachlauf in **Audiozeit** gezaehlt (2 s Mikrofon ohne neue Sprache) – im Echtbetrieb gleich, im Test
  deterministisch. Steuerwoerter (`immediate`) ohne Nachlauf. Wiederholtes „Claude,“ wird beim Anhaengen entfernt.
- Gegenproben: alle vier alten Verhaltensweisen (20 s, 0,8 s, mitwandernde Schwelle, keine
  Dauergeraeusch-Erkennung) lassen je mindestens einen Regressionstest rot werden.
- Synthetische Sprache fuer Tests braucht echte Silben-Modulation, sonst sieht sie wie ein Luefter aus.

### Erkenntnisse Schritt 6 (2026-10-08)
- Reachys Daemon liefert seine Version: `GET http://<reachy>:8000/api/daemon/status` → `"version": "1.11.0"`
  (gegen echten Daemon im Simulationsmodus geprueft). Damit prueft `pruefen` die Luecken aus S10.
- `claude auth status --json` → `{"loggedIn": true, ...}` – Anmeldung pruefbar ohne Netzanfrage an Claude.
- „stopp“ braucht Zuhoeren waehrend Claude arbeitet → Auftraege laufen jetzt im Hintergrund
  (`ClaudeAssistant.submit`), `SpeechGate` serialisiert Reachys Saetze und meldet „weghoeren“, damit
  Hintergrund-Ansagen („Claude arbeitet noch.“ beginnt mit „Claude“!) nicht als Auftrag zurueckkommen.
- Abbruch: `ClaudeRunner.cancel()` beendet den Prozessbaum (eigenes Lock, da `ask` das Auftrags-Lock haelt);
  echte CLI: nach 4 s abgebrochen, Prozess weg, naechster Auftrag normal.
- Steuerwoerter nur, wenn der *ganze* Auftrag eines ist („wiederhole den Test“ geht an Claude).
- Einstellungen: `[reachy]` (roboter, stimme, sprecher, bewegung) neben `[claude]`; Werte werden vor dem
  Schreiben geprueft; neue Stimme ohne Sprecher loescht den alten Sprecher; `say -Stimme` speichert nicht.
- `.cmd` braucht CRLF → `.gitattributes`; `pause` nur bei Fehler (Fenster bleibt offen); im CI mit `< NUL`.
- Desktop-Pfad ueber `GetFolderPath(Desktop, Create)` (leer, falls Ordner fehlt, ohne `Create`).
- CLI-Tests laufen im Temp-Ordner (sonst wuerden sie die echte `einstellungen.toml` ueberschreiben).

### Erkenntnisse Sicherheits-Nachbesserung (2026-10-08)
- Anlass: externe Auswertung (Reachy-Luecken, Claude-Actions). Stellungnahme: Reachy-Luecken betreffen den
  Daemon auf dem Roboter (nicht unser PC-Paket); Claude-Actions nutzen wir nicht (CI nur Tests, `contents: read`).
- **Echte Luecke gefunden und per Test mit echter CLI belegt:** `claude -p` fuehrt Hooks aus
  `<Projekt>/.claude/settings.json` aus (SessionStart, UserPromptSubmit) – an `--disallowedTools Bash` vorbei.
  Fix: `--setting-sources user` → Hooks liefen nicht mehr (auch ueber `ClaudeRunner` geprueft).
- Schreiben in `.claude/`, `.git/`, `.vscode/` blockiert die CLI schon selbst; zusaetzlich ausdruecklich
  `Edit(.claude/**)` usw. gesperrt (gitignore-Muster, wirkt auch in Unterordnern, gilt auch fuer Write – getestet).

### Erkenntnisse Schritt 5
- SDK: `set_target(head=4x4, antennas=[rechts, links] rad)` per WebSocket, 25 Hz; `create_head_pose(x,y,z,roll,pitch,yaw,
  mm=True, degrees=True)`; Pitch > 0 = nach unten (Schlafpose 24° + 44 mm tiefer); Antennen (-0.17, +0.17) aufrecht,
  (-3.05, +3.05) flach. `enable_wobbling()` laesst den Daemon den Kopf zur eingehenden WebRTC-Sprache bewegen.
- Pollens „Atmen“ als Massstab (Kopf ±5 mm/0,1 Hz, Antennen ±15°/0,5 Hz). Eigene Stimmungen IDLE/LISTENING/THINKING/
  SPEAKING + „acknowledge“ beim Aktivierungswort; Glaettung mit Zeitkonstante 0,35 s; harte Grenzen.
- Echter Daemon im Modus `--mockup-sim --no-media`: wake_up 2,5 s, goto_sleep 4 s, Kopf folgt den Stimmungen.
- Stimmen: 10 deutsche Piper-Stimmen (rhasspy/piper VOICES.md), Mehrsprecher-Stimmen ueber `speaker_id_map`
  (Name oder Nummer), Befehl `voices`, Startskript `-Stimme/-Sprecher`.

### Erkenntnisse Schritt 4
- v1-Bausteine uebernommen: `claude.py` (aus legacy/bridge runner.py, ohne Token/HTTP) und `spoken.py`
  (speech.py) inkl. Tests und Fake-CLI (`.cmd` unter Windows).
- Einstellungen in `app/einstellungen.toml` (tomllib); `-Projekt` speichert, Handaenderungen bleiben erhalten.
- `assistant.py`: Claude im Thread, alle 45 s „Claude arbeitet noch.“; Terminal zeigt die volle Antwort
  (Einrueckung bleibt, Steuerzeichen raus), Vorlesen nur SPRECHTEXT; „neues Thema“ (Hoeflichkeitswoerter
  wie „bitte“ sind kein Auftrag – per Test gefunden).
- Echter Durchlauf mit Claude Code CLI: 3 Auftraege (aendern 16 s, Folgefrage 8 s, neues Thema 18 s) ok.

### Erkenntnisse Schritt 3
- Piper 1.8 (`PiperVoice.load/synthesize`, Chunks mit `audio_float_array`), Stimme `de_DE-thorsten-medium`
  per `hf_hub_download` aus `rhasspy/piper-voices` nach `app/voices`. Ausgabe auf 16 kHz umgerechnet
  (linear), Spitze auf 0,8 normiert. Lokal: 4,2 s Sprache in 0,6 s erzeugt (schwache Cloud-CPU).
- **Fehler am echten Reachy (`say`, keine Stimme, Warnung „AppSrc is not initialized“):** Bei WebRTC ist
  `start_playing()` ein No-op; der Sendeweg wird erst aufgebaut, wenn der Mikrofon-Strom ankommt (gleicher
  Callback im SDK). `say` sendete direkt nach dem Verbinden → Ton verworfen. Fix: `robot.wait_for_audio()`
  wartet auf die ersten Mikrofon-Daten (oeffentliche API) vor jeder Ausgabe; Abspiel-Nachlauf 0,5 s.
- **Reachy hat Hardware-Echounterdrueckung** (XMOS-Audiochip, AEC im SDK `audio_gstreamer.py`/`audio_control_utils.py`):
  der eigene Lautsprecher wird aus dem Mikrofon herausgerechnet. Folge: Messung Lautsprecher→Mikrofon per
  Piepton unmoeglich (am Reachy „nicht erkannt“) → wieder entfernt. Gut fuers Selbstgespraech; die
  Wartezeiten (say 2 s, taub 1,5 s) bleiben als Sicherheit.
- **Aussprache:** Piper (deutsch) spricht „Reachy“ falsch. Ersetzungsliste vor der Synthese
  (`Reachy = Rietschi`, `Claude = Klohd`), vom Nutzer erweiterbar in `app/aussprache.txt`; Anzeige bleibt im Original.
- **Fehler am echten Reachy (`say`, Satz bricht nach der Haelfte ab):** Reachy spielt WebRTC-Ton verzoegert
  ab (Netz + Puffer im Roboter); `say` trennte die Verbindung zu frueh. `stop_sound` ist es nicht (stoppt nur
  Sounddateien). Fix: `say` haelt die Verbindung 2 s laenger offen; Taubheitsfenster nach eigener Ansage
  0,6 → 1,5 s. Neu: `check-audio` misst die Rundlauf-Verzoegerung (Piepton → Mikrofon), um die Werte mit
  echten Zahlen einzustellen → am Reachy nicht messbar (siehe AEC unten). **`say` jetzt vollstaendig (Nutzer bestaetigt).**
- Kein Selbstgespraech: Antwort laeuft blockierend im Hauptthread; danach Mikrofon-Warteschlange leeren,
  Satzerkennung zuruecksetzen, 0,6 s „taub“ (Netzlatenz/Nachhall). Test mit phasenweisem Fake-Mikrofon,
  Gegenprobe ohne Echo-Loeschen schlaegt fehl.

### Erkenntnisse Schritt 2
- Satzerkennung: eigene Pegel-Erkennung (30-ms-Frames, Grundrauschen = 10 %-Quantil der letzten 3 s,
  0,8 s Pause = Satzende, 0,3 s Vorlauf). An Piper-Sprache + −40 dB Rauschen abgestimmt:
  Schwelle 12 dB fand nur 2/4 Saetze, **6 dB findet 4/4** (Regressionstest `tests/data`).
- Whisper: `large-v3-turbo` int8_float16 auf CUDA, Rueckfall `small` int8 auf CPU; `vad_filter=True`
  (Silero aus faster-whisper) gegen erfundene Saetze; `initial_prompt` mit „Claude“.
- Windows/CUDA: pip-Extra `gpu` (nvidia-cublas-cu12, nvidia-cudnn-cu12); DLL-Ordner werden zur
  Laufzeit registriert. Startskript installiert es nur, wenn `nvidia-smi` existiert. **Auf echter
  Hardware ungetestet.**
- Hugging Face ist in der Cloud-Arbeitsumgebung gesperrt → echte Whisper-Pruefung laeuft in CI (Windows).
- CI-Ergebnis (Whisper `small`, CPU, Piper-Testsprache): Aktivierungswort 3/3 korrekt; Inhalt teils
  fehlerhaft („Login“ → „Locking“, „main punkt py“ → „meinen Punkt fühlen“). Hinweistext hatte „fuer“
  ohne Umlaut → Whisper schrieb „fuer“; korrigiert (Hinweistext mit echten Umlauten + Fachbegriffen).
- faster-whisper 1.2.1 und piper-tts 1.8.0 vertragen sich mit reachy-mini 1.11 (onnxruntime 1.27 bleibt).

### Erkenntnisse Schritt 1
- PyPI-Version `reachy-mini` 1.11.0 (GitHub-main ist 1.12-dev); API identisch für unseren Bedarf.
  Bringt `onnxruntime==1.27.0` mit (später nutzbar für VAD).
- `ReachyMini(..., log_level=...)` steuert die SDK-Ausgaben; Standard bei uns WARNING.
- Fehlerbilder unterscheiden: Port 8000 (Daemon) zu → Roboter nicht erreichbar;
  8000 offen, 8443 zu → Medienserver/WebRTC-Problem.
- Harmlose SDK-Meldung „No Reachy Mini Audio USB device found!“ (sucht USB-Soundkarte am PC) wird ausgefiltert.
- Im Linux-Container fehlt das GStreamer-WebRTC-Plugin (webrtcsink) → WebRTC-Audio hier nicht
  testbar; unter Windows liefert `gstreamer-bundle` es mit.

### Anlass
- Nutzer will **nicht plaudern**, nur Anweisungen an Claude geben; Reachy liest Claudes Antwort vor.
- PC: RTX 4060 (8 GB VRAM), 32 GB RAM, Windows.
- Das lokale Gesprächs-LLM der v1-Stufe 3 (speech-to-speech, ~24 GB VRAM komplett lokal)
  ist dafür unnötig und zu groß – Claude übernimmt das Denken.

### Verifizierte SDK-Fakten (reachy_mini @ fbdbca3, 2026-10-05)
- `ReachyMini(host=..., connection_mode="network")` verbindet sich vom PC mit dem Daemon (Port 8000).
- Media-Backend `WEBRTC` (automatisch bei Remote-Client): `media.get_audio_sample()` liefert das
  Roboter-Mikrofon (float32, 16 kHz, 2 Kanäle), `media.push_audio_sample()` spielt auf dem
  Roboter-Lautsprecher (nicht blockierend), `media.get_DoA()` liefert Richtung + Sprach-Erkennung.
- Signalisierung des Python-WebRTC-Clients: `ws://<roboter>:8443` **auf dem Roboter** → kein Cloud-Handshake.
- Windows offiziell unterstützt; GStreamer kommt als Wheel (`gstreamer-bundle`) mit.

### Architektur v2
```
Reachy (nur Daemon, nichts installiert)          Windows-PC: reachy-claude (eine App)
  Mikrofon ──WebRTC/Opus (LAN)──────────────────►  VAD (Silero, CPU) → Satz erkannt
                                                    STT (faster-whisper, GPU) → Text
                                                    Aktivierungswort? ("Claude, …")
                                                    ClaudeRunner (claude -p, wie v1) ─► Anthropic
                                                    Vorlesetext (speech.py, wie v1)
  Lautsprecher ◄──WebRTC (LAN)───────────────────  TTS (Piper, deutsche Stimme, CPU)
  Kopf/Antennen ◄──Daemon-API (LAN)──────────────  Bewegung: zuhören / arbeiten / sprechen
                                                    Terminal: "Du: …" / "Reachy: …" + Mitschrift
```

### Bausteine und Ressourcen (Planwerte, auf echter Hardware zu prüfen)
| Baustein | Wahl | läuft auf | Bemerkung |
|---|---|---|---|
| Sprachaktivität | Silero VAD | CPU | sehr klein |
| Spracherkennung | faster-whisper `large-v3-turbo` (int8) | GPU | sehr gutes Deutsch; Fallback `small` auf CPU |
| Sprachausgabe | Piper, deutsche Stimme | CPU | schnell, offline |
| Claude | Claude Code CLI wie v1 (`dontAsk`, keine Shell/Web/MCP) | PC | unverändert übernommen |
Erwartung: deutlich unter 8 GB VRAM; genaue Werte werden gemessen.

### Verhalten
- Start: Verbindung zu Reachy, Reachy wacht auf (`wake_up`), kurzer Hinweis per Sprache.
- Zuhören: Antennen/Kopf bewegen sich leicht (lebendig); Mikrofon wird während Reachy spricht stummgeschaltet (kein Selbstgespräch).
- Nur Sätze mit **Aktivierungswort** (Standard: „Claude, …“) gehen an Claude – Rest wird ignoriert (Fernseher, Gespräche im Raum).
- Während Claude arbeitet: „Denk“-Bewegung; kurze Ansage „Ich frage Claude.“
- Antwort: Vorlesetext (2–4 Sätze) per Piper auf Reachys Lautsprecher, dazu Sprech-Bewegung.
- Befehle: „Claude, neues Thema …“ → neue Claude-Sitzung; „Reachy, schlaf“ → Ruheposition, App endet.
- Terminal zeigt alles als Text (wie `listen`) und schreibt die Mitschrift.

### Datenflüsse v2
- Audio: nur Heimnetz (Roboter ↔ PC, WebRTC P2P, lokale Signalisierung).
- Internet: **nur** der Auftrag an Claude + benötigte Projektdateien → Anthropic.
- Einmalig: Modelle (Whisper, Piper-Stimme, Silero) und Pakete herunterladen.

### Sicherheit v2
- Kein offener Port auf dem PC mehr (die App baut die Verbindung zum Roboter selbst auf) → Token/HMAC/Tunnel entfallen.
- Claude-Rechte wie v1; Aktivierungswort gegen versehentliche Aufträge; ein Auftrag gleichzeitig.
- Restrisiko: Daemon-API und WebRTC-Signalisierung des Roboters sind im WLAN ohne Passwort erreichbar (Pollen-Design).

### Was aus v1 wegfällt / bleibt
- Bleibt: `runner.py` (Claude), `speech.py` (Vorlesetext), Konfiguration/Tests davon, `listen` (für die Conversation-App).
- Entfällt (nach Freigabe in einen Ordner `legacy/` bzw. gelöscht): HTTP-Server, Signatur, Roboter-Tool + Profil,
  Zuhör-Patch für die Conversation-App, SSH-Tunnel, speech-to-speech-Anleitung.

### Umsetzungsschritte (jeweils mit Tests)
1. Audio-Test: PC ↔ Reachy (Mikrofon aufnehmen, Ton abspielen) – `reachy-claude check-audio`.
2. Spracherkennung + Aktivierungswort, Ausgabe nur als Text (ohne Claude).
3. Sprachausgabe auf Reachy (Echo-Test: „Sag: …“).
4. Claude anbinden (Runner aus v1).
5. Bewegungen (zuhören / denken / sprechen).
6. Doku, Startskript `start.ps1`, Aufräumen v1.

### Offene Fragen an den Nutzer
(beantwortet, siehe Entscheidungen oben)

---

## v1 (umgesetzt 2026-10-02) – über die Conversation-App

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
