from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
import time
import uuid
from typing import Any


@dataclass
class Student:
    student_id: str
    name: str
    address: tuple[str, int]
    joined_at: float
    last_seen: float
    client_id: str | None = None
    online: bool = True
    active_connection_id: str | None = None
    feedback: str | None = None
    hand_raised_at: float | None = None


@dataclass
class HandRaise:
    student_id: str
    student_name: str
    raised_at: float


@dataclass
class TeacherReply:
    reply_id: str
    request_id: str
    student_id: str
    client_id: str | None
    text: str
    teacher_name: str
    created_at: float
    read_by_student: bool = False


@dataclass
class HelpRequest:
    request_id: str
    student_id: str
    client_id: str | None
    student_name: str
    text: str
    created_at: float
    screenshot: str | None = None
    image_format: str | None = None
    width: int | None = None
    height: int | None = None
    saved_image_path: str | None = None
    thumbnail_path: str | None = None
    handled: bool = False
    replies: list[TeacherReply] | None = None

    @property
    def reply_status(self) -> str:
        return "已回复" if self.replies else "未回复"


class ClassroomState:
    def __init__(self) -> None:
        self._students: dict[str, Student] = {}
        self._help_requests: list[HelpRequest] = []
        self._lock = RLock()

    def join_student(
        self,
        name: str,
        address: tuple[str, int],
        client_id: str | None = None,
        connection_id: str | None = None,
    ) -> str:
        clean_name = name.strip() or "未命名学生"
        now = time.time()
        with self._lock:
            if client_id:
                existing = self._student_by_client_id(client_id)
                if existing is not None:
                    existing.name = clean_name
                    existing.address = address
                    existing.last_seen = now
                    existing.online = True
                    existing.active_connection_id = connection_id
                    return existing.student_id

            student_id = f"stu-{uuid.uuid4().hex[:8]}"
            self._students[student_id] = Student(
                student_id=student_id,
                name=clean_name,
                address=address,
                joined_at=now,
                last_seen=now,
                client_id=client_id,
                online=True,
                active_connection_id=connection_id,
            )
        return student_id

    def _student_by_client_id(self, client_id: str) -> Student | None:
        for student in self._students.values():
            if student.client_id == client_id:
                return student
        return None

    def touch_student(self, student_id: str) -> None:
        with self._lock:
            student = self._students.get(student_id)
            if student is not None:
                student.last_seen = time.time()

    def leave_student(self, student_id: str) -> None:
        self.mark_student_offline(student_id)

    def mark_student_offline(self, student_id: str, connection_id: str | None = None) -> bool:
        with self._lock:
            student = self._students.get(student_id)
            if student is None:
                return False
            if connection_id is not None and student.active_connection_id != connection_id:
                return False
            was_online = student.online
            student.online = False
            student.active_connection_id = None
            student.last_seen = time.time()
            return was_online

    def is_active_connection(self, student_id: str, connection_id: str) -> bool:
        with self._lock:
            student = self._students.get(student_id)
            return bool(student and student.online and student.active_connection_id == connection_id)

    def online_students(self) -> list[Student]:
        with self._lock:
            return sorted((student for student in self._students.values() if student.online), key=lambda item: item.joined_at)

    def get_student(self, student_id: str) -> Student:
        with self._lock:
            student = self._students.get(student_id)
            if student is None:
                raise ValueError("学生不存在或已离线")
            return student

    def raise_hand(self, student_id: str) -> bool:
        with self._lock:
            student = self.get_student(student_id)
            if student.hand_raised_at is not None:
                student.last_seen = time.time()
                return False
            student.hand_raised_at = time.time()
            student.last_seen = time.time()
            return True

    def lower_hand(self, student_id: str) -> None:
        with self._lock:
            student = self.get_student(student_id)
            student.hand_raised_at = None
            student.last_seen = time.time()

    def hand_queue(self) -> list[HandRaise]:
        with self._lock:
            raised = [
                HandRaise(
                    student_id=student.student_id,
                    student_name=student.name,
                    raised_at=student.hand_raised_at,
                )
                for student in self._students.values()
                if student.online and student.hand_raised_at is not None
            ]
        return sorted(raised, key=lambda item: item.raised_at)

    def set_feedback(self, student_id: str, feedback: str) -> None:
        clean_feedback = feedback.strip()
        if not clean_feedback:
            raise ValueError("反馈内容不能为空")
        with self._lock:
            student = self.get_student(student_id)
            student.feedback = clean_feedback
            student.last_seen = time.time()

    def feedback_summary(self) -> dict[str, int]:
        with self._lock:
            summary: dict[str, int] = {}
            for student in self._students.values():
                if student.online and student.feedback:
                    summary[student.feedback] = summary.get(student.feedback, 0) + 1
        return summary

    def add_help_request(
        self,
        student_id: str,
        text: str,
        image_payload: dict[str, Any] | None,
    ) -> HelpRequest:
        clean_text = text.strip()
        screenshot = image_payload.get("screenshot") if image_payload else None
        if not clean_text and not screenshot:
            raise ValueError("请填写文字说明或添加截图")

        with self._lock:
            student = self.get_student(student_id)
            request = HelpRequest(
                request_id=f"help-{uuid.uuid4().hex[:10]}",
                student_id=student_id,
                client_id=student.client_id,
                student_name=student.name,
                text=clean_text,
                screenshot=screenshot,
                image_format=image_payload.get("image_format") if image_payload else None,
                width=image_payload.get("width") if image_payload else None,
                height=image_payload.get("height") if image_payload else None,
                created_at=time.time(),
                replies=[],
            )
            self._help_requests.append(request)
            student.last_seen = time.time()
            return request

    def help_requests(self, status: str = "all", student_id: str | None = None) -> list[HelpRequest]:
        with self._lock:
            requests = list(self._help_requests)
            if status == "unread":
                requests = [request for request in requests if not request.handled]
            elif status == "handled":
                requests = [request for request in requests if request.handled]
            elif status != "all":
                raise ValueError("问题筛选状态必须是 all、unread 或 handled")
            if student_id:
                requests = [request for request in requests if request.student_id == student_id]
            return sorted(requests, key=lambda item: item.created_at, reverse=True)

    def unread_help_count(self) -> int:
        with self._lock:
            return sum(1 for request in self._help_requests if not request.handled)

    def mark_help_handled(self, request_id: str) -> bool:
        with self._lock:
            for request in self._help_requests:
                if request.request_id == request_id:
                    request.handled = True
                    return True
        return False

    def add_teacher_reply(
        self,
        request_id: str,
        text: str,
        teacher_name: str = "老师",
    ) -> TeacherReply:
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("回复内容不能为空")
        with self._lock:
            request = self.get_help_request(request_id)
            student = self._students.get(request.student_id)
            reply = TeacherReply(
                reply_id=f"reply-{uuid.uuid4().hex[:10]}",
                request_id=request_id,
                student_id=request.student_id,
                client_id=(student.client_id if student else self._client_id_for_request(request)),
                text=clean_text,
                teacher_name=teacher_name.strip() or "老师",
                created_at=time.time(),
            )
            if request.replies is None:
                request.replies = []
            request.replies.append(reply)
            return reply

    def get_help_request(self, request_id: str) -> HelpRequest:
        with self._lock:
            for request in self._help_requests:
                if request.request_id == request_id:
                    return request
        raise ValueError("问题不存在")

    def unread_replies_for_client(self, client_id: str) -> list[TeacherReply]:
        with self._lock:
            replies: list[TeacherReply] = []
            for request in self._help_requests:
                for reply in request.replies or []:
                    if reply.client_id == client_id and not reply.read_by_student:
                        replies.append(reply)
            return sorted(replies, key=lambda item: item.created_at)

    def mark_replies_read(self, reply_ids: list[str]) -> None:
        reply_id_set = set(reply_ids)
        with self._lock:
            for request in self._help_requests:
                for reply in request.replies or []:
                    if reply.reply_id in reply_id_set:
                        reply.read_by_student = True

    def _client_id_for_request(self, request: HelpRequest) -> str | None:
        for student in self._students.values():
            if student.student_id == request.student_id:
                return student.client_id
        if request.client_id:
            return request.client_id
        for old_request in self._help_requests:
            for reply in old_request.replies or []:
                if old_request.student_id == request.student_id and reply.client_id:
                    return reply.client_id
        return None

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            students = [
                {
                    "student_id": student.student_id,
                    "name": student.name,
                    "address": student.address,
                    "joined_at": student.joined_at,
                    "last_seen": student.last_seen,
                    "feedback": student.feedback,
                    "hand_raised_at": student.hand_raised_at,
                    "client_id": student.client_id,
                    "online": student.online,
                    "active_connection_id": student.active_connection_id,
                    "connection_status": "在线" if student.online else "离线",
                }
                for student in sorted(self._students.values(), key=lambda item: item.joined_at)
            ]
            hand_queue = [
                {
                    "student_id": item.student_id,
                    "student_name": item.student_name,
                    "raised_at": item.raised_at,
                }
                for item in self.hand_queue()
            ]
            help_requests = [
                {
                    "request_id": request.request_id,
                    "student_id": request.student_id,
                    "client_id": request.client_id,
                    "student_name": request.student_name,
                    "text": request.text,
                    "created_at": request.created_at,
                    "image_format": request.image_format,
                    "width": request.width,
                    "height": request.height,
                    "saved_image_path": request.saved_image_path,
                    "thumbnail_path": request.thumbnail_path,
                    "handled": request.handled,
                    "has_screenshot": bool(request.screenshot or request.saved_image_path),
                    "reply_status": request.reply_status,
                    "reply_count": len(request.replies or []),
                }
                for request in self.help_requests()
            ]
            feedback_summary = self.feedback_summary()
            return {
                "students": students,
                "online_count": sum(1 for student in self._students.values() if student.online),
                "hand_queue": hand_queue,
                "hand_count": len(hand_queue),
                "feedback_summary": feedback_summary,
                "help_requests": help_requests,
                "unread_help_count": sum(1 for request in self._help_requests if not request.handled),
            }
