from __future__ import annotations

from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_honeypot_posture_plan_marks_h5_executed_and_points_to_h5_packet() -> None:
    root = _project_root()
    posture_plan = (
        root
        / "local_untracked"
        / "reports"
        / "CALAMUM_HONEYPOT_POSTURE_PLAN_20260410.md"
    ).read_text(encoding="utf-8")

    assert "Frame H5 was executed on `2026-04-11`." in posture_plan
    assert "CALAMUM_H5_COHERENCE_REVIEW_CHECKLIST_PACKET_20260411.md" in posture_plan
    assert "the next active move after H5 is to return to the parent D5 frame" in posture_plan
    assert "Frame H5 is not yet executed." not in posture_plan


def test_parent_stack_records_h5_materialization_and_resolves_honeypot_blocker() -> None:
    root = _project_root()
    parent_stack = (
        root
        / "local_untracked"
        / "reports"
        / "CALAMUM_CANONICAL_DS_REGENERATION_AND_SUBMISSION_PLAN_20260410.md"
    ).read_text(encoding="utf-8")

    assert "CALAMUM_H5_COHERENCE_REVIEW_CHECKLIST_PACKET_20260411.md" in parent_stack
    assert "H5 coherence review checklist is materialized" in parent_stack
    assert "honeypot platform interaction contract | now satisfied with bounded representative-traffic caution" in parent_stack
    assert "Frame D5 was executed on `2026-04-11`." in parent_stack
    assert "the next active frame after D5 is Frame D6" in parent_stack
    assert "| honeypot platform interaction contract | present blocker |" not in parent_stack


def test_priority_stack_routes_to_d6_after_d5_close() -> None:
    root = _project_root()
    priority_stack = (
        root
        / "planning"
        / "CALAMUM_FINAL_REPORT_PRIORITY_STACK_20260409.md"
    ).read_text(encoding="utf-8")

    assert "Frame D5 is now closed" in priority_stack
    assert "the next active lane is now Frame D6" in priority_stack
    assert "continue with **Frame D6**" in priority_stack
    assert "Frame D5 is still open" not in priority_stack


def test_parent_stack_materializes_d6_microplan_and_routes_to_execution() -> None:
    root = _project_root()
    parent_stack = (
        root
        / "local_untracked"
        / "reports"
        / "CALAMUM_CANONICAL_DS_REGENERATION_AND_SUBMISSION_PLAN_20260410.md"
    ).read_text(encoding="utf-8")

    assert "##### Frame D6 micro-plan — 2026-04-11" in parent_stack
    assert "Frame D6 was executed on `2026-04-11`." in parent_stack
    assert "Remaining work is now bounded submission/render/export/package sanity only" in parent_stack
    assert "##### Closeout micro-plan — 2026-04-11" in parent_stack
    assert "The bounded v1 ship/package closeout micro-plan was executed on `2026-04-11`." in parent_stack
    assert "remaining residue is now limited to the operator-chosen final PDF/docx export/package step" in parent_stack
    assert "submission venue does not require export/package handling" in parent_stack
    assert "local_untracked/package_lane_20260411T204051Z/" in parent_stack
    assert "local_untracked/package_lane_20260411T204051Z.zip" in parent_stack
    assert "no `pandoc`, `xelatex`, `pdflatex`, `tectonic`, `typst`, or `wkhtmltopdf` executable was available" in parent_stack
    assert "DATA7** course-deliverable expansion remains explicitly deferred" in parent_stack
    assert "full DS pipeline has been run successfully end-to-end" in parent_stack
    assert "honeypot-ready `TV-0` / `TV-3`-labeled dataset has been materialized" in parent_stack
    assert "Generate the micro-plan immediately before implementation." not in parent_stack


def test_priority_stack_routes_to_bounded_ship_package_after_d6_close() -> None:
    root = _project_root()
    priority_stack = (
        root
        / "planning"
        / "CALAMUM_FINAL_REPORT_PRIORITY_STACK_20260409.md"
    ).read_text(encoding="utf-8")

    assert "Frame D6 is now closed" in priority_stack
    assert "the D-frame stack is now complete" in priority_stack
    assert "bounded v1 ship/package sanity closeout micro-plan is now executed" in priority_stack
    assert "operator-chosen final export/package step even though the submission venue does not require it" in priority_stack
    assert "local_untracked/package_lane_20260411T204051Z/" in priority_stack
    assert "source bundle rather than a rendered PDF package" in priority_stack
    assert "DATA7** work remains deferred behind two explicit gates" in priority_stack
    assert "bounded **v1 ship/package export step**" in priority_stack
    assert "Do not reopen DATA7** tasks until the full pipeline has run successfully end-to-end" in priority_stack
    assert "the next active lane is now Frame D6" not in priority_stack
