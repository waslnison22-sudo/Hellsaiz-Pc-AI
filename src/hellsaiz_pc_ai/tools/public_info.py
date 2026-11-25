from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import parse_qs, quote, unquote, urlparse
from urllib.request import Request, urlopen

from hellsaiz_pc_ai.core.models import RiskLevel, ToolResult
from hellsaiz_pc_ai.core.registry import ToolRegistry, ToolSpec
from hellsaiz_pc_ai.version import APP_VERSION


USER_AGENT = f"Hellsaiz-PC-AI/{APP_VERSION} (personal desktop assistant)"
WEATHER_CODES = {
    0: "ясно", 1: "преимущественно ясно", 2: "переменная облачность",
    3: "пасмурно", 45: "туман", 48: "изморозевый туман",
    51: "небольшая морось", 53: "морось", 55: "сильная морось",
    56: "ледяная морось", 57: "сильная ледяная морось",
    61: "небольшой дождь", 63: "дождь", 65: "сильный дождь",
    66: "ледяной дождь", 67: "сильный ледяной дождь",
    71: "небольшой снег", 73: "снег", 75: "сильный снег",
    77: "снежные зёрна",
    80: "ливневый дождь", 81: "сильные ливни", 82: "очень сильные ливни",
    85: "снежные ливни", 86: "сильные снежные ливни",
    95: "гроза", 96: "гроза с градом", 99: "сильная гроза с градом",
}


def _get_json(url: str, timeout: int = 8):
    """Fetch JSON with two transient-error retries (pauses: 0.4s, 0.8s)."""
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    delays = (0.0, 0.4, 0.8)
    last_error: Exception | None = None
    for index, delay in enumerate(delays):
        if delay:
            time.sleep(delay)
        try:
            with urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as error:
            last_error = error
            logging.warning(
                "Request %s failed (attempt %d/%d): %s", url, index + 1, len(delays), error
            )
    assert last_error is not None
    raise last_error


class _DuckDuckGoParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self.current: dict[str, str] | None = None
        self.capture: str | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        values = dict(attrs)
        classes = set((values.get("class") or "").split())
        if tag == "a" and "result__a" in classes:
            self.current = {"title": "", "url": values.get("href", ""), "snippet": ""}
            self.results.append(self.current)
            self.capture = "title"
        elif self.current is not None and classes.intersection(
            {"result__snippet", "result-snippet"}
        ):
            self.capture = "snippet"

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.capture == "title":
            self.capture = None
        elif tag in {"div", "td"} and self.capture == "snippet":
            self.capture = None

    def handle_data(self, data: str) -> None:
        if self.current is not None and self.capture:
            self.current[self.capture] += data


def search_web(query: str, limit: int = 3) -> str:
    query = " ".join(query.split()).strip()
    if not 2 <= len(query) <= 300:
        raise ValueError("Поисковый запрос должен содержать от 2 до 300 символов.")
    url = f"https://html.duckduckgo.com/html/?q={quote(query)}"
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=15) as response:
        page = response.read(3_000_000).decode("utf-8", errors="replace")
    parser = _DuckDuckGoParser()
    parser.feed(page)
    results = []
    for item in parser.results:
        raw_url = item["url"].strip()
        if not raw_url:
            continue
        parsed = urlparse(raw_url)
        if parsed.path == "/l/" and parsed.query:
            raw_url = parse_qs(parsed.query).get("uddg", [raw_url])[0]
        raw_url = unquote(raw_url)
        host = urlparse(raw_url).netloc.removeprefix("www.")
        title = " ".join(item["title"].split())
        snippet = " ".join(item["snippet"].split())
        if title and snippet and host and raw_url.startswith(("https://", "http://")):
            results.append((title[:180], snippet[:450], host[:100], raw_url))
        if len(results) >= max(1, min(limit, 5)):
            break
    if not results:
        return (
            "Поисковая система не вернула читаемые результаты. "
            "Попробуй переформулировать запрос или открыть браузер."
        )
    lines = [f"Нашёл информацию по запросу «{query}». Кратко:"]
    for index, (title, snippet, host, _) in enumerate(results, 1):
        lines.append(f"{index}. {title}. {snippet} Источник: {host}.")
    lines.append("Данные взяты из поисковых сниппетов; для важных решений открой первоисточник.")
    return "\n".join(lines)


WEATHER_ICONS = {
    0: "\u2600\ufe0f", 1: "\U0001f324\ufe0f", 2: "\u26c5", 3: "\u2601\ufe0f",
    45: "\U0001f32b\ufe0f", 48: "\U0001f32b\ufe0f",
    51: "\U0001f326\ufe0f", 53: "\U0001f326\ufe0f", 55: "\U0001f326\ufe0f",
    56: "\U0001f327\ufe0f", 57: "\U0001f327\ufe0f",
    61: "\U0001f327\ufe0f", 63: "\U0001f327\ufe0f", 65: "\U0001f327\ufe0f",
    66: "\U0001f327\ufe0f", 67: "\U0001f327\ufe0f",
    71: "\U0001f328\ufe0f", 73: "\U0001f328\ufe0f", 75: "\U0001f328\ufe0f",
    77: "\U0001f328\ufe0f",
    80: "\U0001f326\ufe0f", 81: "\U0001f326\ufe0f", 82: "\u26c8\ufe0f",
    85: "\U0001f328\ufe0f", 86: "\U0001f328\ufe0f",
    95: "\u26c8\ufe0f", 96: "\u26c8\ufe0f", 99: "\u26c8\ufe0f",
}

WEEKDAYS_SHORT_RU = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
WEATHER_CACHE_TTL = timedelta(minutes=10)
WEATHER_CACHE_LIMIT = 64
_WEATHER_CACHE: dict[str, tuple[datetime, "WeatherReport"]] = {}
_WEATHER_LOCK = threading.Lock()


@dataclass(frozen=True)
class WeatherDay:
    weekday: str
    temperature_max: float | None
    temperature_min: float | None
    code: int | None
    condition: str
    icon: str


@dataclass(frozen=True)
class WeatherReport:
    city: str
    latitude: float
    longitude: float
    temperature: float | None
    apparent: float | None
    humidity: float | None
    wind: float | None
    code: int | None
    condition: str
    icon: str
    hourly: tuple[tuple[str, float], ...]
    daily: tuple[WeatherDay, ...]
    fetched_at: datetime

    def short_line(self) -> str:
        return f"{self.icon} {self.condition}, {_format_temp(self.temperature)}"

    def forecast_line(self) -> str:
        return "  ".join(
            f"{day.weekday} {_format_temp(day.temperature_max)}" for day in self.daily
        )


def _format_temp(value: float | None) -> str:
    if value is None:
        return "—"
    rounded = round(value)
    prefix = "+" if rounded > 0 else ""
    return f"{prefix}{rounded}°"


def _condition(code: int | None) -> str:
    if code is None:
        return "погодные условия неизвестны"
    return WEATHER_CODES.get(code, "погодные условия неизвестны")


def _icon(code: int | None) -> str:
    if code is None:
        return "\u2601\ufe0f"
    return WEATHER_ICONS.get(code, "\u2601\ufe0f")


def _as_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


class WeatherCityNotFound(ValueError):
    """Raised when the geocoding service has no match for the requested city."""

    def __init__(self, city: str) -> None:
        self.city = city
        super().__init__(f"Не нашёл город «{city}». Уточни название.")


def _geocode(city: str) -> dict:
    location = _get_json(
        "https://geocoding-api.open-meteo.com/v1/search"
        f"?name={quote(city)}&count=1&language=ru&format=json"
    )
    matches = location.get("results") or []
    if not matches:
        raise WeatherCityNotFound(city)
    return matches[0]


def get_weather_report(city: str) -> WeatherReport:
    """Current weather plus an hourly slice and a five day outlook from Open-Meteo.

    The result is cached in memory for ten minutes, keyed by the city name.
    """
    city = " ".join(city.split()).strip()
    if not 2 <= len(city) <= 100:
        raise ValueError("Укажи название города.")

    key = city.casefold()
    now = datetime.now(timezone.utc)
    with _WEATHER_LOCK:
        cached = _WEATHER_CACHE.get(key)
        if cached is not None and now - cached[0] < WEATHER_CACHE_TTL:
            return cached[1]

    place = _geocode(city)
    query = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={place['latitude']}&longitude={place['longitude']}"
        "&current=temperature_2m,apparent_temperature,relative_humidity_2m,"
        "weather_code,wind_speed_10m"
        "&hourly=temperature_2m&forecast_days=2"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min&forecast_days=5"
        "&timezone=auto"
    )
    data = _get_json(query)
    current = data.get("current") or {}
    code = _as_int(current.get("weather_code"))

    hourly_times = ((data.get("hourly") or {}).get("time")) or []
    hourly_temps = ((data.get("hourly") or {}).get("temperature_2m")) or []
    hourly: list[tuple[str, float]] = []
    stamp = str(current.get("time") or "")
    for index, moment in enumerate(hourly_times):
        if index >= len(hourly_temps):
            break
        temperature = _as_float(hourly_temps[index])
        if temperature is None or not isinstance(moment, str) or moment <= stamp:
            continue
        hourly.append((moment[11:16], temperature))
        if len(hourly) == 6:
            break

    daily_data = data.get("daily") or {}
    days: list[WeatherDay] = []
    dates = daily_data.get("time") or []
    maxes = daily_data.get("temperature_2m_max") or []
    mins = daily_data.get("temperature_2m_min") or []
    codes = daily_data.get("weather_code") or []
    for index, date_text in enumerate(dates[:5]):
        try:
            weekday = WEEKDAYS_SHORT_RU[datetime.fromisoformat(str(date_text)).weekday()]
        except (ValueError, TypeError):
            weekday = str(date_text)
        day_code = _as_int(codes[index]) if index < len(codes) else None
        days.append(
            WeatherDay(
                weekday=weekday,
                temperature_max=_as_float(maxes[index]) if index < len(maxes) else None,
                temperature_min=_as_float(mins[index]) if index < len(mins) else None,
                code=day_code,
                condition=_condition(day_code),
                icon=_icon(day_code),
            )
        )

    report = WeatherReport(
        city=str(place.get("name") or city),
        latitude=float(place["latitude"]),
        longitude=float(place["longitude"]),
        temperature=_as_float(current.get("temperature_2m")),
        apparent=_as_float(current.get("apparent_temperature")),
        humidity=_as_float(current.get("relative_humidity_2m")),
        wind=_as_float(current.get("wind_speed_10m")),
        code=code,
        condition=_condition(code),
        icon=_icon(code),
        hourly=tuple(hourly),
        daily=tuple(days),
        fetched_at=now,
    )
    with _WEATHER_LOCK:
        _WEATHER_CACHE[key] = (now, report)
        while len(_WEATHER_CACHE) > WEATHER_CACHE_LIMIT:
            oldest = min(_WEATHER_CACHE, key=lambda name: _WEATHER_CACHE[name][0])
            del _WEATHER_CACHE[oldest]
    return report


def get_weather(city: str) -> str:
    """Text form kept for the command/tool layer."""
    try:
        report = get_weather_report(city)
    except WeatherCityNotFound:
        return f"Города «{city}» нет в базе сервиса — проверь название."
    parts = [
        f"Сейчас в {report.city}: {report.condition}, {_format_temp(report.temperature)}.",
        f"Ощущается как {_format_temp(report.apparent)}, "
        f"ветер {report.wind if report.wind is not None else '—'} км/ч, "
        f"влажность {report.humidity if report.humidity is not None else '—'}%.",
    ]
    if report.hourly:
        hours = ", ".join(f"{moment} {_format_temp(value)}" for moment, value in report.hourly[:4])
        parts.append(f"Ближайшие часы: {hours}.")
    if report.daily:
        parts.append("Прогноз на 5 дней: " + report.forecast_line() + ".")
    return " ".join(parts)


def get_exchange_rate(base: str, quote_currency: str) -> str:
    base = base.upper().strip()
    quote_currency = quote_currency.upper().strip()
    if not re.fullmatch(r"[A-Z]{3}", base) or not re.fullmatch(r"[A-Z]{3}", quote_currency):
        raise ValueError("Используй трёхбуквенные коды валют, например USD и RUB.")
    if base == quote_currency:
        return f"1 {base} = 1 {quote_currency}."
    data = _get_json(f"https://api.frankfurter.dev/v2/rate/{base}/{quote_currency}")
    rate = data.get("rate")
    date = data.get("date", "последняя доступная дата")
    if not isinstance(rate, (int, float)):
        raise ValueError("Сервис не вернул курс для этой валютной пары.")
    return (
        f"По последним доступным справочным данным на {date}: "
        f"1 {base} ≈ {rate:.4f} {quote_currency}. "
        "Это справочный курс, не биржевая котировка в реальном времени."
    )


def register_public_info_tools(registry: ToolRegistry) -> None:
    registry.register(ToolSpec(
        name="web_search",
        description="Найти в интернете несколько коротких результатов и пересказать их.",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string", "minLength": 2, "maxLength": 300}},
            "required": ["query"],
            "additionalProperties": False,
        },
        risk=RiskLevel.SAFE,
        handler=lambda args: ToolResult(True, search_web(str(args["query"]))),
    ))
    registry.register(ToolSpec(
        name="get_weather",
        description="Получить текущую погоду, ближайшие часы и прогноз на 5 дней (Open-Meteo).",
        parameters={
            "type": "object",
            "properties": {"city": {"type": "string", "minLength": 2, "maxLength": 100}},
            "required": ["city"],
            "additionalProperties": False,
        },
        risk=RiskLevel.SAFE,
        handler=lambda args: ToolResult(True, get_weather(str(args["city"]))),
    ))
    registry.register(ToolSpec(
        name="get_exchange_rate",
        description="Получить последний справочный курс одной валюты к другой.",
        parameters={
            "type": "object",
            "properties": {
                "base": {"type": "string", "pattern": "[A-Z]{3}"},
                "quote_currency": {"type": "string", "pattern": "[A-Z]{3}"},
            },
            "required": ["base", "quote_currency"],
            "additionalProperties": False,
        },
        risk=RiskLevel.SAFE,
        handler=lambda args: ToolResult(
            True, get_exchange_rate(str(args["base"]), str(args["quote_currency"]))
        ),
    ))
