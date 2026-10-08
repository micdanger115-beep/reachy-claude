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

## Stand: Schritt 2 von 6

Die App wird schrittweise gebaut; jeden Schritt kannst du selbst am echten Reachy testen.

| Schritt | Inhalt | Stand |
|---|---|---|
| 1 | **Audio-Test:** PC hört Reachys Mikrofon, spielt auf Reachys Lautsprecher | ✅ am Reachy getestet |
| 2 | **Spracherkennung + Aktivierungswort „Claude“**, Ausgabe als Text | ✅ fertig – bitte testen |
| 3 | Sprachausgabe auf Reachy (deutsche Stimme) | geplant |
| 4 | Claude anbinden | geplant |
| 5 | Lebendige Bewegungen (zuhören, nachdenken, sprechen) | geplant |
| 6 | Ein Startskript für alles, Feinschliff | geplant |

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
│   │   └── listener.py      Schritt 2: Mikrofon-Thread → Sätze → Text → Auftrag
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

**Verifiziert Schritt 2 (2026-10-08):** 46 Tests ✅ · Satzerkennung mit echter (synthetischer) deutscher Sprache + Raumrauschen ✅ (dabei Schwelle von 12 auf 6 dB korrigiert) · echte Whisper-Erkennung läuft in CI unter Windows (hier blockiert die Umgebung Hugging Face).

**Verifiziert Schritt 1 (2026-10-08):** 17 Tests ✅ · Ruff/Mypy (strict) ✅ · gegen das echte SDK
`reachy-mini 1.11.0` und einen simulierten Reachy-Daemon (`--mockup-sim`): Verbindung
und Fehlermeldungen ✅. Der WebRTC-Audioweg selbst ist **noch nicht am echten Reachy
getestet** – genau dafür ist Schritt 1 da.
