import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QRect

from classroom_hand_raise.teacher.ui import TeacherWindow
from classroom_hand_raise.student.ui import StudentWindow
from classroom_hand_raise.shared.constants import RAISE_HAND_COOLDOWN_SECONDS


class UiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QApplication.instance() or QApplication([])

    def test_teacher_window_exposes_v02_dashboard_controls(self):
        window = TeacherWindow()
        self.addCleanup(window.close)

        texts = window.visible_texts()

        self.assertIn("课堂控制台", texts)
        self.assertIn("在线人数：0", texts)
        self.assertIn("举手人数：0", texts)
        self.assertIn("未读问题：0", texts)
        self.assertIn("全部问题", texts)
        self.assertIn("导出课堂记录", texts)
        self.assertIn("课堂名称", texts)
        self.assertIn("保存设置", texts)
        self.assertIn("新班级清空", texts)
        self.assertIn("自动备份", texts)
        self.assertIn("课堂提醒", texts)
        self.assertIn("回复学生", texts)
        self.assertIn("发送回复", texts)
        self.assertIn("连接状态", texts)
        self.assertIn("推荐连接地址", texts)

    def test_teacher_window_can_center_on_screen(self):
        window = TeacherWindow()
        self.addCleanup(window.close)
        screen_rect = QRect(100, 80, 1200, 800)

        window.center_on_screen(screen_rect)

        self.assertEqual(window.frameGeometry().center(), screen_rect.center())

    def test_student_window_can_center_on_screen(self):
        window = StudentWindow()
        window.force_exit = True
        self.addCleanup(window.close)
        screen_rect = QRect(40, 60, 1000, 700)

        window.center_on_screen(screen_rect)

        self.assertEqual(window.frameGeometry().center(), screen_rect.center())

    def test_teacher_window_uses_anonymous_alert_for_hand_raise(self):
        window = TeacherWindow()
        self.addCleanup(window.close)

        student_id = window.server.state.join_student("张三", ("127.0.0.1", 50001))
        window.handle_teacher_event("raise_hand", {"student_id": student_id})

        self.assertIn("有学生举手提问", window.alert_label.text())
        self.assertIn("有学生举手提问", window.popup_texts())
        self.assertNotIn("张三", window.alert_label.text())
        self.assertNotIn("张三", " ".join(window.popup_texts()))
        self.assertIn("张三", window.classroom_reminders_list.item(0).text())

    def test_teacher_window_uses_anonymous_alert_for_slow_feedback(self):
        window = TeacherWindow()
        self.addCleanup(window.close)

        student_id = window.server.state.join_student("李四", ("127.0.0.1", 50001))
        window.handle_teacher_event("feedback", {"student_id": student_id, "feedback": "讲慢一点"})

        self.assertIn("有学生反馈：讲慢一点", window.alert_label.text())
        self.assertIn("有学生反馈：讲慢一点", window.popup_texts())
        self.assertNotIn("李四", window.alert_label.text())
        self.assertNotIn("李四", " ".join(window.popup_texts()))
        self.assertIn("李四", window.classroom_reminders_list.item(0).text())

    def test_teacher_window_uses_anonymous_popup_for_help_request(self):
        window = TeacherWindow()
        self.addCleanup(window.close)

        student_id = window.server.state.join_student("王五", ("127.0.0.1", 50001))
        request = window.server.state.add_help_request(student_id, "这里没懂", None)
        window.handle_teacher_event("help_request", request.__dict__)

        self.assertIn("有学生提交不懂点", window.alert_label.text())
        self.assertIn("有学生提交不懂点", window.popup_texts())
        self.assertNotIn("王五", window.alert_label.text())
        self.assertNotIn("王五", " ".join(window.popup_texts()))
        self.assertIn("王五", window.classroom_reminders_list.item(0).text())

    def test_teacher_window_limits_anonymous_popups_to_three(self):
        window = TeacherWindow()
        self.addCleanup(window.close)

        for index in range(4):
            window.show_anonymous_popup(f"匿名提醒 {index}")

        self.assertEqual(window.popup_texts(), ["匿名提醒 1", "匿名提醒 2", "匿名提醒 3"])

    def test_student_window_exposes_v04_classroom_actions(self):
        window = StudentWindow()
        window.force_exit = True
        self.addCleanup(window.close)

        texts = window.visible_texts()

        self.assertIn("连接课堂", texts)
        self.assertIn("举手提问", texts)
        self.assertIn("取消举手", texts)
        self.assertIn("可以继续", texts)
        self.assertIn("我没听懂", texts)
        self.assertIn("讲慢一点", texts)
        self.assertIn("请再讲一遍", texts)
        self.assertIn("发送给老师", texts)
        self.assertIn("选择截图图片", texts)
        self.assertIn("粘贴截图", texts)
        self.assertIn("老师回复", texts)
        self.assertIn("发送状态：未发送", texts)
        self.assertNotIn("截取当前屏幕", texts)

    def test_student_window_shows_local_cooldown_text(self):
        window = StudentWindow()
        window.force_exit = True
        self.addCleanup(window.close)
        window.client._socket = socket.socket()
        window.client.student_id = "stu-test"
        self.addCleanup(window.client.disconnect)

        window._set_connected(True)
        window._start_cooldown("raise_hand", RAISE_HAND_COOLDOWN_SECONDS)

        self.assertFalse(window.raise_button.isEnabled())
        self.assertIn("请稍候", window.raise_button.text())
        self.assertTrue(window.lower_button.isEnabled())

    def test_source_smoke_test_does_not_create_class_session_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["QT_QPA_PLATFORM"] = "offscreen"
            env["PYTHONPATH"] = str(Path.cwd())
            env["CLASSROOM_HAND_RAISE_LOCK_DIR"] = str(Path(tmp) / "locks")

            result = subprocess.run(
                [sys.executable, "-m", "classroom_hand_raise.teacher.app", "--smoke-test"],
                cwd=tmp,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=20,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((Path(tmp) / "data" / "class_sessions").exists())


if __name__ == "__main__":
    unittest.main()
