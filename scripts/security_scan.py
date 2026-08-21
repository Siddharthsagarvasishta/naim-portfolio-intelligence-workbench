#!/usr/bin/env python3
"""Run a conservative, value-redacting secret and deployment-config scan.

The scanner intentionally covers authored source/configuration surfaces and skips
generated data, local environments, caches, dependencies, binaries, and frozen
migration evidence. Findings never include the matched value: only a rule, path,
line number, and one-way fingerprint are emitted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]

SCAN_ROOTS: Final = (
    Path(".github"),
    Path("alembic"),
    Path("app"),
    Path("apps"),
    Path("build"),
    Path("config"),
    Path("db"),
    Path("docs"),
    Path("models"),
    Path("public"),
    Path("scripts"),
    Path("src"),
    Path("tests"),
    Path("worker"),
)
ROOT_FILES: Final = (
    Path(".dockerignore"),
    Path(".env.example"),
    Path(".gitignore"),
    Path(".openai/hosting.json"),
    Path("Dockerfile.api"),
    Path("Dockerfile.web"),
    Path("Makefile"),
    Path("README.md"),
    Path("alembic.ini"),
    Path("docker-compose.yml"),
    Path("drizzle.config.ts"),
    Path("eslint.config.mjs"),
    Path("next.config.ts"),
    Path("package.json"),
    Path("postcss.config.mjs"),
    Path("pyproject.toml"),
    Path("requirements-backend.txt"),
    Path("requirements.lock"),
    Path("tsconfig.json"),
    Path("vite.config.ts"),
)
IGNORED_PARTS: Final = {
    ".artifact-workbook",
    ".git",
    ".hypothesis",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "data",
    "dist",
    "htmlcov",
    "node_modules",
    "outputs",
    "work",
}
TEXT_SUFFIXES: Final = {
    "",
    ".css",
    ".env",
    ".html",
    ".ini",
    ".json",
    ".md",
    ".mjs",
    ".py",
    ".sh",
    ".svg",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
MAX_TEXT_BYTES: Final = 2 * 1024 * 1024


@dataclass(frozen=True)
class Rule:
    rule_id: str
    severity: str
    category: str
    description: str
    pattern: re.Pattern[str]
    production_only: bool = False


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: str
    category: str
    description: str
    path: str
    line: int
    fingerprint: str


RULES: Final = (
    Rule(
        "SECRET_PRIVATE_KEY",
        "error",
        "secret",
        "Private key material is present in an authored text file.",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    ),
    Rule(
        "SECRET_AWS_ACCESS_KEY",
        "error",
        "secret",
        "An AWS access-key identifier pattern is present.",
        re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    ),
    Rule(
        "SECRET_GITHUB_TOKEN",
        "error",
        "secret",
        "A GitHub token pattern is present.",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,255}|github_pat_[A-Za-z0-9_]{50,})\b"),
    ),
    Rule(
        "SECRET_GOOGLE_API_KEY",
        "error",
        "secret",
        "A Google API-key pattern is present.",
        re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    ),
    Rule(
        "SECRET_SLACK_TOKEN",
        "error",
        "secret",
        "A Slack token pattern is present.",
        re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{20,}\b"),
    ),
    Rule(
        "SECRET_STRIPE_LIVE_KEY",
        "error",
        "secret",
        "A Stripe live secret-key pattern is present.",
        re.compile(r"\bsk_live_[0-9A-Za-z]{16,}\b"),
    ),
    Rule(
        "SECRET_PASSWORD_URI",
        "error",
        "secret",
        "A database or broker URI appears to contain an inline password.",
        re.compile(
            r"\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|redis|amqps?)"
            r"://[^\s/:@]+:[^\s/@]+@",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "SECRET_LITERAL_ASSIGNMENT",
        "error",
        "secret",
        "A sensitive variable appears to contain a hard-coded literal.",
        re.compile(
            r"\b(?:api[_-]?key|client[_-]?secret|access[_-]?token|auth[_-]?token|"
            r"token[_-]?secret|password)\b\s*[:=]\s*[\"']"
            r"(?!replace-|example|test-|dummy|placeholder|changeme)[^\"'\n]{16,}[\"']",
            re.IGNORECASE,
        ),
        production_only=True,
    ),
    Rule(
        "CONFIG_PUBLIC_SECRET_NAME",
        "error",
        "configuration",
        "A client-exposed NEXT_PUBLIC variable name suggests secret material.",
        re.compile(r"\bNEXT_PUBLIC_[A-Z0-9_]*(?:SECRET|PASSWORD|PRIVATE|TOKEN|API_KEY)\b"),
    ),
    Rule(
        "CONFIG_WILDCARD_CORS",
        "error",
        "configuration",
        "A wildcard CORS origin is configured.",
        re.compile(
            r"(?:NAIM_ALLOWED_ORIGINS\s*=\s*\*|allow_origins\s*=\s*\[\s*[\"']\*[\"'])"
        ),
    ),
    Rule(
        "CONFIG_AUTH_DISABLED_DEFAULT",
        "warning",
        "configuration",
        "Container configuration defaults authentication to disabled; deployment must override it.",
        re.compile(r"\$\{NAIM_AUTH_MODE:-disabled\}"),
    ),
    Rule(
        "CONFIG_EMPTY_TOKEN_SECRET_DEFAULT",
        "warning",
        "configuration",
        "Container configuration permits an empty local token secret; authenticated modes fail closed.",
        re.compile(r"\$\{NAIM_TOKEN_SECRET:-\}"),
    ),
)


def _candidate_files(root: Path) -> list[Path]:
    candidates: set[Path] = set()
    for relative in SCAN_ROOTS:
        directory = root / relative
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if not path.is_file() or any(part in IGNORED_PARTS for part in path.parts):
                continue
            if path.suffix.casefold() in TEXT_SUFFIXES and path.stat().st_size <= MAX_TEXT_BYTES:
                candidates.add(path)
    for relative in ROOT_FILES:
        path = root / relative
        if path.is_file() and path.stat().st_size <= MAX_TEXT_BYTES:
            candidates.add(path)
    return sorted(candidates)


def _is_test_path(relative: Path) -> bool:
    return bool(relative.parts and relative.parts[0] == "tests")


def _fingerprint(rule_id: str, relative: Path, line_number: int, match: str) -> str:
    value = f"{rule_id}:{relative.as_posix()}:{line_number}:{match}".encode()
    return hashlib.sha256(value).hexdigest()[:20]


def scan_repository(root: Path = REPOSITORY_ROOT) -> dict[str, object]:
    """Return a JSON-serializable report without exposing matched secret values."""

    resolved_root = root.resolve()
    findings: list[Finding] = []
    unreadable_files: list[str] = []
    candidates = _candidate_files(resolved_root)
    for path in candidates:
        relative = path.relative_to(resolved_root)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            unreadable_files.append(relative.as_posix())
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            for rule in RULES:
                if rule.production_only and _is_test_path(relative):
                    continue
                for match in rule.pattern.finditer(line):
                    findings.append(
                        Finding(
                            rule_id=rule.rule_id,
                            severity=rule.severity,
                            category=rule.category,
                            description=rule.description,
                            path=relative.as_posix(),
                            line=line_number,
                            fingerprint=_fingerprint(
                                rule.rule_id,
                                relative,
                                line_number,
                                match.group(0),
                            ),
                        )
                    )

    errors = sum(item.severity == "error" for item in findings)
    warnings = sum(item.severity == "warning" for item in findings)
    status = "FAIL" if errors else ("PASS_WITH_WARNINGS" if warnings else "PASS")
    return {
        "schema_version": "1.0.0",
        "tool": "nAIM authored-surface secret and configuration scanner",
        "status": status,
        "root": ".",
        "scope": {
            "files_scanned": len(candidates),
            "generated_data_scanned": False,
            "local_dotenv_scanned": False,
            "dependency_directories_scanned": False,
            "maximum_text_file_bytes": MAX_TEXT_BYTES,
        },
        "summary": {
            "errors": errors,
            "warnings": warnings,
            "unreadable_files": len(unreadable_files),
        },
        "findings": [asdict(item) for item in findings],
        "unreadable_files": unreadable_files,
        "value_redaction": "Matched values are never emitted; fingerprints are one-way SHA-256.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--compact", action="store_true", help="Emit compact JSON")
    args = parser.parse_args()
    report = scan_repository(args.root)
    print(json.dumps(report, indent=None if args.compact else 2, sort_keys=True))
    return 1 if report["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
