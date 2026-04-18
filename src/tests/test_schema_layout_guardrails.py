from __future__ import annotations

import json
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_simulation_code_locality_under_src() -> None:
    root = _project_root()
    assert not (root / "simulation").exists(), "Top-level simulation/ must not exist after migration"

    src_sim = root / "src" / "simulation"
    assert src_sim.exists(), "src/simulation/ must exist"

    required = {
        "run_simulation.py",
        "calamum_observer_daemon.py",
        "README.md",
    }
    actual = {p.name for p in src_sim.iterdir() if p.is_file()}
    missing = sorted(required - actual)
    assert not missing, f"Missing expected simulation files under src/simulation: {missing}"


def test_jobs_and_operations_report_naming_boundaries() -> None:
    root = _project_root()

    jobs_dir = root / "jobs"
    local_reports_dir = root / "local_untracked" / "reports" / "operations"
    legacy_ops_reports_dir = root / "docs" / "reports" / "operations"
    legacy_queststack_reports_dir = root / "docs" / "reports" / "queststack"

    bad_in_jobs = sorted(
        p.name for p in jobs_dir.glob("**/*") if p.is_file() and p.name.startswith("JOB_REPORT_")
    )
    assert not bad_in_jobs, f"Job report files found in jobs/: {bad_in_jobs}"

    assert not legacy_ops_reports_dir.exists(), "Legacy docs/reports/operations/ must not exist after report-root realignment"
    assert not legacy_queststack_reports_dir.exists(), "Legacy docs/reports/queststack/ must not exist after report-root realignment"

    bad_in_reports = sorted(
        p.name for p in local_reports_dir.glob("**/*") if p.is_file() and p.name.startswith("CALAMUM_JOB_")
    )
    assert not bad_in_reports, f"Job definition files found in local_untracked/reports/operations/: {bad_in_reports}"


def test_manifest_authoritative_root_alignment() -> None:
    root = _project_root()
    manifest = json.loads((root / "PROJECT_MANIFEST.json").read_text(encoding="utf-8"))

    public_surface = manifest["public_surface"]
    content_roots = set(public_surface["content_roots"].keys())
    public_reports = set(manifest["public_reports"])
    tracked_roots = set(manifest["layout"]["tracked_roots"])

    assert "src/" in content_roots, "src/ must remain a public content root"
    assert "docs/manuals/" in content_roots, "docs/manuals/ must remain a public content root"
    assert "docs/reports/" in content_roots, "docs/reports/ must remain a public content root"
    assert "docs/Spring2026/" in content_roots, "docs/Spring2026/ must remain a public tracked writeup root"
    assert "docs/metrics/" not in content_roots, "docs/metrics/ must not appear as a public content root"
    assert "template_library/" in content_roots, "template_library/ must remain a public content root"
    assert "tools/" in content_roots, "tools/ must remain a public content root"
    assert "local_untracked/" not in content_roots, "local_untracked/ must not appear as a public content root"
    assert "semantics_staging/" not in tracked_roots, "semantics_staging/ must not remain in tracked product roots"

    assert "docs/reports/aggregates/AGGREGATE_REPORT.md" in public_reports, "Aggregate report must remain declared as a public report"
    assert "docs/reports/aggregates/PUBLIC_RUN_LEDGER.md" in public_reports, "Public run ledger must remain declared as a public report"
    assert "docs/reports/aggregates/LATEST_COLLECTIONS.md" in public_reports, "Latest collections aggregate must remain declared as a public report"
    assert "docs/reports/aggregates/WORKFLOW_ROLLUP.md" in public_reports, "Workflow rollup must remain declared as a public report"
    assert "docs/reports/aggregates/THRESHOLD_SUMMARY.md" in public_reports, "Threshold summary must remain declared as a public report"
    assert "docs/reports/reference/GENERATED_REPORT_SURFACES.md" in public_reports, "Generated-report reference must use the reference lane"
    assert "docs/reports/validations/INDEX.md" in public_reports, "Validation index must use the validations lane"
    assert "docs/reports/validations/APEXLAB_REFERENCE_VALIDATION_REPORT_20260324.md" in public_reports, "ApexLab validation markdown must remain declared as a public report"
    assert "docs/reports/validations/APEXLAB_REFERENCE_VALIDATION_REPORT_20260324.html" in public_reports, "ApexLab validation HTML must remain declared as a public report"

    assert "docs/reports/PUBLIC_RUN_LEDGER.md" not in public_reports, "Legacy root-level public run ledger path must not remain in the manifest"
    assert "docs/reports/AGGREGATE_REPORT.md" not in public_reports, "Legacy root-level aggregate report path must not remain in the manifest"
    assert "docs/reports/GENERATED_REPORT_SURFACES.md" not in public_reports, "Legacy root-level generated-report reference must not remain in the manifest"
    assert "docs/reports/AGGREGATE_REPORT_SCHEMA.md" not in public_reports, "Archived aggregate schema must not remain in the manifest"
    assert "docs/reports/ds/INDEX.md" not in public_reports, "Legacy DS publication index must not remain in the manifest"


def test_stale_tracked_seed_report_surfaces_remain_absent() -> None:
    root = _project_root()

    assert not (root / "docs" / "metrics").exists(), "docs/metrics/ must stay removed from the tracked documentation tree"
    assert not (root / "docs" / "reports" / "aggregates" / "cache").exists(), "docs/reports/aggregates/cache/ must stay absent from the tracked report tree"
    assert not (root / "docs" / "reports" / "collections" / "sample").exists(), "docs/reports/collections/sample/ must stay absent until a fresh sample packet is regenerated"


def test_stale_collection_report_landing_pages_remain_absent() -> None:
    root = _project_root()
    collection_reports_root = root / "docs" / "reports" / "collections"
    stale_report_paths = sorted(
        path.relative_to(root).as_posix()
        for path in collection_reports_root.glob("**/report.md")
        if path.is_file()
    )

    assert not stale_report_paths, f"Stale tracked collection landing pages found: {stale_report_paths}"


def test_validation_lane_retains_apex_reference_reports() -> None:
    root = _project_root()
    validations_root = root / "docs" / "reports" / "validations"
    validations_index = (validations_root / "INDEX.md").read_text(encoding="utf-8")
    apex_md = validations_root / "APEXLAB_REFERENCE_VALIDATION_REPORT_20260324.md"
    apex_html = validations_root / "APEXLAB_REFERENCE_VALIDATION_REPORT_20260324.html"

    assert apex_md.exists(), "ApexLab validation markdown must remain present in the tracked validations lane"
    assert apex_html.exists(), "ApexLab validation HTML must remain present in the tracked validations lane"
    assert apex_md.name in validations_index, "Validation index must route to the ApexLab validation markdown"
    assert apex_html.name in validations_index, "Validation index must route to the ApexLab validation HTML"


def test_reports_index_and_generated_surfaces_follow_current_public_report_contract() -> None:
    root = _project_root()
    reports_index = (root / "docs" / "reports" / "INDEX.md").read_text(encoding="utf-8")
    generated_surfaces = (root / "docs" / "reports" / "reference" / "GENERATED_REPORT_SURFACES.md").read_text(encoding="utf-8")

    for expected in (
        "aggregates/AGGREGATE_REPORT.md",
        "aggregates/PUBLIC_RUN_LEDGER.md",
        "aggregates/LATEST_COLLECTIONS.md",
        "aggregates/WORKFLOW_ROLLUP.md",
        "aggregates/THRESHOLD_SUMMARY.md",
        "reference/GENERATED_REPORT_SURFACES.md",
        "validations/INDEX.md",
        "How to use this report family",
        "Flagship synthesis narrative",
        "Front-door collection routing",
        "Threshold-bearing packet follow-through",
    ):
        assert expected in reports_index, f"Current report index must reference {expected}"

    assert "collection/report.md" not in reports_index, "Aggregate-facing report index routes must not continue to privilege the stable collection landing page"

    for forbidden in (
        "ds/INDEX.md",
        "docs/reports/PUBLIC_RUN_LEDGER.md",
        "docs/reports/AGGREGATE_REPORT.md",
    ):
        assert forbidden not in reports_index, f"Legacy report index reference must not remain: {forbidden}"

    for expected in (
        "docs/reports/aggregates/AGGREGATE_REPORT.md",
        "docs/reports/aggregates/PUBLIC_RUN_LEDGER.md",
        "docs/reports/collections/<collection-alias>/collection/YYYYMMDDTHHMMSSffffffZ.collection.md",
        "docs/reports/collections/<collection-alias>/processing/<stage>/YYYYMMDDTHHMMSSffffffZ.<stage>.md",
        "When published runs exist, they are rendered under `docs/reports/collections/<collection-alias>/`.",
        "Zero-state publication may leave `docs/reports/collections/` present but empty",
        "Aggregate-facing collection routes use the dated collection packet leaf",
        "No stable `collection/report.md` landing page is part of the current tracked packet contract.",
        "Aggregate-consumer route authority",
        "Aggregate surface roles",
        "Flagship synthesis narrative",
        "Runtime-safe population census",
        "Front-door collection routing",
        "Workflow-family overview",
        "Evaluation-only threshold follow-through",
        "Contract/reference surface",
        "whenever packet families are materialized",
        "Zero-state publication should remain honest",
        "AGGREGATE_REPORT.md",
        "PUBLIC_RUN_LEDGER.md",
        "LATEST_COLLECTIONS.md",
        "WORKFLOW_ROLLUP.md",
        "THRESHOLD_SUMMARY.md",
        "validations/INDEX.md",
    ):
        assert expected in generated_surfaces, f"Generated surfaces reference must describe {expected}"

    for forbidden in (
        "docs/reports/ds",
        "docs/reports/PUBLIC_RUN_LEDGER.md",
        "docs/reports/AGGREGATE_REPORT.md",
        "Published runs are rendered under `docs/reports/collections/<collection-alias>/`.",
    ):
        assert forbidden not in generated_surfaces, f"Legacy generated-surface reference must not remain: {forbidden}"


def test_honeypot_h_frame_packet_family_is_materialized_locally() -> None:
    root = _project_root()
    reports_root = root / "local_untracked" / "reports"

    expected_packets = {
        "CALAMUM_H1_TARGET_IDENTITY_PACKET_20260411.md",
        "CALAMUM_H2_OUTWARD_CONTENT_BANK_PACKET_20260411.md",
        "CALAMUM_H3_FRESHNESS_SCHEDULE_PACKET_20260411.md",
        "CALAMUM_H4_DISCOVERABILITY_MAP_PACKET_20260411.md",
        "CALAMUM_H5_COHERENCE_REVIEW_CHECKLIST_PACKET_20260411.md",
    }

    missing = sorted(name for name in expected_packets if not (reports_root / name).exists())
    assert not missing, f"Expected H-frame packet artifacts are missing: {missing}"


def test_active_final_deliverables_align_to_d2_through_d6_authority_chain() -> None:
    root = _project_root()
    final_writeup = (root / "deliverables" / "DATA780" / "BLIND_ML_FINAL_WRITEUP.md").read_text(encoding="utf-8")
    ethical_report = (root / "deliverables" / "DATA740" / "BLIND_ML_ETHICAL_ANALYSIS_REPORT.md").read_text(encoding="utf-8")

    for expected in (
        "dataset-p3-demo-current-20260406",
        "dataset-p3-provenance-labeled-20260410",
        "build_20260411T042407214529Z",
        "train_20260411T042431425146Z",
        "score_20260411T042449359583Z",
        "docs/reports/collections/liv-r8bc9/",
    ):
        assert expected in final_writeup, f"Final DATA780 write-up must align to the current D2-D4 authority chain: {expected}"

    for forbidden in (
        "selector run_id: `p3-demo-current-20260406`",
        "build_20260406T213204617082Z",
        "train_20260406T165940271708Z",
        "evaluate_20260406T211232484108Z",
        "score_20260406T170017731886Z",
        "tracked public report collection lane remained in honest zero-state even after explicit republish",
        "tracked public report collection lane is still in zero-state even after explicit republish",
    ):
        assert forbidden not in final_writeup, f"Final DATA780 write-up must not retain stale D6-preclose authority wording: {forbidden}"

    assert "docs/reports/collections/liv-r8bc9/" in ethical_report, "DATA740 ethical report must acknowledge the current tracked public report family"
    assert "public report publication lane is currently zero-state" not in ethical_report, "DATA740 ethical report must not describe the current report lane as zero-state"
    assert "returned a truthful zero-state publication outcome" not in ethical_report, "DATA740 ethical report must not retain the stale pre-D4 republish description"


def test_active_submission_readmes_point_to_current_final_surfaces() -> None:
    root = _project_root()
    data780_readme = (root / "deliverables" / "DATA780" / "README.md").read_text(encoding="utf-8")
    data740_readme = (root / "deliverables" / "DATA740" / "README.md").read_text(encoding="utf-8")

    assert "BLIND_ML_FINAL_WRITEUP.md" in data780_readme, "DATA780 README must point to the active final write-up"
    assert "current D2-D6 authority chain" in data780_readme, "DATA780 README must describe the current closeout authority basis"
    assert "R6 dataset and citation freeze" not in data780_readme, "DATA780 README must not describe the final write-up as R6-only"

    assert "BLIND_ML_ETHICAL_ANALYSIS_REPORT.md" in data740_readme, "DATA740 README must point to the active ethical final write-up"
    assert "current D2-D6 authority chain" in data740_readme, "DATA740 README must describe the current closeout authority basis"
    assert "R6 dataset and citation freeze" not in data740_readme, "DATA740 README must not describe the final write-up as R6-only"


def test_package_lane_bundle_artifacts_exist() -> None:
    root = _project_root()
    package_dirs = sorted((root / "local_untracked").glob("package_lane_*"))

    bundle_dirs = [path for path in package_dirs if path.is_dir()]
    bundle_zips = [path for path in package_dirs if path.is_file() and path.suffix.lower() == ".zip"]

    assert bundle_dirs, "At least one package_lane bundle directory must exist after package-lane execution"
    assert bundle_zips, "At least one package_lane zip archive must exist after package-lane execution"

    latest_bundle = sorted(bundle_dirs)[-1]
    assert (latest_bundle / "PACKAGE_MANIFEST.json").exists(), "Latest package_lane bundle must include PACKAGE_MANIFEST.json"
    assert (latest_bundle / "README.md").exists(), "Latest package_lane bundle must include README.md"


def test_public_contract_surfaces_are_scrubbed_of_dev_lineage() -> None:
    root = _project_root()
    contributing = (root / "CONTRIBUTING.md").read_text(encoding="utf-8")
    methodology = (root / "DATA_METHODOLOGY.md").read_text(encoding="utf-8")
    runtime_ops = (root / "docs" / "manuals" / "runtime" / "RUNTIME_OPERATIONS.md").read_text(encoding="utf-8")
    vscode_tasks = (root / ".vscode" / "tasks.json").read_text(encoding="utf-8")

    for forbidden in (
        "Academic Integrity",
        "coursework submission",
        "semester grading period",
        "Submission State",
    ):
        assert forbidden not in contributing, f"Contributing guide must not retain development-lineage wording: {forbidden}"

    for forbidden in (
        "PUBLIC / ACADEMIC OPEN",
        "Stage-4 scalar feature quartet",
        "frame8-proof-window",
    ):
        assert forbidden not in methodology, f"Methodology manual must not retain development-lineage wording: {forbidden}"

    for forbidden in (
        "quest logs",
        "quest evidence",
    ):
        assert forbidden not in runtime_ops, f"Runtime manual must not advertise internal workflow residue: {forbidden}"

    assert "semantics_staging/" not in vscode_tasks, "Active VS Code tasks must not target semantics_staging helpers"


def test_runtime_operator_docs_surface_bootstrap_readiness_path() -> None:
    root = _project_root()
    readme = (root / "README.md").read_text(encoding="utf-8")
    manual_index = (root / "docs" / "manuals" / "INDEX.md").read_text(encoding="utf-8")
    runtime_index = (root / "docs" / "manuals" / "runtime" / "INDEX.md").read_text(encoding="utf-8")
    runtime_workflows = (root / "docs" / "manuals" / "runtime" / "RUNTIME_WORKFLOWS.md").read_text(encoding="utf-8")
    runtime_ops = (root / "docs" / "manuals" / "runtime" / "RUNTIME_OPERATIONS.md").read_text(encoding="utf-8")
    contributing = (root / "CONTRIBUTING.md").read_text(encoding="utf-8")

    assert "observerctl ops bootstrap --json" in readme, "README must route operators to the bootstrap entry surface"
    assert "observerctl ops bootstrap --check --json" in readme, "README must surface non-mutating bootstrap validation"
    assert "[`runtime/INDEX.md`](runtime/INDEX.md) -> [`runtime/RUNTIME_WORKFLOWS.md`](runtime/RUNTIME_WORKFLOWS.md)" in manual_index, "Manual index must route runtime readers through the bootstrap-aware runtime index"
    assert "bootstrap readiness through closure and analysis handoff" in runtime_index, "Runtime index must describe bootstrap readiness as part of the operator path"
    assert "observerctl ops bootstrap --check --json" in runtime_workflows, "Runtime workflows must include bootstrap validation before runtime execution"
    assert "local_untracked/" in runtime_workflows, "Runtime workflows must explain the local runtime-root family explicitly"
    assert "Fresh environment or temp-root readiness" in runtime_ops, "Runtime operations must include a dedicated bootstrap playbook"
    assert "observerctl ops bootstrap --check --json" in runtime_ops, "Runtime operations must include bootstrap validation in common playbooks"
    assert "observerctl ops bootstrap --check --json" in contributing, "Contributing guide must include bootstrap validation in the typical workflow"


def test_packaged_docs_and_report_framework_boundary_is_explicit() -> None:
    root = _project_root()
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    manifest_in = (root / "MANIFEST.in").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    docs_index = (root / "docs" / "INDEX.md").read_text(encoding="utf-8")
    manuals_index = (root / "docs" / "manuals" / "INDEX.md").read_text(encoding="utf-8")
    methodology = (root / "DATA_METHODOLOGY.md").read_text(encoding="utf-8")
    contract_map = (root / "local_untracked" / "reports" / "CALAMUM_SHIPPED_PACKAGE_AND_PUBLIC_REPO_CONTRACT_MAP_20260411.md").read_text(encoding="utf-8")

    assert '"share/calamum-moltbook-observer/docs"' in pyproject, "Package metadata must ship the docs root entry surface"
    assert '"share/calamum-moltbook-observer/docs/manuals/runtime"' in pyproject, "Package metadata must ship runtime manuals"
    assert '"share/calamum-moltbook-observer/docs/manuals/data-science"' in pyproject, "Package metadata must ship data-science manuals"
    assert '"share/calamum-moltbook-observer/docs/manuals/reference"' in pyproject, "Package metadata must ship reference manuals"
    assert '"share/calamum-moltbook-observer/docs/reports"' in pyproject, "Package metadata must ship the report framework entry surface"
    assert '"share/calamum-moltbook-observer/docs/reports/aggregates"' in pyproject, "Package metadata must ship report aggregate framework surfaces"
    assert '"share/calamum-moltbook-observer/docs/reports/collections"' in pyproject, "Package metadata must preserve the structural report collections lane"
    assert '"share/calamum-moltbook-observer/docs/reports/reference"' in pyproject, "Package metadata must ship the generated-report reference surface"
    assert '"share/calamum-moltbook-observer/docs/reports/validations"' in pyproject, "Package metadata must ship the validation index surface"
    assert "recursive-include docs/manuals *.md" in manifest_in, "Installable source manifest must include the manual library"
    assert "include docs/reports/INDEX.md" in manifest_in, "Installable source manifest must include the report framework entry surface"
    assert "recursive-include docs/reports/aggregates *.md" in manifest_in, "Installable source manifest must include report aggregate framework surfaces"
    assert "include docs/reports/collections/.gitkeep" in manifest_in, "Installable source manifest must preserve the structural collections lane"
    assert "include docs/reports/reference/GENERATED_REPORT_SURFACES.md" in manifest_in, "Installable source manifest must include the generated-report reference surface"
    assert "include docs/reports/validations/INDEX.md" in manifest_in, "Installable source manifest must include the validation index surface"
    assert "Collection alias: `liv-r8bc9`" not in readme, "README must not package the current populated collection state as the shipped boundary"
    assert "docs/INDEX.md` + `docs/manuals/**` | tracked in the repo and shipped with the installable application package" in readme, "README must describe the shipped manual-library boundary"
    assert "docs/reports/INDEX.md`, `docs/reports/aggregates/*`, `docs/reports/reference/GENERATED_REPORT_SURFACES.md`, `docs/reports/validations/INDEX.md`, and the structural `docs/reports/collections/` lane | tracked in the repo and shipped as the report framework baseline" in readme, "README must describe the shipped report framework baseline"
    assert "adjacent tracked writeups under `docs/Spring2026/`" in readme, "README must classify the public Spring2026 writeups as tracked but unshipped"
    assert "tracked in the repo and shipped with the installable application package" in docs_index, "Docs index must describe the shipped docs-library boundary"
    assert "report framework baseline under [`reports/INDEX.md`](reports/INDEX.md)" in docs_index, "Docs index must describe the shipped report framework baseline"
    assert "[`Spring2026/INDEX.md`](Spring2026/INDEX.md) and the adjacent writeups under [`Spring2026/`](Spring2026/)" in docs_index, "Docs index must classify the Spring2026 writeup subtree explicitly"
    assert "tracked in the repo, not part of the shipped application package" in docs_index, "Docs index must keep Spring2026 writeups outside the shipped package boundary"
    assert "part of the shipped application documentation payload" in manuals_index, "Manual index must state that the manual library ships with the application package"
    assert "report framework baseline under [`docs/reports/`](docs/reports/)" in methodology, "Methodology manual must describe the shipped report framework baseline"
    assert "publication-derived repository surfaces built from canonical local artifacts" in methodology, "Methodology manual must keep populated tracked reports in the publication-derived lane"
    assert "`docs/INDEX.md` and `docs/manuals/**` | shipped documentation library for the installable application package" in contract_map, "Contract map must name the shipped docs subtree explicitly"
    assert "`docs/reports/INDEX.md`, aggregate surfaces, report reference, validation routing, and the structural `collections/` lane form the **v1 shipped report framework baseline**" in contract_map, "Contract map must name the shipped report framework baseline explicitly"
    assert "dated collection leaves, dated processing leaves, figure-backed packet content, and emitted validation packet leaves form **derived populated publication content**" in contract_map, "Contract map must keep populated report packets in the derived publication class"

    for forbidden in (
        "recursive-include docs/Spring2026",
        "recursive-include docs/reports *.md",
        "recursive-include docs/reports/collections *.md",
        "docs/reports/collections/liv-r8bc9",
        "DATA740_FinalProject_JoeWaller.pdf",
        "DATA780_FinalProject_JoeWaller.pdf",
        "APEXLAB_REFERENCE_VALIDATION_REPORT_20260324.md",
        "APEXLAB_REFERENCE_VALIDATION_REPORT_20260324.html",
    ):
        assert forbidden not in manifest_in, f"Installable source manifest must exclude derived populated report content: {forbidden}"


def test_active_surfaces_exclude_backup_and_oneoff_patch_artifacts() -> None:
    root = _project_root()

    assert not (root / "render_patch.py").exists(), "One-off root patch helpers must not remain in the active project root"
    assert not (root / "src" / "observerctl.py.bak").exists(), "Backup copies must not remain in the active source tree"

    src_backup_paths = sorted(
        path.relative_to(root).as_posix()
        for path in (root / "src").glob("**/*.bak")
        if path.is_file()
    )
    assert not src_backup_paths, f"Active source tree must not retain backup artifacts: {src_backup_paths}"


def test_semantics_staging_active_helper_inventory_is_cleared() -> None:
    root = _project_root()
    staging_root = root / "semantics_staging"

    remaining_files = sorted(
        path.relative_to(root).as_posix()
        for path in staging_root.glob("**/*")
        if path.is_file()
    )

    assert not remaining_files, f"Active semantics_staging helper inventory must be cleared after P5 classification: {remaining_files}"
