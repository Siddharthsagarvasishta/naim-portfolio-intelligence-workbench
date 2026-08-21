from __future__ import annotations

import binascii
import hashlib
import json
import struct
import zipfile
import zlib
from pathlib import Path

import pytest

from scripts.build_final_release_packages import (
    FINAL_RELEASE_EVIDENCE,
    FIXED_ZIP_TIME,
    GITHUB_REQUIRED_PACKAGES,
    GITHUB_USER_DOCS,
    LEDGER_NAME,
    OFFICE_BUILDER_PATHS,
    PACKAGE_ROOTS,
    PACKAGE_TARGETS,
    REQUIRED_SCREENSHOT_VIEWS,
    RESEARCH_METHOD_DOCS,
    RESEARCH_REQUIRED_PATHS,
    RETIRED_BRAND,
    SOURCE_REQUIRED_PATHS,
    PackageBuildError,
    PackageEntry,
    PackagePlan,
    build_package,
    build_selected_packages,
    create_package_plan,
    sha256_file,
    validate_package_archive,
)


def _write(root: Path, relative: str, content: str = "fixture\n") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _write_json(root: Path, relative: str, payload: object) -> Path:
    return _write(root, relative, json.dumps(payload, sort_keys=True) + "\n")


def _seed_source_tree(root: Path) -> None:
    for relative in SOURCE_REQUIRED_PATHS:
        content = "fixture\n"
        if relative == "vite.config.ts":
            content = 'import { sites } from "./build/sites-vite-plugin";\n'
        _write(root, relative, content)
    _write(root, "src/naim_risk/runtime.py", "VALUE = 1\n")
    _write(root, "docs/guide.md", "# Guide\n")
    _write(root, "public/mark.svg", "<svg></svg>\n")
    for relative in OFFICE_BUILDER_PATHS:
        _write(root, relative, "// governed builder\n")


def _zip_file(path: Path, name: str = "payload/readme.txt", content: bytes = b"ok\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    info = zipfile.ZipInfo(name, date_time=FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (0o100644 & 0xFFFF) << 16
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(info, content)


def _png_chunk(chunk_type: bytes, content: bytes) -> bytes:
    checksum = binascii.crc32(chunk_type)
    checksum = binascii.crc32(content, checksum) & 0xFFFFFFFF
    return struct.pack(">I", len(content)) + chunk_type + content + struct.pack(">I", checksum)


def _png(width: int = 640, height: int = 360) -> bytes:
    rows = b"".join(b"\x00" + (b"\x1a\x2b\x3c" * width) for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(rows, level=9))
        + _png_chunk(b"IEND", b"")
    )


def _seed_core_evidence(root: Path) -> Path:
    return _write_json(
        root,
        "outputs/nAIM_Release_Core_Evidence.json",
        {"schema_version": "1.0.0", "snapshot_id": "NAIM-test-core"},
    )


def _seed_final_reconciliation(root: Path) -> Path:
    proof = _write(root, "outputs/validation/final-channel-proof.txt", "current proof\n")
    proof_record = {
        "path": proof.relative_to(root).as_posix(),
        "bytes": proof.stat().st_size,
        "sha256": sha256_file(proof),
    }
    channel_ids = (
        "api_service_evidence",
        "ui_snapshot",
        "excel_workbook",
        "powerpoint_review",
        "tableau_hyper",
        "power_bi_validation",
        "streamlit_snapshot",
        "static_share_site",
        "linkedin_carousel",
    )
    channels = []
    for channel_id in channel_ids:
        incomplete = channel_id == "streamlit_snapshot"
        channels.append(
            {
                "channel_id": channel_id,
                "required": True,
                "status": "INCOMPLETE" if incomplete else "PASS",
                "checks": [
                    {
                        "check_id": f"{channel_id}.fixture",
                        "required": True,
                        "outcome": "MISSING" if incomplete else "PASS",
                    }
                ],
                "artifact_paths": [] if incomplete else [proof_record["path"]],
                "artifacts": [] if incomplete else [proof_record],
            }
        )
    return _write_json(
        root,
        "outputs/validation/final_cross_artifact_reconciliation.json",
        {
            "result": "INCOMPLETE",
            "release_allowed": False,
            "channels": channels,
            "summary": {"failed_check_count": 0, "failed_channels": []},
        },
    )


def _seed_research_tree(root: Path) -> None:
    _seed_core_evidence(root)
    for relative in RESEARCH_METHOD_DOCS:
        _write(root, relative, f"# {Path(relative).stem}\n")
    _write_json(root, "exports/validation/evidence_snapshot.json", {"evidence_id": "E-1"})
    _write_json(
        root,
        "outputs/nAIM_Release_Readiness_Matrix.json",
        {"schema_version": "1.0.0", "release_allowed": True},
    )
    _zip_file(root / "outputs/nAIM_Release_Readiness_Matrix.xlsx", "[Content_Types].xml")
    _seed_final_reconciliation(root)
    _write_json(
        root,
        "outputs/validation/release_readiness_workbook_validation.json",
        {"status": "PASS"},
    )
    assert all((root / relative).is_file() for relative in RESEARCH_REQUIRED_PATHS)


def _seed_screenshot_tree(root: Path) -> None:
    _seed_core_evidence(root)
    captures: list[dict[str, object]] = []
    for view_id in REQUIRED_SCREENSHOT_VIEWS:
        file_name = f"{view_id}-desktop.png"
        path = root / "outputs/screenshots" / file_name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_png())
        captures.append(
            {
                "view_id": view_id,
                "file": file_name,
                "real_browser": True,
                "validation_status": "PASS",
                "availability_state": "LIVE",
                "viewport": {"name": "desktop", "width": 640, "height": 360},
            }
        )
    for viewport in ("tablet", "mobile"):
        file_name = f"start-here-{viewport}.png"
        (root / "outputs/screenshots" / file_name).write_bytes(_png())
        captures.append(
            {
                "view_id": "start-here",
                "file": file_name,
                "real_browser": True,
                "validation_status": "PASS",
                "availability_state": "LIVE",
                "viewport": {"name": viewport, "width": 640, "height": 360},
            }
        )
    _write_json(
        root,
        "outputs/screenshots/browser_capture_index.json",
        {
            "schema_version": "1.0.0",
            "capture_kind": "REAL_BROWSER",
            "real_browser": True,
            "validation_status": "PASS",
            "browser": "Codex in-app browser",
            "captures": captures,
        },
    )


def _seed_github_docs(root: Path) -> None:
    for relative in GITHUB_USER_DOCS:
        if not (root / relative).exists():
            _write(root, relative, f"# {Path(relative).stem}\n")


def test_source_package_is_deterministic_portable_and_relocates_builders(
    tmp_path: Path,
) -> None:
    _seed_source_tree(tmp_path)
    _write(tmp_path, "node_modules/secret.js", 'SECRET = "real-production-secret"\n')
    _write(tmp_path, "docs/powerbi_setup 2.md", "stale\n")
    _write(tmp_path, "public/favicon 2.svg", "stale\n")
    _write(tmp_path, "outputs/generated.txt", "generated\n")
    plan = create_package_plan("source", root=tmp_path)

    first = build_package(plan)
    first_bytes = plan.target.read_bytes()
    second = build_package(create_package_plan("source", root=tmp_path))

    assert first["sha256"] == second["sha256"]
    assert first_bytes == plan.target.read_bytes()
    with zipfile.ZipFile(plan.target) as archive:
        names = archive.namelist()
        root = PACKAGE_ROOTS["source"]
        assert names == sorted(names)
        assert f"{root}/release-builders/readiness/build_readiness_matrix.mjs" in names
        assert f"{root}/release-builders/sites-vite-plugin.ts" in names
        assert not any("node_modules" in name or "outputs/" in name for name in names)
        assert not any(" 2." in name or RETIRED_BRAND in name for name in names)
        vite = archive.read(f"{root}/vite.config.ts")
        assert b"./release-builders/sites-vite-plugin" in vite
        assert b"./build/sites-vite-plugin" not in vite
    validation = validate_package_archive(plan.target)
    assert validation["package"] == "source"


def test_package_validator_rejects_forbidden_name_secret_and_undeclared_file(
    tmp_path: Path,
) -> None:
    source = _write(tmp_path, "source.txt", "safe\n")
    target = tmp_path / "outputs/package.zip"
    plan = PackagePlan(
        package="source",
        target=target,
        archive_root="pkg",
        entries=(
            PackageEntry(
                archive_path=f"pkg/{RETIRED_BRAND}_notes.md",
                source_classification="AUTHORED_SOURCE",
                source_path=source,
            ),
        ),
    )
    with pytest.raises(PackageBuildError, match="Retired branded"):
        build_package(plan, dry_run=True)

    secret = _write(tmp_path, "secret.py", 'SECRET = "actual-live-credential"\n')
    secret_plan = PackagePlan(
        package="source",
        target=target,
        archive_root="pkg",
        entries=(
            PackageEntry(
                archive_path="pkg/secret.py",
                source_classification="AUTHORED_SOURCE",
                source_path=secret,
            ),
        ),
    )
    with pytest.raises(PackageBuildError, match="Possible assigned secret"):
        build_package(secret_plan, dry_run=True)

    ledger = {
        "schema_version": "1.0.0",
        "package": "source",
        "dependencies": [],
        "files": [
            {
                "archive_path": "pkg/a.txt",
                "sha256": hashlib.sha256(b"a").hexdigest(),
                "size_bytes": 1,
                "source_classification": "AUTHORED_SOURCE",
            }
        ],
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w") as archive:
        for name, content in sorted(
            {
                f"pkg/{LEDGER_NAME}": json.dumps(ledger).encode(),
                "pkg/a.txt": b"a",
                "pkg/z.txt": b"undeclared",
            }.items()
        ):
            info = zipfile.ZipInfo(name, date_time=FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (0o100644 & 0xFFFF) << 16
            archive.writestr(info, content)
    with pytest.raises(PackageBuildError, match="Ledger/archive mismatch"):
        validate_package_archive(target)


def test_research_package_is_core_evidence_bound_cycle_safe_and_portable(
    tmp_path: Path,
) -> None:
    _seed_research_tree(tmp_path)
    run_id = "default-test"
    _write_json(
        tmp_path,
        "data/manifests/latest.json",
        {"run_id": run_id, "manifest": str(tmp_path / "data/manifests/run.json")},
    )
    _write_json(
        tmp_path,
        f"data/manifests/{run_id}/run_manifest.json",
        {"run_id": run_id, "path": str(tmp_path / "data/validated/snapshot.parquet")},
    )
    _write_json(tmp_path, f"outputs/{FINAL_RELEASE_EVIDENCE}", {"release_allowed": True})

    result = build_package(create_package_plan("research", root=tmp_path))

    target = tmp_path / "outputs" / PACKAGE_TARGETS["research"]
    assert result["core_evidence_sha256"] == sha256_file(
        tmp_path / "outputs/nAIM_Release_Core_Evidence.json"
    )
    with zipfile.ZipFile(target) as archive:
        names = archive.namelist()
        assert not any(FINAL_RELEASE_EVIDENCE in name for name in names)
        run_manifest = archive.read(
            f"{PACKAGE_ROOTS['research']}/evidence/core_run_manifest.json"
        )
        assert str(tmp_path).encode() not in run_manifest
        ledger = json.loads(
            archive.read(f"{PACKAGE_ROOTS['research']}/{LEDGER_NAME}")
        )
        assert ledger["dependencies"][0]["sha256"] == result["core_evidence_sha256"]


def test_research_package_rejects_incomplete_ui_channel(tmp_path: Path) -> None:
    _seed_research_tree(tmp_path)
    reconciliation_path = (
        tmp_path / "outputs/validation/final_cross_artifact_reconciliation.json"
    )
    payload = json.loads(reconciliation_path.read_text(encoding="utf-8"))
    ui = next(item for item in payload["channels"] if item["channel_id"] == "ui_snapshot")
    ui.update(
        {
            "status": "INCOMPLETE",
            "checks": [
                {
                    "check_id": "ui_snapshot.fixture",
                    "required": True,
                    "outcome": "MISSING",
                }
            ],
            "artifact_paths": [],
            "artifacts": [],
        }
    )
    reconciliation_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(PackageBuildError, match="required final channel ui_snapshot"):
        create_package_plan("research", root=tmp_path)


def test_screenshot_package_fails_closed_then_accepts_complete_real_browser_index(
    tmp_path: Path,
) -> None:
    _seed_core_evidence(tmp_path)
    with pytest.raises(PackageBuildError, match="Missing prerequisite"):
        create_package_plan("screenshots", root=tmp_path)

    _seed_screenshot_tree(tmp_path)
    plan = create_package_plan("screenshots", root=tmp_path)
    summary = build_package(plan)
    assert summary["file_count"] == len(REQUIRED_SCREENSHOT_VIEWS) + 4

    stale = tmp_path / f"outputs/screenshots/{RETIRED_BRAND}-stale.png"
    stale.write_bytes(_png())
    with pytest.raises(PackageBuildError, match="undeclared or stale"):
        create_package_plan("screenshots", root=tmp_path)


def test_topological_release_build_creates_cycle_safe_github_envelope(tmp_path: Path) -> None:
    _seed_source_tree(tmp_path)
    _seed_research_tree(tmp_path)
    _seed_screenshot_tree(tmp_path)
    _seed_github_docs(tmp_path)
    build_selected_packages(
        ["source", "research", "screenshots"],
        root=tmp_path,
    )
    for package_name in GITHUB_REQUIRED_PACKAGES:
        path = tmp_path / "outputs" / package_name
        if path.exists():
            continue
        if path.suffix.lower() in {".xlsx", ".pptx"}:
            _zip_file(path, "[Content_Types].xml")
        else:
            _zip_file(path)

    results = build_selected_packages(["github"], root=tmp_path)

    target = tmp_path / "outputs" / PACKAGE_TARGETS["github"]
    assert results[0]["package"] == "github"
    with zipfile.ZipFile(target) as archive:
        names = archive.namelist()
        assert not any(FINAL_RELEASE_EVIDENCE in name for name in names)
        assert not any(PACKAGE_TARGETS["github"] in name for name in names)
        assert not any(name.endswith(f"{PACKAGE_TARGETS['github']}.manifest.json") for name in names)
        ledger = json.loads(archive.read(f"{PACKAGE_ROOTS['github']}/{LEDGER_NAME}"))
        assert ledger["dependencies"][0]["path"] == (
            "outputs/nAIM_Release_Core_Evidence.json"
        )


def test_dry_run_is_non_mutating_and_missing_prerequisites_fail(tmp_path: Path) -> None:
    _seed_source_tree(tmp_path)
    results = build_selected_packages(["source"], root=tmp_path, dry_run=True)
    assert results[0]["dry_run"] is True
    assert not (tmp_path / "outputs" / PACKAGE_TARGETS["source"]).exists()

    with pytest.raises(PackageBuildError, match="Missing prerequisite"):
        build_selected_packages(["research"], root=tmp_path, dry_run=True)
