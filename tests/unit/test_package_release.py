from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

from scripts.package_release import EXCLUDED_FILES, build_archive_from_entries


def test_multi_entry_release_archive_is_deterministic_and_portable(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "README.md").write_text("governed package\n", encoding="utf-8")
    documentation = tmp_path / "guide.md"
    documentation.write_text("desktop validation is external\n", encoding="utf-8")
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"

    entries = [(project, "source"), (documentation, "documentation")]
    build_archive_from_entries(entries, first)
    build_archive_from_entries(entries, second)

    assert hashlib.sha256(first.read_bytes()).hexdigest() == hashlib.sha256(
        second.read_bytes()
    ).hexdigest()
    with zipfile.ZipFile(first) as archive:
        assert archive.namelist() == ["source/README.md", "documentation/guide.md"]
        assert all(not Path(name).is_absolute() for name in archive.namelist())


def test_multi_entry_archive_excludes_known_duplicate_export(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "measures.dax").write_text("Current", encoding="utf-8")
    (source / "measures 2.dax").write_text("Stale duplicate", encoding="utf-8")
    target = tmp_path / "interop.zip"

    build_archive_from_entries([(source, "exports/powerbi")], target)

    with zipfile.ZipFile(target) as archive:
        assert archive.namelist() == ["exports/powerbi/measures.dax"]
    assert "measures 2.dax" in EXCLUDED_FILES
