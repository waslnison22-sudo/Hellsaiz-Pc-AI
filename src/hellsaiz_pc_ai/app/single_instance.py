from __future__ import annotations

import os
from pathlib import Path
from typing import IO


class SingleInstanceLock:
    """Cross-platform advisory lock for one running desktop process."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._file: IO[bytes] | None = None

    def acquire(self) -> bool:
        if self._file is not None:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        try:
            if self.path.stat().st_size == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            handle.seek(0)
            handle.truncate()
            handle.write(f"{os.getpid()}\n".encode("ascii"))
            handle.flush()
            self._file = handle
            return True
        except (OSError, BlockingIOError):
            handle.close()
            return False

    def release(self) -> None:
        handle = self._file
        if handle is None:
            return
        self._file = None
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()

    def __enter__(self) -> SingleInstanceLock:
        if not self.acquire():
            raise RuntimeError("Hellsaiz PC AI is already running.")
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.release()
