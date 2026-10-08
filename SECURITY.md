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
| S4 | Claude richtet Schaden an | Wie v1: `--permission-mode dontAsk`, nur Lesen/Bearbeiten im Projektordner (`-Rechte read` möglich), **keine Shell, kein Internet, keine MCP-Server**, Timeout beendet den Prozessbaum, Prompt nur über stdin (keine Argument-Injection, auch nicht über `claude.cmd`), ganzes Laufwerk als Projektordner verboten | ✅ |
| S5 | Manipulierte Texte im Terminal (Steuerzeichen) | Erkannte Texte werden vor Anzeige/Weitergabe bereinigt | ✅ |
| S6 | Supply-Chain | wenige, verbreitete Abhängigkeiten; Reachy-SDK auf `~=1.11.0` begrenzt | ✅ |
| S7 | Aufnahmen/Mitschriften auf der Festplatte | Audio-Test-WAV in `app/aufnahmen/`, Claude-Mitschriften in `app/mitschriften/` – nur lokal, nicht in Git | ✅ |
| S8 | Daten an Anthropic | Nur der Auftrag und die Projektdateien, die Claude für den Auftrag liest. Projektordner bewusst wählen (keine Geheimnisse darin) | ✅ |

## Bewusst offen / Restrisiken
- **Reachys eigene Dienste** (Daemon-API Port 8000, WebRTC-Signalisierung Port 8443,
  Dashboard) sind im WLAN **ohne Passwort** erreichbar. Das ist das Design von Pollen,
  nicht unser Code. Wer im Heimnetz ist, kann Reachy steuern bzw. mithören.
  Empfehlung: Gäste-WLAN für fremde Geräte.
- Der WebRTC-Ton zwischen Reachy und PC ist verschlüsselt (WebRTC/DTLS); die
  Signalisierung (`ws://`, Port 8443) nicht.
- Keine Sprechererkennung: Jeder im Raum kann „Claude, …“ sagen.
- **Kamerabild:** Die WebRTC-Verbindung des SDK überträgt fest auch Reachys Kamerabild an den PC
  (mehr Netzlast im Heimnetz). Es wird weder gespeichert noch ausgewertet. Ein „nur Audio“-Modus
  existiert im SDK (1.11 und main) nicht; Entscheidung des Nutzers (2026-10-08): **so lassen**.
