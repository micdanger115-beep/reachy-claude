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
| S2 | Sprache verlässt das Haus | Spracherkennung und -ausgabe lokal auf dem PC; Audio nur im Heimnetz (WebRTC, Signalisierung auf dem Roboter) | ✅ Audio-Weg / ⏳ STT+TTS ab Schritt 2–3 |
| S3 | Versehentliche Aufträge (Fernseher, Gäste, Fehlerkennung) | Nur Sätze mit Aktivierungswort „Claude“ gehen weiter; ein Auftrag gleichzeitig | ⏳ Schritt 2/4 |
| S4 | Claude richtet Schaden an | Wie v1: `--permission-mode dontAsk`, nur Lesen/Bearbeiten im Projektordner, **keine Shell, kein Internet, keine MCP-Server**, Timeout, Prompt nur über stdin | ⏳ Schritt 4 (Code aus v1 übernommen) |
| S5 | Manipulierte Texte im Terminal (Steuerzeichen) | Texte werden vor der Anzeige bereinigt (wie v1 `listen`) | ⏳ Schritt 2 |
| S6 | Supply-Chain | wenige, verbreitete Abhängigkeiten; Reachy-SDK auf `~=1.11.0` begrenzt | ✅ |
| S7 | Aufnahmen auf der Festplatte | Audio-Test speichert WAV nur lokal in `app/aufnahmen/` (nicht in Git) | ✅ |

## Bewusst offen / Restrisiken
- **Reachys eigene Dienste** (Daemon-API Port 8000, WebRTC-Signalisierung Port 8443,
  Dashboard) sind im WLAN **ohne Passwort** erreichbar. Das ist das Design von Pollen,
  nicht unser Code. Wer im Heimnetz ist, kann Reachy steuern bzw. mithören.
  Empfehlung: Gäste-WLAN für fremde Geräte.
- Der WebRTC-Ton zwischen Reachy und PC ist verschlüsselt (WebRTC/DTLS); die
  Signalisierung (`ws://`, Port 8443) nicht.
- Keine Sprechererkennung: Jeder im Raum kann „Claude, …“ sagen.
