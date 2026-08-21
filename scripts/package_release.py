"""Create reproducible, user-facing nAIM release archives."""

from __future__ import annotations

import argparse
import os
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    ".next",
    ".vinext",
    ".wrangler",
    ".pytest_cache",
    ".ruff_cache",
    ".hypothesis",
    "__pycache__",
    "build",
    "dist",
    "work",
    "outputs",
    "benchmarks",
    "catalogue",
    "demo",
    "generated_exports",
    "ground_truth",
    "marts",
    "raw",
    "validated",
    "curated",
    "quarantine",
    "manifests",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".DS_Store"}
EXCLUDED_FILES = {".coverage", "measures 2.dax"}


def _write_file(
    archive: zipfile.ZipFile,
    source: Path,
    archive_path: Path,
) -> None:
    info = zipfile.ZipInfo(archive_path.as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (source.stat().st_mode & 0xFFFF) << 16
    with source.open("rb") as input_stream, archive.open(info, "w") as output_stream:
        shutil.copyfileobj(input_stream, output_stream, length=1024 * 1024)


def _write_tree(
    archive: zipfile.ZipFile,
    source: Path,
    *,
    archive_root: Path,
) -> None:
    for current_root, dir_names, file_names in os.walk(source):
        current = Path(current_root)
        dir_names[:] = sorted(
            name
            for name in dir_names
            if name not in EXCLUDED_DIRS and not name.endswith(".egg-info")
        )
        for name in sorted(file_names):
            path = current / name
            if (
                name in EXCLUDED_FILES
                or (name.startswith(".env") and name != ".env.example")
                or name == ".DS_Store"
                or name.endswith(".inspect.ndjson")
                or path.suffix in EXCLUDED_SUFFIXES
            ):
                continue
            _write_file(archive, path, archive_root / path.relative_to(source))


def build_archive(source: Path, target: Path, archive_root: str) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        _write_tree(archive, source, archive_root=Path(archive_root))
    return target


def build_archive_from_entries(
    entries: list[tuple[Path, str]],
    target: Path,
) -> Path:
    """Build one deterministic archive from governed files and directory trees."""

    target.parent.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source, archive_root in entries:
            if not source.exists():
                continue
            if source.is_dir():
                for current_root, dir_names, file_names in os.walk(source):
                    current = Path(current_root)
                    dir_names[:] = sorted(
                        name
                        for name in dir_names
                        if name not in EXCLUDED_DIRS and not name.endswith(".egg-info")
                    )
                    for name in sorted(file_names):
                        path = current / name
                        if (
                            name in EXCLUDED_FILES
                            or name.endswith(".inspect.ndjson")
                            or path.suffix in EXCLUDED_SUFFIXES
                        ):
                            continue
                        member = (Path(archive_root) / path.relative_to(source)).as_posix()
                        if member in seen:
                            raise ValueError(f"Duplicate archive member: {member}")
                        seen.add(member)
                        _write_file(archive, path, Path(member))
            else:
                member = (Path(archive_root) / source.name).as_posix()
                if member in seen:
                    raise ValueError(f"Duplicate archive member: {member}")
                seen.add(member)
                _write_file(archive, source, Path(member))
    return target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scope",
        choices=("source", "powerbi", "tableau", "sas", "linkedin", "share", "interop", "all"),
        default="all",
    )
    args = parser.parse_args()

    targets: list[Path] = []
    if args.scope in {"source", "all"}:
        targets.append(
            build_archive(
                ROOT,
                OUTPUTS / "nAIM_Portfolio_Intelligence_Workbench_Source.zip",
                "naim-portfolio-intelligence-workbench",
            )
        )
    if args.scope in {"powerbi", "all"} and (
        ROOT / "outputs" / "powerbi" / "nAIM.PowerBIProject"
    ).exists():
        targets.append(
            build_archive_from_entries(
                [
                    (ROOT / "outputs" / "powerbi" / "nAIM.PowerBIProject", "nAIM.PowerBIProject"),
                    (ROOT / "docs" / "powerbi_setup.md", "documentation"),
                ],
                OUTPUTS / "nAIM_PowerBI_Desktop_Package.zip",
            )
        )
    if args.scope in {"tableau", "all"} and (ROOT / "exports" / "tableau").exists():
        targets.append(
            build_archive_from_entries(
                [
                    (ROOT / "exports" / "tableau", "tableau-source"),
                    (ROOT / "outputs" / "tableau", "validated-output"),
                    (ROOT / "docs" / "tableau_setup.md", "documentation"),
                ],
                OUTPUTS / "nAIM_Tableau_Desktop_Package.zip",
            )
        )
    if args.scope in {"sas", "all"} and (ROOT / "exports" / "sas").exists():
        targets.append(
            build_archive_from_entries(
                [
                    (ROOT / "exports" / "sas", "sas"),
                    (ROOT / "docs" / "sas_interoperability.md", "documentation"),
                ],
                OUTPUTS / "nAIM_SAS_Compatibility_Package.zip",
            )
        )
    if args.scope in {"linkedin", "all"} and (OUTPUTS / "linkedin").exists():
        targets.append(
            build_archive(
                OUTPUTS / "linkedin",
                OUTPUTS / "nAIM_LinkedIn_Showcase.zip",
                "linkedin-showcase",
            )
        )
    if args.scope in {"share", "all"} and (OUTPUTS / "share_site").exists():
        targets.append(
            build_archive(
                OUTPUTS / "share_site",
                OUTPUTS / "nAIM_Static_Share_Package.zip",
                "naim-share-site",
            )
        )
    if args.scope in {"interop", "all"} and (ROOT / "exports").exists():
        targets.append(
            build_archive_from_entries(
                [
                    (ROOT / "exports" / "powerbi", "exports/powerbi"),
                    (ROOT / "exports" / "tableau", "exports/tableau"),
                    (ROOT / "exports" / "sas", "exports/sas"),
                    (ROOT / "exports" / "vba", "exports/vba"),
                    (ROOT / "exports" / "vbscript", "exports/vbscript"),
                    (
                        ROOT / "exports" / "validation" / "interop_evidence_snapshot.json",
                        "exports/validation",
                    ),
                    (
                        ROOT
                        / "exports"
                        / "validation"
                        / "interop_reconciliation_totals.csv",
                        "exports/validation",
                    ),
                    (
                        ROOT / "exports" / "validation" / "governed_formula_metadata.csv",
                        "exports/validation",
                    ),
                ],
                OUTPUTS / "nAIM_Interoperability_Package.zip",
            )
        )
    for target in targets:
        print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
