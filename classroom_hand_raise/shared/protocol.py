from __future__ import annotations

import json
import struct
from typing import BinaryIO

from .constants import MAX_FRAME_BYTES


class ProtocolError(Exception):
    """网络消息帧或 JSON 内容不符合协议。"""


_LENGTH_PREFIX = struct.Struct(">I")


def encode_frame(message: dict) -> bytes:
    if not isinstance(message, dict):
        raise ProtocolError("消息必须是 JSON 对象")

    try:
        payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProtocolError(f"消息无法编码为 JSON：{exc}") from exc

    if len(payload) > MAX_FRAME_BYTES:
        raise ProtocolError("消息过大，无法发送")

    return _LENGTH_PREFIX.pack(len(payload)) + payload


def decode_frame(frame: bytes) -> dict:
    if len(frame) < _LENGTH_PREFIX.size:
        raise ProtocolError("消息帧不完整")

    expected_length = _LENGTH_PREFIX.unpack(frame[: _LENGTH_PREFIX.size])[0]
    if expected_length > MAX_FRAME_BYTES:
        raise ProtocolError("消息过大，已拒绝")

    payload = frame[_LENGTH_PREFIX.size :]
    if len(payload) != expected_length:
        raise ProtocolError("消息长度不匹配")

    try:
        message = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"消息不是有效 JSON：{exc}") from exc

    if not isinstance(message, dict):
        raise ProtocolError("消息必须是 JSON 对象")

    return message


def read_exact(stream: BinaryIO, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        chunk = stream.read(remaining)
        if not chunk:
            raise ProtocolError("连接已断开")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_frame(stream: BinaryIO) -> dict:
    header = read_exact(stream, _LENGTH_PREFIX.size)
    expected_length = _LENGTH_PREFIX.unpack(header)[0]
    if expected_length > MAX_FRAME_BYTES:
        raise ProtocolError("消息过大，已拒绝")
    payload = read_exact(stream, expected_length)
    return decode_frame(header + payload)


def write_frame(stream: BinaryIO, message: dict) -> None:
    stream.write(encode_frame(message))
    flush = getattr(stream, "flush", None)
    if flush is not None:
        flush()
