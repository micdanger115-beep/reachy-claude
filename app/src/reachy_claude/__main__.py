"""Kommandozeile: ``reachy-claude listen | pruefen | check-audio | say | voices``."""

from __future__ import annotations

import argparse
import logging
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .check_audio import run_audio_check
from .robot import DEFAULT_ROBOT, RobotConnectionError, connect, wait_for_audio
from .settings import SETTINGS_FILE, ReachySettings, SettingsError, remember_reachy
from .tts import DEFAULT_VOICE, Speaker

if TYPE_CHECKING:
    from .assistant import Speaks
    from .motion import Animator
    from .settings import ClaudeSettings

logger = logging.getLogger("reachy_claude")

GREETING = "Hallo! Ich höre zu. Sag Claude und dann deinen Auftrag."
SAY_LINGER_S = 2.0  # Verbindung nach "say" offen halten, bis Reachy wirklich fertig gesprochen hat


def print_line(line: str) -> None:
    print(line, flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reachy-claude", description="Mit Reachy sprechen, Claude arbeitet."
    )
    parser.add_argument(
        "--robot", help=f"Name oder IP von Reachy (wird gespeichert; Standard: {DEFAULT_ROBOT})"
    )
    parser.add_argument("--debug", action="store_true", help="ausfuehrliche Meldungen")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check-audio", help="Schritt 1: Mikrofon und Lautsprecher von Reachy testen")
    check.add_argument("--seconds", type=float, default=5.0, help="Aufnahmedauer in Sekunden (Standard: 5)")
    check.add_argument(
        "--save", type=Path, default=Path("aufnahmen") / f"audio-test-{time.strftime('%Y%m%d-%H%M%S')}.wav"
    )

    sub.add_parser("voices", help="Alle deutschen Stimmen anzeigen")

    check = sub.add_parser("pruefen", help="Startpruefung: ist alles bereit?")
    check.add_argument("--device", choices=["auto", "cuda", "cpu"], default="auto")

    say = sub.add_parser("say", help="Schritt 3: Reachy einen Text sprechen lassen")
    say.add_argument("text", help="was Reachy sagen soll")
    say.add_argument("--voice", help="Piper-Stimme zum Ausprobieren (Standard: die gespeicherte)")
    say.add_argument("--speaker", help="Sprecher bei Stimmen mit mehreren Sprechern (Name oder Nummer)")

    listen = sub.add_parser(
        "listen", help="Zuhoeren: 'Claude, ...' geht an Claude Code, Reachy liest die Antwort vor"
    )
    listen.add_argument("--project", type=Path, help="Projektordner fuer Claude (wird gespeichert)")
    listen.add_argument(
        "--permission", choices=["read", "edit"], help="Rechte fuer Claude (wird gespeichert)"
    )
    listen.add_argument(
        "--no-claude", action="store_true", help="Test ohne Claude: Reachy wiederholt nur den Auftrag"
    )
    listen.add_argument(
        "--device", choices=["auto", "cuda", "cpu"], default="auto", help="Spracherkennung auf ..."
    )
    listen.add_argument("--model", help="Whisper-Modell (Standard: large-v3-turbo auf GPU, small auf CPU)")
    listen.add_argument("--voice", help=f"Piper-Stimme (wird gespeichert; Standard: {DEFAULT_VOICE})")
    listen.add_argument("--speaker", help="Sprecher bei Stimmen mit mehreren Sprechern (wird gespeichert)")
    listen.add_argument("--silent", action="store_true", help="Reachy antwortet nicht mit Stimme (nur Text)")
    listen.add_argument(
        "--motion",
        action=argparse.BooleanOptionalAction,
        help="Kopf und Antennen bewegen (wird gespeichert; Standard: an)",
    )
    listen.add_argument("--stay-awake", action="store_true", help="Reachy am Ende nicht schlafen legen")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    if args.command == "check-audio" and not 1.0 <= args.seconds <= 60.0:
        print("--seconds muss zwischen 1 und 60 liegen.")
        return 2

    if args.command == "voices":
        return run_voices()
    try:
        reachy = remember_reachy(
            SETTINGS_FILE,
            robot=args.robot,
            # Stimme/Bewegung merken wir nur beim Zuhoeren; "say" ist zum Ausprobieren da.
            **(
                {"voice": args.voice, "speaker": args.speaker, "motion": args.motion}
                if args.command == "listen"
                else {}
            ),
        )
    except SettingsError as exc:
        print(f"FEHLER: {exc}")
        return 2

    try:
        if args.command == "listen":
            return run_listen(args, reachy)
        if args.command == "say":
            return run_say(args, reachy)
        if args.command == "pruefen":
            return run_doctor(args, reachy)
        print(f"Verbinde mit Reachy ({reachy.robot}) ...")
        with connect(reachy.robot, debug=args.debug) as mini:
            print("Verbunden.")
            result = run_audio_check(mini.media, print_line, seconds=args.seconds, save_to=args.save)
        return 0 if result.mic_ok else 1
    except RobotConnectionError as exc:
        print(f"FEHLER: {exc}")
        return 1
    except KeyboardInterrupt:
        print("Beendet.")
        return 0


def run_voices() -> int:
    from .tts import GERMAN_VOICES

    print("Deutsche Stimmen (Auswahl mit -Stimme <Name>, Download beim ersten Benutzen):\n")
    for name, description in GERMAN_VOICES.items():
        print(f"  {name:34s} {description}")
    print(
        '\nAusprobieren:  .\\reachy-claude.ps1 say -Stimme de_DE-kerstin-low -Text "Hallo, ich bin Reachy."'
    )
    return 0


def load_speaker(voice: str, speaker_name: str | None = None) -> Speaker | None:
    """Piper-Stimme laden (beim ersten Mal Download); ``None`` mit Meldung bei Fehler."""
    from .tts import PiperSpeaker, TtsConfig

    print("Lade Stimme (beim ersten Start einmaliger Download von Hugging Face, ca. 60 MB) ...")
    try:
        speaker = PiperSpeaker(TtsConfig(voice=voice, speaker=speaker_name))
    except Exception as exc:  # Download-, Datei- oder Modellfehler – alle gleich behandeln
        logger.debug("Stimme nicht ladbar", exc_info=True)
        print(f"FEHLER: Stimme '{voice}' konnte nicht geladen werden ({type(exc).__name__}: {exc}).")
        print("Beim ersten Start braucht der PC Internet, um die Stimme herunterzuladen.")
        return None
    print(f"Stimme bereit: {speaker.description}")
    return speaker


def run_doctor(args: argparse.Namespace, reachy: ReachySettings) -> int:
    from .doctor import has_errors, report, run_checks

    print(f"Startpruefung (Reachy: {reachy.robot}, Einstellungen: app\\{SETTINGS_FILE}) ...\n")
    checks = run_checks(
        host=reachy.robot, voice=reachy.voice, settings_file=SETTINGS_FILE, device=args.device
    )
    report(checks, print_line)
    if has_errors(checks):
        print("\nEs gibt Fehler (FEHL) – bitte zuerst beheben.")
        return 1
    print("\nAlles bereit. Starten mit Doppelklick auf Reachy-Claude.cmd.")
    return 0


def run_say(args: argparse.Namespace, reachy: ReachySettings) -> int:
    from .listener import Voice

    # eigene Stimme zum Ausprobieren; sonst die gespeicherte samt Sprecher
    voice = args.voice or reachy.voice
    speaker_name = args.speaker if (args.voice or args.speaker) else reachy.speaker
    speaker = load_speaker(voice, speaker_name)
    if speaker is None:
        return 1
    print(f"Verbinde mit Reachy ({reachy.robot}) ...")
    with connect(reachy.robot, debug=args.debug) as mini:
        wait_for_audio(mini.media)
        Voice(speaker, mini.media, print_line).say(args.text)
        # Reachy spielt mit Verzoegerung ab; trennt man sofort, fehlt das Satzende.
        time.sleep(SAY_LINGER_S)
    return 0


def ask_for_project(input_fn: Callable[[str], str] = input) -> Path | None:
    """Projektordner abfragen: Ordner-Auswahlfenster, sonst Eingabe im Terminal."""
    print(
        "Noch kein Projektordner fuer Claude festgelegt. Bitte waehle den Ordner, in dem Claude arbeiten soll."
    )
    folder = _folder_dialog()
    if folder == "":  # im Auswahlfenster abgebrochen
        return None
    if folder is None:
        try:
            folder = input_fn("Projektordner (Pfad einfuegen, leer = abbrechen): ").strip().strip('"')
        except EOFError:
            folder = ""
    return Path(folder) if folder else None


def _folder_dialog() -> str | None:
    """Windows-Ordnerauswahl ueber tkinter (Teil von Python).

    ``None``, wenn kein Fenster moeglich ist; ``""``, wenn im Fenster abgebrochen wurde.
    """
    if sys.platform != "win32":
        return None
    try:
        from tkinter import Tk, filedialog

        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        chosen = filedialog.askdirectory(title="Projektordner fuer Claude waehlen", mustexist=True)
        root.destroy()
    except Exception as exc:  # kein tkinter/kein Bildschirm: dann eben per Eingabe
        logger.debug("Ordnerauswahl nicht moeglich: %s", exc)
        return None
    return str(chosen) if chosen else ""


def prepare_claude(
    args: argparse.Namespace, choose_project: Callable[[], Path | None] | None = None
) -> ClaudeSettings | None:
    """Einstellungen fuer Claude laden (und ggf. neuen Projektordner speichern)."""
    from .settings import MissingProjectError, Permission, load_settings, save_settings

    if args.project is None and choose_project is not None:
        try:
            load_settings(SETTINGS_FILE)
        except MissingProjectError:
            args.project = choose_project()
            if args.project is None:
                print("Abgebrochen – ohne Projektordner kann Claude nicht arbeiten.")
                return None
        except SettingsError:
            pass  # wird unten mit Meldung behandelt

    try:
        if args.project is not None:
            settings = load_settings(SETTINGS_FILE, workdir_override=args.project)
            save_settings(SETTINGS_FILE, settings.workdir, Permission(args.permission or settings.permission))
        settings = load_settings(SETTINGS_FILE)
        if args.permission and settings.permission.value != args.permission:
            save_settings(SETTINGS_FILE, settings.workdir, Permission(args.permission))
            settings = load_settings(SETTINGS_FILE)
    except SettingsError as exc:
        print(f"FEHLER: {exc}")
        return None
    rights = "lesen + Dateien bearbeiten" if settings.permission.value == "edit" else "nur lesen"
    print(f"Claude arbeitet in: {settings.workdir}  (Rechte: {rights}; nie Shell, nie Internet)")
    return settings


def run_listen(args: argparse.Namespace, reachy: ReachySettings) -> int:
    from .assistant import ClaudeAssistant, PrintOnly, control_word
    from .claude import ClaudeRunner
    from .doctor import has_errors, report, run_checks
    from .listener import CommandParser, SpeechGate, Voice, listen
    from .motion import Mood, MovingVoice
    from .stt import SttConfig, WhisperTranscriber

    print(f"Startpruefung (Reachy: {reachy.robot}) ...")
    checks = run_checks(
        host=reachy.robot,
        voice=reachy.voice,
        settings_file=SETTINGS_FILE,
        with_claude=not args.no_claude,
        with_project=False,  # fragt prepare_claude selbst ab
        with_gpu=False,  # meldet die Spracherkennung beim Laden selbst
    )
    report(checks, print_line, problems_only=True)
    if has_errors(checks):
        print("Start abgebrochen – bitte zuerst beheben (Gesamtuebersicht: reachy-claude.ps1 pruefen).")
        return 1

    interactive = sys.stdin is not None and sys.stdin.isatty()
    settings = None if args.no_claude else prepare_claude(args, ask_for_project if interactive else None)
    if settings is None and not args.no_claude:
        return 1

    print("Lade Spracherkennung (beim ersten Start einmaliger Download von Hugging Face, bis ca. 1,5 GB) ...")
    try:
        transcriber = WhisperTranscriber(SttConfig(device=args.device, model=args.model))
    except RuntimeError as exc:
        print(f"FEHLER: {exc}")
        print("Beim ersten Start braucht der PC Internet, um das Sprachmodell herunterzuladen.")
        return 1
    print(f"Spracherkennung bereit: {transcriber.description}")

    speaker = None
    if not args.silent:
        speaker = load_speaker(reachy.voice, reachy.speaker)
        if speaker is None:
            return 1

    print(f"Verbinde mit Reachy ({reachy.robot}) ...")
    with connect(reachy.robot, debug=args.debug) as mini:
        wait_for_audio(mini.media)
        animator = start_motion(mini) if reachy.motion else None
        print('Verbunden. Sprich mit Reachy – Auftraege beginnen mit "Claude, ...". Beenden mit Strg+C.')
        print(
            'Waehrend Claude arbeitet: "Claude, stopp" bricht ab, "Claude, wiederhole" liest nochmal vor.\n'
        )
        base_voice: Speaks = (
            Voice(speaker, mini.media, print_line) if speaker is not None else PrintOnly(print_line)
        )
        # Ein Satz gleichzeitig; waehrenddessen hoert Reachy weg (sonst hoert er sich selbst).
        voice = SpeechGate(MovingVoice(base_voice, animator) if animator is not None else base_voice)

        assistant: ClaudeAssistant | None = None
        if settings is None:

            def on_command(command: str) -> None:
                voice.say(f"Verstanden: {command}")  # Test ohne Claude

        else:
            assistant = ClaudeAssistant(
                ClaudeRunner(settings),
                voice,
                print_line,
                spoken_max_chars=settings.spoken_max_chars,
                mood=animator,
            )
            on_command = assistant.submit  # Claude arbeitet im Hintergrund, Reachy hoert weiter zu

        def on_event(event: str) -> None:
            if animator is None:
                return
            if event == "speech_start":
                animator.set_mood(Mood.LISTENING)
            elif event == "speech_end" and animator.mood is Mood.LISTENING:
                busy = assistant is not None and assistant.busy
                animator.set_mood(Mood.THINKING if busy else Mood.IDLE)

        parser = CommandParser(print_line, on_wake=animator.acknowledge if animator is not None else None)
        voice.say(GREETING)
        stop = threading.Event()
        try:
            listen(
                mini.media,
                transcriber,
                print_line,
                on_command=on_command,
                stop=stop,
                parser=parser,
                on_event=on_event,
                muted=voice.muted,
                # "stopp"/"wiederhole" sofort, ohne auf eine Fortsetzung des Auftrags zu warten
                immediate=lambda command: control_word(command) is not None,
            )
        except KeyboardInterrupt:
            stop.set()
            print("Beendet.")
        finally:
            if assistant is not None:
                assistant.shutdown()
            if animator is not None:
                animator.stop()
                if not args.stay_awake:
                    print("Reachy legt sich schlafen ...")
                    try:
                        mini.goto_sleep()
                    except Exception as exc:  # Ende soll nie an der Schlafbewegung scheitern
                        logger.warning("Schlafbewegung fehlgeschlagen: %s", exc)
    return 0


def start_motion(mini: Any) -> Animator | None:
    """Reachy aufwecken, Sprech-Wackeln einschalten und die Bewegung starten."""
    from reachy_mini.utils import create_head_pose

    from .motion import Animator

    try:
        print("Reachy wacht auf ...")
        mini.wake_up()
        mini.enable_wobbling()  # Kopf bewegt sich passend zur gesprochenen Antwort
    except Exception as exc:  # Bewegung ist Zugabe: ohne sie geht es trotzdem weiter
        logger.warning("Aufwachen/Wackeln nicht moeglich: %s", exc)
        print(f"Hinweis: Bewegungen nicht verfuegbar ({type(exc).__name__}). Es geht ohne weiter.")
        return None
    animator = Animator(mini, create_head_pose)
    animator.start()
    return animator


if __name__ == "__main__":
    sys.exit(main())
