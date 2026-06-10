import socket
import tempfile
import time
import unittest
from pathlib import Path

from classroom_hand_raise.shared.protocol import read_frame, write_frame
from classroom_hand_raise.teacher.server import TeacherServer


class TeacherReplyTests(unittest.TestCase):
    def test_classroom_state_adds_reply_and_marks_unread_for_student(self):
        server = TeacherServer(host="127.0.0.1", port=0, enable_discovery=False)
        student_id = server.state.join_student("张三", ("127.0.0.1", 50001), client_id="client-a")
        request = server.state.add_help_request(student_id, "这里不会", None)

        reply = server.state.add_teacher_reply(request.request_id, "看第 3 行条件", "老师")

        self.assertEqual(reply.text, "看第 3 行条件")
        self.assertEqual(server.state.help_requests()[0].reply_status, "已回复")
        self.assertEqual(len(server.state.unread_replies_for_client("client-a")), 1)

    def test_online_student_receives_teacher_reply_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = TeacherServer(host="127.0.0.1", port=0, data_dir=Path(tmp), enable_discovery=False)
            server.start()
            self.addCleanup(server.stop)

            with socket.create_connection(("127.0.0.1", server.port), timeout=2) as sock:
                stream = sock.makefile("rwb")
                write_frame(stream, {"type": "join", "name": "张三", "client_id": "client-online"})
                joined = read_frame(stream)
                write_frame(
                    stream,
                    {
                        "type": "help_request",
                        "student_id": joined["student_id"],
                        "text": "循环没懂",
                        "screenshot": None,
                    },
                )

                deadline = time.time() + 2
                request = None
                while time.time() < deadline:
                    requests = server.state.help_requests()
                    if requests:
                        request = requests[0]
                        break
                    time.sleep(0.02)
                self.assertIsNotNone(request)

                server.send_teacher_reply(request.request_id, "先看循环条件，再看缩进")
                message = read_frame(stream)

                self.assertEqual(message["type"], "teacher_reply")
                self.assertEqual(message["request_id"], request.request_id)
                self.assertIn("循环条件", message["text"])
                self.assertEqual(len(server.state.unread_replies_for_client("client-online")), 1)

                write_frame(
                    stream,
                    {
                        "type": "reply_read",
                        "student_id": joined["student_id"],
                        "reply_ids": [message["reply_id"]],
                    },
                )
                deadline = time.time() + 2
                while time.time() < deadline and server.state.unread_replies_for_client("client-online"):
                    time.sleep(0.02)
                self.assertEqual(server.state.unread_replies_for_client("client-online"), [])
            server.stop()

    def test_offline_reply_is_sent_after_reconnect_with_same_client_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = TeacherServer(host="127.0.0.1", port=0, data_dir=Path(tmp), enable_discovery=False)
            server.start()
            self.addCleanup(server.stop)

            with socket.create_connection(("127.0.0.1", server.port), timeout=2) as sock:
                stream = sock.makefile("rwb")
                write_frame(stream, {"type": "join", "name": "李四", "client_id": "client-offline"})
                joined = read_frame(stream)
                write_frame(stream, {"type": "help_request", "student_id": joined["student_id"], "text": "这里不会"})
                deadline = time.time() + 2
                request = None
                while time.time() < deadline:
                    requests = server.state.help_requests()
                    if requests:
                        request = requests[0]
                        break
                    time.sleep(0.02)
                self.assertIsNotNone(request)

            deadline = time.time() + 2
            while time.time() < deadline and server.state.online_students():
                time.sleep(0.02)

            server.send_teacher_reply(request.request_id, "答案是先判断再进入循环")

            with socket.create_connection(("127.0.0.1", server.port), timeout=2) as sock:
                stream = sock.makefile("rwb")
                write_frame(stream, {"type": "join", "name": "李四", "client_id": "client-offline"})
                joined = read_frame(stream)

                self.assertEqual(joined["type"], "join_ack")
                self.assertEqual(len(joined["pending_replies"]), 1)
                self.assertEqual(joined["pending_replies"][0]["request_id"], request.request_id)
            server.stop()


if __name__ == "__main__":
    unittest.main()
