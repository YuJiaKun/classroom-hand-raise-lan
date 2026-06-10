import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from classroom_hand_raise.shared.single_instance import SingleInstanceLock


class AppEntryLockTests(unittest.TestCase):
    def _run_smoke_with_existing_lock(self, app_key: str, module_name: str, message: str) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as tmp:
            lock = SingleInstanceLock(app_key, message, lock_dir=tmp)
            self.assertTrue(lock.try_acquire())
            self.addCleanup(lock.release)
            env = os.environ.copy()
            env["QT_QPA_PLATFORM"] = "offscreen"
            env["PYTHONPATH"] = str(Path.cwd())
            env["CLASSROOM_HAND_RAISE_LOCK_DIR"] = tmp

            return subprocess.run(
                [sys.executable, "-m", module_name, "--smoke-test"],
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=20,
            )

    def test_teacher_entry_refuses_second_instance_with_chinese_message(self):
        result = self._run_smoke_with_existing_lock(
            "teacher",
            "classroom_hand_raise.teacher.app",
            "教师端已经在运行，请不要重复打开。",
        )

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("教师端已经在运行，请不要重复打开。", result.stdout)

    def test_student_entry_refuses_second_instance_with_chinese_message(self):
        result = self._run_smoke_with_existing_lock(
            "student",
            "classroom_hand_raise.student.app",
            "学生端已经在运行，请不要重复打开。",
        )

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("学生端已经在运行，请不要重复打开。", result.stdout)


if __name__ == "__main__":
    unittest.main()
