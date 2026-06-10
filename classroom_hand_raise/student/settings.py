from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import uuid

from classroom_hand_raise.shared.constants import DEFAULT_TCP_PORT


def default_settings_path() -> Path:
    base_dir = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base_dir:
        return Path(base_dir) / "ClassroomHandRaise" / "student_settings.json"
    return Path.home() / ".classroom_hand_raise" / "student_settings.json"


@dataclass
class StudentSettings:
    path: Path
    client_id: str
    name: str = ""
    host: str = "127.0.0.1"
    port: int = DEFAULT_TCP_PORT

    @classmethod
    def load(cls, path: Path | str | None = None) -> "StudentSettings":
        settings_path = Path(path) if path is not None else default_settings_path()
        data = {}
        if settings_path.exists():
            try:
                data = json.loads(settings_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
        settings = cls(
            path=settings_path,
            client_id=str(data.get("client_id") or f"client-{uuid.uuid4().hex[:12]}"),
            name=str(data.get("name") or ""),
            host=str(data.get("host") or "127.0.0.1"),
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
            "client_id": self.client_id,
            "name": self.name,
            "host": self.host,
            "port": self.port,
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
