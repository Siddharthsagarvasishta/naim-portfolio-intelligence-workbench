"""Layered Parquet storage with an optional DuckDB analytical catalogue."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Mapping
from pathlib import Path

import pandas as pd


def _normalise_for_storage(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in result.columns:
        if result[column].dtype == "object":
            sample = result[column].dropna().head(10)
            if any(isinstance(value, (list, dict, tuple, set)) for value in sample):
                result[column] = result[column].map(
                    lambda value: (
                        json.dumps(value, sort_keys=True)
                        if isinstance(value, (list, dict, tuple, set))
                        else value
                    )
                )
    return result


def write_table(frame: pd.DataFrame, path_without_suffix: Path) -> Path:
    """Write Parquet when PyArrow is available, otherwise a typed CSV fallback."""

    path_without_suffix.parent.mkdir(parents=True, exist_ok=True)
    clean = _normalise_for_storage(frame)
    try:
        import pyarrow  # noqa: F401

        path = path_without_suffix.with_suffix(".parquet")
        clean.to_parquet(path, index=False)
        return path
    except (ImportError, ModuleNotFoundError):
        path = path_without_suffix.with_suffix(".csv")
        clean.to_csv(path, index=False)
        return path


def read_table(path: Path) -> pd.DataFrame:
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    if path.suffix == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"Unsupported table format: {path}")


def write_layer(tables: Mapping[str, pd.DataFrame], layer_root: Path) -> dict[str, Path]:
    """Write each canonical table to one deterministic layer directory."""

    return {name: write_table(frame, layer_root / name) for name, frame in tables.items()}


def build_analytical_catalogue(
    table_paths: Mapping[str, Path],
    mart_paths: Mapping[str, Path],
    target_root: Path,
) -> tuple[Path, str]:
    """Create DuckDB views when available, or a compact SQLite mart fallback."""

    target_root.mkdir(parents=True, exist_ok=True)
    all_paths = {**table_paths, **mart_paths}
    try:
        import duckdb

        path = target_root / "naim.duckdb"
        connection = duckdb.connect(str(path))
        for table_name, source_path in all_paths.items():
            escaped = str(source_path).replace("'", "''")
            if source_path.suffix == ".parquet":
                reader = f"read_parquet('{escaped}')"
            else:
                reader = f"read_csv_auto('{escaped}', header=true)"
            connection.execute(f'CREATE OR REPLACE VIEW "{table_name}" AS SELECT * FROM {reader}')
        connection.close()
        return path, "duckdb"
    except (ImportError, ModuleNotFoundError):
        path = target_root / "naim.sqlite"
        connection = sqlite3.connect(path)
        for table_name, source_path in mart_paths.items():
            read_table(source_path).to_sql(table_name, connection, if_exists="replace", index=False)
        connection.commit()
        connection.close()
        return path, "sqlite_mart_fallback"


def latest_manifest(data_root: Path) -> Path | None:
    candidates: Iterable[Path] = data_root.glob("manifests/*/run_manifest.json")
    ordered = sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True)
    return ordered[0] if ordered else None
