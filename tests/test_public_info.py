
from hellsaiz_pc_ai.tools import public_info


class FakeResponse:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, size=-1):
        return self.payload if size < 0 else self.payload[:size]


def test_search_web_returns_short_result_and_source(monkeypatch):
    html = (
        '<div class="result"><a class="result__a" href="https://example.org/page">Title</a>'
        '<a class="result__snippet">Short source summary</a></div>'
    ).encode()
    monkeypatch.setattr(public_info, "urlopen", lambda *args, **kwargs: FakeResponse(html))

    result = public_info.search_web("test query")

    assert "Title" in result
    assert "Short source summary" in result
    assert "example.org" in result


def test_currency_rate_uses_reference_rate_endpoint(monkeypatch):
    monkeypatch.setattr(
        public_info,
        "_get_json",
        lambda url, timeout=12: {"base": "USD", "quote": "RUB", "rate": 91.25, "date": "2026-11-13"},
    )

    result = public_info.get_exchange_rate("USD", "RUB")

    assert "91.2500" in result
    assert "не биржевая котировка" in result


def test_weather_resolves_city_then_current_conditions(monkeypatch):
    responses = iter([
        {"results": [{"name": "Москва", "latitude": 55.75, "longitude": 37.61}]},
        {"current": {
            "temperature_2m": -2,
            "apparent_temperature": -5,
            "precipitation": 0,
            "weather_code": 3,
            "wind_speed_10m": 4,
        }},
    ])
    monkeypatch.setattr(public_info, "_get_json", lambda *args, **kwargs: next(responses))

    result = public_info.get_weather("Москва")

    assert "Москва" in result
    assert "пасмурно" in result
