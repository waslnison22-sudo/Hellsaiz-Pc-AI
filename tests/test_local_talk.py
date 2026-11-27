"""Local conversation bank contracts: intent matching, variety, no repeats."""

from __future__ import annotations

import random

from hellsaiz_pc_ai.app import local_talk


def test_greeting_matches_and_answers():
    local_talk.reset_history()
    assert local_talk.has_local_answer("Привет, как дела?")
    answer = local_talk.reply("Привет!")
    assert answer
    assert isinstance(answer, str)


def test_unknown_phrase_still_gets_a_live_answer():
    local_talk.reset_history()
    assert local_talk.has_local_answer("совершенно случайная фраза без ключевых слов") is False
    answer = local_talk.reply("совершенно случайная фраза без ключевых слов")
    assert answer
    assert "локальных команд" not in answer


def test_replies_do_not_repeat_back_to_back():
    local_talk.reset_history()
    rng = random.Random(7)
    seen = [local_talk.reply("привет", rng=rng) for _ in range(6)]
    assert all(seen[index] != seen[index + 1] for index in range(len(seen) - 1))


def test_bank_is_large_enough_to_feel_alive():
    phrases = sum(len(intent.patterns) for intent in local_talk.INTENTS)
    replies = sum(len(intent.replies) for intent in local_talk.INTENTS) + len(local_talk.GENERIC)
    assert phrases >= 60
    assert replies >= 100


def test_thanks_and_goodbye_are_recognised():
    local_talk.reset_history()
    assert local_talk.has_local_answer("Спасибо большое!")
    assert local_talk.has_local_answer("Пока, до встречи")
    assert local_talk.has_local_answer("Расскажи шутку")
