import tempfile
import time
import unittest
from pathlib import Path
from types import MethodType

from classroom_hand_raise.student.client import StudentClient
from classroom_hand_raise.teacher.server import TeacherServer


class OneRetryStopEvent:
    def __init__(self) -> None:
        self.calls = 0
        self.stopped = False

    def is_set(self) -> bool:
        return self.stopped

    def set(self) -> None:
        self.stopped = True

    def wait(self, _seconds: float) -> bool:
        if self.calls == 0:
            self.calls += 1
            return False
        self.stopped = True
        return True


class StudentClientTests(unittest.TestCase):
    def test_client_connects_and_sends_classroom_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = TeacherServer(host="127.0.0.1", port=0, data_dir=Path(tmp), enable_discovery=False)
            server.start()
            self.addCleanup(server.stop)

            send_states = []
            client = StudentClient(reconnect_enabled=False)
            client.on_send_status = send_states.append
            self.addCleanup(client.disconnect)

            client.connect("127.0.0.1", server.port, "李四")
            client.raise_hand()
            client.send_feedback("太快")
            client.send_help_request("这里没听清", None)

            deadline = time.time() + 2
            while time.time() < deadline and server.state.unread_help_count() == 0:
                time.sleep(0.02)

            self.assertEqual(len(server.state.online_students()), 1)
            self.assertEqual(len(server.state.hand_queue()), 1)
            self.assertEqual(server.state.feedback_summary(), {"太快": 1})
            self.assertEqual(server.state.unread_help_count(), 1)
            self.assertIn("发送中", send_states)
            self.assertIn("发送成功", send_states)
            client.disconnect()
            server.stop()

    def test_heartbeat_send_is_silent_for_user_send_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = TeacherServer(host="127.0.0.1", port=0, data_dir=Path(tmp), enable_discovery=False)
            server.start()
            self.addCleanup(server.stop)

            send_states = []
            client = StudentClient(reconnect_enabled=False)
            client.on_send_status = send_states.append
            self.addCleanup(client.disconnect)
            client.connect("127.0.0.1", server.port, "李四", client_id="client-silent")
            send_states.clear()

            client._send({"type": "heartbeat"}, emit_status=False)

            self.assertEqual(send_states, [])
            client.disconnect()
            server.stop()

    def test_background_reconnect_failure_is_status_not_error_popup_signal(self):
        statuses = []
        errors = []
        client = StudentClient(on_status=statuses.append, on_error=errors.append)
        client.host = "127.0.0.1"
        client.port = 8765
        client.name = "张三"
        client.client_id = "client-retry"
        client._stop_event = OneRetryStopEvent()

        def fail_open(self, *_args):
            raise ConnectionRefusedError(10061, "由于目标计算机积极拒绝，无法连接。")

        client._open_connection = MethodType(fail_open, client)

        client._handle_disconnect_locked()

        self.assertEqual(errors, [])
        self.assertIn("老师端已断开，正在后台重连。请等待老师重新启动课堂。", statuses)


if __name__ == "__main__":
    unittest.main()
