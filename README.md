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

## Stand: alle 6 Schritte umgesetzt

Die App wird schrittweise gebaut; jeden Schritt kannst du selbst am echten Reachy testen.

| Schritt | Inhalt | Stand |
|---|---|---|
| 1 | **Audio-Test:** PC hört Reachys Mikrofon, spielt auf Reachys Lautsprecher | ✅ am Reachy getestet |
| 2 | **Spracherkennung + Aktivierungswort „Claude“**, Ausgabe als Text | ✅ am Reachy getestet (GPU) |
| 3 | **Sprachausgabe auf Reachy** (deutsche Stimme) | ✅ am Reachy getestet |
| 4 | **Claude anbinden** – Reachy liest Claudes Antwort vor | ✅ am Reachy getestet |
| 5 | **Lebendige Bewegungen** (aufwachen, zuhören, nachdenken, sprechen, schlafen) | ✅ am Reachy getestet |
| 6 | **Start per Doppelklick**, Startprüfung, alles merken, „stopp“/„wiederhole“ | ✅ fertig – bitte testen |

---

## Schnellstart (Schritt 6)

1. **Voraussetzungen** (einmalig):
   - **Python 3.12** (3.11–3.13 gehen; neuere noch nicht): `winget install -e --id Python.Python.3.12`
     oder von python.org („Add python.exe to PATH“ anhaken).
   - [Claude Code](https://claude.com/claude-code) installiert und einmal `claude` im Terminal gestartet (anmelden).
   - Reachy eingeschaltet, im selben WLAN/LAN wie der PC.
2. **Die App auf den PC holen:** `git clone https://github.com/micdanger115-beep/reachy-claude.git C:\reachy-claude`
   (oder auf GitHub „Code → Download ZIP“ und entpacken). Am besten in einen Ordner **ohne Umlaute
   und nicht in OneDrive** (OneDrive würde Mitschriften in die Cloud laden und die Installation stören).
3. **Doppelklick auf `Reachy-Claude.cmd`.** Beim ersten Start richtet die App ihre Python-Umgebung
   ein und lädt Reachy-SDK, Spracherkennung und Stimme (einmalig **3–4 GB, 10–30 Minuten** – Fenster
   offen lassen). Ist noch kein Projektordner festgelegt, öffnet sich ein **Ordner-Auswahlfenster**
   (falls nicht sichtbar: Taskleiste).
4. **Sprechen:** „Claude, erklär mir die Datei main.py.“ – Reachy liest die Antwort vor.
5. **Beenden:** Strg+C. Fragt Windows danach „Batchvorgang abbrechen (J/N)?“, mit **J** bestätigen.
   Reachy legt sich vorher schlafen (außer mit `-WachBleiben` oder `-Bewegung aus`). Das Fenster
   bitte nicht mit dem X schließen – dann bleibt Reachy wach stehen.

**Befehle mit Parametern** gibst du in einem Terminal im App-Ordner ein: im Explorer Rechtsklick auf den
Ordner → „Im Terminal öffnen“, dann z. B. `.\Reachy-Claude.cmd pruefen`.

Optional: `.\Reachy-Claude.cmd verknuepfung` legt eine **Desktop-Verknüpfung** „Reachy Claude“ an.

### Vor dem Start: Startprüfung

Vor jedem Zuhören prüft die App kurz, ob alles bereit ist, und bricht mit einer konkreten
Anleitung ab, wenn etwas fehlt. Die vollständige Übersicht zeigt:

```powershell
.\Reachy-Claude.cmd pruefen
```

```
[ OK ] Python-Pakete: vollstaendig
[ OK ] Grafikkarte: NVIDIA-Grafikkarte wird fuer die Spracherkennung genutzt
[ OK ] Stimme: de_DE-thorsten-medium ist installiert
[ OK ] Claude Code: installiert und angemeldet
[ OK ] Projektordner: D:\code\mein-projekt (lesen + bearbeiten)
[ OK ] Reachy erreichbar: reachy-mini.local (Steuerung)
[ OK ] Reachy Ton/Video: bereit
[ OK ] Reachy-Version: 1.11.0
[INFO] Reachy-Sicherheit: Bluetooth-PIN-Umgehung (GHSA-993g-hgjh-whmf); behoben ab 1.12.0
       -> Update, sobald 1.12 erscheint; bis dahin Bluetooth nur bei Bedarf koppeln.
```

Geprüft wird auch Reachys Software-Version gegen die bekannten Sicherheitslücken
(siehe [`SECURITY.md`](SECURITY.md), S10). Alles bleibt im Heimnetz bzw. auf dem PC.

### Alles wird gemerkt

Was du einmal per Parameter setzt, gilt beim nächsten Start (Doppelklick) weiter –
gespeichert in `app\einstellungen.toml` (darf auch von Hand bearbeitet werden):

| Parameter | Wirkung | gespeichert |
|---|---|---|
| `-Projekt "D:\code\x"` | Ordner, in dem Claude arbeitet | ✅ |
| `-Rechte read` / `edit` | nur lesen / auch Dateien bearbeiten (Standard) | ✅ |
| `-Robot 192.168.1.30` | Adresse von Reachy (Standard `reachy-mini.local`) | ✅ |
| `-Stimme …` / `-Sprecher …` | Stimme (Liste: `voices`) | ✅ |
| `-Bewegung aus` / `an` | Kopf und Antennen bewegen | ✅ |
| `-WachBleiben`, `-Silent`, `-OhneClaude`, `-Device cpu`, `-Details` | nur für diesen Start | – |

Beispiel: `.\Reachy-Claude.cmd listen -Projekt "D:\code\anderes-projekt" -Rechte read`

### Sprachbefehle

| Du sagst | Reachy … |
|---|---|
| „Claude, *Auftrag*“ | gibt den Auftrag an Claude, liest die Antwort vor |
| „Claude.“ … *Auftrag* | zweistufig: erst „Claude“, dann innerhalb von 8 s den Auftrag |
| „Claude, *langer Auftrag* … *Denkpause* … *weiter*“ | hängt an: Der Auftrag geht erst los, wenn du **ca. 3 s** nichts mehr sagst (bis zu 2 Minuten am Stück) |
| „Claude, **stopp**“ / „abbrechen“ / „hör auf“ | bricht den laufenden Auftrag ab („Abgebrochen.“) – auch wenn Claude noch gar nicht gestartet ist; im Nachlauf verwirft es den gerade diktierten Auftrag, nichts geht an Claude |
| „Claude, **wiederhole**“ / „nochmal“ / „wie bitte?“ | liest die letzte Antwort nochmal vor |
| „Claude, **neues Thema**: …“ | beginnt eine neue Unterhaltung mit Claude |

Lange Aufträge kannst du in Ruhe diktieren: Nach dem Satz wartet Reachy noch 2 s
(„hoere weiter zu“ im Terminal); sprichst du weiter, wird angehängt. „Stopp“ und
„wiederhole“ wirken sofort.

Während Claude arbeitet, hört Reachy weiter zu (für „stopp“). Ein zweiter Auftrag wird erst
angenommen, wenn der erste fertig ist. Während Reachy selbst spricht, hört er nicht zu –
„stopp“ also in einer Sprechpause sagen.

## Wenn etwas nicht klappt

| Problem | Lösung |
|---|---|
| „Installation fehlgeschlagen“ / Start hängt nach Abbruch | Ordner `app\.venv` löschen, neu starten (Details in `app\pip-log.txt`) |
| „Kein passendes Python“ | Python 3.12 installieren (siehe Schnellstart), Fenster neu öffnen |
| `einstellungen.toml ist fehlerhaft` | Windows-Pfade in einfache Anführungszeichen setzen – oder `app\einstellungen.toml` löschen (wird neu angelegt) |
| Reachy nicht erreichbar | `.\Reachy-Claude.cmd pruefen`; ggf. mit `-Robot <IP>` starten (IP im Router/in der Reachy-App) |
| Fenster „hängt“, nachdem du hineingeklickt hast | Windows 10 markiert dann Text und hält das Programm an: **Esc** drücken |
| Claude „nicht gefunden“ | Claude Code installieren, neues Fenster öffnen; sonst `claude_programm` in `app\einstellungen.toml` |

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
| `-Bewegung aus` | Reachy bewegt sich nicht (nur Stimme; wird gemerkt, wieder an mit `-Bewegung an`) |
| `-WachBleiben` | am Ende nicht schlafen legen |

## Stimmen

```powershell
.\Reachy-Claude.cmd voices
.\Reachy-Claude.cmd say -Stimme de_DE-kerstin-low -Text "Hallo, ich bin Reachy."
.\Reachy-Claude.cmd listen -Stimme de_DE-kerstin-low
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
.\Reachy-Claude.cmd listen -Projekt "D:\code\mein-projekt"
# danach genügt:
.\Reachy-Claude.cmd listen
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
- Es läuft immer **ein Auftrag** zur Zeit. Währenddessen hört Reachy weiter zu – für „stopp“
  und „wiederhole“; ein neuer Auftrag wird erst nach dem laufenden angenommen.

**Was Claude darf** (fest eingebaut): Dateien **nur im Projektordner** lesen und – mit Rechten
`edit` (Standard) – bearbeiten/anlegen. **Nie**: Dateien außerhalb des Projektordners, Shell-Befehle
(auch PowerShell), Internet, Zusatz-Server (MCP), Subagenten; nie ändern: `.git`, `.github`, `.claude`,
`.vscode`, `.idea`, Git-Hooks und `CLAUDE.md`. Einstellungen und Hooks aus Einstellungsdateien gelten
für Sprachaufträge nicht – auch ein fremdes, manipuliertes Repo kann so keine Befehle einschleusen.
Als Projektordner nicht erlaubt: ganzes Laufwerk, dein Benutzerordner, AppData, der Ordner dieser App.
Alles andere wird ohne Rückfrage verweigert.

| Option | Wirkung |
|---|---|
| `-Projekt "D:\pfad"` | Projektordner festlegen/wechseln (gespeichert) |
| `-Rechte read` / `-Rechte edit` | nur lesen / auch bearbeiten (gespeichert) |
| `-OhneClaude` | Test ohne Claude: Reachy wiederholt nur den Auftrag |

In `app\einstellungen.toml` lassen sich außerdem `timeout_minuten` und `claude_programm`
(Pfad zu `claude.exe`, falls nicht gefunden – nur Programme namens `claude`, `claude.exe` oder
`claude.cmd`) eintragen. **Windows-Pfade in einfache Anführungszeichen**, z. B.
`claude_programm = 'C:\Users\anna\.local\bin\claude.exe'` (in doppelten Anführungszeichen
müssten die Backslashes verdoppelt werden).

---

## Schritt 3 testen: Reachy spricht

```powershell
git pull
.\Reachy-Claude.cmd say -Text "Hallo, ich bin Reachy."
.\Reachy-Claude.cmd listen
```

- Beim ersten Start wird die Sprachausgabe *Piper* installiert und die deutsche Stimme
  *thorsten-medium* (~60 MB) einmalig heruntergeladen (`app\voices\`). Danach lokal.
- `say` lässt Reachy einen beliebigen Text sprechen.
- `listen -OhneClaude` bestätigt jeden Auftrag nur mit Stimme („Verstanden: …“) – zum Testen
  ohne Claude.
- Damit Reachy sich nicht selbst zuhört, wird alles verworfen, was das Mikrofon während
  seiner eigenen Ansage und 1,5 s danach aufnimmt.
- `-Silent`: Reachy antwortet nur als Text, ohne Stimme.
- **Aussprache:** Englische Wörter spricht die deutsche Stimme „deutsch“ aus. In
  `app\aussprache.txt` steht, wie sie gesprochen werden sollen (z. B. `Reachy = Rietschi`,
  `Claude = Klohd`). Eigene Ergänzungen bitte in **`app\aussprache-eigene.txt`** (gleiches Format,
  wird nicht von `git pull` überschrieben); gilt ab dem nächsten Start.

Bitte achte auf: Klingt die Stimme gut/verständlich? Reagiert Reachy auf seine eigene
Ansage (sollte er nicht)? Wie lange dauert es vom Satzende bis Reachy antwortet?

---

## Schritt 2 testen: Spracherkennung + Aktivierungswort

```powershell
git pull
.\Reachy-Claude.cmd listen
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
- (Damals in Schritt 2 ging noch nichts an Claude; seit Schritt 4 schon.)

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
.\Reachy-Claude.cmd check-audio
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
├── Reachy-Claude.cmd        Doppelklick-Start (ruft reachy-claude.ps1 auf)
├── reachy-claude.ps1        Startskript (Windows): Parameter, Desktop-Verknuepfung
├── plan.md                  Plan, Entscheidungen, Recherche
├── SECURITY.md              Sicherheit
├── app/                     die App (Python ≥ 3.11)
│   ├── src/reachy_claude/
│   │   ├── __main__.py      Kommandozeile (listen, pruefen, check-audio, say, voices)
│   │   ├── doctor.py        Schritt 6: Startpruefung mit „So behebst du es“ (inkl. Reachy-Version vs. Sicherheitsluecken)
│   │   ├── robot.py         Verbindung zu Reachy (SDK), verständliche Fehlermeldungen
│   │   ├── audio.py         Audio-Hilfen: Mono, Pegel, Töne, WAV
│   │   ├── check_audio.py   Schritt 1: Audio-Test
│   │   ├── segmenter.py     Sätze aus dem Mikrofon-Strom schneiden (Pegel, lernt Grundrauschen)
│   │   ├── stt.py           Spracherkennung (faster-whisper; GPU, sonst CPU)
│   │   ├── wakeword.py      Aktivierungswort „Claude“ (tolerant: Cloud, Klod …)
│   │   ├── tts.py           Sprachausgabe (Piper, deutsche Stimme, 16 kHz, Aussprache-Liste)
│   │   ├── settings.py      gemerkte Einstellungen (einstellungen.toml: [claude], [reachy]), strenge Prüfung
│   │   ├── claude.py        Claude Code CLI sicher aufrufen (aus v1): dontAsk, keine Shell/Web/MCP, Timeout
│   │   ├── spoken.py        Vorlesetext aus Claudes Antwort (SPRECHTEXT-Zeile, aus v1)
│   │   ├── assistant.py     Auftrag → Claude im Hintergrund (Zwischenmeldungen, „stopp“, „wiederhole“) → Terminal + Vorlesen
│   │   ├── motion.py        Schritt 5: Stimmungen → Kopf/Antennen (25 Hz, geglättet, begrenzt)
│   │   └── listener.py      Mikrofon-Thread → Sätze → Text → Auftrag; Voice/SpeechGate: Reachy spricht (ohne Selbstgespräch)
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

**Verifiziert Schritt 6 (2026-10-08):** 186 Tests ✅ (u. a. Abbruch beendet den Prozessbaum, Steuerwörter vs. echte Aufträge, Einstellungen gemerkt/geprüft, keine Echos während Hintergrund-Ansagen, Startprüfung inkl. echtem HTTP-Abruf) · `pruefen` gegen den **echten Reachy-Daemon (Simulation)**: Version 1.11.0 gelesen, Sicherheitshinweise korrekt · **echte Claude CLI**: Auftrag nach 4 s per „stopp“ abgebrochen (Prozess beendet), danach Auftrag + „wiederhole“ ✅ · CI Windows: `Reachy-Claude.cmd pruefen` und Desktop-Verknüpfung.

**Verifiziert Schritt 5 (2026-10-08):** 126 Tests ✅ (u. a. alle Stimmungen innerhalb der Grenzen, keine Sprünge > 3°/40 ms) · gegen den **echten Reachy-Daemon im Simulationsmodus**: Aufwachen, alle Stimmungen (Kopf folgt: Zuhören 8° schräg/3° hoch, Nachdenken 8° hoch), Antennen-Richtungen, Sprech-Wackeln, Schlafen ✅.

**Verifiziert Schritt 4 (2026-10-08):** 104 Tests ✅ (inkl. v1-Tests des Claude-Aufrufs, unter Windows mit `.cmd`-Startdatei) · **echter Durchlauf mit Claude Code CLI**: Datei geändert, Folgefrage mit Kontext, „neues Thema“ – Sprechtexte mit Piper vertont ✅.

**Verifiziert Schritt 3 (2026-10-08):** 55 Tests ✅ (u. a. „Reachy hört sich nicht selbst zu“ – Gegenprobe: ohne Echo-Löschen wird der Test rot) · echte Piper-Synthese lokal ✅ · CI: Piper thorsten-medium + Rundweg Piper → Whisper → Aktivierungswort.

**Verifiziert Schritt 2 (2026-10-08):** 46 Tests ✅ · Satzerkennung mit echter (synthetischer) deutscher Sprache + Raumrauschen ✅ (dabei Schwelle von 12 auf 6 dB korrigiert) · echte Whisper-Erkennung läuft in CI unter Windows (hier blockiert die Umgebung Hugging Face).

**Verifiziert Schritt 1 (2026-10-08):** 17 Tests ✅ · Ruff/Mypy (strict) ✅ · gegen das echte SDK
`reachy-mini 1.11.0` und einen simulierten Reachy-Daemon (`--mockup-sim`): Verbindung
und Fehlermeldungen ✅. Der WebRTC-Audioweg selbst ist **noch nicht am echten Reachy
getestet** – genau dafür ist Schritt 1 da.
