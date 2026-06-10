from __future__ import annotations

import ipaddress
import json
import socket
import threading
import time
from typing import Any, Iterable

from .constants import (
    DEFAULT_CLASSROOM_NAME,
    DISCOVERY_BROADCAST_INTERVAL_SECONDS,
    DISCOVERY_MAGIC,
    DISCOVERY_PORT,
    PROTOCOL_VERSION,
)


def get_local_ip_addresses() -> list[str]:
    addresses: set[str] = {"127.0.0.1"}
    try:
        hostname = socket.gethostname()
        for address in socket.gethostbyname_ex(hostname)[2]:
            if address:
                addresses.add(address)
    except OSError:
        pass
    return rank_local_ip_addresses(addresses)


def rank_local_ip_addresses(addresses: Iterable[str]) -> list[str]:
    unique_addresses = sorted({str(address).strip() for address in addresses if str(address).strip()})
    return sorted(unique_addresses, key=_address_rank)


def primary_local_ip_address(addresses: Iterable[str] | None = None) -> str:
    ranked = rank_local_ip_addresses(addresses) if addresses is not None else get_local_ip_addresses()
    return ranked[0] if ranked else "127.0.0.1"


def _address_rank(address: str) -> tuple[int, str]:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return (90, address)
    if ip.is_loopback:
        return (80, address)
    parts = address.split(".")
    last_octet = parts[-1] if len(parts) == 4 else ""
    is_gateway_like = last_octet == "1"
    if address.startswith("192.168."):
        return (10 if not is_gateway_like else 30, address)
    if address.startswith("10."):
        return (20 if not is_gateway_like else 40, address)
    if ip.is_private:
        return (50 if not is_gateway_like else 60, address)
    return (70, address)


def build_discovery_packet(classroom_name: str, tcp_port: int) -> bytes:
    payload = {
        "type": DISCOVERY_MAGIC,
        "protocol_version": PROTOCOL_VERSION,
        "classroom_name": classroom_name or DEFAULT_CLASSROOM_NAME,
        "tcp_port": tcp_port,
        "addresses": get_local_ip_addresses(),
        "timestamp": time.time(),
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def decode_discovery_packet(data: bytes, source: tuple[str, int]) -> dict[str, Any] | None:
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict) or payload.get("type") != DISCOVERY_MAGIC:
        return None

    tcp_port = payload.get("tcp_port")
    if not isinstance(tcp_port, int) or tcp_port <= 0:
        return None

    return {
        "classroom_name": str(payload.get("classroom_name") or DEFAULT_CLASSROOM_NAME),
        "tcp_port": tcp_port,
        "addresses": list(payload.get("addresses") or []),
        "timestamp": float(payload.get("timestamp") or time.time()),
        "source_host": source[0],
    }


def listen_for_classrooms(timeout: float = 3.0, discovery_port: int = DISCOVERY_PORT) -> list[dict[str, Any]]:
    found: dict[tuple[str, int], dict[str, Any]] = {}
    deadline = time.time() + timeout
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(0.2)
        sock.bind(("", discovery_port))
        while time.time() < deadline:
            try:
                data, source = sock.recvfrom(65535)
            except socket.timeout:
                continue
            classroom = decode_discovery_packet(data, source)
            if classroom:
                found[(classroom["source_host"], classroom["tcp_port"])] = classroom
    return sorted(found.values(), key=lambda item: item["timestamp"], reverse=True)


class DiscoveryBroadcaster:
    def __init__(
        self,
        classroom_name: str,
        tcp_port: int,
        discovery_port: int = DISCOVERY_PORT,
        interval: float = DISCOVERY_BROADCAST_INTERVAL_SECONDS,
    ) -> None:
        self.classroom_name = classroom_name
        self.tcp_port = tcp_port
        self.discovery_port = discovery_port
        self.interval = interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="DiscoveryBroadcaster", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1)

    def _run(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            while not self._stop_event.is_set():
                packet = build_discovery_packet(self.classroom_name, self.tcp_port)
                try:
                    sock.sendto(packet, ("255.255.255.255", self.discovery_port))
                except OSError:
                    pass
                self._stop_event.wait(self.interval)
