from __future__ import annotations

from pathlib import Path

import pytest

from naim_risk.auth import (
    AuthenticationError,
    AuthMode,
    AuthorizationError,
    AuthService,
    AuthSettings,
    Permission,
    Role,
)
from naim_risk.workflow import WorkflowStore

SECRET = "test-only-signing-secret-that-is-long-enough"


def service(tmp_path: Path, mode: AuthMode = AuthMode.DEMO) -> AuthService:
    store = WorkflowStore(f"sqlite+pysqlite:///{(tmp_path / 'auth.sqlite3').resolve()}")
    return AuthService(AuthSettings(mode=mode, token_secret=SECRET), store)


def test_demo_account_uses_argon2_and_signed_expiring_token(tmp_path: Path) -> None:
    auth = service(tmp_path)
    auth.setup_demo_account(
        "portfolio.analyst",
        "correct horse battery staple",
        Role.PORTFOLIO_ANALYST,
    )
    record = auth.account_record("portfolio.analyst")
    assert record["password_hash"].startswith("$argon2")
    assert "correct horse" not in record["password_hash"]

    token = auth.authenticate_demo("portfolio.analyst", "correct horse battery staple")
    principal = auth.principal(token)
    assert principal.username == "portfolio.analyst"
    assert principal.role is Role.PORTFOLIO_ANALYST
    assert Permission.CREATE_INVESTIGATIONS in principal.permissions


def test_invalid_password_and_duplicate_setup_are_rejected(tmp_path: Path) -> None:
    auth = service(tmp_path)
    auth.setup_demo_account("validator", "secure password phrase", Role.MODEL_VALIDATOR)
    with pytest.raises(AuthenticationError, match="Invalid username or password"):
        auth.authenticate_demo("validator", "wrong password phrase")
    with pytest.raises(ValueError, match="already exists"):
        auth.setup_demo_account("validator", "different secure phrase", Role.MODEL_VALIDATOR)


def test_logout_revokes_token(tmp_path: Path) -> None:
    auth = service(tmp_path)
    auth.setup_demo_account("strategist", "secure strategy phrase", Role.STRATEGY_ANALYST)
    token = auth.authenticate_demo("strategist", "secure strategy phrase")
    assert auth.principal(token).role is Role.STRATEGY_ANALYST
    auth.logout(token)
    with pytest.raises(AuthenticationError, match="no longer active"):
        auth.principal(token)


def test_role_permissions_are_enforced_by_service(tmp_path: Path) -> None:
    auth = service(tmp_path)
    viewer = auth.setup_demo_account("executive", "secure executive phrase", Role.EXECUTIVE_VIEWER)
    assert viewer is None
    principal = auth.principal(auth.authenticate_demo("executive", "secure executive phrase"))
    AuthService.require(principal, Permission.VIEW_APPROVED_REPORTS)
    with pytest.raises(AuthorizationError, match="does not have permission"):
        AuthService.require(principal, Permission.CREATE_WORKSPACES)


def test_disabled_mode_is_explicit_and_local_administrator(tmp_path: Path) -> None:
    store = WorkflowStore(f"sqlite+pysqlite:///{(tmp_path / 'auth.sqlite3').resolve()}")
    with pytest.warns(RuntimeWarning, match="private local development"):
        auth = AuthService(AuthSettings(mode=AuthMode.DISABLED), store)
    principal = auth.principal(None)
    assert principal.username == "local-development"
    assert principal.role is Role.ADMINISTRATOR


def test_configuration_requires_secret_and_oidc_coordinates() -> None:
    with pytest.raises(ValueError, match="NAIM_TOKEN_SECRET"):
        AuthSettings(mode=AuthMode.DEMO).validate()
    with pytest.raises(ValueError, match="NAIM_OIDC_ISSUER"):
        AuthSettings(mode=AuthMode.OIDC).validate()


def test_short_password_is_rejected(tmp_path: Path) -> None:
    auth = service(tmp_path)
    with pytest.raises(ValueError, match="at least 12"):
        auth.setup_demo_account("analyst", "short", Role.PORTFOLIO_ANALYST)
