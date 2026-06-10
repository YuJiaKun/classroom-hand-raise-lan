from __future__ import annotations

from dataclasses import dataclass
import math
from threading import RLock
import time
from typing import Callable

from classroom_hand_raise.shared.constants import (
    FEEDBACK_COOLDOWN_SECONDS,
    HELP_REQUEST_COOLDOWN_SECONDS,
    RAISE_HAND_COOLDOWN_SECONDS,
)


ACTION_RAISE_HAND = "raise_hand"
ACTION_FEEDBACK = "feedback"
ACTION_HELP_REQUEST = "help_request"


DEFAULT_COOLDOWNS = {
    ACTION_RAISE_HAND: RAISE_HAND_COOLDOWN_SECONDS,
    ACTION_FEEDBACK: FEEDBACK_COOLDOWN_SECONDS,
    ACTION_HELP_REQUEST: HELP_REQUEST_COOLDOWN_SECONDS,
}


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int = 0

    @property
    def message(self) -> str:
        if self.allowed:
            return ""
        return f"操作太频繁，请 {self.retry_after_seconds} 秒后再试"


class InteractionRateLimiter:
    def __init__(
        self,
        cooldowns: dict[str, int] | None = None,
        time_func: Callable[[], float] | None = None,
    ) -> None:
        self.cooldowns = dict(cooldowns or DEFAULT_COOLDOWNS)
        self.time_func = time_func or time.time
        self._last_allowed_at: dict[tuple[str, str], float] = {}
        self._lock = RLock()

    def check(self, identity: str, action: str) -> RateLimitResult:
        clean_identity = identity.strip()
        cooldown = int(self.cooldowns.get(action, 0))
        if not clean_identity or cooldown <= 0:
            return RateLimitResult(True)

        now = self.time_func()
        key = (clean_identity, action)
        with self._lock:
            last_allowed_at = self._last_allowed_at.get(key)
            if last_allowed_at is not None:
                elapsed = now - last_allowed_at
                if elapsed < cooldown:
                    retry_after = max(1, math.ceil(cooldown - elapsed))
                    return RateLimitResult(False, retry_after)
            self._last_allowed_at[key] = now
        return RateLimitResult(True)

    def reset(self) -> None:
        with self._lock:
            self._last_allowed_at.clear()
