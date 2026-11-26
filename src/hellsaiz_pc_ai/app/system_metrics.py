"""Lightweight system metrics for the dashboard system card.

Kept free of Qt: the numbers are produced here, the UI only displays them.
GPU usage is best-effort — when NVML is missing (no NVIDIA driver, not
installed) the caller hides the GPU row instead of showing a broken value.
"""

from __future__ import annotations

import logging
import threading

_WARMUP_DONE = False
_CACHE_LOCK = threading.Lock()

try:  # pragma: no cover - exercised through the opt-in GPU branch
    import pynvml  # type: ignore[import-untyped]

    try:
        pynvml.nvmlInit()
        _GPU_HANDLE = pynvml.nvmlDeviceGetHandleByIndex(0)
        GPU_AVAILABLE = True
    except Exception:  # noqa: BLE001 - NVML init may fail on any machine
        _GPU_HANDLE = None
        GPU_AVAILABLE = False
except ImportError:
    pynvml = None  # type: ignore[assignment]
    _GPU_HANDLE = None
    GPU_AVAILABLE = False


def _read_cpu() -> float:
    global _WARMUP_DONE
    import psutil

    # The first cpu_percent() call returns 0.0 by contract, so warm it up once.
    if not _WARMUP_DONE:
        with _CACHE_LOCK:
            if not _WARMUP_DONE:
                psutil.cpu_percent(interval=None)
                _WARMUP_DONE = True
    return float(psutil.cpu_percent(interval=None))


def _read_ram() -> float:
    import psutil

    return float(psutil.virtual_memory().percent)


def _read_gpu() -> float | None:
    if not GPU_AVAILABLE or pynvml is None:
        return None
    try:
        util = pynvml.nvmlDeviceGetUtilizationRates(_GPU_HANDLE)
        return float(util.gpu)
    except Exception:  # noqa: BLE001 - driver hiccups must not break the UI
        logging.debug("GPU utilization query failed", exc_info=True)
        return None


def system_snapshot() -> tuple[float, float, float | None]:
    """Return (cpu_percent, ram_percent, gpu_percent-or-None)."""
    try:
        return _read_cpu(), _read_ram(), _read_gpu()
    except Exception:  # noqa: BLE001 - metrics are decorative, never fatal
        logging.debug("System metrics unavailable", exc_info=True)
        return 0.0, 0.0, None
