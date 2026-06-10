from __future__ import annotations

import base64
from datetime import datetime
import math
import threading
import time

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStyle,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QMenu,
)

from classroom_hand_raise.shared.constants import (
    DEFAULT_TCP_PORT,
    FEEDBACK_COOLDOWN_SECONDS,
    FEEDBACK_OPTIONS,
    HELP_REQUEST_COOLDOWN_SECONDS,
    RAISE_HAND_COOLDOWN_SECONDS,
)
from classroom_hand_raise.shared.discovery import listen_for_classrooms, rank_local_ip_addresses
from classroom_hand_raise.shared.image_tools import compress_image_for_upload, load_image_file_for_upload
from classroom_hand_raise.shared.ui_geometry import center_window
from classroom_hand_raise.student.client import StudentClient
from classroom_hand_raise.student.settings import StudentSettings
from classroom_hand_raise.student.ui_components import apply_student_style


class StudentUiSignals(QObject):
    status = Signal(str)
    error = Signal(str)
    connected = Signal(bool)
    classrooms = Signal(list)
    send_status = Signal(str)
    teacher_reply = Signal(dict)


class StudentWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("局域网课堂互动 - 学生端")
        self.resize(780, 760)

        self.signals = StudentUiSignals()
        self.settings = StudentSettings.load()
        self.client = StudentClient(
            on_status=self.signals.status.emit,
            on_error=self.signals.error.emit,
            on_send_status=self.signals.send_status.emit,
            on_teacher_reply=self.signals.teacher_reply.emit,
        )
        self.screenshot_payload: dict | None = None
        self.force_exit = False
        self._cooldown_until: dict[str, float] = {}
        self._cooldown_groups: dict[str, list[QPushButton]] = {}

        self.title_label = QLabel("课堂互动")
        self.title_label.setProperty("class", "title")
        self.status_label = QLabel("未连接老师端，请重新连接")
        self.status_label.setProperty("class", "status")
        self.send_status_label = QLabel("发送状态：未发送")
        self.send_status_label.setProperty("class", "status")

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("请输入姓名")
        self.name_input.setText(self.settings.name)
        self.classroom_combo = QComboBox()
        self.host_input = QLineEdit(self.settings.host)
        self.port_input = QLineEdit(str(self.settings.port or DEFAULT_TCP_PORT))
        self.connect_button = QPushButton("连接老师端")
        self.disconnect_button = QPushButton("断开")
        self.disconnect_button.setObjectName("SecondaryButton")

        self.raise_button = QPushButton("举手提问")
        self.raise_button.setObjectName("MainAction")
        self.lower_button = QPushButton("取消举手")
        self.lower_button.setObjectName("MainAction")
        self.lower_button.setProperty("class", "secondary")
        self.feedback_buttons: list[QPushButton] = []

        self.help_text = QTextEdit()
        self.help_text.setPlaceholderText("写下你不懂的点，例如：第三步循环条件没听懂")
        self.select_image_button = QPushButton("选择截图图片")
        self.select_image_button.setObjectName("SecondaryButton")
        self.paste_image_button = QPushButton("粘贴截图")
        self.paste_image_button.setObjectName("SecondaryButton")
        self.clear_image_button = QPushButton("清除截图")
        self.clear_image_button.setObjectName("SecondaryButton")
        self.send_help_button = QPushButton("发送给老师")
        self.preview_label = QLabel("暂无截图")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(180)
        self.preview_label.setStyleSheet("border: 1px solid #d0d7de; background: #ffffff; color: #64748b;")
        self.reply_list = QListWidget()
        self.reply_list.addItem("暂无老师回复")

        self._build_ui()
        self._cooldown_groups = {
            "raise_hand": [self.raise_button],
            "feedback": self.feedback_buttons,
            "help_request": [self.send_help_button],
        }
        for button in [self.raise_button, self.send_help_button, *self.feedback_buttons]:
            button.setProperty("defaultText", button.text())
        self._wire_events()
        apply_student_style(self)

        self.cooldown_timer = QTimer(self)
        self.cooldown_timer.timeout.connect(self._refresh_cooldown_buttons)

        self._set_connected(False)
        self._setup_tray()

        self.discovery_timer = QTimer(self)
        self.discovery_timer.timeout.connect(self.refresh_classrooms)
        self.discovery_timer.start(5000)
        self.refresh_classrooms()

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.addWidget(self._build_top_bar())
        layout.addWidget(self._build_actions())
        layout.addWidget(self._build_help_box(), stretch=1)
        layout.addWidget(self._build_reply_box())
        self.setCentralWidget(root)

    def _build_top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        layout = QGridLayout(bar)
        layout.addWidget(self.title_label, 0, 0)
        layout.addWidget(self.status_label, 0, 1, 1, 3)
        layout.addWidget(QLabel("姓名"), 1, 0)
        layout.addWidget(self.name_input, 1, 1)
        layout.addWidget(QLabel("发现课堂"), 2, 0)
        layout.addWidget(self.classroom_combo, 2, 1, 1, 3)
        layout.addWidget(QLabel("老师 IP"), 3, 0)
        layout.addWidget(self.host_input, 3, 1)
        layout.addWidget(QLabel("端口"), 3, 2)
        layout.addWidget(self.port_input, 3, 3)
        layout.addWidget(self.connect_button, 1, 4)
        layout.addWidget(self.disconnect_button, 2, 4)
        layout.setColumnStretch(1, 1)
        return bar

    def _build_actions(self) -> QWidget:
        box = QGroupBox("课堂操作")
        layout = QVBoxLayout(box)
        hand_layout = QHBoxLayout()
        hand_layout.addWidget(self.raise_button)
        hand_layout.addWidget(self.lower_button)
        layout.addLayout(hand_layout)

        feedback_layout = QHBoxLayout()
        for label in FEEDBACK_OPTIONS:
            button = QPushButton(label)
            button.setObjectName("FeedbackButton")
            self.feedback_buttons.append(button)
            feedback_layout.addWidget(button)
        layout.addLayout(feedback_layout)
        return box

    def _build_help_box(self) -> QWidget:
        box = QGroupBox("上传不懂点")
        layout = QVBoxLayout(box)
        layout.addWidget(self.help_text)
        layout.addWidget(self.preview_label)
        layout.addWidget(self.send_status_label)
        actions = QHBoxLayout()
        actions.addWidget(self.select_image_button)
        actions.addWidget(self.paste_image_button)
        actions.addWidget(self.clear_image_button)
        actions.addWidget(self.send_help_button)
        layout.addLayout(actions)
        return box

    def _build_reply_box(self) -> QWidget:
        box = QGroupBox("老师回复")
        layout = QVBoxLayout(box)
        layout.addWidget(self.reply_list)
        return box

    def _wire_events(self) -> None:
        self.connect_button.clicked.connect(self.connect_to_teacher)
        self.disconnect_button.clicked.connect(self.disconnect_from_teacher)
        self.raise_button.clicked.connect(
            lambda: self._safe_send(
                self.client.raise_hand,
                "已举手",
                cooldown_key="raise_hand",
                cooldown_seconds=RAISE_HAND_COOLDOWN_SECONDS,
            )
        )
        self.lower_button.clicked.connect(lambda: self._safe_send(self.client.lower_hand, "已取消举手"))
        for button in self.feedback_buttons:
            button.clicked.connect(
                lambda checked=False, text=button.text(): self._safe_send(
                    lambda: self.client.send_feedback(text),
                    f"已发送反馈：{text}",
                    cooldown_key="feedback",
                    cooldown_seconds=FEEDBACK_COOLDOWN_SECONDS,
                )
            )
        self.select_image_button.clicked.connect(self.select_screenshot_file)
        self.paste_image_button.clicked.connect(self.paste_screenshot)
        self.clear_image_button.clicked.connect(self.clear_screenshot)
        self.send_help_button.clicked.connect(self.send_help_request)
        self.classroom_combo.currentIndexChanged.connect(self.apply_selected_classroom)

        self.signals.status.connect(self.update_connection_status)
        self.signals.error.connect(self.show_error)
        self.signals.connected.connect(self._set_connected)
        self.signals.classrooms.connect(self.update_classroom_combo)
        self.signals.send_status.connect(self.update_send_status)
        self.signals.teacher_reply.connect(self.add_teacher_reply)

    def connect_to_teacher(self) -> None:
        host = self.host_input.text().strip() or "127.0.0.1"
        try:
            port = int(self.port_input.text().strip())
        except ValueError:
            self.show_error("端口必须是数字")
            return
        name = self.name_input.text().strip() or "未命名学生"

        self.status_label.setText("正在连接老师端...")
        self.connect_button.setEnabled(False)

        def worker() -> None:
            try:
                self.client.connect(host, port, name, self.settings.client_id)
                self.settings.name = name
                self.settings.host = host
                self.settings.port = port
                self.settings.save()
                self.signals.connected.emit(True)
            except Exception as exc:
                self.signals.error.emit(f"连接失败：{exc}")
                self.signals.connected.emit(False)

        threading.Thread(target=worker, daemon=True).start()

    def disconnect_from_teacher(self) -> None:
        self.client.disconnect()
        self.status_label.setText("未连接老师端，请重新连接")
        self._set_connected(False)

    def select_screenshot_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择截图图片",
            "",
            "截图图片 (*.png *.jpg *.jpeg *.webp)",
        )
        if not path:
            return
        try:
            self._set_screenshot_payload(load_image_file_for_upload(path))
        except ValueError as exc:
            self.show_error(str(exc))

    def paste_screenshot(self) -> None:
        image = QApplication.clipboard().image()
        if image.isNull():
            self.show_error("剪贴板中没有可粘贴的截图图片")
            return
        byte_array = QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        try:
            self._set_screenshot_payload(compress_image_for_upload(bytes(byte_array)))
        except ValueError as exc:
            self.show_error(str(exc))

    def _set_screenshot_payload(self, payload: dict) -> None:
        self.screenshot_payload = payload
        preview = QPixmap()
        preview.loadFromData(base64.b64decode(self.screenshot_payload["screenshot"]))
        self.preview_label.setPixmap(
            preview.scaled(
                560,
                180,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.preview_label.setText("")
        size_kb = int(self.screenshot_payload.get("byte_size", 0) / 1024)
        self.update_send_status(f"截图已准备（约 {size_kb} KB），确认后可发送")

    def clear_screenshot(self) -> None:
        self.screenshot_payload = None
        self.preview_label.clear()
        self.preview_label.setText("暂无截图")
        self.update_send_status("未发送")

    def send_help_request(self) -> None:
        text = self.help_text.toPlainText().strip()
        if not text and not self.screenshot_payload:
            self.show_error("请填写文字说明或添加截图")
            return
        if self.screenshot_payload:
            answer = QMessageBox.question(
                self,
                "确认发送",
                "确认把当前文字和截图发送给老师吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            self.client.send_help_request(text, self.screenshot_payload)
        except Exception as exc:
            self.show_error(str(exc))
            self.update_send_status("发送失败，可修改后重试")
            return
        self.help_text.clear()
        self.clear_screenshot()
        self.update_send_status("老师已收到")
        self._start_cooldown("help_request", HELP_REQUEST_COOLDOWN_SECONDS)

    def refresh_classrooms(self) -> None:
        def worker() -> None:
            try:
                classrooms = listen_for_classrooms(timeout=0.4)
            except OSError:
                classrooms = []
            self.signals.classrooms.emit(classrooms)

        threading.Thread(target=worker, daemon=True).start()

    def update_classroom_combo(self, classrooms: list) -> None:
        current = self.classroom_combo.currentData()
        self.classroom_combo.blockSignals(True)
        self.classroom_combo.clear()
        self.classroom_combo.addItem("手动输入老师 IP", None)
        for classroom in classrooms:
            address = self._preferred_address(classroom)
            label = f"{classroom['classroom_name']} · {address}:{classroom['tcp_port']}"
            self.classroom_combo.addItem(label, classroom)
        if current:
            for index in range(self.classroom_combo.count()):
                data = self.classroom_combo.itemData(index)
                if data and data.get("source_host") == current.get("source_host") and data.get("tcp_port") == current.get("tcp_port"):
                    self.classroom_combo.setCurrentIndex(index)
                    break
        self.classroom_combo.blockSignals(False)

    def apply_selected_classroom(self) -> None:
        classroom = self.classroom_combo.currentData()
        if not classroom:
            return
        self.host_input.setText(self._preferred_address(classroom))
        self.port_input.setText(str(classroom["tcp_port"]))

    def update_send_status(self, text: str) -> None:
        self.send_status_label.setText(f"发送状态：{text}")

    def update_connection_status(self, text: str) -> None:
        self.status_label.setText(self._friendly_connection_text(text))

    def add_teacher_reply(self, message: dict) -> None:
        if self.reply_list.count() == 1 and self.reply_list.item(0).text() == "暂无老师回复":
            self.reply_list.clear()
        created_at = float(message.get("created_at") or 0)
        time_text = datetime.fromtimestamp(created_at).strftime("%H:%M:%S") if created_at else "刚刚"
        teacher_name = str(message.get("teacher_name") or "老师")
        request_id = str(message.get("request_id") or "未知问题")
        text = str(message.get("text") or "")
        self.reply_list.insertItem(0, f"{time_text} · {teacher_name}回复 {request_id}：{text}")
        self.status_label.setText("收到老师回复，请查看下方列表")
        if self.tray_icon and self.tray_icon.isVisible():
            self.tray_icon.showMessage("收到老师回复", text[:80] or "老师已回复你的问题")

    def _preferred_address(self, classroom: dict) -> str:
        source_host = str(classroom.get("source_host") or "")
        if source_host and not source_host.startswith("127."):
            return source_host
        for address in rank_local_ip_addresses(classroom.get("addresses", [])):
            if not str(address).startswith("127."):
                return str(address)
        return source_host or "127.0.0.1"

    def _safe_send(
        self,
        action,
        success_text: str,
        cooldown_key: str | None = None,
        cooldown_seconds: int = 0,
    ) -> None:
        try:
            action()
        except Exception as exc:
            self.show_error(str(exc))
            return
        self.status_label.setText(success_text)
        if cooldown_key and cooldown_seconds > 0:
            self._start_cooldown(cooldown_key, cooldown_seconds)

    def _start_cooldown(self, key: str, seconds: int) -> None:
        self._cooldown_until[key] = time.monotonic() + max(0, seconds)
        self._refresh_cooldown_buttons()
        if not self.cooldown_timer.isActive():
            self.cooldown_timer.start(250)

    def _refresh_cooldown_buttons(self) -> None:
        now = time.monotonic()
        any_active = False
        for key, buttons in self._cooldown_groups.items():
            remaining = max(0, math.ceil(self._cooldown_until.get(key, 0) - now))
            active = remaining > 0
            any_active = any_active or active
            for button in buttons:
                default_text = str(button.property("defaultText") or button.text())
                if active:
                    button.setText(f"请稍候 {remaining} 秒")
                    button.setEnabled(False)
                else:
                    button.setText(default_text)
                    button.setEnabled(self.client.connected)
        if not any_active and self.cooldown_timer.isActive():
            self.cooldown_timer.stop()

    def show_error(self, text: str) -> None:
        friendly_text = self._friendly_connection_text(text)
        self.status_label.setText(friendly_text)
        if self._is_background_reconnect_error(text):
            return
        QMessageBox.warning(self, "提示", friendly_text)

    def _friendly_connection_text(self, text: str) -> str:
        if self._is_background_reconnect_error(text):
            return "老师端已断开，正在后台重连。请等待老师重新启动课堂。"
        if text.startswith("连接失败") and self._looks_like_connection_refused(text):
            return "连接失败：老师端未启动或拒绝连接，请确认老师端已点击“启动课堂”。"
        return text

    def _is_background_reconnect_error(self, text: str) -> bool:
        return text.startswith("重连失败")

    def _looks_like_connection_refused(self, text: str) -> bool:
        markers = ("WinError 10061", "Errno 10061", "积极拒绝", "Connection refused")
        return any(marker in text for marker in markers)

    def _set_connected(self, connected: bool) -> None:
        self.connect_button.setEnabled(not connected)
        self.disconnect_button.setEnabled(connected)
        for button in [
            self.raise_button,
            self.lower_button,
            self.select_image_button,
            self.paste_image_button,
            self.clear_image_button,
            self.send_help_button,
        ]:
            button.setEnabled(connected)
        for button in self.feedback_buttons:
            button.setEnabled(connected)
        if not connected:
            self._cooldown_until.clear()
            self.status_label.setText("未连接老师端，请重新连接")
        self._refresh_cooldown_buttons()

    def _setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = None
            return
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
        menu = QMenu()
        show_action = QAction("显示窗口", self)
        quit_action = QAction("退出", self)
        show_action.triggered.connect(self.showNormal)
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(show_action)
        menu.addAction(quit_action)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()

    def visible_texts(self) -> set[str]:
        texts = {
            "连接课堂",
            "上传不懂点",
            self.title_label.text(),
            self.status_label.text(),
            self.send_status_label.text(),
            self.connect_button.text(),
            self.disconnect_button.text(),
            self.raise_button.text(),
            self.lower_button.text(),
            self.select_image_button.text(),
            self.paste_image_button.text(),
            self.clear_image_button.text(),
            self.send_help_button.text(),
            self.classroom_combo.itemText(0),
            "老师回复",
        }
        texts.update(button.text() for button in self.feedback_buttons)
        return texts

    def center_on_screen(self, available_geometry=None) -> None:
        center_window(self, available_geometry)

    def quit_app(self) -> None:
        self.force_exit = True
        self.client.disconnect()
        QApplication.instance().quit()

    def closeEvent(self, event) -> None:
        if self.tray_icon and not self.force_exit:
            event.ignore()
            self.hide()
            self.tray_icon.showMessage("局域网课堂互动", "学生端已最小化到托盘")
            return
        self.client.disconnect()
        super().closeEvent(event)
