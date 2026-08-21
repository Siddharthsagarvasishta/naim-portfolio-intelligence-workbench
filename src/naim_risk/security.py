"""Small dependency-free security controls for request and artifact delivery paths."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass


class DownloadTokenError(ValueError):
    """Raised when an artifact download token is invalid, expired, or mis-scoped."""


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int


class SlidingWindowRateLimiter:
    """Thread-safe, bounded-process request limiter for local and single-node deployments."""

    def __init__(self, limit: int = 240, window_seconds: int = 60) -> None:
        if limit < 1 or window_seconds < 1:
            raise ValueError("Rate-limit values must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, *, now: float | None = None) -> RateLimitDecision:
        current = time.monotonic() if now is None else now
        cutoff = current - self.window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.limit:
                retry_after = max(1, int(self.window_seconds - (current - events[0]) + 0.999))
                return RateLimitDecision(False, self.limit, 0, retry_after)
            events.append(current)
            return RateLimitDecision(True, self.limit, self.limit - len(events), 0)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as exc:
        raise DownloadTokenError("Malformed download token") from exc


class DownloadTokenService:
    """Issue expiring HMAC tokens bound to one user and one governed artifact."""

    def __init__(self, secret: str | bytes, *, ttl_seconds: int = 300) -> None:
        secret_bytes = secret.encode("utf-8") if isinstance(secret, str) else secret
        if len(secret_bytes) < 32:
            raise ValueError("Download-token secret must be at least 32 bytes")
        if not 30 <= ttl_seconds <= 3600:
            raise ValueError("Download-token TTL must be between 30 and 3600 seconds")
        self._secret = secret_bytes
        self.ttl_seconds = ttl_seconds

    def issue(
        self,
        resource: str,
        subject: str,
        *,
        now: int | None = None,
    ) -> str:
        issued = int(time.time()) if now is None else int(now)
        payload = {
            "exp": issued + self.ttl_seconds,
            "iat": issued,
            "nonce": secrets.token_hex(8),
            "resource": resource,
            "sub": subject,
            "v": 1,
        }
        encoded = _b64encode(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        signature = _b64encode(
            hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).digest()
        )
        return f"{encoded}.{signature}"

    def verify(
        self,
        token: str,
        resource: str,
        subject: str,
        *,
        now: int | None = None,
    ) -> dict[str, object]:
        try:
            encoded, signature = token.split(".", 1)
        except ValueError as exc:
            raise DownloadTokenError("Malformed download token") from exc
        expected = _b64encode(
            hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(signature, expected):
            raise DownloadTokenError("Invalid download token signature")
        try:
            payload = json.loads(_b64decode(encoded))
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
            raise DownloadTokenError("Malformed download token payload") from exc
        current = int(time.time()) if now is None else int(now)
        if payload.get("v") != 1:
            raise DownloadTokenError("Unsupported download token version")
        if payload.get("resource") != resource or payload.get("sub") != subject:
            raise DownloadTokenError("Download token is not valid for this artifact or user")
        if not isinstance(payload.get("exp"), int) or current >= int(payload["exp"]):
            raise DownloadTokenError("Download token has expired")
        return payload


def opaque_rate_limit_key(client_host: str, authorization: str | None) -> str:
    """Avoid retaining raw credentials while distinguishing authenticated callers."""

    credential_digest = hashlib.sha256((authorization or "anonymous").encode("utf-8")).hexdigest()
    return f"{client_host}:{credential_digest[:24]}"
