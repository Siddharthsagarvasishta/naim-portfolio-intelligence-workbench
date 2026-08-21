#!/usr/bin/env python3
"""Fail when retired branding returns to active public or executable text."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RETIRED_TOKEN = bytes((97, 101, 103, 105, 115)).decode("ascii")
RETIRED_UPPER = RETIRED_TOKEN.upper()
RETIRED_PACKAGE = f"{RETIRED_TOKEN}_risk"
RETIRED_CONFIG_CLASS = f"{RETIRED_TOKEN.title()}Config"

SCAN_ROOTS = (
    Path("app"),
    Path("apps"),
    Path("config"),
    Path("docs"),
    Path("exports/powerbi"),
    Path("exports/sas"),
    Path("exports/tableau"),
    Path("exports/vba"),
    Path("exports/vbscript"),
    Path("models"),
    Path("public"),
    Path("scripts"),
    Path("sql"),
    Path("src"),
    Path("tests"),
    Path(".github"),
)
ROOT_FILES = (
    Path(".env.example"),
    Path(".dockerignore"),
    Path(".gitignore"),
    Path(".openai/hosting.json"),
    Path("Dockerfile.api"),
    Path("Dockerfile.web"),
    Path("IMPLEMENTATION_CHECKLIST.md"),
    Path("LICENSE"),
    Path("Makefile"),
    Path("README.md"),
    Path("docker-compose.yml"),
    Path("data/DATA_LAYERS.json"),
    Path("drizzle.config.ts"),
    Path("eslint.config.mjs"),
    Path("next.config.ts"),
    Path("package-lock.json"),
    Path("package.json"),
    Path("postcss.config.mjs"),
    Path("pyproject.toml"),
    Path("requirements-backend.txt"),
    Path("requirements.lock"),
    Path("tsconfig.json"),
    Path("vite.config.ts"),
)
TEXT_SUFFIXES = {
    ".bas",
    ".css",
    ".csv",
    ".dax",
    ".ini",
    ".json",
    ".md",
    ".mjs",
    ".py",
    ".sas",
    ".svg",
    ".ts",
    ".tsx",
    ".txt",
    ".vbs",
    ".yaml",
    ".yml",
}

# Every exception is an intentional migration, frozen-legacy, or compatibility
# boundary. Adding a path requires a reason that is printed in scanner output.
ALLOWLIST_EXACT = {
    Path("app/data/legacy-environment.ts"): "deprecated frontend environment adapter",
    Path("docs/continuation_audit.md"): "frozen pre-migration audit evidence",
    Path("docs/naim_migration_plan.md"): "controlled migration record",
    Path("src/naim_risk/compat.py"): "deprecated backend environment adapter",
    Path("tests/compat/test_legacy_compatibility.py"): "compatibility regression coverage",
    Path("src") / f"{RETIRED_TOKEN}_risk" / "__init__.py": "deprecated Python import shim",
    Path("src") / f"{RETIRED_TOKEN}_risk" / "config.py": "deprecated Python import shim",
}
ALLOWED_RETIRED_FRAGMENTS = {
    Path("app/data/legacy-environment.ts"): (f"NEXT_PUBLIC_{RETIRED_UPPER}_API_URL",),
    Path("src/naim_risk/compat.py"): (
        f"{RETIRED_UPPER}_DATASET_PROFILE",
        f"{RETIRED_UPPER}_PROFILE",
        f"{RETIRED_UPPER}_DATA_DIR",
        f"{RETIRED_UPPER}_DATA_ROOT",
        f"{RETIRED_UPPER}_RANDOM_SEED",
        f"{RETIRED_UPPER}_LOG_LEVEL",
        f"{RETIRED_UPPER}_ALLOWED_ORIGINS",
        f"{RETIRED_UPPER}_CORS_ORIGINS",
    ),
    Path("tests/compat/test_legacy_compatibility.py"): (
        f"{RETIRED_UPPER}_DATASET_PROFILE",
        RETIRED_PACKAGE,
        RETIRED_CONFIG_CLASS,
    ),
    Path("src") / f"{RETIRED_TOKEN}_risk" / "__init__.py": (
        RETIRED_PACKAGE,
        RETIRED_CONFIG_CLASS,
    ),
    Path("src") / f"{RETIRED_TOKEN}_risk" / "config.py": (
        f"{RETIRED_PACKAGE}.config",
        RETIRED_CONFIG_CLASS,
    ),
}
IGNORED_PARTS = {
    ".git",
    ".hypothesis",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "dist",
    "node_modules",
    "work",
}

FORBIDDEN_PUBLIC_ASSET_HASHES = {
    "838048e742f9dc05ac82bf8b15a3248ba3aa4d3cdb544ded27285c1024be03db",
}
REQUIRED_PNG_DIMENSIONS = {Path("public/og.png"): (1200, 627)}


def allowlist_reason(path: Path) -> str | None:
    relative = path.relative_to(ROOT)
    if relative in ALLOWLIST_EXACT:
        return ALLOWLIST_EXACT[relative]
    return None


def candidate_files() -> list[Path]:
    candidates: set[Path] = set()
    for relative in SCAN_ROOTS:
        root = ROOT / relative
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if (
                not path.is_file()
                or any(part in IGNORED_PARTS for part in path.parts)
                or any(part.endswith(".egg-info") for part in path.parts)
            ):
                continue
            candidates.add(path)
    candidates.update(ROOT / relative for relative in ROOT_FILES if (ROOT / relative).is_file())
    return sorted(candidates)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as stream:
        header = stream.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG file")
    return struct.unpack(">II", header[16:24])


def scan_public_binary_assets() -> list[dict[str, object]]:
    """Reject known stale visuals and incorrect social-card dimensions."""

    violations: list[dict[str, object]] = []
    for relative, expected_dimensions in REQUIRED_PNG_DIMENSIONS.items():
        path = ROOT / relative
        if not path.is_file():
            violations.append(
                {
                    "path": relative.as_posix(),
                    "path_match": False,
                    "lines": [],
                    "reason": "required public image is missing",
                }
            )
            continue
        digest = _sha256(path)
        if digest in FORBIDDEN_PUBLIC_ASSET_HASHES:
            violations.append(
                {
                    "path": relative.as_posix(),
                    "path_match": False,
                    "lines": [],
                    "reason": "public image matches a superseded pre-migration visual",
                }
            )
        try:
            actual_dimensions = _png_dimensions(path)
        except ValueError as exc:
            violations.append(
                {
                    "path": relative.as_posix(),
                    "path_match": False,
                    "lines": [],
                    "reason": str(exc),
                }
            )
        else:
            if actual_dimensions != expected_dimensions:
                violations.append(
                    {
                        "path": relative.as_posix(),
                        "path_match": False,
                        "lines": [],
                        "reason": (
                            f"expected {expected_dimensions[0]}x{expected_dimensions[1]}, "
                            f"found {actual_dimensions[0]}x{actual_dimensions[1]}"
                        ),
                    }
                )
    return violations


def scan() -> tuple[list[dict[str, object]], list[dict[str, str]]]:
    violations: list[dict[str, object]] = []
    allowed: list[dict[str, str]] = []
    token = RETIRED_TOKEN.casefold()
    for path in candidate_files():
        reason = allowlist_reason(path)
        relative = path.relative_to(ROOT)
        path_contains_token = token in relative.as_posix().casefold()
        text = (
            path.read_text(encoding="utf-8", errors="replace")
            if path.suffix.lower() in TEXT_SUFFIXES or relative in ROOT_FILES
            else ""
        )
        matching_lines = [
            line_number
            for line_number, line in enumerate(text.splitlines(), start=1)
            if token in line.casefold()
        ]
        if not path_contains_token and not matching_lines:
            continue
        if reason is not None:
            allowed_fragments = ALLOWED_RETIRED_FRAGMENTS.get(relative)
            unexpected_lines: list[int] = []
            if matching_lines and allowed_fragments is not None:
                for line_number, line in enumerate(text.splitlines(), start=1):
                    if token not in line.casefold():
                        continue
                    remainder = line
                    for fragment in allowed_fragments:
                        remainder = remainder.replace(fragment, "")
                    if token in remainder.casefold():
                        unexpected_lines.append(line_number)
            if unexpected_lines:
                violations.append(
                    {
                        "path": relative.as_posix(),
                        "path_match": path_contains_token,
                        "lines": unexpected_lines,
                        "reason": "retired token is outside the permitted compatibility vocabulary",
                    }
                )
                continue
            allowed.append({"path": relative.as_posix(), "reason": reason})
            continue
        violations.append(
            {
                "path": relative.as_posix(),
                "path_match": path_contains_token,
                "lines": matching_lines,
            }
        )
    shim_root = ROOT / "src" / f"{RETIRED_TOKEN}_risk"
    for path in sorted(shim_root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        forbidden = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ]
        if forbidden:
            violations.append(
                {
                    "path": path.relative_to(ROOT).as_posix(),
                    "path_match": True,
                    "lines": forbidden,
                    "reason": "legacy shim must not contain functions, classes or analytical logic",
                }
            )
    violations.extend(scan_public_binary_assets())
    return violations, allowed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable output.")
    args = parser.parse_args(argv)
    violations, allowed = scan()
    result = {"ok": not violations, "violations": violations, "allowlisted": allowed}
    if args.json:
        print(json.dumps(result, indent=2))
    elif violations:
        print("Retired public-brand references found:")
        for item in violations:
            print(f"- {item['path']} (lines: {item['lines']})")
    else:
        print(f"Public-brand scan passed; {len(allowed)} explicit compatibility exceptions.")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
