from hellsaiz_pc_ai.core.reply_style import build_system_prompt


def test_reply_style_adds_expected_russian_guidance():
    assert "Отвечай кратко" in build_system_prompt("Базовая роль", "brief")
    assert "структурированно" in build_system_prompt("Базовая роль", "normal")
    assert "подробно" in build_system_prompt("Базовая роль", "detailed")


def test_unknown_reply_style_falls_back_to_normal():
    assert build_system_prompt("Базовая роль", "unknown") == build_system_prompt(
        "Базовая роль", "normal"
    )
