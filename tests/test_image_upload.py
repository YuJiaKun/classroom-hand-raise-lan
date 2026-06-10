import tempfile
import unittest
from pathlib import Path

from PIL import Image

from classroom_hand_raise.shared.image_tools import load_image_file_for_upload


class ImageUploadTests(unittest.TestCase):
    def test_load_image_file_accepts_supported_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "question.png"
            Image.new("RGB", (640, 360), (40, 130, 220)).save(path, format="PNG")

            payload = load_image_file_for_upload(path)

            self.assertEqual(payload["image_format"], "jpeg")
            self.assertGreater(payload["byte_size"], 0)

    def test_load_image_file_rejects_non_image_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "note.txt"
            path.write_text("not image", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "只支持上传截图图片"):
                load_image_file_for_upload(path)

    def test_load_image_file_rejects_broken_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.png"
            path.write_bytes(b"not a real image")

            with self.assertRaisesRegex(ValueError, "截图无法识别"):
                load_image_file_for_upload(path)


if __name__ == "__main__":
    unittest.main()
