
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


def _weather_payloads():
    geocoding = {"results": [{"name": "Москва", "latitude": 55.75, "longitude": 37.61}]}
    forecast = {
        "current": {
            "time": "2026-11-19T20:00",
            "temperature_2m": -2.4,
            "apparent_temperature": -5.1,
            "relative_humidity_2m": 81,
            "weather_code": 3,
            "wind_speed_10m": 4.3,
        },
        "hourly": {
            "time": ["2026-11-19T20:00", "2026-11-19T21:00", "2026-11-19T22:00"],
            "temperature_2m": [-2.4, -2.9, -3.4],
        },
        "daily": {
            "time": ["2026-11-19", "2026-11-20", "2026-11-21", "2026-11-22", "2026-11-23"],
            "weather_code": [3, 61, 0, 71, 2],
            "temperature_2m_max": [3.2, 4.4, 1.1, -0.5, 2.0],
            "temperature_2m_min": [-1.4, 0.2, -2.1, -4.4, -3.0],
        },
    }
    return geocoding, forecast


def test_weather_report_resolves_city_with_open_meteo(monkeypatch):
    public_info._WEATHER_CACHE.clear()
    geocoding, forecast = _weather_payloads()
    responses = iter([geocoding, forecast])
    calls: list[str] = []

    def fake_get_json(url, timeout=12):
        calls.append(url)
        return next(responses)

    monkeypatch.setattr(public_info, "_get_json", fake_get_json)

    report = public_info.get_weather_report("Москва")

    assert report.city == "Москва"
    assert report.condition == "пасмурно"
    assert report.code == 3
    assert round(report.temperature) == -2
    assert round(report.apparent) == -5
    assert report.humidity == 81
    assert len(report.hourly) == 2
    assert report.hourly[0][0] == "21:00"
    assert len(report.daily) == 5
    assert report.daily[0].weekday == "Чт"
    assert report.daily[1].condition == "небольшой дождь"
    assert "Чт +3°" in report.forecast_line()
    assert all("open-meteo.com" in url for url in calls)


def test_weather_report_is_cached_for_ten_minutes(monkeypatch):
    public_info._WEATHER_CACHE.clear()
    geocoding, forecast = _weather_payloads()
    calls: list[str] = []

    def fake_get_json(url, timeout=12):
        calls.append(url)
        return geocoding if "geocoding" in url else forecast

    monkeypatch.setattr(public_info, "_get_json", fake_get_json)

    first = public_info.get_weather_report("Москва")
    second = public_info.get_weather_report("Москва")

    assert first is second
    assert len(calls) == 2  # geocoding + forecast, no second network round trip


def test_weather_text_mentions_hours_and_forecast(monkeypatch):
    public_info._WEATHER_CACHE.clear()
    geocoding, forecast = _weather_payloads()
    monkeypatch.setattr(
        public_info, "_get_json", lambda url, timeout=12: geocoding if "geocoding" in url else forecast
    )

    result = public_info.get_weather("Москва")

    assert "пасмурно" in result
    assert "Ближайшие часы" in result
    assert "Прогноз на 5 дней" in result


def test_weather_report_rejects_unknown_city(monkeypatch):
    public_info._WEATHER_CACHE.clear()
    monkeypatch.setattr(public_info, "_get_json", lambda *args, **kwargs: {"results": []})

    try:
        public_info.get_weather_report("Атлантида")
    except public_info.WeatherCityNotFound as error:
        assert "Не нашёл город" in str(error)
        assert error.city == "Атлантида"
    except ValueError as error:
        assert "Не нашёл город" in str(error)
    else:
        raise AssertionError("expected ValueError for an unknown city")


def test_weather_text_for_unknown_city_is_human_and_specific(monkeypatch):
    public_info._WEATHER_CACHE.clear()
    monkeypatch.setattr(public_info, "_get_json", lambda *args, **kwargs: {"results": []})

    result = public_info.get_weather("Атлантида")

    assert "нет в базе сервиса" in result
    assert "проверь название" in result
    assert "интернет" not in result


def test_get_json_retries_transient_errors_then_succeeds(monkeypatch):
    calls = {"count": 0}
    sleeps = []

    def flaky(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] < 3:
            raise OSError("transient network hiccup")
        return FakeResponse(b'{"ok": true}')

    monkeypatch.setattr(public_info, "urlopen", flaky)
    monkeypatch.setattr(public_info.time, "sleep", lambda seconds: sleeps.append(seconds))

    assert public_info._get_json("https://example.test/ping") == {"ok": True}
    assert calls["count"] == 3
    assert sleeps == [0.4, 0.8]


def test_get_json_retries_are_exhausted_and_error_propagates(monkeypatch):
    monkeypatch.setattr(public_info.time, "sleep", lambda _seconds: None)

    def always_fails(*args, **kwargs):
        raise OSError("no route to host")

    monkeypatch.setattr(public_info, "urlopen", always_fails)

    try:
        public_info._get_json("https://example.test/ping")
    except OSError:
        pass
    else:
        raise AssertionError("expected the last network error to propagate")
