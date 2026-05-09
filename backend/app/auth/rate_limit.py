from dataclasses import dataclass
from time import monotonic

from app.core.config import get_settings


@dataclass
class LoginAttemptBucket:
    attempts: int
    reset_at: float


class LoginRateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, LoginAttemptBucket] = {}

    def check(
        self,
        key: str,
        *,
        attempts_limit: int | None = None,
        window_seconds: int | None = None,
    ) -> int | None:
        settings = get_settings()
        attempts_limit = attempts_limit or settings.login_rate_limit_attempts
        window_seconds = window_seconds or settings.login_rate_limit_window_seconds
        now = monotonic()
        bucket = self._buckets.get(key)
        if bucket is None or now >= bucket.reset_at:
            self._buckets[key] = LoginAttemptBucket(
                attempts=1,
                reset_at=now + window_seconds,
            )
            return None

        if bucket.attempts >= attempts_limit:
            return max(1, int(bucket.reset_at - now))

        bucket.attempts += 1
        return None

    def reset(self, key: str) -> None:
        self._buckets.pop(key, None)

    def clear(self) -> None:
        self._buckets.clear()


login_rate_limiter = LoginRateLimiter()
signup_rate_limiter = LoginRateLimiter()
