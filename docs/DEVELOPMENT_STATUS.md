# Состояние разработки — Hellsaiz PC AI

Срез: 15 ноября 2026 года  
Рабочая ветка: `dev/bootstrap`  
Коммит на момент аудита: `b13981a6d6bca2004a8078c1c364da82ea38723c`  
Версия в исходниках: `0.1.4`

Этот документ описывает состояние кода и этапов реализации. Он не является подтверждением успешной сборки, тестирования или готовности к публикации.

## Общая оценка

**Около 76% плана P0–P7 реализовано на уровне исходников.**

Оценка рассчитана как среднее восьми этапов из `docs/IMPLEMENTATION_ROADMAP.md`, с учётом того, что модуль или интерфейс считается реализованным в исходниках, но незапущенные на Windows интеграционные проверки не засчитываются как завершённые. Это инженерная оценка прогресса, а не автоматическая метрика покрытия или успешности тестов.

| Этап | Прогресс | Что уже есть | Что остаётся |
|---|---:|---|---|
| P0 — стабильность | 75% | Детерминированный роутер команд, single-instance lock, SQLite history, напоминания, библиотека и планировщик сценариев, allowlist приложений/процессов, clipboard/system tools, очистка фоновых workers | Прогон на Windows 3.11/3.12; живые проверки напоминаний, буфера, сценариев, shutdown, микрофона и TTS |
| P1 — платформенные основы | 90% | Разделены provider/STT/TTS/wake-name слои; DPAPI secret storage; Vosk, Whisper.cpp, SAPI5, Piper; профили голосов и локальная маршрутизация | Проверка устройств, моделей и fallback на нескольких реальных конфигурациях Windows |
| P2 — язык и intents | 75% | Русская детерминированная маршрутизация intent/slots, wake aliases, app aliases, отказ от неоднозначного выбора приложения/окна | Расширение фраз, noisy-ASR набор для каждого intent, более полный редактируемый каталог сущностей |
| P3 — AI и голосовые движки | 70% | LM Studio, Ollama, llama.cpp profiles; отдельный GigaChat OAuth/function-calling adapter; discovery моделей и health checks | Живые тесты настроенных провайдеров; проверка primary/fallback и запрета повторного выполнения действий после неопределённого timeout |
| P4 — управление Windows | 75% | Инвентаризация процессов/окон, focus/minimize/maximize/restore/close, UI Automation inspect/click/type, ограниченные hotkeys, scoped file operations, optional local Russian OCR | Реальные тесты в Notepad, Explorer, Settings и браузере; custom/protected UI; OCR на разных DPI и нескольких мониторах |
| P5 — упаковка и обновление | 55% | В исходниках есть PyInstaller pipeline, stable Launcher/Updater, Inno Setup script, signed manifest, проверка SHA-256, staged update, rollback и разделение пользовательских данных | Реальная Windows-сборка, self-tests EXE, silent install/uninstall, обновление существующей 0.1.3, health marker, сохранность данных и failure-path rollback |
| P6 — сеть и Telegram | 70% | Выбор/запуск v2RayTun EXE, проверка локального HTTP proxy без глобального изменения сети; отдельный Telegram worker, DPAPI token, user/chat allowlists и read-only tool permissions | Живой тест настроенного proxy/client и отдельного Telegram test chat; проверка остановки/повторного старта и отказа при недоступном proxy |
| P7 — companion foundation | 100% | Renderer-neutral mode/emotion/viseme contracts, thread-safe controller, renderer protocol и безопасная проверка model manifest | Сам renderer намеренно отложен: avatar, overlay host, Live2D/VRM не входят в текущую основу 0.1.4 |

## Что уже реализовано в кодовой базе

### Чат и локальное ядро
- PySide6 desktop UI с тёмной графитовой темой и чатом в качестве главного экрана.
- Локальные команды без обязательной LLM.
- Русские intent/slot маршруты, wake aliases и каталог разрешённых приложений.
- История SQLite, напоминания и уведомления, работающие пока приложение открыто.
- Сценарии как валидируемые JSON-графы: text/hotkey/schedule/startup triggers, часовые/недельные условия, tool/repeat/wait actions и ветвления.

### Голос и AI
- Локальный STT через Vosk и Whisper.cpp.
- Локальный TTS через Windows SAPI5 и Piper.
- Основной и резервный движки, voice library, проверка доступности и опциональный hands-free wake listener.
- Опциональные AI-профили LM Studio, Ollama, llama.cpp и отдельный GigaChat adapter. Они выключены по умолчанию.

### Управление рабочим столом
- Allowlist запуска приложений и процессов.
- Операции с видимыми окнами и UI Automation.
- Файловые операции внутри явно разрешённых корней.
- Clipboard по прямой команде пользователя.
- Локальный OCR с ручным включением и проверкой моделей по SHA-256.
- Автозапуск через Windows Task Scheduler.

### Интеграции
- v2RayTun: выбор и запуск пользовательского EXE плюс проверка заданного локального proxy/health endpoint. Подключение туннеля не переключается скрытым CLI.
- Telegram: отдельный выключенный по умолчанию worker; токен защищён DPAPI, требуются allowlists user/chat и отдельные разрешения на ограниченные read-only инструменты.

### Инфраструктура обновления
- Подготовлены manifest/signature verification, Launcher/Updater, проверка содержимого архива, staged activation и rollback.
- Подготовлены scripts/workflows для Windows x64, portable ZIP, full update ZIP и Inno Setup.
- Подготовлены тесты для updater, launcher, packaging, install layout и smoke checks.

## Объём кода и тестовой базы

На момент среза Git tree содержит:
- 73 Python-файла в `src/hellsaiz_pc_ai`;
- 53 Python-файла в `tests`;
- 9 документов в `docs`.

Количество файлов не равно покрытию тестами. Этот срез не подтверждает, что тесты успешно прошли: CI не смог выделить Runner и ни один шаг актуального workflow не стартовал.

## Блокеры и границы текущего результата

1. **Windows CI:** актуальные задания GitHub Actions завершаются до старта первого шага. В последнем доступном запуске у matrix jobs `runner_id = 0`, пустое имя runner и `steps = []`. GitHub показывал ограничение по оплате/лимиту расходов. Это не результат тестирования исходного кода.
2. **Реальный Windows runtime:** без выделенного Windows runner нельзя заявить, что зависимости, PyInstaller bundle, Inno Setup installer, UAC, Task Scheduler и устройства работают на чистой системе.
3. **Внешние секреты:** наличие и корректность Actions secret `HELLSAIZ_UPDATE_SIGNING_KEY` не подтверждены. Ключ нельзя помещать в source code, commit или чат; workflow должен сам проверить соответствие встроенному public key.
4. **Провайдеры и сеть:** реальные LM Studio/Ollama/llama.cpp/GigaChat, v2RayTun proxy и Telegram bot test chat не подтверждены интеграционными тестами.
5. **Компаньон:** renderer не входит в текущую цель; есть только контракт и безопасный фундамент.

## Приоритет следующего цикла разработки

1. Расширить тесты нормализации русских фраз, ASR-опечаток, конфликтов aliases и разрешения сущностей.
2. Проверить provider capability detection, fallback и поведение при timeout после возможного side effect; не допускать повторного исполнения команды.
3. Укрепить тестовые сценарии UI Automation и файловых разрешений: не допускать выхода за scoped roots и случайного выбора похожих окон.
4. Провести ревизию voice model download/unpack/health paths: повреждённые архивы, отсутствие модели, недоступный микрофон, остановка wake listener.
5. Проверить жизненный цикл Telegram worker и proxy gate на mocks, затем на отдельном тестовом чате.
6. Подготовить более подробные диагностические отчёты для Windows smoke tests, чтобы после восстановления Runner быстро находить конкретные ошибки.

## Что не делать в этом цикле

- Не создавать и не публиковать новый release.
- Не перемещать и не перепривязывать тег `v0.1.4`.
- Не менять установленную пользователем версию и не удалять данные.
- Не считать source implementation эквивалентом проверенному Windows build.
- Не включать по умолчанию удалённую LLM, Telegram, OCR или hands-free микрофон.

## Источники статуса

- `docs/IMPLEMENTATION_ROADMAP.md` — этапы P0–P7 и критерии проверок.
- `docs/PRODUCT_REQUIREMENTS.md` — целевой контракт продукта.
- `docs/WINDOWS_INSTALL_AND_UPDATES.md` — установка, обновление и rollback.
- `.github/workflows/ci.yml` и `.github/workflows/release-windows.yml` — запланированные проверки и сборка.
- `docs/RELEASE_READINESS_0.1.4.md` — отдельные условия release acceptance.
