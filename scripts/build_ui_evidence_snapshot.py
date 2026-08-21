#!/usr/bin/env python3
"""Build or verify the browser-derived UI release-evidence snapshot.

The builder does not launch a browser.  It promotes an operator-supplied capture
ledger only after every governed field is bound to a visible DOM observation and
every screenshot is independently re-hashed and inspected as an image.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
import sys
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    from scripts.reconcile_release_artifacts import PASS, canonical_context, sha256_file
except ModuleNotFoundError:  # Direct execution places scripts/ rather than the repository on sys.path.
    from reconcile_release_artifacts import PASS, canonical_context, sha256_file

SCHEMA_VERSION = "1.0.0"
CAPTURE_METHOD = "codex-in-app-browser/browser-client"
DEFAULT_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = Path("outputs/validation/ui_evidence_snapshot.json")
CANONICAL_PATH = "exports/validation/interop_evidence_snapshot.json"

RATE_FIELDS = {
    "governed_story.current_annualised_net_loss_rate",
    "governed_story.prior_annualised_net_loss_rate",
}
BPS_FIELDS = {
    "governed_story.observed_change_bps",
    "governed_story.mix_contribution_bps",
    "governed_story.within_segment_contribution_bps",
}
RESIDUAL_FIELD = "governed_story.reconciliation_residual_bps"
DATE_FIELDS = {
    "governed_story.reporting_period",
    "governed_story.comparison_period",
}
STORY_FIELDS = (
    "reporting_period",
    "comparison_period",
    "current_annualised_net_loss_rate",
    "prior_annualised_net_loss_rate",
    "observed_change_bps",
    "mix_contribution_bps",
    "within_segment_contribution_bps",
    "reconciliation_residual_bps",
    "primary_dimension",
    "primary_driver",
    "causal_status",
    "run_id",
    "metric_registry_version",
    "data_quality_status",
    "synthetic_data",
)


class UIEvidenceError(RuntimeError):
    """Raised when browser-capture evidence cannot be promoted."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise UIEvidenceError(message)


def _read_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise UIEvidenceError(f"Cannot read JSON object {path}: {type(exc).__name__}") from exc
    _require(isinstance(payload, dict), f"Expected a JSON object: {path}")
    return payload


def _canonical_json_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _parse_time(value: Any, label: str) -> datetime:
    _require(isinstance(value, str) and value.strip(), f"{label} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise UIEvidenceError(f"{label} is not a valid ISO-8601 timestamp") from exc
    _require(parsed.tzinfo is not None, f"{label} must include a UTC offset")
    return parsed.astimezone(UTC)


def _normalise_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).casefold()).strip()


def _local_url(value: Any, label: str) -> tuple[str, int | None]:
    _require(isinstance(value, str) and value.strip(), f"{label} must be a URL")
    parsed = urlparse(value)
    _require(parsed.scheme in {"http", "https"}, f"{label} must use http or https")
    _require(
        parsed.hostname in {"localhost", "127.0.0.1", "::1"},
        f"{label} must target localhost",
    )
    _require(parsed.username is None and parsed.password is None, f"{label} cannot contain credentials")
    try:
        port = parsed.port
    except ValueError as exc:
        raise UIEvidenceError(f"{label} has an invalid port") from exc
    _require(parsed.fragment == "", f"{label} cannot contain a fragment")
    return parsed.scheme, port


def _portable_screenshot(repository_root: Path, value: Any) -> Path:
    _require(isinstance(value, str) and value.strip(), "screenshot.path must be non-empty")
    candidate = (repository_root / value).resolve()
    screenshot_root = (repository_root / "outputs" / "screenshots").resolve()
    _require(candidate.is_relative_to(screenshot_root), "Screenshot must be under outputs/screenshots")
    _require(candidate.is_file(), f"Screenshot is missing: {value}")
    return candidate


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    if not data.startswith(b"\xff\xd8"):
        return None
    offset = 2
    while offset + 9 < len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue
        marker = data[offset + 1]
        offset += 2
        if marker in {0xD8, 0xD9}:
            continue
        if offset + 2 > len(data):
            break
        length = int.from_bytes(data[offset : offset + 2], "big")
        if length < 2 or offset + length > len(data):
            break
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            height = int.from_bytes(data[offset + 3 : offset + 5], "big")
            width = int.from_bytes(data[offset + 5 : offset + 7], "big")
            return width, height
        offset += length
    return None


def _image_details(path: Path) -> tuple[str, int, int]:
    data = path.read_bytes()
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        media_type = "image/png"
    else:
        dimensions = _jpeg_dimensions(data)
        _require(dimensions is not None, f"Screenshot is not a supported PNG or JPEG: {path}")
        width, height = dimensions
        media_type = "image/jpeg"
    _require(width >= 320 and height >= 240, f"Screenshot is implausibly small: {width}x{height}")
    _require(len(data) >= 1024, f"Screenshot is implausibly small: {len(data)} bytes")
    return media_type, width, height


def _numeric_match(field: str, expected: Any, actual: Any) -> bool:
    if isinstance(actual, bool) or not isinstance(actual, (int, float)):
        return False
    expected_number = float(expected)
    actual_number = float(actual)
    if not math.isfinite(expected_number) or not math.isfinite(actual_number):
        return False
    if field in RATE_FIELDS:
        tolerance = 5e-5
    elif field in BPS_FIELDS:
        tolerance = 0.05
    elif field == RESIDUAL_FIELD:
        tolerance = 0.0005
    else:
        tolerance = 0.0
    return abs(expected_number - actual_number) <= tolerance


def _values_match(field: str, expected: Any, actual: Any) -> bool:
    if isinstance(expected, bool):
        return isinstance(actual, bool) and actual is expected
    if isinstance(expected, (int, float)):
        return _numeric_match(field, expected, actual)
    if field == "governed_story.primary_dimension":
        return _normalise_text(expected) == _normalise_text(actual)
    return actual == expected


def _date_renderings(value: str) -> set[str]:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return {value.casefold()}
    return {
        value.casefold(),
        parsed.strftime("%b %Y").casefold(),
        parsed.strftime("%B %Y").casefold(),
        parsed.strftime("%d %b %Y").casefold(),
    }


def _rendered_text_supports(field: str, actual: Any, rendered_text: str) -> bool:
    text = rendered_text.casefold()
    if field in DATE_FIELDS and isinstance(actual, str):
        return any(rendering in text for rendering in _date_renderings(actual))
    if isinstance(actual, bool):
        marker = "synthetic" if actual else "non synthetic"
        return marker in _normalise_text(rendered_text)
    if isinstance(actual, (int, float)) and not isinstance(actual, bool):
        numbers = [float(item) for item in re.findall(r"[-+]?\d+(?:\.\d+)?", rendered_text)]
        if field in RATE_FIELDS and "%" in rendered_text:
            return any(_numeric_match(field, actual, item / 100.0) for item in numbers)
        return any(_numeric_match(field, actual, item) for item in numbers)
    return _normalise_text(actual) in _normalise_text(rendered_text)


def _expected_facts(story: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "source_context.active_mode": "OFFLINE_SNAPSHOT",
        "source_context.run_id": story.get("run_id"),
        "source_context.configuration_hash": story.get("configuration_hash"),
        "source_context.dataset_hash": story.get("dataset_hash"),
    }
    expected.update({f"governed_story.{field}": story.get(field) for field in STORY_FIELDS})
    missing = [field for field, value in expected.items() if value is None]
    _require(not missing, f"Canonical evidence lacks required fields: {', '.join(missing)}")
    return expected


def validate_capture_ledger(
    ledger: Mapping[str, Any],
    story: Mapping[str, Any],
    repository_root: Path,
    *,
    now: datetime | None = None,
    enforce_wall_clock_freshness: bool = True,
) -> dict[str, Any]:
    """Validate a capture ledger and return independently measured evidence."""

    _require(ledger.get("schema_version") == SCHEMA_VERSION, "Unsupported ledger schema_version")
    _require(ledger.get("channel") == "ui", "ledger.channel must be 'ui'")
    _require(ledger.get("capture_method") == CAPTURE_METHOD, f"capture_method must be {CAPTURE_METHOD}")
    session_id = ledger.get("session_id")
    _require(isinstance(session_id, str) and len(session_id.strip()) >= 12, "session_id is too short")

    started = _parse_time(ledger.get("started_at_utc"), "started_at_utc")
    completed = _parse_time(ledger.get("completed_at_utc"), "completed_at_utc")
    _require(started <= completed, "Capture session completed before it started")
    _require(completed - started <= timedelta(hours=4), "Capture session exceeds four hours")
    current = (now or datetime.now(UTC)).astimezone(UTC)
    _require(completed <= current + timedelta(minutes=5), "Capture session is future-dated")
    if enforce_wall_clock_freshness:
        _require(current - completed <= timedelta(hours=24), "Capture session is older than 24 hours")

    source_url = ledger.get("source_url")
    source_origin = _local_url(source_url, "source_url")
    _require(urlparse(str(source_url)).query == "", "source_url cannot contain a query")

    binding = ledger.get("canonical_binding")
    _require(isinstance(binding, Mapping), "canonical_binding must be an object")
    _require(binding.get("path") == CANONICAL_PATH, f"canonical_binding.path must be {CANONICAL_PATH}")
    canonical_file = repository_root / CANONICAL_PATH
    _require(canonical_file.is_file(), f"Canonical evidence is missing: {CANONICAL_PATH}")
    _require(
        binding.get("sha256") == sha256_file(canonical_file),
        "canonical_binding.sha256 does not match the canonical evidence bytes",
    )

    captures = ledger.get("captures")
    _require(isinstance(captures, list) and captures, "captures must contain at least one page capture")
    capture_ids: set[str] = set()
    observed_facts: dict[str, list[Any]] = {}
    measured_captures: list[dict[str, Any]] = []
    total_console_errors = 0
    total_assertions = 0

    for index, capture in enumerate(captures):
        label = f"captures[{index}]"
        _require(isinstance(capture, Mapping), f"{label} must be an object")
        capture_id = capture.get("capture_id")
        _require(isinstance(capture_id, str) and len(capture_id.strip()) >= 3, f"{label}.capture_id is invalid")
        _require(capture_id not in capture_ids, f"Duplicate capture_id: {capture_id}")
        capture_ids.add(capture_id)
        captured_at = _parse_time(capture.get("captured_at_utc"), f"{label}.captured_at_utc")
        _require(started <= captured_at <= completed, f"{label} falls outside the capture session")

        page_url = capture.get("page_url")
        page_origin = _local_url(page_url, f"{label}.page_url")
        _require(page_origin == source_origin, f"{label}.page_url must use the source_url origin")
        title = capture.get("page_title")
        _require(isinstance(title, str) and len(title.strip()) >= 3, f"{label}.page_title is invalid")
        _require(capture.get("load_state") == "load", f"{label}.load_state must be 'load'")
        _require(
            capture.get("document_ready_state") == "complete",
            f"{label}.document_ready_state must be 'complete'",
        )

        viewport = capture.get("viewport")
        _require(isinstance(viewport, Mapping), f"{label}.viewport must be an object")
        width, height = viewport.get("width"), viewport.get("height")
        _require(isinstance(width, int) and 320 <= width <= 7680, f"{label}.viewport.width is invalid")
        _require(isinstance(height, int) and 240 <= height <= 4320, f"{label}.viewport.height is invalid")

        console = capture.get("console_errors")
        _require(isinstance(console, Mapping), f"{label}.console_errors must be an object")
        error_count, entries = console.get("count"), console.get("entries")
        _require(isinstance(error_count, int) and error_count >= 0, f"{label}.console_errors.count is invalid")
        _require(isinstance(entries, list) and len(entries) == error_count, f"{label}.console_errors ledger is inconsistent")
        _require(error_count == 0, f"{label} contains {error_count} console errors")
        total_console_errors += error_count

        screenshot = capture.get("screenshot")
        _require(isinstance(screenshot, Mapping), f"{label}.screenshot must be an object")
        screenshot_path = _portable_screenshot(repository_root, screenshot.get("path"))
        screenshot_bytes = screenshot_path.stat().st_size
        screenshot_sha = sha256_file(screenshot_path)
        _require(screenshot.get("bytes") == screenshot_bytes, f"{label}.screenshot.bytes mismatch")
        _require(screenshot.get("sha256") == screenshot_sha, f"{label}.screenshot.sha256 mismatch")
        media_type, pixel_width, pixel_height = _image_details(screenshot_path)
        _require(screenshot.get("media_type") == media_type, f"{label}.screenshot.media_type mismatch")
        declared_pixels = screenshot.get("pixel_dimensions")
        _require(isinstance(declared_pixels, Mapping), f"{label}.screenshot.pixel_dimensions missing")
        _require(
            declared_pixels.get("width") == pixel_width and declared_pixels.get("height") == pixel_height,
            f"{label}.screenshot.pixel_dimensions mismatch",
        )
        _require(pixel_width >= width and pixel_height >= height, f"{label}.screenshot does not cover its viewport")
        mtime = datetime.fromtimestamp(screenshot_path.stat().st_mtime, tz=UTC)
        _require(
            abs((mtime - captured_at).total_seconds()) <= 6 * 60 * 60,
            f"{label}.screenshot mtime is not close to captured_at_utc",
        )

        assertions = capture.get("dom_assertions")
        _require(isinstance(assertions, list) and assertions, f"{label}.dom_assertions cannot be empty")
        has_route_assertion = False
        measured_assertions: list[dict[str, Any]] = []
        for assertion_index, assertion in enumerate(assertions):
            assertion_label = f"{label}.dom_assertions[{assertion_index}]"
            _require(isinstance(assertion, Mapping), f"{assertion_label} must be an object")
            assertion_id = assertion.get("assertion_id")
            _require(isinstance(assertion_id, str) and len(assertion_id.strip()) >= 3, f"{assertion_label}.assertion_id is invalid")
            locator = assertion.get("locator")
            _require(
                isinstance(locator, str)
                and len(locator.strip()) >= 3
                and locator.strip().casefold() not in {"*", "body", "html", "main", "#root"},
                f"{assertion_label}.locator is too broad",
            )
            rendered_text = assertion.get("rendered_text")
            _require(isinstance(rendered_text, str) and rendered_text.strip(), f"{assertion_label}.rendered_text is empty")
            _require(assertion.get("visible") is True, f"{assertion_label} was not visible")
            kind = assertion.get("kind")
            if kind == "binding":
                field = assertion.get("field")
                _require(isinstance(field, str), f"{assertion_label}.field is missing")
                observed_facts.setdefault(field, []).append(assertion.get("observed_value"))
                _require(
                    _rendered_text_supports(field, assertion.get("observed_value"), rendered_text),
                    f"{assertion_label}.rendered_text does not support observed_value",
                )
            elif kind == "text_contains":
                expected_text = assertion.get("expected_text")
                _require(isinstance(expected_text, str) and len(expected_text.strip()) >= 3, f"{assertion_label}.expected_text is invalid")
                _require(
                    _normalise_text(expected_text) in _normalise_text(rendered_text),
                    f"{assertion_label}.expected_text was not observed",
                )
                has_route_assertion = True
            else:
                raise UIEvidenceError(f"{assertion_label}.kind must be 'binding' or 'text_contains'")
            measured_assertions.append(dict(assertion))
        _require(has_route_assertion, f"{label} needs a page-specific text_contains assertion")
        total_assertions += len(assertions)
        measured_captures.append(
            {
                "capture_id": capture_id,
                "captured_at_utc": captured_at.isoformat(),
                "page_url": page_url,
                "page_title": title,
                "load_state": "load",
                "document_ready_state": "complete",
                "viewport": {"width": width, "height": height},
                "console_errors": {"count": 0, "entries": []},
                "screenshot": {
                    "path": screenshot_path.relative_to(repository_root).as_posix(),
                    "bytes": screenshot_bytes,
                    "sha256": screenshot_sha,
                    "media_type": media_type,
                    "pixel_dimensions": {"width": pixel_width, "height": pixel_height},
                },
                "dom_assertions": measured_assertions,
            }
        )

    expected_facts = _expected_facts(story)
    unknown = sorted(set(observed_facts) - set(expected_facts))
    _require(not unknown, f"Unknown governed binding fields: {', '.join(unknown)}")
    missing = sorted(set(expected_facts) - set(observed_facts))
    _require(not missing, f"Missing visible governed bindings: {', '.join(missing)}")
    for field, expected_value in expected_facts.items():
        for observed_value in observed_facts[field]:
            _require(
                _values_match(field, expected_value, observed_value),
                f"DOM binding mismatch for {field}: expected {expected_value!r}, observed {observed_value!r}",
            )

    return {
        "started_at_utc": started.isoformat(),
        "completed_at_utc": completed.isoformat(),
        "source_url": source_url,
        "captures": measured_captures,
        "capture_count": len(measured_captures),
        "assertion_count": total_assertions,
        "required_binding_count": len(expected_facts),
        "console_error_count": total_console_errors,
    }


def _load_canonical(repository_root: Path) -> dict[str, Any]:
    canonical, _ = canonical_context(repository_root)
    _require(canonical.get("status") == PASS, "Canonical evidence checks are not all PASS")
    story = canonical.get("story")
    _require(isinstance(story, dict), "Canonical story is missing")
    return story


def build_snapshot(
    repository_root: Path,
    ledger_path: Path,
    output_path: Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    story = _load_canonical(repository_root)
    ledger = _read_object(ledger_path)
    measured = validate_capture_ledger(ledger, story, repository_root, now=now)
    embedded_ledger = {
        "schema_version": SCHEMA_VERSION,
        "channel": "ui",
        "capture_method": CAPTURE_METHOD,
        "session_id": ledger["session_id"],
        "started_at_utc": measured["started_at_utc"],
        "completed_at_utc": measured["completed_at_utc"],
        "source_url": measured["source_url"],
        "canonical_binding": dict(ledger["canonical_binding"]),
        "captures": measured["captures"],
    }
    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "channel": "ui",
        "captured_at_utc": measured["completed_at_utc"],
        "source_url": measured["source_url"],
        "source_context": {
            "active_mode": "OFFLINE_SNAPSHOT",
            "run_id": story["run_id"],
            "configuration_hash": story["configuration_hash"],
            "dataset_hash": story["dataset_hash"],
        },
        "governed_story": {field: story[field] for field in STORY_FIELDS},
        "browser_capture": {
            "capture_method": CAPTURE_METHOD,
            "session_id": ledger["session_id"],
            "started_at_utc": measured["started_at_utc"],
            "completed_at_utc": measured["completed_at_utc"],
            "canonical_binding": dict(ledger["canonical_binding"]),
            "ledger_sha256": _canonical_json_sha256(embedded_ledger),
            "captures": measured["captures"],
        },
        "validation": {
            "status": PASS,
            "capture_count": measured["capture_count"],
            "assertion_count": measured["assertion_count"],
            "required_binding_count": measured["required_binding_count"],
            "console_error_count": measured["console_error_count"],
            "limitations": [
                "This is rendered-state evidence for localhost browser captures, not a hosted-service claim.",
                "The capture ledger is operator-collected; file hashes and governed values are independently verified, but the browser itself does not provide cryptographic attestation.",
            ],
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output_path)
    return snapshot


def verify_snapshot(
    repository_root: Path,
    snapshot_path: Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    snapshot = _read_object(snapshot_path)
    _require(snapshot.get("schema_version") == SCHEMA_VERSION, "Unsupported snapshot schema_version")
    _require(snapshot.get("channel") == "ui", "snapshot.channel must be 'ui'")
    _require(snapshot.get("validation", {}).get("status") == PASS, "Snapshot status is not PASS")
    browser_capture = snapshot.get("browser_capture")
    _require(isinstance(browser_capture, Mapping), "browser_capture is missing")
    embedded_ledger = {
        "schema_version": SCHEMA_VERSION,
        "channel": "ui",
        "capture_method": browser_capture.get("capture_method"),
        "session_id": browser_capture.get("session_id"),
        "started_at_utc": browser_capture.get("started_at_utc"),
        "completed_at_utc": browser_capture.get("completed_at_utc"),
        "source_url": snapshot.get("source_url"),
        "canonical_binding": browser_capture.get("canonical_binding"),
        "captures": browser_capture.get("captures"),
    }
    _require(
        browser_capture.get("ledger_sha256") == _canonical_json_sha256(embedded_ledger),
        "Embedded capture ledger hash mismatch",
    )
    story = _load_canonical(repository_root)
    measured = validate_capture_ledger(
        embedded_ledger,
        story,
        repository_root,
        now=now,
        enforce_wall_clock_freshness=False,
    )
    expected_source = {
        "active_mode": "OFFLINE_SNAPSHOT",
        "run_id": story["run_id"],
        "configuration_hash": story["configuration_hash"],
        "dataset_hash": story["dataset_hash"],
    }
    _require(snapshot.get("source_context") == expected_source, "Snapshot source_context drifted")
    _require(
        snapshot.get("governed_story") == {field: story[field] for field in STORY_FIELDS},
        "Snapshot governed_story drifted",
    )
    validation = snapshot.get("validation")
    _require(isinstance(validation, Mapping), "Snapshot validation block is missing")
    for field in ("capture_count", "assertion_count", "required_binding_count", "console_error_count"):
        _require(validation.get(field) == measured[field], f"Snapshot validation.{field} drifted")
    return snapshot


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=DEFAULT_REPOSITORY_ROOT)
    parser.add_argument("--capture-ledger", type=Path, help="Browser-capture ledger to promote")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verify", action="store_true", help="Verify the existing output in place")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.repository_root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    try:
        if args.verify:
            _require(args.capture_ledger is None, "--capture-ledger cannot be used with --verify")
            verify_snapshot(root, output)
            print(f"PASS: verified {output}")
        else:
            _require(args.capture_ledger is not None, "--capture-ledger is required when building")
            ledger = args.capture_ledger
            if not ledger.is_absolute():
                ledger = root / ledger
            build_snapshot(root, ledger, output)
            print(f"PASS: wrote {output}")
    except UIEvidenceError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
