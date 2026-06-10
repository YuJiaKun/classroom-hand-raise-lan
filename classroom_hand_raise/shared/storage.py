from __future__ import annotations

import base64
import io
from dataclasses import asdict, is_dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any
import zipfile

from PIL import Image


class SessionStorage:
    def __init__(
        self,
        data_dir: Path | str = Path("data"),
        session_id: str | None = None,
        create: bool = False,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.session_id = session_id or datetime.now().strftime("%Y%m%d-%H%M%S")
        self.session_dir = self.data_dir / "class_sessions" / self.session_id
        self.uploads_dir = self.session_dir / "uploads"
        self.events_path = self.session_dir / "events.jsonl"
        if create:
            self.ensure_created()

    def ensure_created(self) -> None:
        try:
            self.uploads_dir.mkdir(parents=True, exist_ok=True)
        except FileExistsError:
            if not self.uploads_dir.is_dir():
                raise

    def append_event(self, event_type: str, payload: dict[str, Any]) -> None:
        event = {
            "event_type": event_type,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "payload": self._jsonable(payload),
        }
        self.ensure_created()
        with self.events_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")

    def save_help_screenshot(self, request_id: str, screenshot_base64: str, image_format: str = "jpeg") -> Path:
        return self.save_help_image(request_id, screenshot_base64, image_format)["image_path"]

    def save_help_image(self, request_id: str, screenshot_base64: str, image_format: str = "jpeg") -> dict[str, Path]:
        self.ensure_created()
        suffix = "jpg" if image_format.lower() in {"jpeg", "jpg"} else image_format.lower()
        safe_name = "".join(ch for ch in request_id if ch.isalnum() or ch in {"-", "_"}) or "screenshot"
        path = self.uploads_dir / f"{safe_name}.{suffix}"
        image_bytes = base64.b64decode(screenshot_base64)
        path.write_bytes(image_bytes)

        thumbnail_path = self.uploads_dir / f"{safe_name}.thumb.jpg"
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        image.thumbnail((240, 160), Image.Resampling.LANCZOS)
        image.save(thumbnail_path, format="JPEG", quality=76, optimize=True)

        return {"image_path": path, "thumbnail_path": thumbnail_path}

    def archive_class_sessions(self, label: str = "before-clear") -> Path | None:
        class_sessions_dir = self.data_dir / "class_sessions"
        if not class_sessions_dir.exists() or not any(class_sessions_dir.rglob("*")):
            return None

        safe_label = "".join(ch for ch in label if ch.isalnum() or ch in {"-", "_"}) or "archive"
        archives_dir = self.data_dir / "class_session_archives"
        archives_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        archive_path = archives_dir / f"{timestamp}-{safe_label}.zip"
        counter = 1
        while archive_path.exists():
            archive_path = archives_dir / f"{timestamp}-{safe_label}-{counter}.zip"
            counter += 1

        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(class_sessions_dir.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(self.data_dir).as_posix())
        return archive_path

    def _jsonable(self, value: Any) -> Any:
        if is_dataclass(value):
            return self._jsonable(asdict(value))
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {key: self._jsonable(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._jsonable(item) for item in value]
        return value
