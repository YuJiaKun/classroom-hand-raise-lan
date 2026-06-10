import os
import tempfile
import unittest
from pathlib import Path

from classroom_hand_raise.shared.single_instance import SingleInstanceLock


class SingleInstanceLockTests(unittest.TestCase):
    def test_second_lock_with_same_key_fails_until_first_releases(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = SingleInstanceLock("teacher", "教师端已经在运行，请不要重复打开。", lock_dir=tmp)
            second = SingleInstanceLock("teacher", "教师端已经在运行，请不要重复打开。", lock_dir=tmp)

            self.assertTrue(first.try_acquire())
            self.assertFalse(second.try_acquire())

            first.release()
            self.assertTrue(second.try_acquire())
            second.release()

    def test_stale_lock_is_cleaned_when_process_is_gone(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "student.lock"
            lock_path.write_text('{"pid": 999999, "created_at": 1.0}', encoding="utf-8")
            lock = SingleInstanceLock(
                "student",
                "学生端已经在运行，请不要重复打开。",
                lock_dir=tmp,
                process_exists=lambda _pid: False,
            )

            self.assertTrue(lock.try_acquire())
            self.assertTrue(lock_path.exists())
            self.assertNotIn("999999", lock_path.read_text(encoding="utf-8"))

            lock.release()

    def test_lock_dir_can_be_overridden_for_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_value = os.environ.get("CLASSROOM_HAND_RAISE_LOCK_DIR")
            os.environ["CLASSROOM_HAND_RAISE_LOCK_DIR"] = tmp
            self.addCleanup(self._restore_env, "CLASSROOM_HAND_RAISE_LOCK_DIR", old_value)

            lock = SingleInstanceLock("teacher", "教师端已经在运行，请不要重复打开。")

            self.assertEqual(lock.lock_path, Path(tmp) / "teacher.lock")

    def _restore_env(self, key: str, value: str | None) -> None:
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
