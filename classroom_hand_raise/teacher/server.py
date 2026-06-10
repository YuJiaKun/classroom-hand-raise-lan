from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
import shutil
import socket
import threading
import time
import uuid
from typing import Any, Callable

from classroom_hand_raise.shared.classroom import ClassroomState
from classroom_hand_raise.shared.constants import DEFAULT_CLASSROOM_NAME, DEFAULT_TCP_PORT
from classroom_hand_raise.shared.discovery import DiscoveryBroadcaster
from classroom_hand_raise.shared.protocol import ProtocolError, read_frame, write_frame
from classroom_hand_raise.shared.rate_limiter import (
    ACTION_FEEDBACK,
    ACTION_HELP_REQUEST,
    ACTION_RAISE_HAND,
    InteractionRateLimiter,
)
from classroom_hand_raise.shared.storage import SessionStorage


EventCallback = Callable[[str, dict[str, Any]], None]


class TeacherServer:
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = DEFAULT_TCP_PORT,
        data_dir: Path | str = Path("data"),
        classroom_name: str = DEFAULT_CLASSROOM_NAME,
        enable_discovery: bool = True,
        on_event: EventCallback | None = None,
        time_func: Callable[[], float] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.classroom_name = classroom_name
        self.enable_discovery = enable_discovery
        self.on_event = on_event
        self.state = ClassroomState()
        self.storage = SessionStorage(data_dir)
        self.rate_limiter = InteractionRateLimiter(time_func=time_func)
        self._has_started = False

        self._server_socket: socket.socket | None = None
        self._accept_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._clients: set[socket.socket] = set()
        self._clients_lock = threading.Lock()
        self._client_threads: set[threading.Thread] = set()
        self._client_threads_lock = threading.Lock()
        self._student_streams: dict[str, Any] = {}
        self._stream_lock = threading.Lock()
        self._broadcaster: DiscoveryBroadcaster | None = None

    @property
    def running(self) -> bool:
        return self._server_socket is not None and not self._stop_event.is_set()

    def start(self) -> None:
        if self.running:
            return

        self._stop_event.clear()
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((self.host, self.port))
        server_socket.listen()
        server_socket.settimeout(0.2)
        self.port = int(server_socket.getsockname()[1])
        self._server_socket = server_socket
        self._has_started = True

        self._accept_thread = threading.Thread(target=self._accept_loop, name="TeacherServerAccept", daemon=True)
        self._accept_thread.start()

        if self.enable_discovery:
            self._broadcaster = DiscoveryBroadcaster(self.classroom_name, self.port)
            self._broadcaster.start()

        self._record_event("server_started", {"host": self.host, "port": self.port})

    def stop(self) -> None:
        if not self._has_started and self._server_socket is None:
            return

        self._stop_event.set()

        if self._broadcaster:
            self._broadcaster.stop()
            self._broadcaster = None

        if self._server_socket:
            try:
                self._server_socket.close()
            except OSError:
                pass
            self._server_socket = None

        with self._clients_lock:
            clients = list(self._clients)
            self._clients.clear()
        for client in clients:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                client.close()
            except OSError:
                pass

        if self._accept_thread:
            self._accept_thread.join(timeout=1)
            self._accept_thread = None

        with self._client_threads_lock:
            client_threads = list(self._client_threads)
        for thread in client_threads:
            if thread is not threading.current_thread():
                thread.join(timeout=1)

        self._record_event("server_stopped", {"port": self.port})
        self._has_started = False

    def snapshot(self) -> dict[str, Any]:
        state_snapshot = self.state.snapshot()
        state_snapshot.update(
            {
                "running": self.running,
                "classroom_name": self.classroom_name,
                "host": self.host,
                "port": self.port,
                "session_id": self.storage.session_id,
                "session_dir": str(self.storage.session_dir),
            }
        )
        return state_snapshot

    def send_teacher_reply(self, request_id: str, text: str, teacher_name: str = "老师") -> dict[str, Any]:
        reply = self.state.add_teacher_reply(request_id, text, teacher_name)
        payload = self._reply_payload(reply)
        self._record_event("teacher_reply", payload)
        if reply.client_id:
            with self._stream_lock:
                stream = self._student_streams.get(reply.client_id)
            if stream is not None:
                try:
                    write_frame(stream, payload)
                except (OSError, ProtocolError):
                    with self._stream_lock:
                        if self._student_streams.get(reply.client_id) is stream:
                            self._student_streams.pop(reply.client_id, None)
        return payload

    def clear_classroom_data(self) -> Path | None:
        data_dir = self.storage.data_dir
        self.stop()
        archive_path = self.storage.archive_class_sessions("before-clear")
        self.state = ClassroomState()
        self.rate_limiter.reset()
        with self._stream_lock:
            self._student_streams.clear()
        class_sessions_dir = data_dir / "class_sessions"
        if class_sessions_dir.exists():
            shutil.rmtree(class_sessions_dir)
        self.storage = SessionStorage(data_dir)
        return archive_path

    def _accept_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                assert self._server_socket is not None
                client, address = self._server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            with self._clients_lock:
                self._clients.add(client)
            thread = threading.Thread(
                target=self._client_loop,
                args=(client, address),
                name=f"StudentClient-{address[0]}:{address[1]}",
                daemon=True,
            )
            with self._client_threads_lock:
                self._client_threads.add(thread)
            thread.start()

    def _client_loop(self, client: socket.socket, address: tuple[str, int]) -> None:
        student_id: str | None = None
        client_id: str | None = None
        connection_id = f"conn-{uuid.uuid4().hex[:12]}"
        stream = client.makefile("rwb")
        try:
            while not self._stop_event.is_set():
                message = read_frame(stream)
                message_type = message.get("type")
                if message_type == "join":
                    student_id, client_id = self._handle_join(stream, message, address, connection_id)
                    continue

                resolved_student_id = str(message.get("student_id") or student_id or "")
                if not resolved_student_id:
                    self._send_error(stream, "请先加入课堂")
                    continue
                if student_id and not self.state.is_active_connection(student_id, connection_id):
                    break

                self._handle_student_message(stream, resolved_student_id, message, connection_id)
        except (OSError, ProtocolError):
            pass
        finally:
            try:
                stream.close()
            except OSError:
                pass
            try:
                client.close()
            except OSError:
                pass
            with self._clients_lock:
                self._clients.discard(client)
            if client_id:
                with self._stream_lock:
                    if self._student_streams.get(client_id) is stream:
                        self._student_streams.pop(client_id, None)
            if student_id and self.state.mark_student_offline(student_id, connection_id=connection_id):
                self._record_event("student_left", {"student_id": student_id})
            with self._client_threads_lock:
                self._client_threads.discard(threading.current_thread())

    def _handle_join(
        self,
        stream: Any,
        message: dict[str, Any],
        address: tuple[str, int],
        connection_id: str,
    ) -> tuple[str, str | None]:
        name = str(message.get("name") or "未命名学生")
        client_id = str(message.get("client_id") or "") or None
        student_id = self.state.join_student(name, address, client_id=client_id, connection_id=connection_id)
        pending_replies = []
        if client_id:
            with self._stream_lock:
                self._student_streams[client_id] = stream
            pending = self.state.unread_replies_for_client(client_id)
            pending_replies = [self._reply_payload(reply) for reply in pending]
        response = {
            "type": "join_ack",
            "student_id": student_id,
            "classroom_name": self.classroom_name,
            "server_time": time.time(),
            "tcp_port": self.port,
            "pending_replies": pending_replies,
        }
        write_frame(stream, response)
        self._record_event("student_joined", {"student_id": student_id, "client_id": client_id, "name": name, "address": address})
        return student_id, client_id

    def _handle_student_message(self, stream: Any, student_id: str, message: dict[str, Any], connection_id: str) -> None:
        message_type = message.get("type")
        try:
            if message_type == "raise_hand":
                student = self.state.get_student(student_id)
                if student.hand_raised_at is not None:
                    self._send_error(stream, "你已经举手了，请等待老师处理")
                    return
                if not self._check_rate_limit(stream, student_id, ACTION_RAISE_HAND):
                    return
                if self.state.raise_hand(student_id):
                    self._record_event("raise_hand", {"student_id": student_id})
            elif message_type == "lower_hand":
                self.state.lower_hand(student_id)
                self._record_event("lower_hand", {"student_id": student_id})
            elif message_type == "feedback":
                if not self._check_rate_limit(stream, student_id, ACTION_FEEDBACK):
                    return
                feedback = str(message.get("feedback") or "")
                self.state.set_feedback(student_id, feedback)
                self._record_event("feedback", {"student_id": student_id, "feedback": feedback})
            elif message_type == "help_request":
                if not self._check_rate_limit(stream, student_id, ACTION_HELP_REQUEST):
                    return
                request = self._handle_help_request(student_id, message)
                self._record_event("help_request", request)
            elif message_type == "reply_read":
                self._handle_reply_read(message)
            elif message_type == "heartbeat":
                self.state.touch_student(student_id)
                write_frame(stream, {"type": "heartbeat_ack", "server_time": time.time()})
            elif message_type == "leave":
                if self.state.mark_student_offline(student_id, connection_id=connection_id):
                    self._record_event("student_left", {"student_id": student_id})
            else:
                self._send_error(stream, "无法识别的消息类型")
        except ValueError as exc:
            self._send_error(stream, str(exc))

    def _handle_reply_read(self, message: dict[str, Any]) -> None:
        reply_ids = message.get("reply_ids") or []
        if not isinstance(reply_ids, list):
            raise ValueError("已读回执格式不正确")
        clean_reply_ids = [str(reply_id) for reply_id in reply_ids if str(reply_id).strip()]
        self.state.mark_replies_read(clean_reply_ids)

    def _check_rate_limit(self, stream: Any, student_id: str, action: str) -> bool:
        identity = self._rate_limit_identity(student_id)
        result = self.rate_limiter.check(identity, action)
        if result.allowed:
            return True
        self._send_error(stream, result.message)
        return False

    def _rate_limit_identity(self, student_id: str) -> str:
        student = self.state.get_student(student_id)
        return student.client_id or student.student_id

    def _handle_help_request(self, student_id: str, message: dict[str, Any]):
        image_payload = None
        if message.get("screenshot"):
            image_payload = {
                "screenshot": message.get("screenshot"),
                "image_format": message.get("image_format") or "jpeg",
                "width": message.get("width"),
                "height": message.get("height"),
            }

        request = self.state.add_help_request(student_id, str(message.get("text") or ""), image_payload)
        if request.screenshot:
            saved = self.storage.save_help_image(
                request.request_id,
                request.screenshot,
                request.image_format or "jpeg",
            )
            request.saved_image_path = str(saved["image_path"])
            request.thumbnail_path = str(saved["thumbnail_path"])
        return request

    def _send_error(self, stream: Any, text: str) -> None:
        try:
            write_frame(stream, {"type": "error", "message": text})
        except (OSError, ProtocolError):
            pass

    def _record_event(self, event_type: str, payload: Any) -> None:
        jsonable = self._jsonable(payload)
        self.storage.append_event(event_type, jsonable if isinstance(jsonable, dict) else {"value": jsonable})
        if self.on_event:
            self.on_event(event_type, jsonable if isinstance(jsonable, dict) else {"value": jsonable})

    def _reply_payload(self, reply) -> dict[str, Any]:
        return {
            "type": "teacher_reply",
            "reply_id": reply.reply_id,
            "request_id": reply.request_id,
            "text": reply.text,
            "teacher_name": reply.teacher_name,
            "created_at": reply.created_at,
        }

    def _jsonable(self, payload: Any) -> Any:
        if is_dataclass(payload):
            payload = asdict(payload)
        if isinstance(payload, dict):
            clean = {}
            for key, value in payload.items():
                if key == "screenshot" and value:
                    clean[key] = "<saved>"
                else:
                    clean[key] = self._jsonable(value)
            return clean
        if isinstance(payload, (list, tuple)):
            return [self._jsonable(item) for item in payload]
        if isinstance(payload, Path):
            return str(payload)
        return payload
