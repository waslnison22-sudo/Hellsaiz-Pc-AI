import pytest

from hellsaiz_pc_ai.speech.sapi5 import Sapi5Synthesizer


def test_sapi5_rejects_invalid_rate():
    with pytest.raises(ValueError):
        Sapi5Synthesizer(rate=400)


def test_sapi5_rejects_invalid_volume():
    with pytest.raises(ValueError):
        Sapi5Synthesizer(volume=1.1)
