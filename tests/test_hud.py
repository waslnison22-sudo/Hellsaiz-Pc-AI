import pytest


pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QLabel

from hellsaiz_pc_ai.app.hud import AnimatedPageStack


def _application():
    return QApplication.instance() or QApplication([])


def test_animated_page_stack_can_disable_transitions():
    _application()
    stack = AnimatedPageStack(duration_ms=160)
    stack.addWidget(QLabel("Чат"))
    stack.addWidget(QLabel("Сценарии"))
    stack.set_animations_enabled(False)

    stack.setCurrentIndex(1)

    assert stack.currentIndex() == 1
    assert stack._animation is None


def test_animated_page_stack_uses_a_bounded_transition_duration():
    _application()

    assert AnimatedPageStack(duration_ms=900).duration_ms == 400
    assert AnimatedPageStack(duration_ms=-10).duration_ms == 0
