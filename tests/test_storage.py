import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import zipfile

from PIL import Image

from classroom_hand_raise.shared.image_tools import compress_image_for_upload
from classroom_hand_raise.shared.storage import SessionStorage


class StorageTests(unittest.TestCase):
    def test_save_help_image_writes_full_image_and_thumbnail(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "screen.png"
            Image.new("RGB", (800, 500), (30, 120, 210)).save(source, format="PNG")
            payload = compress_image_for_upload(source.read_bytes())
            storage = SessionStorage(Path(tmp) / "data", create=True)

            saved = storage.save_help_image("help-1", payload["screenshot"], "jpeg")

            self.assertTrue(saved["image_path"].exists())
            self.assertTrue(saved["thumbnail_path"].exists())
            self.assertLess(saved["thumbnail_path"].stat().st_size, saved["image_path"].stat().st_size)

    def test_archive_class_sessions_writes_zip_with_existing_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            storage = SessionStorage(data_dir, session_id="session-a", create=True)
            storage.append_event("server_started", {"port": 8765})

            archive_path = storage.archive_class_sessions("before-clear")

            self.assertIsNotNone(archive_path)
            self.assertTrue(archive_path.exists())
            self.assertEqual(archive_path.suffix, ".zip")
            with zipfile.ZipFile(archive_path) as archive:
                names = set(archive.namelist())
            self.assertIn("class_sessions/session-a/events.jsonl", names)

    def test_archive_class_sessions_returns_none_without_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = SessionStorage(Path(tmp) / "data")

            archive_path = storage.archive_class_sessions("before-clear")

            self.assertIsNone(archive_path)

    def test_ensure_created_tolerates_existing_uploads_directory_race(self):
        storage = SessionStorage(Path("data"), session_id="session-a")

        with patch.object(Path, "mkdir", side_effect=FileExistsError), patch.object(Path, "is_dir", return_value=True):
            storage.ensure_created()

    def test_ensure_created_reraises_when_uploads_path_is_not_directory(self):
        storage = SessionStorage(Path("data"), session_id="session-a")

        with patch.object(Path, "mkdir", side_effect=FileExistsError), patch.object(Path, "is_dir", return_value=False):
            with self.assertRaises(FileExistsError):
                storage.ensure_created()


if __name__ == "__main__":
    unittest.main()
