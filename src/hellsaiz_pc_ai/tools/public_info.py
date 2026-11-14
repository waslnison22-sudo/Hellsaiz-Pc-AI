from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, quote, unquote, urlparse
from urllib.request import Request, urlopen

from hellsaiz_pc_ai.core.models import RiskLevel, ToolResult
from hellsaiz_pc_ai.core.registry import ToolRegistry, ToolSpec


USER_AGENT = "Hellsaiz-PC-AI/0.1.4 (personal desktop assistant)"
WEATHER_CODES = {
    0: "ясно", 1: "преимущественно ясно", 2: "переменная облачность",
    3: "пасмурно", 45: "туман", 48: "изморозевый туман",
    51: "небольшая морось", 53: "морось", 55: "сильная морось",
    61: "небольшой дождь", 63: "дождь", 65: "сильный дождь",
    71: "небольшой снег", 73: "снег", 75: "сильный снег",
    80: "ливневый дождь", 81: "сильные ливни", 82: "очень сильные ливни",
    95: "гроза", 96: "гроза с градом", 99: "сильная гроза с градом",
}


def _get_json(url: str, timeout: int = 12):
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


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


def get_weather(city: str) -> str:
    city = " ".join(city.split()).strip()
    if not 2 <= len(city) <= 100:
        raise ValueError("Укажи название города.")
    location = _get_json(
        "https://geocoding-api.open-meteo.com/v1/search"
        f"?name={quote(city)}&count=1&language=ru&format=json"
    )
    matches = location.get("results") or []
    if not matches:
        return f"Не нашёл город «{city}». Уточни название."
    place = matches[0]
    query = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={place['latitude']}&longitude={place['longitude']}"
        "&current=temperature_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m"
        "&timezone=auto"
    )
    data = _get_json(query)
    current = data.get("current") or {}
    code = int(current.get("weather_code", -1))
    description = WEATHER_CODES.get(code, "погодные условия неизвестны")
    return (
        f"Сейчас в {place.get('name', city)}: {description}, "
        f"{current.get('temperature_2m', '—')} градусов. "
        f"Ощущается как {current.get('apparent_temperature', '—')}, "
        f"ветер {current.get('wind_speed_10m', '—')} километров в час."
    )


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
        description="Получить текущую погоду в указанном городе.",
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
