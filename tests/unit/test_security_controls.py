from __future__ import annotations

import pytest

from naim_risk.security import (
    DownloadTokenError,
    DownloadTokenService,
    SlidingWindowRateLimiter,
    opaque_rate_limit_key,
)


def test_sliding_window_rate_limiter_releases_capacity_after_window() -> None:
    limiter = SlidingWindowRateLimiter(limit=2, window_seconds=10)

    assert limiter.check("caller", now=100).allowed is True
    assert limiter.check("caller", now=101).remaining == 0
    denied = limiter.check("caller", now=102)
    assert denied.allowed is False
    assert denied.retry_after_seconds == 8
    assert limiter.check("caller", now=111).allowed is True


def test_download_token_is_expiring_and_bound_to_user_and_resource() -> None:
    service = DownloadTokenService(b"t" * 32, ttl_seconds=30)
    token = service.issue("presentation:PRES-1", "analyst", now=100)

    claims = service.verify(token, "presentation:PRES-1", "analyst", now=129)
    assert claims["exp"] == 130
    with pytest.raises(DownloadTokenError, match="artifact or user"):
        service.verify(token, "presentation:PRES-2", "analyst", now=129)
    with pytest.raises(DownloadTokenError, match="artifact or user"):
        service.verify(token, "presentation:PRES-1", "viewer", now=129)
    with pytest.raises(DownloadTokenError, match="expired"):
        service.verify(token, "presentation:PRES-1", "analyst", now=130)


def test_download_token_rejects_tampering_and_rate_key_hides_bearer() -> None:
    service = DownloadTokenService(b"s" * 32)
    token = service.issue("export:EXP-1", "analyst", now=100)
    with pytest.raises(DownloadTokenError, match="signature"):
        service.verify(token + "x", "export:EXP-1", "analyst", now=101)

    key = opaque_rate_limit_key("127.0.0.1", "Bearer highly-sensitive")
    assert "highly-sensitive" not in key
    assert key.startswith("127.0.0.1:")
