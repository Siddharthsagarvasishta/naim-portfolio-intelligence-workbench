import json
from pathlib import Path

from naim_risk.config import CONFIG_ROOT, MODEL_ROOT, REPOSITORY_ROOT, load_config


def test_bundled_governed_defaults_match_repository_sources() -> None:
    package_root = REPOSITORY_ROOT / "src" / "naim_risk" / "resources"
    pairs = [
        (REPOSITORY_ROOT / "config" / name, package_root / "config" / name)
        for name in (
            "alert_rules.json",
            "dataset_profiles.json",
            "economic_scenarios.json",
            "metric_registry.json",
            "rating_methodologies.json",
        )
    ]
    pairs.append(
        (
            REPOSITORY_ROOT / "models" / "analysis_template_registry.json",
            package_root / "models" / "analysis_template_registry.json",
        )
    )
    for source, bundled in pairs:
        assert json.loads(source.read_text(encoding="utf-8")) == json.loads(
            bundled.read_text(encoding="utf-8")
        )


def test_resolved_configuration_and_model_roots_are_usable(tmp_path: Path) -> None:
    assert (CONFIG_ROOT / "dataset_profiles.json").is_file()
    assert (MODEL_ROOT / "analysis_template_registry.json").is_file()
    config = load_config("test", data_root=tmp_path)
    assert config.profile.name == "test"
