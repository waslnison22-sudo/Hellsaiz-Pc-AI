import pytest

try:
    from hellsaiz_pc_ai.app.skills_page import SKILL_CARDS
except ImportError as exc:  # Linux CI runners lack Qt native libs (libEGL); full run on Windows.
    pytest.skip(f"Qt native libraries unavailable: {exc}", allow_module_level=True)


def test_skill_cards_exist_and_cover_real_capabilities():
    assert len(SKILL_CARDS) >= 10

    titles = [title for _, title, _ in SKILL_CARDS]
    for expected in ("Программы", "Окна", "Напоминания", "Погода и курсы", "Приватность"):
        assert expected in titles, expected


def test_skill_cards_reference_only_real_command_phrases():
    for _glyph, _title, note in SKILL_CARDS:
        assert note and note.strip()
        # Notes quote real commands; no invented timers or shutdowns.
        assert "таймер" not in note.casefold()
        assert "выключи компьютер" not in note.casefold()


def test_every_card_has_glyph_title_and_note():
    for glyph, title, note in SKILL_CARDS:
        assert glyph.strip()
        assert title.strip()
        assert note.strip()
