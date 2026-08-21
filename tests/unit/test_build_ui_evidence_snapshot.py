from __future__ import annotations

import binascii
import hashlib
import json
import struct
import zlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts import build_ui_evidence_snapshot as evidence


def _png(width: int = 640, height: int = 360) -> bytes:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        checksum = binascii.crc32(kind)
        checksum = binascii.crc32(payload, checksum) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)

    rows = b"".join(b"\x00" + b"\x18\x3d\x51" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows, level=9))
        + chunk(b"IEND", b"")
    )


def _story() -> dict[str, object]:
    return {
        "reporting_period": "2025-08-01",
        "comparison_period": "2025-07-01",
        "current_annualised_net_loss_rate": 0.06685632988073756,
        "prior_annualised_net_loss_rate": 0.035714829388391336,
        "observed_change_bps": 311.4150049234624,
        "mix_contribution_bps": 4.433506460154617,
        "within_segment_contribution_bps": 306.9814984633076,
        "reconciliation_residual_bps": 0.0,
        "primary_dimension": "acquisition_channel",
        "primary_driver": "Affiliate",
        "causal_status": "ASSOCIATIONAL",
        "run_id": "default-test-run",
        "metric_registry_version": "1.0.0",
        "data_quality_status": "PASS",
        "synthetic_data": True,
        "configuration_hash": "c" * 64,
        "dataset_hash": "d" * 64,
    }


def _ledger(root: Path, story: dict[str, object], now: datetime) -> dict[str, object]:
    canonical = root / evidence.CANONICAL_PATH
    canonical.parent.mkdir(parents=True)
    canonical.write_text('{"evidence":"fixture"}\n', encoding="utf-8")
    screenshot = root / "outputs/screenshots/root-cause-desktop.png"
    screenshot.parent.mkdir(parents=True)
    screenshot.write_bytes(_png())
    screenshot_bytes = screenshot.read_bytes()

    assertions: list[dict[str, object]] = [
        {
            "assertion_id": "route-title",
            "kind": "text_contains",
            "locator": "[data-testid='page-title']",
            "expected_text": "Root Cause Explorer",
            "rendered_text": "Root Cause Explorer",
            "visible": True,
        }
    ]
    expected = evidence._expected_facts(story)
    for index, (field, value) in enumerate(expected.items()):
        rendered = "Synthetic data" if isinstance(value, bool) else str(value)
        assertions.append(
            {
                "assertion_id": f"binding-{index}",
                "kind": "binding",
                "field": field,
                "locator": f"[data-binding='{index}']",
                "observed_value": value,
                "rendered_text": rendered,
                "visible": True,
            }
        )

    started = now - timedelta(minutes=2)
    completed = now - timedelta(minutes=1)
    return {
        "schema_version": "1.0.0",
        "channel": "ui",
        "capture_method": evidence.CAPTURE_METHOD,
        "session_id": "browser-session-test",
        "started_at_utc": started.isoformat(),
        "completed_at_utc": completed.isoformat(),
        "source_url": "http://localhost:3000",
        "canonical_binding": {
            "path": evidence.CANONICAL_PATH,
            "sha256": hashlib.sha256(canonical.read_bytes()).hexdigest(),
        },
        "captures": [
            {
                "capture_id": "root-cause-desktop",
                "captured_at_utc": completed.isoformat(),
                "page_url": "http://localhost:3000/root-cause",
                "page_title": "nAIM — Root Cause Explorer",
                "load_state": "load",
                "document_ready_state": "complete",
                "viewport": {"width": 640, "height": 360},
                "console_errors": {"count": 0, "entries": []},
                "screenshot": {
                    "path": "outputs/screenshots/root-cause-desktop.png",
                    "bytes": len(screenshot_bytes),
                    "sha256": hashlib.sha256(screenshot_bytes).hexdigest(),
                    "media_type": "image/png",
                    "pixel_dimensions": {"width": 640, "height": 360},
                },
                "dom_assertions": assertions,
            }
        ],
    }


def test_capture_ledger_rehashes_real_files_and_governed_bindings(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    story = _story()
    measured = evidence.validate_capture_ledger(_ledger(tmp_path, story, now), story, tmp_path, now=now)

    assert measured["capture_count"] == 1
    assert measured["console_error_count"] == 0
    assert measured["required_binding_count"] == 19
    assert measured["captures"][0]["screenshot"]["sha256"]


@pytest.mark.parametrize("mutation", ["remote_url", "console_error", "tampered_hash", "missing_binding"])
def test_capture_ledger_fails_closed_on_untrusted_or_incomplete_evidence(
    tmp_path: Path,
    mutation: str,
) -> None:
    now = datetime.now(UTC)
    story = _story()
    ledger = _ledger(tmp_path, story, now)
    capture = ledger["captures"][0]
    if mutation == "remote_url":
        capture["page_url"] = "https://example.com/root-cause"
    elif mutation == "console_error":
        capture["console_errors"] = {"count": 1, "entries": ["request failed"]}
    elif mutation == "tampered_hash":
        capture["screenshot"]["sha256"] = "0" * 64
    else:
        capture["dom_assertions"] = capture["dom_assertions"][:-1]

    with pytest.raises(evidence.UIEvidenceError):
        evidence.validate_capture_ledger(ledger, story, tmp_path, now=now)


def test_built_snapshot_round_trips_and_detects_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    now = datetime.now(UTC)
    story = _story()
    ledger = _ledger(tmp_path, story, now)
    ledger["started_at_utc"] = str(ledger["started_at_utc"]).replace("+00:00", "Z")
    ledger["completed_at_utc"] = str(ledger["completed_at_utc"]).replace("+00:00", "Z")
    ledger["captures"][0]["captured_at_utc"] = str(
        ledger["captures"][0]["captured_at_utc"]
    ).replace("+00:00", "Z")
    ledger["operator_note"] = "This non-evidentiary field is intentionally not promoted."
    ledger_path = tmp_path / "work/ui-capture-ledger.json"
    ledger_path.parent.mkdir(parents=True)
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    output = tmp_path / evidence.DEFAULT_OUTPUT
    monkeypatch.setattr(evidence, "_load_canonical", lambda _root: story)

    built = evidence.build_snapshot(tmp_path, ledger_path, output, now=now)

    assert built["validation"]["status"] == "PASS"
    assert evidence.verify_snapshot(tmp_path, output, now=now)["channel"] == "ui"
    tampered = json.loads(output.read_text(encoding="utf-8"))
    tampered["source_context"]["dataset_hash"] = "f" * 64
    output.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(evidence.UIEvidenceError, match="source_context drifted"):
        evidence.verify_snapshot(tmp_path, output, now=now)
