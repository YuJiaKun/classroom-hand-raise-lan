import socket
import tempfile
import time
import unittest
from pathlib import Path

from PIL import Image

from classroom_hand_raise.shared.image_tools import compress_image_for_upload
from classroom_hand_raise.shared.protocol import read_frame, write_frame
from classroom_hand_raise.teacher.server import TeacherServer


def wait_until(predicate, timeout: float = 2.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition was not met before timeout")


def connect_student(server: TeacherServer, name: str, client_id: str):
    sock = socket.create_connection(("127.0.0.1", server.port), timeout=2)
    stream = sock.makefile("rwb")
    write_frame(stream, {"type": "join", "name": name, "client_id": client_id})
    joined = read_frame(stream)
    return sock, stream, joined


class NetworkIntegrationTests(unittest.TestCase):
    def test_teacher_server_receives_hand_raise_feedback_and_help_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = TeacherServer(host="127.0.0.1", port=0, data_dir=Path(tmp))
            server.start()
            self.addCleanup(server.stop)

            with socket.create_connection(("127.0.0.1", server.port), timeout=2) as sock:
                stream = sock.makefile("rwb")
                write_frame(stream, {"type": "join", "name": "张三"})
                joined = read_frame(stream)
                student_id = joined["student_id"]

                write_frame(stream, {"type": "raise_hand", "student_id": student_id})
                write_frame(stream, {"type": "feedback", "student_id": student_id, "feedback": "不懂"})
                write_frame(
                    stream,
                    {
                        "type": "help_request",
                        "student_id": student_id,
                        "text": "这个循环条件不懂",
                        "screenshot": None,
                    },
                )

                deadline = time.time() + 2
                while time.time() < deadline and server.state.unread_help_count() == 0:
                    time.sleep(0.02)

                self.assertEqual(len(server.state.hand_queue()), 1)
                self.assertEqual(server.state.feedback_summary(), {"不懂": 1})
                self.assertEqual(server.state.unread_help_count(), 1)
            server.stop()

    def test_teacher_server_saves_uploaded_screenshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = TeacherServer(host="127.0.0.1", port=0, data_dir=Path(tmp), enable_discovery=False)
            server.start()
            self.addCleanup(server.stop)

            image_path = Path(tmp) / "screen.png"
            Image.new("RGB", (320, 180), (40, 120, 220)).save(image_path, format="PNG")
            image_payload = compress_image_for_upload(image_path.read_bytes())

            with socket.create_connection(("127.0.0.1", server.port), timeout=2) as sock:
                stream = sock.makefile("rwb")
                write_frame(stream, {"type": "join", "name": "王五"})
                joined = read_frame(stream)

                write_frame(
                    stream,
                    {
                        "type": "help_request",
                        "student_id": joined["student_id"],
                        "text": "截图里的报错看不懂",
                        **image_payload,
                    },
                )

                deadline = time.time() + 2
                saved_path = None
                while time.time() < deadline:
                    requests = server.state.help_requests()
                    if requests and requests[0].saved_image_path:
                        saved_path = Path(requests[0].saved_image_path)
                        break
                    time.sleep(0.02)

                self.assertIsNotNone(saved_path)
                self.assertTrue(saved_path.exists())
                self.assertGreater(saved_path.stat().st_size, 0)
            server.stop()

    def test_same_client_id_reconnect_does_not_create_duplicate_students(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = TeacherServer(host="127.0.0.1", port=0, data_dir=Path(tmp), enable_discovery=False)
            server.start()
            sockets = []
            streams = []
            try:
                first_sock, first_stream, first_joined = connect_student(server, "张三", "client-stable")
                sockets.append(first_sock)
                streams.append(first_stream)
                second_sock, second_stream, second_joined = connect_student(server, "张三", "client-stable")
                sockets.append(second_sock)
                streams.append(second_stream)

                wait_until(lambda: server.snapshot()["online_count"] == 1)
                snapshot = server.snapshot()

                self.assertEqual(second_joined["student_id"], first_joined["student_id"])
                self.assertEqual(len(snapshot["students"]), 1)
                self.assertEqual(snapshot["students"][0]["client_id"], "client-stable")
                self.assertEqual(snapshot["students"][0]["online"], True)
            finally:
                for stream in streams:
                    try:
                        stream.close()
                    except OSError:
                        pass
                for sock in sockets:
                    try:
                        sock.close()
                    except OSError:
                        pass
                server.stop()

    def test_closing_stale_connection_does_not_mark_reconnected_student_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = TeacherServer(host="127.0.0.1", port=0, data_dir=Path(tmp), enable_discovery=False)
            server.start()
            sockets = []
            streams = []
            try:
                first_sock, first_stream, first_joined = connect_student(server, "李四", "client-reconnect")
                sockets.append(first_sock)
                streams.append(first_stream)
                second_sock, second_stream, second_joined = connect_student(server, "李四", "client-reconnect")
                sockets.append(second_sock)
                streams.append(second_stream)
                self.assertEqual(second_joined["student_id"], first_joined["student_id"])

                first_stream.close()
                first_sock.close()
                wait_until(lambda: server.snapshot()["online_count"] == 1)
                snapshot = server.snapshot()
                self.assertEqual(len(snapshot["students"]), 1)
                self.assertTrue(snapshot["students"][0]["online"])

                second_stream.close()
                second_sock.close()
                wait_until(lambda: server.snapshot()["online_count"] == 0)
                snapshot = server.snapshot()
                self.assertEqual(len(snapshot["students"]), 1)
                self.assertFalse(snapshot["students"][0]["online"])
            finally:
                for stream in streams:
                    try:
                        stream.close()
                    except OSError:
                        pass
                for sock in sockets:
                    try:
                        sock.close()
                    except OSError:
                        pass
                server.stop()


if __name__ == "__main__":
    unittest.main()
