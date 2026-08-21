"""Register the current canonical derivative artifacts in the release manifest ledger."""

from __future__ import annotations

import json
from dataclasses import replace

from generate_artifact_manifests import (
    REPOSITORY_ROOT,
    ManifestContext,
    ProvenanceValue,
    build_manifest,
    portable_path,
    write_manifest,
)

from naim_risk.runtime_modes import dataset_hash

CANONICAL_PATH = REPOSITORY_ROOT / "exports" / "validation" / "interop_evidence_snapshot.json"


def manifest_context() -> ManifestContext:
    canonical = json.loads(CANONICAL_PATH.read_text(encoding="utf-8"))
    run_id = str(canonical["metadata"]["run_id"])
    run_manifest = REPOSITORY_ROOT / "data" / "manifests" / run_id / "run_manifest.json"
    dataset_digest, _basis = dataset_hash(run_manifest, REPOSITORY_ROOT / "data")
    return ManifestContext(
        source_snapshot_id=run_id,
        data_mode="OFFLINE_SNAPSHOT",
        reporting_period=str(canonical["selected_reporting_period"]),
        comparison_period="2025-07-01",
        dataset_profile=str(canonical["metadata"]["profile"]),
        dataset_hash=ProvenanceValue(dataset_digest),
        configuration_hash=ProvenanceValue(canonical["metadata"]["configuration_hash"]),
        model_version=ProvenanceValue("1.0.0"),
        api_version=ProvenanceValue("1.0.0"),
        script_version=ProvenanceValue("2.0.0"),
        metric_registry_version=str(canonical["metadata"]["metric_registry_version"]),
        filter_scope={
            "headline_scope": "all_portfolio",
            "approved_reference_basket": "BASKET-001",
            "scenario": "Baseline",
            "workspace": None,
        },
        evidence_ids=(str(canonical["evidence_id"]),),
        data_quality_result=str(canonical["data_quality"]["status"]),
        synthetic_data=bool(canonical["synthetic_data_flag"]),
        validation_status="PASS",
        creator="scripts.build_derivative_release_manifests",
        artifact_version="2.0.0",
        dependencies=(
            "exports/validation/interop_evidence_snapshot.json",
            f"data/manifests/{run_id}/run_manifest.json",
        ),
        validation_tests=("canonical_lineage", "artifact_sha256"),
        caveats=(
            "All figures are synthetic, institution-neutral demonstration data.",
            "Recommendations require human review and explicit approval.",
        ),
    )


def main() -> None:
    base = manifest_context()
    artifacts: tuple[tuple[str, str, tuple[str, ...], tuple[str, ...]], ...] = (
        (
            "outputs/nAIM_Portfolio_Intelligence_Workbench.xlsx",
            "PASS",
            ("office_workbook_validation", "formula_and_visual_qa"),
            ("outputs/validation/office_workbook_validation.json",),
        ),
        (
            "outputs/nAIM_Portfolio_Intelligence_Review.pptx",
            "PASS",
            ("all_slide_render", "template_fidelity", "visual_qa"),
            ("outputs/validation/office_presentation_validation.json",),
        ),
        (
            "outputs/tableau/nAIM_Portfolio_Intelligence.hyper",
            "PASS",
            ("official_hyper_api", "table_control_totals", "extract_reopen"),
            ("outputs/tableau/nAIM_Portfolio_Intelligence.manifest.json",),
        ),
        (
            "outputs/share_site/index.html",
            "PASS",
            ("static_site_validation", "file_ledger", "canonical_story"),
            ("outputs/share_site/validation.json", "outputs/share_site/build_manifest.json"),
        ),
        (
            "outputs/linkedin/nAIM_LinkedIn_Carousel.pptx",
            "PASS",
            ("slides_test_no_overflow", "all_slide_render", "visual_qa"),
            ("outputs/linkedin/package-manifest.json",),
        ),
        (
            "outputs/linkedin/nAIM_LinkedIn_Carousel.pdf",
            "PASS",
            ("libreoffice_conversion", "poppler_all_page_render", "visual_qa"),
            ("outputs/linkedin/package-manifest.json",),
        ),
        (
            "outputs/nAIM_PowerBI_Desktop_Package.zip",
            "STATIC_VALIDATION_PASS",
            ("pbip_static_validation", "portable_source_package"),
            ("outputs/powerbi/nAIM.PowerBIProject/Build/project-manifest.json",),
        ),
        (
            "outputs/nAIM_Tableau_Desktop_Package.zip",
            "PASS",
            ("official_hyper_api", "portable_source_package"),
            ("outputs/tableau/nAIM_Portfolio_Intelligence.manifest.json",),
        ),
        (
            "outputs/nAIM_SAS_Compatibility_Package.zip",
            "STATIC_VALIDATION_PASS",
            ("sas_program_static_validation", "portable_source_package"),
            (),
        ),
        (
            "outputs/nAIM_LinkedIn_Showcase.zip",
            "PASS",
            ("editable_and_pdf_carousel", "file_ledger", "visual_qa"),
            ("outputs/linkedin/package-manifest.json",),
        ),
        (
            "outputs/nAIM_Static_Share_Package.zip",
            "PASS",
            ("static_site_validation", "portable_source_package"),
            ("outputs/share_site/validation.json",),
        ),
        (
            "outputs/nAIM_Interoperability_Package.zip",
            "PASS",
            ("canonical_flattening", "portable_source_package"),
            ("exports/validation/interop_evidence_snapshot.json",),
        ),
    )
    written: list[str] = []
    for artifact_text, validation_status, tests, evidence in artifacts:
        artifact = REPOSITORY_ROOT / artifact_text
        if not artifact.is_file():
            raise FileNotFoundError(artifact)
        context = replace(
            base,
            validation_status=validation_status,
            validation_tests=base.validation_tests + tests,
            validation_evidence=evidence,
            caveats=(
                *base.caveats,
                *(
                    (
                        "Power BI Desktop validation was not executed; this is a static PBIP source package.",
                    )
                    if "PowerBI" in artifact.name
                    else ()
                ),
                *(
                    ("SAS runtime validation was not executed in this environment.",)
                    if "SAS" in artifact.name
                    else ()
                ),
            ),
        )
        payload = build_manifest(
            artifact,
            context,
            source_inputs=[CANONICAL_PATH],
        )
        written.append(portable_path(write_manifest(payload, artifact), REPOSITORY_ROOT))
    print(json.dumps({"status": "PASS", "manifests": written}, indent=2))


if __name__ == "__main__":
    main()
