import socket
import tempfile
import time
import unittest
from pathlib import Path

from classroom_hand_raise.shared.protocol import read_frame, write_frame
from classroom_hand_raise.teacher.server import TeacherServer


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def time(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def wait_until(predicate, timeout: float = 2.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition was not met before timeout")


class RateLimitingTests(unittest.TestCase):
    def _temporary_data_dir(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name)

    def _connect_student(self, server: TeacherServer, name: str = "张三", client_id: str = "client-a"):
        sock = socket.create_connection(("127.0.0.1", server.port), timeout=2)
        self.addCleanup(sock.close)
        stream = sock.makefile("rwb")
        self.addCleanup(stream.close)
        write_frame(stream, {"type": "join", "name": name, "client_id": client_id})
        joined = read_frame(stream)
        self.assertEqual(joined["type"], "join_ack")
        return stream, joined["student_id"]

    def test_repeated_raise_hand_records_event_once_and_returns_already_raised(self):
        events = []
        server = TeacherServer(
            host="127.0.0.1",
            port=0,
            data_dir=self._temporary_data_dir(),
            enable_discovery=False,
            on_event=lambda event_type, payload: events.append((event_type, payload)),
        )
        server.start()
        self.addCleanup(server.stop)
        stream, student_id = self._connect_student(server)

        write_frame(stream, {"type": "raise_hand", "student_id": student_id})
        wait_until(lambda: len(server.state.hand_queue()) == 1)
        write_frame(stream, {"type": "raise_hand", "student_id": student_id})
        error = read_frame(stream)

        self.assertEqual(error["type"], "error")
        self.assertIn("已经举手", error["message"])
        self.assertEqual(len(server.state.hand_queue()), 1)
        self.assertEqual([event[0] for event in events].count("raise_hand"), 1)

    def test_feedback_is_rate_limited_per_student_and_allows_after_cooldown(self):
        clock = FakeClock()
        server = TeacherServer(
            host="127.0.0.1",
            port=0,
            data_dir=self._temporary_data_dir(),
            enable_discovery=False,
            time_func=clock.time,
        )
        server.start()
        self.addCleanup(server.stop)
        stream, student_id = self._connect_student(server)

        write_frame(stream, {"type": "feedback", "student_id": student_id, "feedback": "我没听懂"})
        wait_until(lambda: server.state.feedback_summary() == {"我没听懂": 1})

        write_frame(stream, {"type": "feedback", "student_id": student_id, "feedback": "讲慢一点"})
        error = read_frame(stream)
        self.assertEqual(error["type"], "error")
        self.assertIn("操作太频繁", error["message"])
        self.assertEqual(server.state.feedback_summary(), {"我没听懂": 1})

        clock.advance(5)
        write_frame(stream, {"type": "feedback", "student_id": student_id, "feedback": "讲慢一点"})
        wait_until(lambda: server.state.feedback_summary() == {"讲慢一点": 1})

    def test_help_request_is_rate_limited_per_student_and_allows_after_cooldown(self):
        clock = FakeClock()
        server = TeacherServer(
            host="127.0.0.1",
            port=0,
            data_dir=self._temporary_data_dir(),
            enable_discovery=False,
            time_func=clock.time,
        )
        server.start()
        self.addCleanup(server.stop)
        stream, student_id = self._connect_student(server)

        write_frame(stream, {"type": "help_request", "student_id": student_id, "text": "第一题不会"})
        wait_until(lambda: server.state.unread_help_count() == 1)

        write_frame(stream, {"type": "help_request", "student_id": student_id, "text": "第二题不会"})
        error = read_frame(stream)
        self.assertEqual(error["type"], "error")
        self.assertIn("操作太频繁", error["message"])
        self.assertEqual(server.state.unread_help_count(), 1)

        clock.advance(30)
        write_frame(stream, {"type": "help_request", "student_id": student_id, "text": "第三题不会"})
        wait_until(lambda: server.state.unread_help_count() == 2)

    def test_lower_hand_is_not_rate_limited(self):
        server = TeacherServer(
            host="127.0.0.1",
            port=0,
            data_dir=self._temporary_data_dir(),
            enable_discovery=False,
        )
        server.start()
        self.addCleanup(server.stop)
        stream, student_id = self._connect_student(server)

        write_frame(stream, {"type": "raise_hand", "student_id": student_id})
        wait_until(lambda: len(server.state.hand_queue()) == 1)
        write_frame(stream, {"type": "lower_hand", "student_id": student_id})
        wait_until(lambda: len(server.state.hand_queue()) == 0)


if __name__ == "__main__":
    unittest.main()
