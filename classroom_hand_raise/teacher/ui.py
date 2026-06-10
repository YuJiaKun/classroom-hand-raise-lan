from __future__ import annotations

import base64
from datetime import datetime
import json
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from classroom_hand_raise.shared.discovery import get_local_ip_addresses, primary_local_ip_address
from classroom_hand_raise.shared.ui_geometry import center_window
from classroom_hand_raise.teacher.server import TeacherServer
from classroom_hand_raise.teacher.settings import TeacherSettings
from classroom_hand_raise.teacher.ui_components import apply_teacher_style, metric_label


ATTENTION_FEEDBACKS = {"我没听懂", "讲慢一点", "请再讲一遍"}


def _format_time(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")


class TeacherSignals(QObject):
    changed = Signal(str, dict)


class HelpDetailDialog(QDialog):
    def __init__(self, help_request, on_reply=None, parent=None) -> None:
        super().__init__(parent)
        self.help_request = help_request
        self.on_reply = on_reply
        self.setWindowTitle("学生问题详情")
        self.resize(840, 760)

        layout = QVBoxLayout(self)
        title = QLabel(f"{help_request.student_name} · {_format_time(help_request.created_at)}")
        title.setProperty("class", "title")
        layout.addWidget(title)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(help_request.text or "学生未填写文字说明")
        text.setMinimumHeight(110)
        layout.addWidget(text)

        image_label = QLabel("本条问题没有截图")
        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_label.setMinimumHeight(380)
        image_label.setStyleSheet("border: 1px solid #d0d7de; background: #f8fafc; color: #64748b;")
        pixmap = self._load_pixmap(help_request)
        if pixmap and not pixmap.isNull():
            image_label.setPixmap(
                pixmap.scaled(
                    780,
                    440,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            image_label.setText("")
        layout.addWidget(image_label)

        layout.addWidget(QLabel("已有回复"))
        self.reply_history = QListWidget()
        self._refresh_reply_history()
        layout.addWidget(self.reply_history)

        layout.addWidget(QLabel("回复学生"))
        self.reply_input = QTextEdit()
        self.reply_input.setPlaceholderText("输入给学生的回复，例如：先看循环条件，再看缩进")
        self.reply_input.setMaximumHeight(90)
        layout.addWidget(self.reply_input)

        action_row = QHBoxLayout()
        self.send_reply_button = QPushButton("发送回复")
        self.send_reply_button.clicked.connect(self.send_reply)
        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.accept)
        action_row.addStretch(1)
        action_row.addWidget(self.send_reply_button)
        action_row.addWidget(close_button)
        layout.addLayout(action_row)

    def _refresh_reply_history(self) -> None:
        self.reply_history.clear()
        replies = self.help_request.replies or []
        if not replies:
            self.reply_history.addItem("暂无回复")
            return
        for reply in sorted(replies, key=lambda item: item.created_at, reverse=True):
            self.reply_history.addItem(
                f"{_format_time(reply.created_at)} · {reply.teacher_name}：{reply.text}"
            )

    def send_reply(self) -> None:
        text = self.reply_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "提示", "回复内容不能为空")
            return
        if self.on_reply is None:
            QMessageBox.warning(self, "提示", "当前无法发送回复")
            return
        try:
            self.on_reply(self.help_request.request_id, text)
        except Exception as exc:
            QMessageBox.warning(self, "发送失败", str(exc))
            return
        self.reply_input.clear()
        self._refresh_reply_history()
        QMessageBox.information(self, "发送成功", "已发送回复给学生")

    def _load_pixmap(self, help_request) -> QPixmap | None:
        if help_request.saved_image_path and Path(help_request.saved_image_path).exists():
            return QPixmap(help_request.saved_image_path)
        if help_request.screenshot:
            pixmap = QPixmap()
            pixmap.loadFromData(base64.b64decode(help_request.screenshot))
            return pixmap
        return None


class TeacherWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.toast_popups: list[QFrame] = []
        self.setWindowTitle("局域网课堂互动 - 老师端")
        self.resize(1260, 760)

        self.signals = TeacherSignals()
        self.signals.changed.connect(self.handle_teacher_event)
        self.settings = TeacherSettings.load()
        self.server = TeacherServer(
            port=self.settings.port,
            classroom_name=self.settings.classroom_name,
            on_event=self.signals.changed.emit,
        )
        self._help_items = []

        self.title_label = QLabel("课堂控制台")
        self.title_label.setProperty("class", "title")
        self.status_label = QLabel("服务状态：未启动")
        self.classroom_label = QLabel(f"课堂：{self.server.classroom_name}")
        self.address_label = QLabel("推荐连接地址：启动课堂后显示")
        self.other_addresses_label = QLabel("其他地址：启动课堂后显示")
        self.alert_label = QLabel("暂无新的课堂提醒")
        self.alert_label.setProperty("class", "alert")
        self.classroom_name_input = QLineEdit(self.settings.classroom_name)
        self.port_input = QLineEdit(str(self.settings.port))
        self.online_metric = metric_label("在线人数", "0")
        self.hand_metric = metric_label("举手人数", "0")
        self.unread_metric = metric_label("未读问题", "0")
        self.save_settings_button = QPushButton("保存设置")
        self.save_settings_button.setObjectName("SecondaryButton")
        self.clear_classroom_button = QPushButton("新班级清空")
        self.clear_classroom_button.setObjectName("SecondaryButton")
        self.start_button = QPushButton("启动课堂")
        self.stop_button = QPushButton("停止课堂")
        self.stop_button.setObjectName("SecondaryButton")
        self.stop_button.setEnabled(False)

        self.students_table = QTableWidget(0, 5)
        self.students_table.setHorizontalHeaderLabels(["姓名", "连接状态", "反馈", "举手状态", "最后活动"])
        self.hand_queue_list = QListWidget()
        self.feedback_table = QTableWidget(0, 2)
        self.feedback_table.setHorizontalHeaderLabels(["反馈", "人数"])
        self.classroom_reminders_list = QListWidget()
        self.classroom_reminders_list.addItem("暂无课堂提醒")
        self.help_filter = QComboBox()
        self.help_filter.addItem("全部问题", "all")
        self.help_filter.addItem("未读问题", "unread")
        self.help_filter.addItem("已处理问题", "handled")
        self.help_table = QTableWidget(0, 5)
        self.help_table.setHorizontalHeaderLabels(["状态", "学生", "时间", "文字摘要", "截图"])
        self.open_detail_button = QPushButton("查看详情")
        self.mark_handled_button = QPushButton("标记已处理")
        self.export_button = QPushButton("导出课堂记录")
        self.export_button.setObjectName("SecondaryButton")

        self._build_ui()
        self._wire_events()
        apply_teacher_style(self)
        self.refresh_view()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_view)
        self.refresh_timer.start(2500)

        self.alert_timer = QTimer(self)
        self.alert_timer.setSingleShot(True)
        self.alert_timer.timeout.connect(self.clear_anonymous_alert)

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.addWidget(self._build_top_bar())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(self._group("在线学生", self.students_table), stretch=3)
        left_layout.addWidget(self._group("举手队列", self.hand_queue_list), stretch=2)

        middle = QWidget()
        middle_layout = QVBoxLayout(middle)
        middle_layout.addWidget(self._group("反馈统计", self.feedback_table))
        middle_layout.addWidget(self._group("课堂提醒", self.classroom_reminders_list))

        right = QWidget()
        right_layout = QVBoxLayout(right)
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("筛选"))
        filter_row.addWidget(self.help_filter, stretch=1)
        filter_row.addWidget(self.open_detail_button)
        filter_row.addWidget(self.mark_handled_button)
        filter_row.addWidget(self.export_button)
        help_box = QGroupBox("问题收件箱")
        help_layout = QVBoxLayout(help_box)
        help_layout.addLayout(filter_row)
        help_layout.addWidget(self.help_table)
        right_layout.addWidget(help_box)

        splitter.addWidget(left)
        splitter.addWidget(middle)
        splitter.addWidget(right)
        splitter.setSizes([420, 260, 580])
        root_layout.addWidget(splitter, stretch=1)
        self.setCentralWidget(root)

        for table in [self.students_table, self.feedback_table, self.help_table]:
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.help_table.setIconSize(self.help_table.iconSize())
        self.help_table.verticalHeader().setDefaultSectionSize(72)

    def _build_top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        layout = QGridLayout(bar)
        layout.addWidget(self.title_label, 0, 0)
        layout.addWidget(self.status_label, 1, 0)
        layout.addWidget(self.classroom_label, 0, 1)
        layout.addWidget(self.address_label, 1, 1, 1, 2)
        layout.addWidget(self.other_addresses_label, 1, 3, 1, 2)
        layout.addWidget(self.alert_label, 3, 0, 1, 6)
        layout.addWidget(self.online_metric, 0, 2)
        layout.addWidget(self.hand_metric, 0, 3)
        layout.addWidget(self.unread_metric, 0, 4)
        layout.addWidget(self.start_button, 0, 5)
        layout.addWidget(self.stop_button, 1, 5)
        layout.addWidget(QLabel("课堂名称"), 2, 0)
        layout.addWidget(self.classroom_name_input, 2, 1)
        layout.addWidget(QLabel("端口"), 2, 2)
        layout.addWidget(self.port_input, 2, 3)
        layout.addWidget(self.save_settings_button, 2, 4)
        layout.addWidget(self.clear_classroom_button, 2, 5)
        layout.setColumnStretch(1, 1)
        return bar

    def _group(self, title: str, child: QWidget) -> QGroupBox:
        box = QGroupBox(title)
        layout = QVBoxLayout(box)
        layout.addWidget(child)
        return box

    def _wire_events(self) -> None:
        self.start_button.clicked.connect(self.start_server)
        self.stop_button.clicked.connect(self.stop_server)
        self.save_settings_button.clicked.connect(self.save_teacher_settings)
        self.clear_classroom_button.clicked.connect(self.clear_classroom_data)
        self.help_filter.currentIndexChanged.connect(self.refresh_view)
        self.open_detail_button.clicked.connect(self.open_selected_help)
        self.mark_handled_button.clicked.connect(self.mark_selected_help_handled)
        self.export_button.clicked.connect(self.export_records)
        self.help_table.cellDoubleClicked.connect(lambda *_: self.open_selected_help())

    def handle_teacher_event(self, event_type: str, payload: dict) -> None:
        if event_type == "raise_hand":
            self.add_classroom_reminder("举手提问", payload, "有学生举手提问")
            self.show_anonymous_popup("有学生举手提问")
        elif event_type == "feedback":
            feedback = str(payload.get("feedback") or "")
            if feedback in ATTENTION_FEEDBACKS:
                self.add_classroom_reminder(feedback, payload, f"有学生反馈：{feedback}")
                self.show_anonymous_popup(f"有学生反馈：{feedback}")
        elif event_type == "help_request":
            self.add_classroom_reminder("提交不懂点", payload, "有学生提交不懂点")
            self.show_anonymous_popup("有学生提交不懂点")
        self.refresh_view()

    def add_classroom_reminder(self, reminder_type: str, payload: dict, anonymous_text: str) -> None:
        student_name = self._student_name_for_event(payload)
        if self.classroom_reminders_list.count() == 1 and self.classroom_reminders_list.item(0).text() == "暂无课堂提醒":
            self.classroom_reminders_list.clear()
        self.classroom_reminders_list.insertItem(0, f"{datetime.now().strftime('%H:%M:%S')} · {student_name} · {reminder_type}")
        while self.classroom_reminders_list.count() > 10:
            self.classroom_reminders_list.takeItem(self.classroom_reminders_list.count() - 1)
        self.alert_label.setText(anonymous_text)
        self.alert_timer.start(5000)

    def show_anonymous_popup(self, text: str) -> None:
        popup = QFrame(self)
        popup.setObjectName("ToastPopup")
        popup.toast_text = text
        popup.setStyleSheet(
            """
            QFrame#ToastPopup {
                background: #0f172a;
                border: 1px solid #334155;
                border-radius: 8px;
            }
            QLabel {
                background: transparent;
                color: #ffffff;
                font-size: 14px;
                font-weight: 700;
            }
            """
        )
        popup.setFixedWidth(280)
        layout = QVBoxLayout(popup)
        layout.setContentsMargins(14, 10, 14, 10)
        label = QLabel(text)
        label.setWordWrap(True)
        layout.addWidget(label)
        popup.adjustSize()
        popup.show()
        self.toast_popups.append(popup)
        while len(self.toast_popups) > 3:
            old_popup = self.toast_popups.pop(0)
            old_popup.close()
            old_popup.deleteLater()
        self._position_toast_popups()
        QTimer.singleShot(6000, lambda item=popup: self._remove_toast_popup(item))

    def popup_texts(self) -> list[str]:
        return [str(getattr(popup, "toast_text", "")) for popup in self.toast_popups]

    def _remove_toast_popup(self, popup: QFrame) -> None:
        if popup in self.toast_popups:
            self.toast_popups.remove(popup)
            popup.close()
            popup.deleteLater()
            self._position_toast_popups()

    def _position_toast_popups(self) -> None:
        margin = 18
        y = margin
        for popup in self.toast_popups:
            popup.adjustSize()
            x = max(margin, self.width() - popup.width() - margin)
            popup.move(x, y)
            y += popup.height() + 10

    def clear_anonymous_alert(self) -> None:
        self.alert_label.setText("暂无新的课堂提醒")

    def _student_name_for_event(self, payload: dict) -> str:
        if payload.get("student_name"):
            return str(payload["student_name"])
        student_id = str(payload.get("student_id") or "")
        if student_id:
            try:
                return self.server.state.get_student(student_id).name
            except ValueError:
                return student_id
        return "未知学生"

    def start_server(self) -> None:
        if not self._save_teacher_settings(show_message=False):
            return
        self._apply_settings_to_server()
        try:
            self.server.start()
        except OSError as exc:
            QMessageBox.critical(self, "启动失败", f"老师端服务启动失败：{exc}")
            return
        self._set_running_ui(True)
        self.refresh_view()

    def stop_server(self) -> None:
        self.server.stop()
        self._set_running_ui(False)
        self.refresh_view()

    def save_teacher_settings(self) -> None:
        if self._save_teacher_settings(show_message=True):
            self._apply_settings_to_server()
            self.refresh_view()

    def clear_classroom_data(self) -> None:
        answer = QMessageBox.question(
            self,
            "确认清空",
            "确认开始新班级并清空当前课堂列表吗？清空前会自动备份旧课堂记录。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            archive_path = self.server.clear_classroom_data()
        except OSError as exc:
            QMessageBox.warning(self, "归档失败", f"归档失败，未清空课堂数据：{exc}")
            return
        self._apply_settings_to_server()
        self._set_running_ui(False)
        self.refresh_view()
        if archive_path:
            QMessageBox.information(
                self,
                "已清空",
                f"旧班级课堂数据已自动备份并清空。\n备份位置：{archive_path}",
            )
        else:
            QMessageBox.information(self, "已清空", "没有旧课堂记录，已清空当前列表，可以开始新班级。")

    def _save_teacher_settings(self, show_message: bool) -> bool:
        classroom_name = self.classroom_name_input.text().strip() or "默认课堂"
        try:
            port = int(self.port_input.text().strip())
        except ValueError:
            QMessageBox.warning(self, "提示", "端口必须是数字")
            return False
        if port < 1 or port > 65535:
            QMessageBox.warning(self, "提示", "端口必须在 1 到 65535 之间")
            return False
        self.settings.classroom_name = classroom_name
        self.settings.port = port
        try:
            self.settings.save()
        except OSError as exc:
            QMessageBox.warning(self, "保存失败", f"老师端设置保存失败：{exc}")
            return False
        if show_message:
            QMessageBox.information(self, "保存成功", "老师端设置已保存。")
        return True

    def _apply_settings_to_server(self) -> None:
        if self.server.running:
            return
        self.server.classroom_name = self.settings.classroom_name
        self.server.port = self.settings.port
        self.classroom_label.setText(f"课堂：{self.server.classroom_name}")

    def _set_running_ui(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.classroom_name_input.setEnabled(not running)
        self.port_input.setEnabled(not running)
        self.save_settings_button.setEnabled(not running)

    def refresh_view(self) -> None:
        snapshot = self.server.snapshot()
        self.status_label.setText(f"服务状态：{'已启动' if snapshot['running'] else '未启动'}")
        if snapshot["running"]:
            recommended_text, other_text = self._address_texts()
            self.address_label.setText(recommended_text)
            self.other_addresses_label.setText(other_text)
        else:
            self.address_label.setText("推荐连接地址：启动课堂后显示")
            self.other_addresses_label.setText("其他地址：启动课堂后显示")
        self.online_metric.setText(f"在线人数：{snapshot['online_count']}")
        self.hand_metric.setText(f"举手人数：{snapshot['hand_count']}")
        self.unread_metric.setText(f"未读问题：{snapshot['unread_help_count']}")
        self._refresh_students(snapshot["students"])
        self._refresh_hand_queue(snapshot["hand_queue"])
        self._refresh_feedback(snapshot["feedback_summary"])
        self._refresh_help_table()

    def _refresh_students(self, students: list[dict]) -> None:
        self.students_table.setRowCount(len(students))
        for row, student in enumerate(students):
            raised = "已举手" if student.get("hand_raised_at") else "未举手"
            values = [
                student.get("name") or "",
                student.get("connection_status") or ("在线" if student.get("online") else "离线"),
                student.get("feedback") or "暂无",
                raised,
                _format_time(student.get("last_seen") or student.get("joined_at") or 0),
            ]
            for column, value in enumerate(values):
                self.students_table.setItem(row, column, QTableWidgetItem(str(value)))

    def _refresh_hand_queue(self, hand_queue: list[dict]) -> None:
        self.hand_queue_list.clear()
        if not hand_queue:
            self.hand_queue_list.addItem("暂无学生举手")
            return
        for index, item in enumerate(hand_queue, start=1):
            self.hand_queue_list.addItem(f"{index}. {item['student_name']}（{_format_time(item['raised_at'])}）")

    def _refresh_feedback(self, summary: dict[str, int]) -> None:
        self.feedback_table.setRowCount(max(len(summary), 1))
        if not summary:
            self.feedback_table.setItem(0, 0, QTableWidgetItem("暂无反馈"))
            self.feedback_table.setItem(0, 1, QTableWidgetItem("0"))
            return
        for row, (label, count) in enumerate(sorted(summary.items())):
            self.feedback_table.setItem(row, 0, QTableWidgetItem(label))
            self.feedback_table.setItem(row, 1, QTableWidgetItem(str(count)))

    def _refresh_help_table(self) -> None:
        status = self.help_filter.currentData() or "all"
        self._help_items = self.server.state.help_requests(status=status)
        self.help_table.setRowCount(len(self._help_items))
        for row, request in enumerate(self._help_items):
            handled_text = "已处理" if request.handled else "未读"
            self.help_table.setItem(row, 0, QTableWidgetItem(f"{handled_text} / {request.reply_status}"))
            self.help_table.setItem(row, 1, QTableWidgetItem(request.student_name))
            self.help_table.setItem(row, 2, QTableWidgetItem(_format_time(request.created_at)))
            text = request.text[:42] + ("..." if len(request.text) > 42 else "")
            self.help_table.setItem(row, 3, QTableWidgetItem(text or "未填写文字"))
            self.help_table.setCellWidget(row, 4, self._thumbnail_label(request))

    def _thumbnail_label(self, request) -> QLabel:
        label = QLabel("无截图")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setMinimumHeight(60)
        image_path = request.thumbnail_path or request.saved_image_path
        pixmap = QPixmap(image_path) if image_path and Path(image_path).exists() else QPixmap()
        if pixmap.isNull() and request.screenshot:
            pixmap.loadFromData(base64.b64decode(request.screenshot))
        if not pixmap.isNull():
            label.setPixmap(
                pixmap.scaled(
                    96,
                    60,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            label.setText("")
        return label

    def open_selected_help(self) -> None:
        request = self._selected_help_request()
        if request is None:
            return
        HelpDetailDialog(request, self.send_reply_to_student, self).exec()

    def send_reply_to_student(self, request_id: str, text: str) -> None:
        self.server.send_teacher_reply(request_id, text)
        self.refresh_view()

    def mark_selected_help_handled(self) -> None:
        request = self._selected_help_request()
        if request is None:
            return
        self.server.state.mark_help_handled(request.request_id)
        self.refresh_view()

    def export_records(self) -> None:
        default_name = f"课堂记录-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        path, _ = QFileDialog.getSaveFileName(self, "导出课堂记录", default_name, "JSON 文件 (*.json)")
        if not path:
            return
        payload = self.server.snapshot()
        Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        QMessageBox.information(self, "导出完成", f"课堂记录已保存到：{path}")

    def _selected_help_request(self):
        row = self.help_table.currentRow()
        if row < 0 or row >= len(self._help_items):
            return None
        return self._help_items[row]

    def _address_texts(self) -> tuple[str, str]:
        addresses = get_local_ip_addresses()
        primary = primary_local_ip_address(addresses)
        others = [address for address in addresses if address != primary and not address.startswith("127.")]
        recommended = f"推荐连接地址：{primary}:{self.server.port}"
        if not others:
            return recommended, "其他地址：无"
        display = [f"{address}:{self.server.port}" for address in others[:2]]
        suffix = f"，另有 {len(others) - 2} 个" if len(others) > 2 else ""
        return recommended, f"其他地址：{'，'.join(display)}{suffix}"

    def visible_texts(self) -> set[str]:
        texts = {
            self.title_label.text(),
            self.status_label.text(),
            self.classroom_label.text(),
            self.address_label.text(),
            self.other_addresses_label.text(),
            self.online_metric.text(),
            self.hand_metric.text(),
            self.unread_metric.text(),
            self.start_button.text(),
            self.stop_button.text(),
            "课堂名称",
            "连接状态",
            "推荐连接地址",
            "其他地址",
            "端口",
            self.save_settings_button.text(),
            self.clear_classroom_button.text(),
            "自动备份",
            self.help_filter.itemText(0),
            self.help_filter.itemText(1),
            self.help_filter.itemText(2),
            self.open_detail_button.text(),
            self.mark_handled_button.text(),
            self.export_button.text(),
            "课堂提醒",
            "弹窗提醒",
            self.alert_label.text(),
            "回复学生",
            "发送回复",
        }
        return texts

    def center_on_screen(self, available_geometry=None) -> None:
        center_window(self, available_geometry)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_toast_popups()

    def closeEvent(self, event) -> None:
        self.server.stop()
        super().closeEvent(event)
