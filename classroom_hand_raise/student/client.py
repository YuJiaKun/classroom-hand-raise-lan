from __future__ import annotations

import socket
import threading
import time
from typing import Any, Callable

from classroom_hand_raise.shared.constants import (
    DEFAULT_TCP_PORT,
    HEARTBEAT_INTERVAL_SECONDS,
    RECONNECT_INTERVAL_SECONDS,
)
from classroom_hand_raise.shared.protocol import ProtocolError, read_frame, write_frame


StatusCallback = Callable[[str], None]
MessageCallback = Callable[[dict[str, Any]], None]


class StudentClient:
    def __init__(
        self,
        reconnect_enabled: bool = True,
        on_status: StatusCallback | None = None,
        on_message: MessageCallback | None = None,
        on_error: StatusCallback | None = None,
        on_send_status: StatusCallback | None = None,
        on_teacher_reply: MessageCallback | None = None,
    ) -> None:
        self.reconnect_enabled = reconnect_enabled
        self.on_status = on_status
        self.on_message = on_message
        self.on_error = on_error
        self.on_send_status = on_send_status
        self.on_teacher_reply = on_teacher_reply

        self.host = "127.0.0.1"
        self.port = DEFAULT_TCP_PORT
        self.name = ""
        self.client_id: str | None = None
        self.student_id: str | None = None

        self._socket: socket.socket | None = None
        self._stream: Any = None
        self._send_lock = threading.Lock()
        self._connect_lock = threading.RLock()
        self._reconnect_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._listener_thread: threading.Thread | None = None
        self._heartbeat_thread: threading.Thread | None = None

    @property
    def connected(self) -> bool:
        return self._socket is not None and self.student_id is not None and not self._stop_event.is_set()

    def connect(self, host: str, port: int, name: str, client_id: str | None = None) -> dict[str, Any]:
        with self._connect_lock:
            self.disconnect()
            self._stop_event.clear()
            response = self._open_connection(host, port, name, client_id)
            self._start_background_threads()
            return response

    def _open_connection(self, host: str, port: int, name: str, client_id: str | None = None) -> dict[str, Any]:
        self.host = host.strip() or "127.0.0.1"
        self.port = int(port)
        self.name = name.strip() or "未命名学生"
        self.client_id = client_id

        sock = socket.create_connection((self.host, self.port), timeout=5)
        stream = sock.makefile("rwb")
        try:
            join_message = {"type": "join", "name": self.name, "client_version": "0.1.0"}
            if client_id:
                join_message["client_id"] = client_id
            write_frame(stream, join_message)
            response = read_frame(stream)
            if response.get("type") != "join_ack":
                message = str(response.get("message") or "老师端未接受连接")
                raise ConnectionError(message)
        except Exception:
            try:
                stream.close()
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
            raise

        self._socket = sock
        self._stream = stream
        self.student_id = str(response["student_id"])
        self._emit_status("已连接老师端")
        for reply in response.get("pending_replies") or []:
            self._emit_teacher_reply(reply)
        return response

    def connect_async(self, host: str, port: int, name: str, client_id: str | None = None) -> threading.Thread:
        thread = threading.Thread(target=self._connect_async_target, args=(host, port, name, client_id), daemon=True)
        thread.start()
        return thread

    def disconnect(self) -> None:
        with self._connect_lock:
            self._stop_event.set()
            self._close_transport(send_leave=True)

    def _close_transport(self, send_leave: bool) -> None:
        if self._stream is not None:
            try:
                if send_leave and self.student_id:
                    self._send({"type": "leave"}, emit_status=False)
            except Exception:
                pass
            try:
                self._stream.close()
            except OSError:
                pass
            self._stream = None

        if self._socket is not None:
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None

        self.student_id = None

    def raise_hand(self) -> None:
        self._send({"type": "raise_hand"})

    def lower_hand(self) -> None:
        self._send({"type": "lower_hand"})

    def send_feedback(self, feedback: str) -> None:
        self._send({"type": "feedback", "feedback": feedback})

    def send_help_request(self, text: str, image_payload: dict[str, Any] | None) -> None:
        message: dict[str, Any] = {"type": "help_request", "text": text}
        if image_payload:
            message.update(image_payload)
        self._send(message)

    def _connect_async_target(self, host: str, port: int, name: str, client_id: str | None = None) -> None:
        try:
            self.connect(host, port, name, client_id)
        except Exception as exc:
            self._emit_error(f"连接失败：{exc}")

    def _start_background_threads(self) -> None:
        self._listener_thread = threading.Thread(target=self._listen_loop, name="StudentClientListener", daemon=True)
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, name="StudentClientHeartbeat", daemon=True)
        self._listener_thread.start()
        self._heartbeat_thread.start()

    def _send(self, message: dict[str, Any], emit_status: bool = True) -> None:
        if not self._stream or not self.student_id:
            if emit_status:
                self._emit_send_status("发送失败")
            raise ConnectionError("未连接老师端，请重新连接")
        message.setdefault("student_id", self.student_id)
        if emit_status:
            self._emit_send_status("发送中")
        try:
            with self._send_lock:
                write_frame(self._stream, message)
        except Exception:
            if emit_status:
                self._emit_send_status("发送失败")
            raise
        if emit_status:
            self._emit_send_status("发送成功")

    def _listen_loop(self) -> None:
        while not self._stop_event.is_set() and self._stream is not None:
            try:
                message = read_frame(self._stream)
            except (OSError, ProtocolError):
                self._handle_disconnect()
                break
            if message.get("type") == "error":
                self._emit_error(str(message.get("message") or "老师端返回错误"))
            elif message.get("type") == "teacher_reply":
                self._emit_teacher_reply(message)
            elif self.on_message:
                self.on_message(message)

    def _heartbeat_loop(self) -> None:
        while not self._stop_event.wait(HEARTBEAT_INTERVAL_SECONDS):
            try:
                self._send({"type": "heartbeat"}, emit_status=False)
            except Exception:
                self._handle_disconnect()
                break

    def _handle_disconnect(self) -> None:
        if not self._reconnect_lock.acquire(blocking=False):
            return
        try:
            self._handle_disconnect_locked()
        finally:
            self._reconnect_lock.release()

    def _handle_disconnect_locked(self) -> None:
        if self._stop_event.is_set():
            return
        self._emit_status("已断开，正在尝试重连")
        old_host, old_port, old_name = self.host, self.port, self.name
        with self._connect_lock:
            self._close_transport(send_leave=False)
        if not self.reconnect_enabled:
            self._emit_status("已断开")
            return

        while not self._stop_event.wait(RECONNECT_INTERVAL_SECONDS):
            try:
                with self._connect_lock:
                    if self._stop_event.is_set():
                        return
                    self._open_connection(old_host, old_port, old_name, self.client_id)
                    self._start_background_threads()
                return
            except Exception:
                self._emit_status("老师端已断开，正在后台重连。请等待老师重新启动课堂。")

    def _emit_status(self, text: str) -> None:
        if self.on_status:
            self.on_status(text)

    def _emit_error(self, text: str) -> None:
        if self.on_error:
            self.on_error(text)

    def _emit_send_status(self, text: str) -> None:
        if self.on_send_status:
            self.on_send_status(text)

    def _emit_teacher_reply(self, message: dict[str, Any]) -> None:
        if self.on_teacher_reply:
            self.on_teacher_reply(message)
        reply_id = str(message.get("reply_id") or "")
        if reply_id:
            self._ack_teacher_replies([reply_id])

    def _ack_teacher_replies(self, reply_ids: list[str]) -> None:
        if not self._stream or not self.student_id:
            return
        clean_reply_ids = [reply_id for reply_id in reply_ids if reply_id]
        if not clean_reply_ids:
            return
        try:
            with self._send_lock:
                write_frame(
                    self._stream,
                    {
                        "type": "reply_read",
                        "student_id": self.student_id,
                        "reply_ids": clean_reply_ids,
                    },
                )
        except Exception:
            pass
