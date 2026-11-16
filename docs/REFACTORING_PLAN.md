# Рефакторинг desktop UI — правила и план

Обновлено: 2026-11-15. Ветка плана: последовательные PR в `dev/bootstrap`.

## Проблема

`src/hellsaiz_pc_ai/app/desktop.py` — 4109 строк, из которых 3853 занимает один `main()`.
Внутри него около 150 вложенных функций и 15 вложенных классов живут в одной области
видимости с более чем 1000 локальных переменных; весь интерфейс (сайдбар и `QStackedWidget`
со страницами) собирается только в конце функции. Правка любой страницы непредсказуемо
цепляет соседние замыкания, поэтому ошибки UI воспроизводятся при каждой доработке.

## Правила рефакторинга

1. Поведение не меняется; меняется только структура кода.
2. Один этап — одна ветка и один PR в `dev/bootstrap`. Этапы не смешивать.
3. `build_runtime()` и её контракт не трогаем (`tests/test_desktop_runtime.py` должен оставаться зелёным).
4. Импорт PySide6 остаётся внутри `main()` внутри существующего `try/except ImportError`.
5. Новые зависимости не добавляются. Тексты пользователю — на русском, идентификаторы — на английском.

## Этап 1 — вынос фоновых воркеров (этот PR)

Добавлен `src/hellsaiz_pc_ai/app/ui_workers.py` с 16 классами, ранее определёнными внутри `main()`:

- QObject-мости: `HotkeyBridge`, `HotkeyDispatcher`, `WakeListenerDispatcher`, `SystemHealthBridge`, `TelegramStatusBridge`.
- QThread-воркеры: `VoskModelDownloadWorker`, `WakeListenerWorker`, `ProviderHealthWorker`,
  `VoiceDownloadWorker`, `VoiceTestWorker`, `SapiVoiceListWorker`, `SystemHealthWorker`,
  `OcrModelsWorker`, `NetworkProbeWorker`, `StartupTaskWorker`, `UpdateWorker`.

Классы, захватывавшие локальные переменные `main()`, параметризованы:

- `SapiVoiceListWorker(rate, volume)` — раньше читал `active_tts`;
- `VoiceDownloadWorker(voice_id, target_dir)` — раньше читал `voice_library_dir`;
- `SystemHealthWorker(..., *, voices_dir, database_path, workflows_path)` — раньше читал `settings`;
- `SystemHealthBridge(summary_status, detail_status, health_button, workers_list, on_completed, parent)` — раньше читал виджеты напрямую;
- `OcrModelsWorker(*, download, models_root)` — раньше читал `ocr_models_root`;
- `UpdateWorker(data_dir, current_version, install_root, *, download=False)` — раньше читал `settings`/`current_app_version`/`install_root`.

Незатронутым остаётся только `Worker` (исполнитель команд чата) — его вынос планирует этап 2.

### Остаток этапа 1: механическая правка `desktop.py`

Пока классы дублируются во вложенном виде, их вынос нельзя считать завершённым. Требуется:

1. Внутри существующего `try:` в начале `main()`, сразу после строки
   `from hellsaiz_pc_ai.telegram.worker import TelegramBotWorker`, добавить:

```python
        from hellsaiz_pc_ai.app.ui_workers import (
            HotkeyBridge,
            HotkeyDispatcher,
            NetworkProbeWorker,
            OcrModelsWorker,
            ProviderHealthWorker,
            SapiVoiceListWorker,
            StartupTaskWorker,
            SystemHealthBridge,
            SystemHealthWorker,
            TelegramStatusBridge,
            UpdateWorker,
            VoskModelDownloadWorker,
            VoiceDownloadWorker,
            VoiceTestWorker,
            WakeListenerDispatcher,
            WakeListenerWorker,
        )
```

2. Удалить из `main()` определения перенесённых классов (номера строк соответствуют коммиту
   `84eb9cab9170d1de52faf73db5a4776fe66bd23c`): `HotkeyBridge` (398–399), `HotkeyDispatcher`
   (401–408), `VoskModelDownloadWorker` (410–425), `WakeListenerWorker` (429–463),
   `WakeListenerDispatcher` (465–487), `ProviderHealthWorker` (914–926), `VoiceDownloadWorker`
   (1981–1997), `VoiceTestWorker` (1999–2035), `SapiVoiceListWorker` (2037–2050),
   `SystemHealthWorker` (2394–2437), `SystemHealthBridge` (2610–2625), `OcrModelsWorker`
   (2743–2763), `NetworkProbeWorker` (3105–3123), `TelegramStatusBridge` (3221–3222),
   `StartupTaskWorker` (3410–3435), `UpdateWorker` (3531–3561).

3. Обновить места вызова (точные замены):

```python
# было
worker = VoiceDownloadWorker(voice_id)
# стало
worker = VoiceDownloadWorker(voice_id, voice_library_dir)

# было
worker = SapiVoiceListWorker()
# стало
worker = SapiVoiceListWorker(active_tts["rate"], active_tts["volume"])

# было
worker = SystemHealthWorker(
    active_stt.copy(),
    active_microphone["name"],
    always_listen_check.isChecked(),
    str(profile_data.get("piper_voice_id") or ""),
    str(profile_data.get("tts_engine") or "sapi5"),
)
# стало
worker = SystemHealthWorker(
    active_stt.copy(),
    active_microphone["name"],
    always_listen_check.isChecked(),
    str(profile_data.get("piper_voice_id") or ""),
    str(profile_data.get("tts_engine") or "sapi5"),
    voices_dir=settings.workflows_path.parent / "voices",
    database_path=settings.database_path,
    workflows_path=settings.workflows_path,
)

# было
system_health_bridge = SystemHealthBridge(window)
# стало
system_health_bridge = SystemHealthBridge(
    summary_status=health_summary_status,
    detail_status=speech_health_status,
    health_button=speech_health_button,
    workers_list=system_health_workers,
    on_completed=show_system_health,
    parent=window,
)

# было
worker = OcrModelsWorker(download=download)
# стало
worker = OcrModelsWorker(download=download, models_root=ocr_models_root)

# было
worker = UpdateWorker()
# стало
worker = UpdateWorker(
    settings.workflows_path.parent,
    current_app_version,
    install_root,
)

# было
worker = UpdateWorker(download=True)
# стало
worker = UpdateWorker(
    settings.workflows_path.parent,
    current_app_version,
    install_root,
    download=True,
)
```

4. Проверка этапа: `python -m compileall src/hellsaiz_pc_ai`, затем
   `pytest tests/test_desktop_runtime.py tests/test_theme.py`, затем ручной запуск `RUN.bat`
   на Windows и быстрый обход всех страниц.

## Этап 2 — разбор `main()` на страницы

- Новый пакет `app/pages/`: одна страница — один модуль с явным конструктором.
- Общий контекст: `dataclass AppContext` с настройками, роутером, сторами и активными
  профилями; страницы получают контекст, а не полагаются на замыкания.
- Порядок выноса — от наименьшего числа зависимостей: `settings_about` → `catalog` →
  `reminders` → `voices` → `scenarios` → `settings_*` → `chat`.
- Каждый PR уменьшает `main()` на размер вынесенной страницы; глобальных переменных
  модуля не вводить.

## Этап 3 — тема и HUD

- Расширить `app/theme.py` до набора дизайн-токенов (цвета, отступы, радиусы, типографика)
  вместо строковых литералов по всему desktop-коду.
- После этапа 2 — согласованный с владельцем визуальный пересмотр «худа»: главная страница
  чата, стеклянная боковая навигация, страницы «Обои» и «Голоса» (см. `docs/HUD_AND_UPDATES.md`).
- Проверить доступность: Narrator, keyboard-only, DPI, reduced-motion (см. `ENGINEERING_NOTES.md`, раздел 5).

## Контроль качества

- `tests/test_desktop_runtime.py` и `tests/test_theme.py` обязаны оставаться зелёными в каждом PR.
- Windows CI в организации сейчас не выделяет runner (см. `docs/DEVELOPMENT_STATUS.md`), поэтому
  до восстановления раннеров финальная проверка — ручной запуск `RUN.bat` на Windows.
