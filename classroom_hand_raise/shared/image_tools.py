from __future__ import annotations

import base64
import io
from pathlib import Path

from PIL import Image

from .constants import MAX_SCREENSHOT_BYTES, MAX_SCREENSHOT_EDGE


SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def compress_image_for_upload(image_bytes: bytes) -> dict[str, object]:
    try:
        image = Image.open(io.BytesIO(image_bytes))
    except Exception as exc:
        raise ValueError("截图无法识别，请重新截图") from exc

    image = image.convert("RGB")
    image.thumbnail((MAX_SCREENSHOT_EDGE, MAX_SCREENSHOT_EDGE), Image.Resampling.LANCZOS)

    last_payload: bytes | None = None
    for quality in range(88, 39, -8):
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=quality, optimize=True)
        payload = output.getvalue()
        last_payload = payload
        if len(payload) <= MAX_SCREENSHOT_BYTES:
            return {
                "screenshot": base64.b64encode(payload).decode("ascii"),
                "image_format": "jpeg",
                "width": image.width,
                "height": image.height,
                "byte_size": len(payload),
            }

    size = len(last_payload) if last_payload else 0
    raise ValueError(f"截图压缩后仍超过 2MB（当前 {size} 字节），请截取更小区域")


def load_image_file_for_upload(path: str | Path) -> dict[str, object]:
    image_path = Path(path)
    if image_path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
        raise ValueError("只支持上传截图图片：png、jpg、jpeg、webp")
    try:
        image_bytes = image_path.read_bytes()
    except OSError as exc:
        raise ValueError(f"无法读取截图图片：{exc}") from exc
    return compress_image_for_upload(image_bytes)
