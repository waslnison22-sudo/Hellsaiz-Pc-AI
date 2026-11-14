from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path


class AudioCaptureError(RuntimeError):
    pass


@dataclass(frozen=True)
class InputDevice:
    index: int
    name: str
    host_api: str
    max_input_channels: int
    default_samplerate: int

    @property
    def display_name(self) -> str:
        prefix = f"{self.name} · {self.host_api}" if self.host_api else self.name
        return f"{prefix} · #{self.index}"


def _sounddevice():
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise AudioCaptureError(
            'Microphone support is not installed. Run: pip install -e ".[voice]"'
        ) from exc
    return sd


def list_input_devices() -> list[InputDevice]:
    """List real input devices while leaving the system default untouched."""
    sd = _sounddevice()
    devices = sd.query_devices()
    host_apis = sd.query_hostapis()
    result: list[InputDevice] = []
    for index, item in enumerate(devices):
        channels = int(item.get("max_input_channels", 0))
        if channels <= 0:
            continue
        host_index = int(item.get("hostapi", -1))
        host_name = (
            str(host_apis[host_index].get("name", ""))
            if 0 <= host_index < len(host_apis) else ""
        )
        result.append(InputDevice(
            index=index,
            name=str(item.get("name") or f"Микрофон {index}"),
            host_api=host_name,
            max_input_channels=channels,
            default_samplerate=int(float(item.get("default_samplerate") or 16000)),
        ))
    return result


def resolve_input_device(device_name: str | None) -> int | None:
    """Resolve a saved microphone name to the current PortAudio device index."""
    if not device_name:
        return None
    for device in list_input_devices():
        if device.name == device_name or device.display_name == device_name:
            return device.index
    raise AudioCaptureError(
        f"Выбранный микрофон «{device_name}» не найден. Подключи его или выбери системный."
    )


def resolve_input_sample_rate(
    device: str | int | None = None, preferred_rate: int = 16000
) -> int:
    """Prefer the STT rate when supported, otherwise use the device's native rate."""
    if not 8000 <= preferred_rate <= 48000:
        raise ValueError("Preferred sample rate must be between 8000 and 48000 Hz.")
    sd = _sounddevice()
    selected_device = resolve_input_device(device) if isinstance(device, str) else device
    try:
        info = sd.query_devices(selected_device, "input")
        native_rate = int(float(info.get("default_samplerate") or preferred_rate))
    except Exception:
        native_rate = preferred_rate
    candidates = [preferred_rate]
    if 8000 <= native_rate <= 48000 and native_rate != preferred_rate:
        candidates.append(native_rate)
    for candidate in candidates:
        try:
            sd.check_input_settings(
                device=selected_device,
                channels=1,
                dtype="int16",
                samplerate=candidate,
            )
            return candidate
        except Exception:
            continue
    raise AudioCaptureError(
        "Микрофон не поддерживает ни 16 кГц, ни собственную частоту дискретизации."
    )


def record_microphone(
    output_file: Path,
    duration_seconds: float = 5.0,
    sample_rate: int = 16000,
    device: str | int | None = None,
) -> Path:
    """Record a short mono PCM16 clip from the selected input device."""
    if not 0.25 <= duration_seconds <= 30:
        raise ValueError("Recording duration must be between 0.25 and 30 seconds.")
    if not 8000 <= sample_rate <= 48000:
        raise ValueError("Sample rate must be between 8000 and 48000 Hz.")
    sd = _sounddevice()
    selected_device = resolve_input_device(device) if isinstance(device, str) else device
    effective_rate = resolve_input_sample_rate(selected_device, sample_rate)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        audio = sd.rec(
            int(duration_seconds * effective_rate),
            samplerate=effective_rate,
            channels=1,
            dtype="int16",
            device=selected_device,
        )
        sd.wait()
    except Exception as exc:
        output_file.unlink(missing_ok=True)
        raise AudioCaptureError(f"Could not record from the selected microphone: {exc}") from exc

    try:
        with wave.open(str(output_file), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(effective_rate)
            wav.writeframes(audio.tobytes())
    except (wave.Error, OSError) as exc:
        output_file.unlink(missing_ok=True)
        raise AudioCaptureError(f"Could not write captured audio: {exc}") from exc
    return output_file
