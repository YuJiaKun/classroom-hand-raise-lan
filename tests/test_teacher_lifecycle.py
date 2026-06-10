import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import zipfile

from classroom_hand_raise.teacher.server import TeacherServer


class TeacherLifecycleTests(unittest.TestCase):
    def test_server_does_not_create_session_directory_before_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"

            TeacherServer(host="127.0.0.1", port=0, data_dir=data_dir, enable_discovery=False)

            self.assertFalse((data_dir / "class_sessions").exists())

    def test_start_and_stop_write_lifecycle_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            server = TeacherServer(host="127.0.0.1", port=0, data_dir=data_dir, enable_discovery=False)

            server.start()
            self.addCleanup(server.stop)
            server.stop()

            events = list(data_dir.glob("class_sessions/*/events.jsonl"))
            self.assertEqual(len(events), 1)
            content = events[0].read_text(encoding="utf-8")
            self.assertIn("server_started", content)
            self.assertIn("server_stopped", content)

    def test_status_snapshot_contains_classroom_counts_and_sorted_lists(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = TeacherServer(host="127.0.0.1", port=0, data_dir=Path(tmp), enable_discovery=False)
            first = server.state.join_student("张三", ("127.0.0.1", 50001))
            time.sleep(0.01)
            second = server.state.join_student("李四", ("127.0.0.1", 50002))
            server.state.raise_hand(second)
            server.state.set_feedback(first, "已懂")
            server.state.add_help_request(first, "这里不会", None)

            snapshot = server.snapshot()

            self.assertFalse(snapshot["running"])
            self.assertEqual(snapshot["online_count"], 2)
            self.assertEqual(snapshot["hand_count"], 1)
            self.assertEqual(snapshot["unread_help_count"], 1)
            self.assertEqual([item["name"] for item in snapshot["students"]], ["张三", "李四"])
            self.assertEqual(snapshot["hand_queue"][0]["student_name"], "李四")
            self.assertEqual(snapshot["feedback_summary"], {"已懂": 1})

    def test_clear_classroom_data_resets_state_and_removes_session_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            server = TeacherServer(host="127.0.0.1", port=0, data_dir=data_dir, enable_discovery=False)
            student_id = server.state.join_student("张三", ("127.0.0.1", 50001))
            server.state.raise_hand(student_id)
            server.state.add_help_request(student_id, "这里不会", None)
            server.start()
            self.addCleanup(server.stop)
            self.assertTrue((data_dir / "class_sessions").exists())

            archive_path = server.clear_classroom_data()

            snapshot = server.snapshot()
            self.assertFalse(snapshot["running"])
            self.assertEqual(snapshot["online_count"], 0)
            self.assertEqual(snapshot["hand_count"], 0)
            self.assertEqual(snapshot["unread_help_count"], 0)
            self.assertFalse((data_dir / "class_sessions").exists())
            self.assertIsNotNone(archive_path)
            self.assertTrue(archive_path.exists())
            with zipfile.ZipFile(archive_path) as archive:
                names = set(archive.namelist())
            self.assertTrue(any(name.endswith("events.jsonl") for name in names))
            self.assertTrue(str(archive_path).endswith(".zip"))

    def test_clear_classroom_data_without_records_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            server = TeacherServer(host="127.0.0.1", port=0, data_dir=data_dir, enable_discovery=False)
            student_id = server.state.join_student("张三", ("127.0.0.1", 50001))
            server.state.raise_hand(student_id)

            archive_path = server.clear_classroom_data()

            snapshot = server.snapshot()
            self.assertIsNone(archive_path)
            self.assertEqual(snapshot["online_count"], 0)
            self.assertEqual(snapshot["hand_count"], 0)

    def test_clear_classroom_data_keeps_records_when_archive_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            server = TeacherServer(host="127.0.0.1", port=0, data_dir=data_dir, enable_discovery=False)
            server.start()
            self.addCleanup(server.stop)
            self.assertTrue((data_dir / "class_sessions").exists())

            with patch.object(server.storage, "archive_class_sessions", side_effect=OSError("zip failed")):
                with self.assertRaises(OSError):
                    server.clear_classroom_data()

            self.assertTrue((data_dir / "class_sessions").exists())
            server.stop()


if __name__ == "__main__":
    unittest.main()
