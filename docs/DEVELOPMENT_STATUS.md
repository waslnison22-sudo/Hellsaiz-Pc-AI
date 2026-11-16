# Состояние разработки — Hellsaiz PC AI

Срез: 16 ноября 2026 года  
Рабочая ветка: `dev/bootstrap`  
Релизный коммит: `4711ba24e84ee922cc6e528695c1c2b79d4ccf26`  
Версия в исходниках: `0.1.5`

Релиз `v0.1.5` опубликован. Документ описывает состояние реализации и оставшиеся интеграционные проверки, которые не входили в выпускной acceptance pipeline.

## Общая оценка

**Около 79% плана P0–P7 реализовано на уровне исходников.**

Оценка рассчитана как среднее восьми этапов из `docs/IMPLEMENTATION_ROADMAP.md`, с учётом того, что модуль или интерфейс считается реализованным в исходниках, но незапущенные на Windows интеграционные проверки не засчитываются как завершённые. Это инженерная оценка прогресса, а не автоматическая метрика покрытия или успешности тестов.

| Этап | Прогресс | Что уже есть | Что остаётся |
|---|---:|---|---|
| P0 — стабильность | 83% | Детерминированный роутер команд, single-instance lock, SQLite history, напоминания, библиотека и планировщик сценариев, allowlist приложений/процессов, clipboard/system tools, очистка фоновых workers; границы аргументов AI, preflight пакетов и read-only диагностика локального хранилища | Прогон на Windows 3.11/3.12; живые проверки напоминаний, буфера, сценариев, shutdown, микрофона и TTS |
| P1 — платформенные основы | 90% | Разделены provider/STT/TTS/wake-name слои; DPAPI secret storage; Vosk, Whisper.cpp, SAPI5, Piper; профили голосов и локальная маршрутизация | Проверка устройств, моделей и fallback на нескольких реальных конфигурациях Windows |
| P2 — язык и intents | 80% | Русская детерминированная маршрутизация intent/slots, wake aliases, app aliases, Unicode NFKC/casefold и нормализация ё/е, отказ от неоднозначного выбора приложения/окна | Расширение фраз, noisy-ASR набор для каждого intent, более полный редактируемый каталог сущностей |
| P3 — AI и голосовые движки | 70% | LM Studio, Ollama, llama.cpp profiles; отдельный GigaChat OAuth/function-calling adapter; discovery моделей и health checks | Живые тесты настроенных провайдеров; проверка primary/fallback и запрета повторного выполнения действий после неопределённого timeout |
| P4 — управление Windows | 80% | Инвентаризация процессов/окон, focus/minimize/maximize/restore/close, UI Automation inspect/click/type с operation-local snapshots и повторной проверкой доступности, ограниченные hotkeys, scoped file operations, optional local Russian OCR | Реальные тесты в Notepad, Explorer, Settings и браузере; custom/protected UI; OCR на разных DPI и нескольких мониторах |
| P5 — упаковка и обновление | 100% | Windows PyInstaller build, Launcher/Updater self-tests, signed manifest verification, ZIP validation, Inno Setup, silent install/uninstall, реальный update 0.1.3 → 0.1.5, health marker, сохранность LocalAppData и rollback прошли в release workflow | Дальнейшие проверки на пользовательских конфигурациях Windows и длительная эксплуатация |
| P6 — сеть и Telegram | 70% | Выбор/запуск v2RayTun EXE, проверка локального HTTP proxy без глобального изменения сети; отдельный Telegram worker, DPAPI token, user/chat allowlists и read-only tool permissions | Живой тест настроенного proxy/client и отдельного Telegram test chat; проверка остановки/повторного старта и отказа при недоступном proxy |
| P7 — companion foundation | 100% | Renderer-neutral mode/emotion/viseme contracts, thread-safe controller, renderer protocol и безопасная проверка model manifest | Сам renderer намеренно отложен: avatar, overlay host, Live2D/VRM не входят в текущую основу 0.1.5 |

## Что уже реализовано в кодовой базе

### Чат и локальное ядро
- PySide6 desktop UI с тёмной графитовой темой, вынесенной в отдельный theme module, видимыми состояниями keyboard focus и чатом в качестве главного экрана.
- Локальные команды без обязательной LLM.
- Русские intent/slot маршруты, wake aliases и каталог разрешённых приложений; нормализация NFKC, casefold, ё/е и совместимых Unicode-вариантов без нечёткого запуска неизвестных приложений.
- История SQLite, напоминания и уведомления, работающие пока приложение открыто.
- Сценарии как валидируемые JSON-графы: text/hotkey/schedule/startup triggers, часовые/недельные условия, tool/repeat/wait actions и ветвления.

### Голос и AI
- Локальный STT через Vosk и Whisper.cpp.
- Локальный TTS через Windows SAPI5 и Piper.
- Основной и резервный движки, voice library, проверка доступности и опциональный hands-free wake listener.
- Опциональные AI-профили LM Studio, Ollama, llama.cpp и отдельный GigaChat adapter. Они выключены по умолчанию.

### Управление рабочим столом
- Allowlist запуска приложений и процессов.
- Операции с видимыми окнами и UI Automation. Идентифицирующие свойства контролов читаются один раз на операцию; перед кликом/вводом доступность проверяется повторно.
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
- Подготовлены тесты для updater, launcher, packaging, install layout, UI Automation snapshots, bounded tool arguments, Unicode command normalization и theme focus states. Тесты и release acceptance checks исполнены на GitHub Windows/Linux runners; см. `docs/RELEASE_READINESS_0.1.5.md`.

## Объём кода и тестовой базы

На момент среза Git tree содержит:
- 74 Python-файла в `src/hellsaiz_pc_ai`;
- 54 Python-файла в `tests`;
- 11 документов в `docs`.

Количество файлов не равно покрытию тестами. На релизном коммите CI и Windows release workflow завершились успешно; результаты не означают, что все необязательные внешние интеграции проверены.

## Блокеры и границы текущего результата

1. **Windows acceptance:** релизный runner подтвердил PyInstaller build, self-tests, Inno Setup, silent install/uninstall и обновление с 0.1.3. Дополнительное тестирование на физическом ПК пользователя всё ещё полезно.
2. **Внешние провайдеры и сеть:** реальные LM Studio/Ollama/llama.cpp/GigaChat, v2RayTun proxy и Telegram bot test chat не подтверждены интеграционными тестами.
3. **Голос и устройства:** микрофоны, аудиодрайверы, локальные модели и разные конфигурации устройств требуют проверки на реальных машинах.
4. **Компаньон:** renderer не входит в текущую цель; есть только контракт и безопасный фундамент.

## Последние инженерные улучшения

- Ограничены глубина вложенности, длина строк и размер коллекций в аргументах инструментов; NaN/Infinity отклоняются до запуска обработчика. Проверка схем вынесена в side-effect-free метод `ToolRegistry.validate_arguments()`.
- AI-оркестратор ограничивает пакет до 8 tool calls и весь пользовательский запрос до 16 вызовов; проверяет уникальность call ID и строгий JSON, а затем выполняет preflight зарегистрированных имён и схем каждого инструмента до первого handler.
- Командная нормализация учитывает Unicode NFKC, регистр, ё/е, совместимые пробелы и конечную пунктуацию. Нечёткое сопоставление неизвестных действий не включалось.
- UI Automation использует снимок свойств контролов в пределах операции и повторно проверяет видимость/доступность непосредственно перед click/type.
- Тема вынесена в `app/theme.py`; для кнопок, полей и основной навигации добавлены видимые клавиатурные состояния фокуса и единый стиль scrollbars.
- Сводная диагностика проверяет голосовые движки, SQLite через read-only URI и `quick_check(1)`, обязательные таблицы, JSON-графы сценариев, доступность пользовательского каталога и свободное место. JSON-сценарии больше 1 МБ пропускаются с предупреждением. Тяжёлая проверка выполняется в QThread; UI обновляется через QObject-слоты главного потока. Подробности можно выделить и скопировать.
- Hands-free переведён на blocking `RawInputStream.read()`: распознавание больше не зависит от PortAudio callback и программной очереди; переполнение аппаратного входного буфера явно выводится в статус без повторяющегося спама, а восстановление фиксируется отдельным сообщением. Тайм-аут ожидания команды после wake-слова сохранён и проверяется на каждом прочитанном блоке.

Для диагностики добавлены тесты целостности SQLite, повреждённых сценариев, отсутствующих путей, глубокой вложенности JSON и агрегирования состояния. Для Hands-free добавлены тесты blocking-read, rate-limited overflow/recovery-уведомлений и сохранения тайм-аута ожидания команды. Тесты не выполнены в окружении без Runner.

## Приоритет следующего цикла разработки

1. Расширить тесты нормализации русских фраз, ASR-опечаток, конфликтов aliases и разрешения сущностей.
2. Проверить provider capability detection, fallback и поведение при timeout после возможного side effect; не допускать повторного исполнения команды.
3. Укрепить тестовые сценарии UI Automation и файловых разрешений: не допускать выхода за scoped roots и случайного выбора похожих окон.
4. Провести ревизию voice model download/unpack/health paths: повреждённые архивы, отсутствие модели, недоступный микрофон, остановка wake listener.
5. Проверить жизненный цикл Telegram worker и proxy gate на mocks, затем на отдельном тестовом чате.
6. Подготовить более подробные диагностические отчёты для Windows smoke tests, чтобы после восстановления Runner быстро находить конкретные ошибки.
7. Изучить нативные UI Automation CacheRequest и события инвалидирования UI-дерева; текущий Python snapshot уменьшает повторные чтения, но не заменяет COM-level bulk cache.
8. Проверить интерфейс с Windows Narrator, keyboard-only navigation, системным масштабированием DPI и reduced-motion настройками.

## Что не делать в этом цикле

- Не перезаписывать опубликованный `v0.1.5` и не удалять его assets.
- Следующие изменения выпускать отдельным номером версии только после отдельного согласования.
- Не менять установленную пользователем версию и не удалять данные.
- Не считать source implementation эквивалентом проверенному Windows build.
- Не включать по умолчанию удалённую LLM, Telegram, OCR или hands-free микрофон.

## Источники статуса

- `docs/IMPLEMENTATION_ROADMAP.md` — этапы P0–P7 и критерии проверок.
- `docs/PRODUCT_REQUIREMENTS.md` — целевой контракт продукта.
- `docs/WINDOWS_INSTALL_AND_UPDATES.md` — установка, обновление и rollback.
- `.github/workflows/ci.yml` и `.github/workflows/release-windows.yml` — запланированные проверки и сборка.
- `docs/RELEASE_READINESS_0.1.5.md` — отдельные условия release acceptance.
