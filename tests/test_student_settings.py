import tempfile
import unittest
from pathlib import Path

from classroom_hand_raise.student.settings import StudentSettings


class StudentSettingsTests(unittest.TestCase):
    def test_settings_create_stable_client_id_and_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"

            first = StudentSettings.load(path)
            second = StudentSettings.load(path)

            self.assertTrue(first.client_id.startswith("client-"))
            self.assertEqual(second.client_id, first.client_id)
            self.assertEqual(first.name, "")
            self.assertEqual(first.host, "127.0.0.1")

    def test_settings_save_name_host_and_port(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            settings = StudentSettings.load(path)

            settings.name = "张三"
            settings.host = "192.168.1.20"
            settings.port = 8765
            settings.save()

            loaded = StudentSettings.load(path)
            self.assertEqual(loaded.client_id, settings.client_id)
            self.assertEqual(loaded.name, "张三")
            self.assertEqual(loaded.host, "192.168.1.20")
            self.assertEqual(loaded.port, 8765)


if __name__ == "__main__":
    unittest.main()
