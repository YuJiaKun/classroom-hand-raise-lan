import tempfile
import unittest
from pathlib import Path

from classroom_hand_raise.teacher.settings import TeacherSettings


class TeacherSettingsTests(unittest.TestCase):
    def test_settings_create_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "teacher_settings.json"

            settings = TeacherSettings.load(path)

            self.assertEqual(settings.classroom_name, "默认课堂")
            self.assertEqual(settings.port, 8765)

    def test_settings_save_classroom_name_and_port(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "teacher_settings.json"
            settings = TeacherSettings.load(path)

            settings.classroom_name = "三年级二班"
            settings.port = 9001
            settings.save()

            loaded = TeacherSettings.load(path)
            self.assertEqual(loaded.classroom_name, "三年级二班")
            self.assertEqual(loaded.port, 9001)


if __name__ == "__main__":
    unittest.main()
