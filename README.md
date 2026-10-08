# Reachy Claude 🤖🎙️ → 💻

Sag Reachy Mini **„Claude, …“**, und Claude Code auf deinem PC erledigt den
Auftrag: programmieren, Fragen zum Projekt beantworten. Reachy liest die
Antwort vor.

- **Auf Reachy wird nichts installiert.** Die App läuft komplett auf deinem Windows-PC
  und nutzt Reachys Mikrofon, Lautsprecher, Kopf und Antennen über das Heimnetz.
- **Datensparsam:** Sprache wird auf deinem PC erkannt und erzeugt. Ins Internet
  geht nur der Auftrag an Claude.
- **Nur auf Ansage:** Nur Sätze, die mit „Claude“ beginnen, gehen an Claude.

> Plan und Entscheidungen: [`plan.md`](plan.md) · Sicherheit: [`SECURITY.md`](SECURITY.md) ·
> erster Ansatz über die Conversation-App: [`legacy/`](legacy/README.md)

---

## Stand: Schritt 5 von 6

Die App wird schrittweise gebaut; jeden Schritt kannst du selbst am echten Reachy testen.

| Schritt | Inhalt | Stand |
|---|---|---|
| 1 | **Audio-Test:** PC hört Reachys Mikrofon, spielt auf Reachys Lautsprecher | ✅ am Reachy getestet |
| 2 | **Spracherkennung + Aktivierungswort „Claude“**, Ausgabe als Text | ✅ am Reachy getestet (GPU) |
| 3 | **Sprachausgabe auf Reachy** (deutsche Stimme) | ✅ am Reachy getestet |
| 4 | **Claude anbinden** – Reachy liest Claudes Antwort vor | ✅ am Reachy getestet |
| 5 | **Lebendige Bewegungen** (aufwachen, zuhören, nachdenken, sprechen, schlafen) | ✅ fertig – bitte testen |
| 6 | Ein Startskript für alles, Feinschliff | geplant |

---

## Schritt 5: Reachy wirkt lebendig

`listen` steuert jetzt Kopf und Antennen passend zur Situation:

| Situation | Reachy … |
|---|---|
| Start | **wacht auf** (Aufwach-Bewegung und -Geräusch) |
| Ruhe | „atmet“: Kopf hebt/senkt sich ein paar Millimeter, Antennen wippen sanft |
| Du sprichst | schaut **aufmerksam**: Kopf leicht schräg und nach oben, Antennen aufgestellt |
| „Claude“ erkannt | Antennen schnellen kurz hoch, kleines Nicken |
| Claude arbeitet | wirkt **nachdenklich**: Blick nach oben, Kopf pendelt langsam, Antennen wandern |
| Reachy spricht | Kopf bewegt sich passend zur Sprache (macht der Roboter selbst), Antennen lebhaft |
| Ende (Strg+C) | weich zurück in Grundstellung, dann **legt er sich schlafen** |

Alle Bewegungen sind klein, weich übergeblendet und auf sichere Grenzen begrenzt
(Kopf max. 15° bzw. 10 mm). Fällt die Verbindung kurz aus, läuft die App weiter.

| Option | Wirkung |
|---|---|
| `-OhneBewegung` | Reachy bewegt sich nicht (nur Stimme) |
| `-WachBleiben` | am Ende nicht schlafen legen |

## Stimmen

```powershell
powershell -ExecutionPolicy Bypass -File .\reachy-claude.ps1 voices
powershell -ExecutionPolicy Bypass -File .\reachy-claude.ps1 say -Stimme de_DE-kerstin-low -Text "Hallo, ich bin Reachy."
powershell -ExecutionPolicy Bypass -File .\reachy-claude.ps1 listen -Stimme de_DE-kerstin-low
```

| Stimme | Beschreibung |
|---|---|
| `de_DE-thorsten-medium` | Thorsten, männlich, klar (**Standard**) |
| `de_DE-thorsten-high` | Thorsten, beste Qualität (größer, etwas langsamer) |
| `de_DE-thorsten-low` | Thorsten, einfache Qualität (klein, schnell) |
| `de_DE-thorsten_emotional-medium` | Thorsten mit Gefühlslagen – mehrere Sprecher, Auswahl mit `-Sprecher` |
| `de_DE-kerstin-low` | Kerstin, weiblich |
| `de_DE-ramona-low` | Ramona, weiblich |
| `de_DE-eva_k-x_low` | Eva K., weiblich, sehr einfache Qualität |
| `de_DE-karlsson-low` | Karlsson, männlich |
| `de_DE-pavoque-low` | Pavoque, männlich |
| `de_DE-mls-medium` | viele verschiedene Sprecher – Auswahl mit `-Sprecher` |

Jede Stimme wird beim ersten Benutzen einmalig heruntergeladen (ca. 20–110 MB) und liegt
dann in `app\voices\`. Bei Stimmen mit mehreren Sprechern zeigt die Zeile „Stimme bereit: …“
die verfügbaren Sprecher an; wählen mit `-Sprecher <Name oder Nummer>`.
Quelle der Liste: offizielles Piper-Stimmenverzeichnis (rhasspy/piper, VOICES.md).

---

## Schritt 4: Mit Claude arbeiten

**Voraussetzung:** Claude Code ist auf dem PC installiert und angemeldet (einmal `claude`
im Terminal starten). Am besten ist der Projektordner ein Git-Repository – dann siehst du
jede Änderung mit `git diff` und kannst sie zurücknehmen.

```powershell
git pull
# einmalig den Projektordner festlegen (wird in app\einstellungen.toml gespeichert):
powershell -ExecutionPolicy Bypass -File .\reachy-claude.ps1 listen -Projekt "D:\code\mein-projekt"
# danach genügt:
powershell -ExecutionPolicy Bypass -File .\reachy-claude.ps1 listen
```

So läuft ein Auftrag:

```
Du:     Claude, füge in calc.py eine Funktion mul hinzu.
  -> Auftrag fuer Claude: füge in calc.py eine Funktion mul hinzu.
Reachy: Ich frage Claude.
Claude:
  Ich habe `mul(a, b)` in `calc.py` unter `add` eingefügt. ...
Reachy: Ich habe in der Datei calc.py die Funktion mul hinzugefügt. Sie multipliziert zwei Zahlen ...
```

- **Im Terminal** steht Claudes vollständige Antwort (auch Code), **vorgelesen** werden nur
  2–4 zusammenfassende Sätze. Alles landet zusätzlich in `app\mitschriften\<Datum>.md`.
- **Folgefragen** („Claude, was hast du gerade geändert?“) setzen dieselbe Unterhaltung fort.
- **„Claude, neues Thema: …“** (oder „neue Unterhaltung“, „von vorne“) beginnt eine frische Unterhaltung.
- Dauert es länger, sagt Reachy alle 45 s „Claude arbeitet noch.“ Abbruch nach 15 Minuten.
- Es läuft immer **ein Auftrag** zur Zeit; währenddessen hört Reachy nicht zu.

**Was Claude darf** (fest eingebaut): Dateien im Projektordner **lesen** und – mit Rechten
`edit` (Standard) – **bearbeiten/anlegen**. **Nie**: Shell-Befehle, Internet, Zusatz-Server
(MCP), die Ordner `.claude`, `.git` und `.vscode` ändern. Einstellungen und Hooks, die im
Projektordner liegen, werden ignoriert – auch ein fremdes, manipuliertes Repo kann so keine
Befehle einschleusen. Alles andere wird ohne Rückfrage verweigert.

| Option | Wirkung |
|---|---|
| `-Projekt "D:\pfad"` | Projektordner festlegen/wechseln (gespeichert) |
| `-Rechte read` / `-Rechte edit` | nur lesen / auch bearbeiten (gespeichert) |
| `-OhneClaude` | Test ohne Claude: Reachy wiederholt nur den Auftrag |

In `app\einstellungen.toml` lassen sich außerdem `timeout_minuten` und `claude_programm`
(Pfad zu `claude.exe`, falls nicht gefunden) eintragen.

---

## Schritt 3 testen: Reachy spricht

```powershell
git pull
powershell -ExecutionPolicy Bypass -File .\reachy-claude.ps1 say -Text "Hallo, ich bin Reachy."
powershell -ExecutionPolicy Bypass -File .\reachy-claude.ps1 listen
```

- Beim ersten Start wird die Sprachausgabe *Piper* installiert und die deutsche Stimme
  *thorsten-medium* (~60 MB) einmalig heruntergeladen (`app\voices\`). Danach lokal.
- `say` lässt Reachy einen beliebigen Text sprechen.
- `listen` begrüßt dich und **bestätigt jeden Auftrag mit Stimme** („Verstanden: …“) –
  noch ohne Claude (kommt in Schritt 4).
- Damit Reachy sich nicht selbst zuhört, wird alles verworfen, was das Mikrofon während
  seiner eigenen Ansage und 0,6 s danach aufnimmt.
- `-Silent`: Reachy antwortet nur als Text, ohne Stimme.
- **Aussprache:** Englische Wörter spricht die deutsche Stimme „deutsch“ aus. In
  `app\aussprache.txt` steht, wie sie gesprochen werden sollen (z. B. `Reachy = Rietschi`,
  `Claude = Klohd`). Die Datei kannst du selbst ergänzen; gilt ab dem nächsten Start.

Bitte achte auf: Klingt die Stimme gut/verständlich? Reagiert Reachy auf seine eigene
Ansage (sollte er nicht)? Wie lange dauert es vom Satzende bis Reachy antwortet?

---

## Schritt 2 testen: Spracherkennung + Aktivierungswort

```powershell
git pull
powershell -ExecutionPolicy Bypass -File .\reachy-claude.ps1 listen
```

Beim ersten Start werden nachinstalliert bzw. heruntergeladen (einmalig, braucht Internet):
die Spracherkennung *faster-whisper*, bei NVIDIA-Grafikkarte die CUDA-Bibliotheken
(~1–2 GB) und das Sprachmodell *Whisper large-v3-turbo* (~1,5 GB). Danach läuft alles
lokal. Ausgabe beim Sprechen:

```
Spracherkennung bereit: Whisper 'large-v3-turbo' auf Grafikkarte
Verbunden. Sprich mit Reachy – Aufträge beginnen mit "Claude, ...". Beenden mit Strg+C.

Du:     Was gibt es heute zu essen?
        (ignoriert – beginnt nicht mit 'Claude')
Du:     Claude, schreib bitte einen Test für die Login-Funktion.
  -> Auftrag fuer Claude: schreib bitte einen Test für die Login-Funktion.
Du:     Claude.
        (Ja? Ich hoere – sag deinen Auftrag.)
Du:     Erkläre mir die Datei main.py.
  -> Auftrag fuer Claude: Erkläre mir die Datei main.py.
```

- „Claude“ darf auch mit „Hey/Hallo/Okay“ beginnen. Sagst du nur „Claude.“, gilt der
  **nächste Satz** (innerhalb von 8 Sekunden) als Auftrag.
- Noch wird **nichts an Claude geschickt** – Schritt 2 zeigt nur, was ankommen würde.

| Option | Wirkung |
|---|---|
| `-Device cpu` | Spracherkennung auf dem Prozessor (Modell `small`, langsamer) |
| `-Device cuda` | nur Grafikkarte (Fehler statt Rückfall, zur Fehlersuche) |
| `-Robot <IP>` / `-Details` | wie bei Schritt 1 |

Bitte achte beim Test auf: Wird „Claude“ zuverlässig erkannt? Wie lange dauert es vom
Satzende bis zur Textzeile? Werden Sätze mitten im Wort abgeschnitten?

---

## Schritt 1 testen: Audio PC ↔ Reachy

**Vorbereitung**

1. **Reachy** einschalten. Im Dashboard **keine andere App laufen lassen**, vor allem
   nicht die Conversation-App: Sie würde Mikrofon und Lautsprecher mitbenutzen.
2. **Python 3.11 oder neuer** auf dem PC (falls `py --version` einen Fehler zeigt):
   ```powershell
   winget install -e --id Python.Python.3.12
   ```
   Danach PowerShell schließen und neu öffnen.

**Starten** (im Ordner `reachy-claude`):

```powershell
git pull
powershell -ExecutionPolicy Bypass -File .\reachy-claude.ps1 check-audio
```

Der erste Start installiert die App und das Reachy-SDK in `app\.venv` – das dauert
einige Minuten (das SDK bringt GStreamer für Audio/Video mit).

**Ablauf**

1. „Sprich jetzt 5 Sekunden lang …“ – zähle laut bis zehn. Eine Pegelanzeige zeigt,
   ob Reachys Mikrofon dich hört:
   ```
     Mikrofon [##############----------------]   -32 dB
   ```
2. Die Aufnahme wird auf dem PC gespeichert: `app\aufnahmen\audio-test-<Zeit>.wav`.
3. Reachy spielt **zwei Töne** und danach **deine Aufnahme** ab.

Hörst du beides aus Reachy, funktioniert Audio – dann kann Schritt 2 kommen.

| Option | Wirkung |
|---|---|
| `-Robot 192.168.1.30` | Reachy per IP ansprechen, falls `reachy-mini.local` nicht gefunden wird |
| `-Seconds 10` | länger aufnehmen (1–60 s) |
| `-Details` | ausführliche Meldungen zur Fehlersuche |

**Mögliche Meldungen**

| Meldung | Bedeutung / Lösung |
|---|---|
| „Python 3.11 oder neuer wurde nicht gefunden“ | Python installieren (siehe oben), **neues** PowerShell-Fenster |
| „Reachy unter … nicht erreichbar“ | Reachy aus oder nicht im selben WLAN → einschalten bzw. `-Robot <IP>` |
| „Reachy ist erreichbar, aber sein Audio/Video-Dienst … antwortet nicht“ | Reachy im Dashboard neu starten |
| „Reachys Mikrofon liefert keine Daten“ | Andere App auf Reachy stoppen (Conversation-App) |
| „Aufnahme sehr leise“ | Mikrofon von Reachy stumm/leise? Näher herangehen |
| Warnung zur Versionsabweichung | PC-SDK (1.11.x) und Reachy-Software passen nicht zusammen → Reachy im Dashboard aktualisieren und mir die Versionen nennen |

---

## Wie es funktioniert (Zielbild)

```
Reachy (nur sein Grundprogramm)              Windows-PC: reachy-claude
  Mikrofon ──── Heimnetz (WebRTC) ────────►  Sprache erkennen  ─┐
                                                                ├ „Claude, …“? → Claude Code ──► Anthropic
  Lautsprecher ◄── Heimnetz (WebRTC) ──────  Antwort vorlesen  ◄┘
  Kopf/Antennen ◄── Heimnetz ─────────────  zuhören / nachdenken / sprechen
                                             Terminal: „Du: …“ / „Reachy: …“
```

Der PC verbindet sich mit dem Programm, das ohnehin auf Reachy läuft (Daemon,
Port 8000). Ton läuft per WebRTC direkt zwischen Reachy und PC; den
Verbindungsaufbau übernimmt Reachy selbst (Port 8443) – **kein Cloud-Dienst**.

### Datenflüsse

| Daten | Weg | Internet? |
|---|---|---|
| Mikrofon-Audio | Reachy → PC (Heimnetz) | nein |
| **Kamerabild** (H.264) – wird nicht genutzt, das SDK überträgt es fest mit | Reachy → PC (Heimnetz), weder gespeichert noch ausgewertet | nein |
| Erkannter Text, Antworten, Mitschrift | nur auf dem PC | nein |
| Vorgelesene Antwort (Audio) | PC → Reachy (Heimnetz) | nein |
| Auftrag + benötigte Projektdateien (ab Schritt 4) | PC → Anthropic | **ja** |
| Einmalig: App, SDK, Sprachmodelle | Download | ja (nur Herunterladen) |

---

## Entwicklung & Tests

```
reachy-claude/
├── reachy-claude.ps1        Startskript (Windows)
├── plan.md                  Plan, Entscheidungen, Recherche
├── SECURITY.md              Sicherheit
├── app/                     die App (Python ≥ 3.11)
│   ├── src/reachy_claude/
│   │   ├── __main__.py      Kommandozeile (check-audio, listen, weitere folgen)
│   │   ├── robot.py         Verbindung zu Reachy (SDK), verständliche Fehlermeldungen
│   │   ├── audio.py         Audio-Hilfen: Mono, Pegel, Töne, WAV
│   │   ├── check_audio.py   Schritt 1: Audio-Test
│   │   ├── segmenter.py     Sätze aus dem Mikrofon-Strom schneiden (Pegel, lernt Grundrauschen)
│   │   ├── stt.py           Spracherkennung (faster-whisper; GPU, sonst CPU)
│   │   ├── wakeword.py      Aktivierungswort „Claude“ (tolerant: Cloud, Klod …)
│   │   ├── tts.py           Sprachausgabe (Piper, deutsche Stimme, 16 kHz, Aussprache-Liste)
│   │   ├── settings.py      Projektordner/Rechte (einstellungen.toml), strenge Prüfung
│   │   ├── claude.py        Claude Code CLI sicher aufrufen (aus v1): dontAsk, keine Shell/Web/MCP, Timeout
│   │   ├── spoken.py        Vorlesetext aus Claudes Antwort (SPRECHTEXT-Zeile, aus v1)
│   │   ├── assistant.py     Schritt 4: Auftrag → Claude (mit Zwischenmeldungen) → Terminal + Vorlesen
│   │   ├── motion.py        Schritt 5: Stimmungen → Kopf/Antennen (25 Hz, geglättet, begrenzt)
│   │   └── listener.py      Mikrofon-Thread → Sätze → Text → Auftrag; Voice: Reachy spricht (ohne Selbstgespräch)
│   ├── tests/               pytest mit nachgebautem Reachy und simulierter Uhr
│   │   └── data/            echte Sprach-Testaufnahme (Regressionstest)
│   └── python-env.ps1       Python finden, .venv einrichten/reparieren
└── legacy/                  v1 (Conversation-App-Ansatz), archiviert
```

```bash
cd app
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy && .venv/bin/pytest -q
```

Die Tests brauchen keinen Roboter: `tests/fakes.py` simuliert Reachys Mikrofon und
Lautsprecher und eine Uhr, damit nichts wirklich warten muss. CI
(`.github/workflows/tests.yml`) läuft auf Ubuntu und Windows; unter Windows wird
zusätzlich die **komplette Installation inkl. Reachy-SDK** und das Startskript unter
Windows PowerShell 5.1 geprüft.

**Verifiziert Schritt 5 (2026-10-08):** 126 Tests ✅ (u. a. alle Stimmungen innerhalb der Grenzen, keine Sprünge > 3°/40 ms) · gegen den **echten Reachy-Daemon im Simulationsmodus**: Aufwachen, alle Stimmungen (Kopf folgt: Zuhören 8° schräg/3° hoch, Nachdenken 8° hoch), Antennen-Richtungen, Sprech-Wackeln, Schlafen ✅.

**Verifiziert Schritt 4 (2026-10-08):** 104 Tests ✅ (inkl. v1-Tests des Claude-Aufrufs, unter Windows mit `.cmd`-Startdatei) · **echter Durchlauf mit Claude Code CLI**: Datei geändert, Folgefrage mit Kontext, „neues Thema“ – Sprechtexte mit Piper vertont ✅.

**Verifiziert Schritt 3 (2026-10-08):** 55 Tests ✅ (u. a. „Reachy hört sich nicht selbst zu“ – Gegenprobe: ohne Echo-Löschen wird der Test rot) · echte Piper-Synthese lokal ✅ · CI: Piper thorsten-medium + Rundweg Piper → Whisper → Aktivierungswort.

**Verifiziert Schritt 2 (2026-10-08):** 46 Tests ✅ · Satzerkennung mit echter (synthetischer) deutscher Sprache + Raumrauschen ✅ (dabei Schwelle von 12 auf 6 dB korrigiert) · echte Whisper-Erkennung läuft in CI unter Windows (hier blockiert die Umgebung Hugging Face).

**Verifiziert Schritt 1 (2026-10-08):** 17 Tests ✅ · Ruff/Mypy (strict) ✅ · gegen das echte SDK
`reachy-mini 1.11.0` und einen simulierten Reachy-Daemon (`--mockup-sim`): Verbindung
und Fehlermeldungen ✅. Der WebRTC-Audioweg selbst ist **noch nicht am echten Reachy
getestet** – genau dafür ist Schritt 1 da.
