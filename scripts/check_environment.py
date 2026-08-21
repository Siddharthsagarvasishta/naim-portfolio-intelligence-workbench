"""Preflight checks for the local nAIM development environment."""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _version_tuple(raw: str) -> tuple[int, int, int]:
    parts = raw.strip().lstrip("v").split(".")
    return tuple(int(part) for part in (parts + ["0", "0"])[:3])


def _port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def main() -> int:
    checks: list[dict[str, object]] = []

    python_ok = sys.version_info >= (3, 12)
    checks.append(
        {
            "check": "python",
            "ok": python_ok,
            "found": sys.version.split()[0],
            "required": ">=3.12",
        }
    )

    node = shutil.which("node")
    node_version = "not found"
    node_ok = False
    if node:
        result = subprocess.run(
            [node, "--version"],
            capture_output=True,
            check=False,
            text=True,
        )
        node_version = result.stdout.strip() or result.stderr.strip()
        try:
            node_ok = _version_tuple(node_version) >= (22, 13, 0)
        except ValueError:
            node_ok = False
    checks.append(
        {
            "check": "node",
            "ok": node_ok,
            "found": node_version,
            "required": ">=22.13",
        }
    )

    checks.extend(
        {
            "check": f"port_{port}",
            "ok": _port_available(port),
            "found": "available" if _port_available(port) else "in use",
            "required": "available",
        }
        for port in (3000, 8000)
    )

    checks.append(
        {
            "check": "configuration",
            "ok": (ROOT / ".env.example").exists(),
            "found": str(ROOT / ".env.example"),
            "required": "present",
        }
    )

    print(json.dumps({"checks": checks}, indent=2))
    failed = [item for item in checks if not item["ok"]]
    if failed:
        print(
            "\nnAIM preflight found blocking items. "
            "Resolve the failed checks above, then run `make setup` again.",
            file=sys.stderr,
        )
        return 1
    print("\nnAIM environment is ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
