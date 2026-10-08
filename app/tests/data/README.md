# Testdaten

- `vier_saetze_raumrauschen.wav` (16 kHz, mono, ~17 s): vier deutsche Saetze, mit der
  Piper-Stimme *Thorsten (low)* erzeugt (Datensatz-Lizenz CC0,
  https://github.com/thorstenMueller/Thorsten-Voice), auf typischen Reachy-Pegel
  abgesenkt (~ -27 dB) und mit Raumrauschen (~ -40 dB, wie am echten Reachy gemessen)
  gemischt. Saetze: "Was gibt es heute zu essen?", "Claude, schreib bitte einen Test fuer
  die Login-Funktion.", "Claude.", "Erklaere mir, was die Datei main punkt py macht."
  Regressionstest: Mit der frueheren Schwelle (12 dB) wurden nur 2 von 4 Saetzen erkannt.
