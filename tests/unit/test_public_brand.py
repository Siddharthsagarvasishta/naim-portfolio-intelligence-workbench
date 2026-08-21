from pathlib import Path

from naim_risk.api import app, root
from scripts.check_public_brand import ROOT, scan, scan_public_binary_assets


def test_active_public_text_uses_only_the_canonical_brand() -> None:
    violations, _ = scan()
    assert violations == []


def test_public_social_asset_is_current_and_correctly_sized() -> None:
    assert scan_public_binary_assets() == []


def test_canonical_identity_contract_is_published() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    layout = (ROOT / "app" / "layout.tsx").read_text(encoding="utf-8")
    api = (ROOT / "src" / "naim_risk" / "api.py").read_text(encoding="utf-8")
    expected = (
        "nAIM Portfolio Intelligence Workbench",
        "Name the movement. Own the evidence.",
        "All Is Mine",
    )
    for value in expected:
        assert value in readme
        assert value in layout or value in api
    assert Path(ROOT / "src" / "naim_risk").is_dir()


def test_public_api_identity_contract() -> None:
    identity = root()
    assert app.title == "nAIM Portfolio Intelligence Workbench API"
    assert identity["name"] == "nAIM Portfolio Intelligence Workbench"
    assert identity["pronunciation"] == "name"
    assert identity["aim_expansion"] == "All Is Mine"
    assert identity["tagline"] == "Name the movement. Own the evidence."
