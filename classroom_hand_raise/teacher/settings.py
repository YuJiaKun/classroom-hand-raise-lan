from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path

from classroom_hand_raise.shared.constants import DEFAULT_CLASSROOM_NAME, DEFAULT_TCP_PORT


def default_settings_path() -> Path:
    base_dir = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base_dir:
        return Path(base_dir) / "ClassroomHandRaise" / "teacher_settings.json"
    return Path.home() / ".classroom_hand_raise" / "teacher_settings.json"


@dataclass
class TeacherSettings:
    path: Path
    classroom_name: str = DEFAULT_CLASSROOM_NAME
    port: int = DEFAULT_TCP_PORT

    @classmethod
    def load(cls, path: Path | str | None = None) -> "TeacherSettings":
        settings_path = Path(path) if path is not None else default_settings_path()
        data = {}
        if settings_path.exists():
            try:
                data = json.loads(settings_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
        settings = cls(
            path=settings_path,
            classroom_name=str(data.get("classroom_name") or DEFAULT_CLASSROOM_NAME),
            port=int(data.get("port") or DEFAULT_TCP_PORT),
        )
        if not settings_path.exists():
            try:
                settings.save()
            except OSError:
                pass
        return settings

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "classroom_name": self.classroom_name.strip() or DEFAULT_CLASSROOM_NAME,
            "port": int(self.port),
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
