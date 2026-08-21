"""Remove only nAIM-generated local data and model artefacts."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = (
    ROOT / "data" / "raw",
    ROOT / "data" / "validated",
    ROOT / "data" / "curated",
    ROOT / "data" / "quarantine",
    ROOT / "data" / "manifests",
    ROOT / "models" / "artifacts",
)


def main() -> None:
    for target in TARGETS:
        target = target.resolve()
        if ROOT not in target.parents:
            raise RuntimeError(f"Refusing unsafe cleanup target: {target}")
        if target.exists():
            shutil.rmtree(target)
            print(f"Removed generated directory: {target.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
