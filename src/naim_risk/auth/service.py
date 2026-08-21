"""Configurable disabled, demo, and OIDC authentication with backend roles."""

from __future__ import annotations

import os
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from jwt import InvalidTokenError, PyJWKClient
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from naim_risk.workflow.models import RevokedToken, UserAccount
from naim_risk.workflow.store import WorkflowStore


class AuthMode(StrEnum):
    DISABLED = "disabled"
    DEMO = "demo"
    OIDC = "oidc"


class Role(StrEnum):
    EXECUTIVE_VIEWER = "Executive Viewer"
    PORTFOLIO_ANALYST = "Portfolio Analyst"
    STRATEGY_ANALYST = "Strategy Analyst"
    MODEL_VALIDATOR = "Model Validator"
    ADMINISTRATOR = "Administrator"


class Permission(StrEnum):
    VIEW_APPROVED_REPORTS = "view:approved_reports"
    VIEW_ANALYTICS = "view:analytics"
    CREATE_INVESTIGATIONS = "create:investigations"
    CREATE_WORKSPACES = "create:workspaces"
    RUN_STRATEGY_SCENARIOS = "run:strategy_scenarios"
    APPROVE_MODELS = "approve:models"
    PUBLISH_CONFIGURATION = "publish:configuration"
    MANAGE_ACCESS = "manage:access"
    MANAGE_ALERTS = "manage:alerts"
    DOWNLOAD_ARTIFACTS = "download:artifacts"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.EXECUTIVE_VIEWER: frozenset(
        {Permission.VIEW_APPROVED_REPORTS, Permission.DOWNLOAD_ARTIFACTS}
    ),
    Role.PORTFOLIO_ANALYST: frozenset(
        {
            Permission.VIEW_APPROVED_REPORTS,
            Permission.VIEW_ANALYTICS,
            Permission.CREATE_INVESTIGATIONS,
            Permission.CREATE_WORKSPACES,
            Permission.MANAGE_ALERTS,
            Permission.DOWNLOAD_ARTIFACTS,
        }
    ),
    Role.STRATEGY_ANALYST: frozenset(
        {
            Permission.VIEW_APPROVED_REPORTS,
            Permission.VIEW_ANALYTICS,
            Permission.CREATE_INVESTIGATIONS,
            Permission.CREATE_WORKSPACES,
            Permission.RUN_STRATEGY_SCENARIOS,
            Permission.MANAGE_ALERTS,
            Permission.DOWNLOAD_ARTIFACTS,
        }
    ),
    Role.MODEL_VALIDATOR: frozenset(
        {
            Permission.VIEW_APPROVED_REPORTS,
            Permission.VIEW_ANALYTICS,
            Permission.APPROVE_MODELS,
            Permission.DOWNLOAD_ARTIFACTS,
        }
    ),
    Role.ADMINISTRATOR: frozenset(Permission),
}


class AuthenticationError(RuntimeError):
    """Raised when credentials or a token cannot be trusted."""


class AuthorizationError(RuntimeError):
    """Raised when a trusted identity lacks the required permission."""


@dataclass(frozen=True)
class Principal:
    username: str
    role: Role
    token_id: str | None
    auth_mode: AuthMode

    @property
    def permissions(self) -> frozenset[Permission]:
        return ROLE_PERMISSIONS[self.role]


@dataclass(frozen=True)
class AuthSettings:
    mode: AuthMode
    token_secret: str | None = None
    token_ttl_seconds: int = 3600
    token_issuer: str = "naim-local"
    token_audience: str = "naim-workbench"
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None
    oidc_role_claim: str = "naim_role"

    @classmethod
    def from_environment(cls) -> AuthSettings:
        raw_mode = os.getenv("NAIM_AUTH_MODE", os.getenv("AUTH_MODE", "disabled"))
        try:
            mode = AuthMode(raw_mode.lower())
        except ValueError as exc:
            raise ValueError("AUTH_MODE must be disabled, demo, or oidc") from exc
        ttl = int(os.getenv("NAIM_TOKEN_TTL_SECONDS", "3600"))
        if not 60 <= ttl <= 86400:
            raise ValueError("NAIM_TOKEN_TTL_SECONDS must be between 60 and 86400")
        settings = cls(
            mode=mode,
            token_secret=os.getenv("NAIM_TOKEN_SECRET"),
            token_ttl_seconds=ttl,
            token_issuer=os.getenv("NAIM_TOKEN_ISSUER", "naim-local"),
            token_audience=os.getenv("NAIM_TOKEN_AUDIENCE", "naim-workbench"),
            oidc_issuer=os.getenv("NAIM_OIDC_ISSUER"),
            oidc_audience=os.getenv("NAIM_OIDC_AUDIENCE"),
            oidc_jwks_url=os.getenv("NAIM_OIDC_JWKS_URL"),
            oidc_role_claim=os.getenv("NAIM_OIDC_ROLE_CLAIM", "naim_role"),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.mode is AuthMode.DEMO and (
            self.token_secret is None or len(self.token_secret) < 32
        ):
            raise ValueError("Demo mode requires NAIM_TOKEN_SECRET with at least 32 characters")
        if self.mode is AuthMode.OIDC and not all(
            (self.oidc_issuer, self.oidc_audience, self.oidc_jwks_url)
        ):
            raise ValueError(
                "OIDC mode requires NAIM_OIDC_ISSUER, NAIM_OIDC_AUDIENCE, and NAIM_OIDC_JWKS_URL"
            )


class AuthService:
    """Authenticate local demo users or verify production OIDC tokens."""

    password_hasher = PasswordHasher(
        time_cost=3,
        memory_cost=65536,
        parallelism=4,
        hash_len=32,
        salt_len=16,
    )

    def __init__(self, settings: AuthSettings, store: WorkflowStore) -> None:
        settings.validate()
        self.settings = settings
        self.store = store
        self._jwk_client = (
            PyJWKClient(settings.oidc_jwks_url)
            if settings.mode is AuthMode.OIDC and settings.oidc_jwks_url
            else None
        )
        if settings.mode is AuthMode.DISABLED:
            warnings.warn(
                "Authentication is disabled. This mode is for private local development only.",
                RuntimeWarning,
                stacklevel=2,
            )

    def setup_demo_account(
        self,
        username: str,
        password: str,
        role: Role,
        *,
        replace: bool = False,
    ) -> None:
        if self.settings.mode is not AuthMode.DEMO:
            raise AuthenticationError("Demo accounts can be created only in demo mode")
        if len(username.strip()) < 3:
            raise ValueError("Username must contain at least three characters")
        if len(password) < 12:
            raise ValueError("Demo password must contain at least 12 characters")
        now = datetime.now(UTC)
        password_hash = self.password_hasher.hash(password)
        with self.store.session_factory.begin() as session:
            existing = session.get(UserAccount, username)
            if existing is not None and not replace:
                raise ValueError(f"Demo account {username} already exists")
            if existing is None:
                session.add(
                    UserAccount(
                        username=username,
                        password_hash=password_hash,
                        role=role.value,
                        enabled=True,
                        token_version=1,
                        created_at=now,
                        modified_at=now,
                    )
                )
            else:
                existing.password_hash = password_hash
                existing.role = role.value
                existing.enabled = True
                existing.token_version += 1
                existing.modified_at = now

    def authenticate_demo(self, username: str, password: str) -> str:
        if self.settings.mode is not AuthMode.DEMO:
            raise AuthenticationError("Password authentication is available only in demo mode")
        with self.store.session_factory() as session:
            user = session.get(UserAccount, username)
            if user is None or not user.enabled:
                raise AuthenticationError("Invalid username or password")
            try:
                self.password_hasher.verify(user.password_hash, password)
            except (VerifyMismatchError, InvalidHashError) as exc:
                raise AuthenticationError("Invalid username or password") from exc
            if self.password_hasher.check_needs_rehash(user.password_hash):
                with self.store.session_factory.begin() as update_session:
                    refreshed = update_session.get(UserAccount, username)
                    if refreshed is not None:
                        refreshed.password_hash = self.password_hasher.hash(password)
                        refreshed.modified_at = datetime.now(UTC)
            return self._issue_demo_token(user)

    def _issue_demo_token(
        self,
        user: UserAccount,
        *,
        expires_in_seconds: int | None = None,
    ) -> str:
        if not self.settings.token_secret:
            raise AuthenticationError("Token signing is not configured")
        now = datetime.now(UTC)
        ttl = self.settings.token_ttl_seconds if expires_in_seconds is None else expires_in_seconds
        payload = {
            "sub": user.username,
            "role": user.role,
            "ver": user.token_version,
            "jti": os.urandom(16).hex(),
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(seconds=ttl),
            "iss": self.settings.token_issuer,
            "aud": self.settings.token_audience,
        }
        return jwt.encode(payload, self.settings.token_secret, algorithm="HS256")

    def _decode_demo_token(self, token: str) -> dict[str, Any]:
        if not self.settings.token_secret:
            raise AuthenticationError("Token verification is not configured")
        try:
            return jwt.decode(
                token,
                self.settings.token_secret,
                algorithms=["HS256"],
                issuer=self.settings.token_issuer,
                audience=self.settings.token_audience,
                options={"require": ["sub", "role", "ver", "jti", "iat", "nbf", "exp"]},
            )
        except InvalidTokenError as exc:
            raise AuthenticationError("Invalid or expired access token") from exc

    def _decode_oidc_token(self, token: str) -> dict[str, Any]:
        if self._jwk_client is None:
            raise AuthenticationError("OIDC verification is not configured")
        try:
            signing_key = self._jwk_client.get_signing_key_from_jwt(token)
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "ES256"],
                issuer=self.settings.oidc_issuer,
                audience=self.settings.oidc_audience,
                options={"require": ["sub", "iat", "exp"]},
            )
        except InvalidTokenError as exc:
            raise AuthenticationError("Invalid or expired OIDC access token") from exc

    def principal(self, token: str | None) -> Principal:
        if self.settings.mode is AuthMode.DISABLED:
            return Principal(
                username="local-development",
                role=Role.ADMINISTRATOR,
                token_id=None,
                auth_mode=AuthMode.DISABLED,
            )
        if not token:
            raise AuthenticationError("Bearer access token is required")
        if self.settings.mode is AuthMode.OIDC:
            payload = self._decode_oidc_token(token)
            raw_role = payload.get(self.settings.oidc_role_claim)
            try:
                role = Role(raw_role)
            except ValueError as exc:
                raise AuthorizationError("OIDC token has no recognized nAIM role") from exc
            return Principal(
                username=str(payload["sub"]),
                role=role,
                token_id=str(payload.get("jti")) if payload.get("jti") else None,
                auth_mode=AuthMode.OIDC,
            )

        payload = self._decode_demo_token(token)
        username = str(payload["sub"])
        token_id = str(payload["jti"])
        with self.store.session_factory() as session:
            user = session.get(UserAccount, username)
            revoked = session.get(RevokedToken, token_id)
            if (
                user is None
                or not user.enabled
                or int(payload["ver"]) != user.token_version
                or revoked is not None
            ):
                raise AuthenticationError("Access token is no longer active")
            try:
                role = Role(user.role)
            except ValueError as exc:
                raise AuthorizationError("Account has no recognized nAIM role") from exc
        return Principal(
            username=username,
            role=role,
            token_id=token_id,
            auth_mode=AuthMode.DEMO,
        )

    def logout(self, token: str) -> None:
        if self.settings.mode is not AuthMode.DEMO:
            return
        payload = self._decode_demo_token(token)
        expires_at = datetime.fromtimestamp(float(payload["exp"]), tz=UTC)
        try:
            with self.store.session_factory.begin() as session:
                session.add(
                    RevokedToken(
                        token_id=str(payload["jti"]),
                        username=str(payload["sub"]),
                        expires_at=expires_at,
                        revoked_at=datetime.now(UTC),
                    )
                )
        except IntegrityError:
            return

    def purge_expired_revocations(self) -> int:
        with self.store.session_factory.begin() as session:
            result = session.execute(
                delete(RevokedToken).where(RevokedToken.expires_at < datetime.now(UTC))
            )
            return int(result.rowcount or 0)

    @staticmethod
    def require(principal: Principal, permission: Permission) -> Principal:
        if permission not in principal.permissions:
            raise AuthorizationError(
                f"{principal.role.value} does not have permission {permission.value}"
            )
        return principal

    def account_record(self, username: str) -> dict[str, Any]:
        """Return non-secret account metadata for setup/administration tests."""

        with self.store.session_factory() as session:
            account = session.scalar(select(UserAccount).where(UserAccount.username == username))
            if account is None:
                raise AuthenticationError("Account not found")
            return {
                "username": account.username,
                "password_hash": account.password_hash,
                "role": account.role,
                "enabled": account.enabled,
                "token_version": account.token_version,
            }
