from __future__ import annotations

import ctypes
import errno
import json
import os
from pathlib import Path
import time
from typing import Callable


class SingleInstanceLock:
    def __init__(
        self,
        app_key: str,
        message: str,
        lock_dir: Path | str | None = None,
        process_exists: Callable[[int], bool] | None = None,
    ) -> None:
        self.app_key = self._safe_key(app_key)
        self.message = message
        self.lock_dir = Path(lock_dir) if lock_dir is not None else self._default_lock_dir()
        self.lock_path = self.lock_dir / f"{self.app_key}.lock"
        self._process_exists = process_exists or _process_exists
        self._owned = False

    def try_acquire(self) -> bool:
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if self._existing_lock_is_active():
                    return False
                try:
                    self.lock_path.unlink()
                except FileNotFoundError:
                    pass
                except OSError:
                    return False
                continue
            except PermissionError:
                if not self.lock_path.exists():
                    return False
                if self._existing_lock_is_active():
                    return False
                try:
                    self.lock_path.unlink()
                except FileNotFoundError:
                    pass
                except OSError:
                    return False
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"pid": os.getpid(), "created_at": time.time()}, handle)
            self._owned = True
            return True
        return False

    def release(self) -> None:
        if not self._owned:
            return
        try:
            payload = json.loads(self.lock_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            self._owned = False
            return
        if int(payload.get("pid") or 0) == os.getpid():
            try:
                self.lock_path.unlink()
            except FileNotFoundError:
                pass
        self._owned = False

    def _existing_lock_is_active(self) -> bool:
        try:
            payload = json.loads(self.lock_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return True
        pid = int(payload.get("pid") or 0)
        if pid <= 0:
            return True
        return self._process_exists(pid)

    @staticmethod
    def _safe_key(app_key: str) -> str:
        return "".join(ch for ch in app_key if ch.isalnum() or ch in ("-", "_")).strip() or "app"

    @staticmethod
    def _default_lock_dir() -> Path:
        override = os.environ.get("CLASSROOM_HAND_RAISE_LOCK_DIR")
        if override:
            return Path(override)
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "ClassroomHandRaise"
        return Path.home() / ".ClassroomHandRaise"


def _process_exists(pid: int) -> bool:
    if pid == os.getpid():
        return True
    if os.name == "nt":
        return _windows_process_exists(pid)
    try:
        os.kill(pid, 0)
    except OSError as exc:
        return exc.errno != errno.ESRCH
    return True


def _windows_process_exists(pid: int) -> bool:
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    SYNCHRONIZE = 0x00100000
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, int(pid))
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return True
        return exit_code.value == 259
    finally:
        kernel32.CloseHandle(handle)
