from reachy_claude.spoken import EMPTY_FALLBACK, TRUNCATION_SUFFIX, make_spoken_text, strip_markdown


def test_spoken_marker_is_preferred() -> None:
    text = "Lange Erklaerung mit `code`.\n\nSPRECHTEXT: Ich habe **zwei** Tests ergaenzt."
    assert make_spoken_text(text, 500) == "Ich habe zwei Tests ergaenzt."


def test_last_marker_wins_and_markdown_decoration_is_tolerated() -> None:
    assert make_spoken_text("SPRECHTEXT: alt\n\n**Sprechtext:** neu", 500) == "neu"


def test_marker_in_middle_of_line_is_ignored() -> None:
    assert make_spoken_text("Das Wort SPRECHTEXT: steht hier.", 500) == "Das Wort SPRECHTEXT: steht hier."


def test_fallback_strips_code_markdown_tables_and_urls() -> None:
    text = (
        "# Ergebnis\n\n- Punkt **eins** mit `foo()`\n- Siehe [Doku](https://x.y/z)\n\n"
        "| a | b |\n|---|---|\n\n```python\nsecret = 1\n```\nMehr unter https://example.com/abc."
    )
    spoken = strip_markdown(text)
    assert "secret" not in spoken
    assert "|" not in spoken and "#" not in spoken and "**" not in spoken
    assert "https://" not in spoken
    assert "Punkt eins mit foo()" in spoken
    assert "Doku" in spoken
    assert "(Code siehe PC)" in spoken


def test_unclosed_code_fence_is_removed() -> None:
    assert "geheim" not in strip_markdown("Text\n```\ngeheim")


def test_truncates_at_sentence_boundary() -> None:
    text = "Erster Satz ist da. " * 40
    spoken = make_spoken_text(text, 200)
    assert len(spoken) <= 200
    assert spoken.endswith(TRUNCATION_SUFFIX)
    assert spoken[: -len(TRUNCATION_SUFFIX)].endswith(".")


def test_truncates_without_sentence_end() -> None:
    spoken = make_spoken_text("wort " * 200, 120)
    assert len(spoken) <= 120 + 2
    assert spoken.endswith(TRUNCATION_SUFFIX)


def test_empty_result_gets_fallback() -> None:
    assert make_spoken_text("```\nnur code\n```", 300) == "(Code siehe PC)"
    assert make_spoken_text("   ", 300) == EMPTY_FALLBACK


def test_snake_case_identifiers_survive() -> None:
    assert strip_markdown("Die Funktion load_user_data und __init__ und _privat_") == (
        "Die Funktion load_user_data und init und privat"
    )
