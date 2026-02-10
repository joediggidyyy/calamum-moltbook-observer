"""Repo health audit for the Calamum Moltbook Observer subtree.

This audit is intentionally *offline* and writes outputs to local_untracked/.
It is designed to be a tracked, school-friendly demonstration of provenance,
policy hygiene, and repo layout discipline.

Outputs:
- A markdown report rendered from a tracked template.
- A JSON evidence bundle (machine-readable details).
- An append-only JSONL audit log (untracked) that stores snapshots and baselines.

No secrets are printed or stored.

Run from repo root:
  .venv-core\\Scripts\\python.exe projects\\calamum-moltbook-observer\\tools\\audit_repo_health.py

Optional flags:
  --set-baseline   Writes a baseline record to the JSONL log (in addition to a snapshot).

"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


AUDITOR = "ORACL-Prime"


@dataclass(frozen=True)
class GitInfo:
    ok: bool
    head: str
    branch: str
    is_dirty: bool
    error: str = ""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _run(cmd: Sequence[str], cwd: Path, timeout_sec: float = 12.0) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(
            list(cmd),
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=float(timeout_sec),
            check=False,
        )
        return int(p.returncode), str(p.stdout or ""), str(p.stderr or "")
    except Exception as e:
        return 999, "", repr(e)


def _git_info(repo_root: Path) -> GitInfo:
    rc, out, err = _run(["git", "rev-parse", "--verify", "HEAD"], cwd=repo_root)
    if rc != 0:
        return GitInfo(ok=False, head="", branch="", is_dirty=False, error=(err.strip() or out.strip() or "git unavailable"))

    head = out.strip()

    rc, out, err = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root)
    branch = out.strip() if rc == 0 else ""

    rc, out, err = _run(["git", "status", "--porcelain"], cwd=repo_root)
    is_dirty = bool(out.strip()) if rc == 0 else False

    return GitInfo(ok=True, head=head, branch=branch, is_dirty=is_dirty)


def _git_ls_files(repo_root: Path, pathspec: str) -> List[str]:
    rc, out, err = _run(["git", "ls-files", "--", pathspec], cwd=repo_root, timeout_sec=30.0)
    if rc != 0:
        return []
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    return lines


def _git_check_ignore(repo_root: Path, rel_paths: Sequence[str]) -> Dict[str, bool]:
    """Returns {path: is_ignored}. Best-effort; missing git returns all False."""
    if not rel_paths:
        return {}

    # git check-ignore exits 0 if any matched, 1 if none matched
    # We'll call per path to keep parsing simple and to also avoid arg limits.
    out: Dict[str, bool] = {}
    for p in rel_paths:
        rc, _stdout, _stderr = _run(["git", "check-ignore", "-q", "--", p], cwd=repo_root)
        out[p] = (rc == 0)
    return out


def _render_template(tpl: str, data: Dict[str, Any]) -> str:
    out = str(tpl)
    for k, v in data.items():
        pat = re.compile(r"\{\{\s*" + re.escape(str(k)) + r"\s*\}\}")
        out = pat.sub(lambda _m, _v=str(v): _v, out)
    return out


def _safe_mkdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _write_text(p: Path, text: str) -> None:
    p.write_text(text, encoding="utf-8")


def _write_json(p: Path, obj: Any) -> None:
    p.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")


def _append_jsonl(p: Path, obj: Any) -> None:
    # Ensure ASCII-ish output expectations while keeping Unicode safe.
    line = json.dumps(obj, sort_keys=True, ensure_ascii=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(line)
        f.write("\n")


def _rel_to(path: Path, base: Path) -> str:
    try:
        return str(path.resolve().relative_to(base.resolve())).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def _load_template(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _block(lines: Sequence[str], empty_msg: str = "(none)") -> str:
    if not lines:
        return empty_msg
    return "\n".join([f"- {ln}" for ln in lines])


def _norm_status(raw: str) -> str:
    """Normalize status values across docs.

    Canonical values returned by this function:
      open | in-progress | blocked | completed
    """
    v = (raw or "").strip().lower()
    v = v.replace("_", "-")
    v = v.replace(" ", "-")
    v = re.sub(r"-+", "-", v)

    if v in {"", "unknown", "n/a", "na"}:
        return ""
    if v in {"active", "in-progress", "inprogress", "doing", "running"}:
        return "in-progress"
    if v in {"planned", "plan", "todo", "open", "opened", "pending", "queued", "backlog", "draft"}:
        return "open"
    if v in {"blocked", "stuck"}:
        return "blocked"
    if v in {"done", "closed", "complete", "completed"}:
        return "completed"
    return v


def _extract_status_from_markdown(text: str) -> str:
    """Best-effort status extraction from markdown."""
    if not text:
        return ""

    pats = [
        r"\*\*Status\*\*\s*:\s*([^\n\r]+)",
        r"^-\s*Status\s*:\s*`([^`]+)`",
        r"^-\s*Status\s*:\s*([^\n\r]+)",
    ]
    for pat in pats:
        m = re.search(pat, text, flags=re.IGNORECASE | re.MULTILINE)
        if not m:
            continue
        raw = (m.group(1) or "").strip()
        # Trim common trailing punctuation.
        raw = raw.rstrip(" .")
        return _norm_status(raw)
    return ""


def _extract_backticked_paths(text: str) -> List[str]:
    if not text:
        return []
    # Keep it simple: paths are consistently wrapped in backticks in this repo.
    items = re.findall(r"`([^`]+)`", text)
    out: List[str] = []
    for it in items:
        it = (it or "").strip()
        if not it:
            continue
        # Exclude obvious non-path payloads.
        if " " in it:
            continue
        out.append(it)
    return out


def _load_jsonc_best_effort(path: Path) -> Any:
    """Load JSON/JSONC using core helper if available."""
    try:
        from codesentinel.utils.jsonc_utils import load_jsonc  # type: ignore

        return load_jsonc(path)
    except Exception:
        raw = path.read_text(encoding="utf-8", errors="ignore")
        return json.loads(raw)


def _check_job_status_sync(repo_root: Path, project_root: Path) -> Dict[str, Any]:
    """Verify that job status is consistent across SSOT + referenced docs.

    Canonical status source is operations/tasks.json for tasks scoped to this project.
    """
    rel_project = _rel_to(project_root, repo_root).replace("\\", "/")
    tasks_path = (repo_root / "operations" / "tasks.json").resolve()
    dashboard_path = (repo_root / "docs" / "dashboards" / "room" / "JOBS_DASHBOARD.md").resolve()

    result: Dict[str, Any] = {
        "tasks_path": str(tasks_path),
        "dashboard_path": str(dashboard_path),
        "checked_task_count": 0,
        "violations": [],  # list[dict]
        "notes": [],
    }

    try:
        payload = _load_jsonc_best_effort(tasks_path)
    except Exception as e:
        result["notes"].append(f"[ERR] could not load operations/tasks.json: {e}")
        return result

    tasks: List[Dict[str, Any]] = payload if isinstance(payload, list) else []
    scoped: List[Dict[str, Any]] = []
    for t in tasks:
        if not isinstance(t, dict):
            continue
        t_path = str(t.get("path") or "").replace("\\", "/")
        if not t_path:
            continue
        if t_path.startswith(rel_project + "/"):
            scoped.append(t)

    result["checked_task_count"] = len(scoped)

    # Build a quick lookup for dashboard rows: {task_id: status}
    dash_status: Dict[str, str] = {}
    try:
        dash_text = dashboard_path.read_text(encoding="utf-8", errors="ignore")
        for ln in dash_text.splitlines():
            if not ln.startswith("|"):
                continue
            parts = [p.strip() for p in ln.strip().strip("|").split("|")]
            if len(parts) < 6:
                continue
            task_id = parts[0]
            status_raw = parts[5]
            if task_id and status_raw:
                dash_status[task_id] = _norm_status(status_raw)
    except Exception:
        # Non-fatal.
        pass

    for t in scoped:
        task_id = str(t.get("id") or "").strip()
        t_path = str(t.get("path") or "").replace("\\", "/")
        expected = _norm_status(str(t.get("status") or ""))
        if not task_id or not t_path or not expected:
            continue

        def add_violation(doc_path: str, found: str, expected_status: str, reason: str) -> None:
            result["violations"].append(
                {
                    "task_id": task_id,
                    "expected": expected_status,
                    "found": found,
                    "doc": doc_path,
                    "reason": reason,
                }
            )

        # Check Jobs dashboard derived view.
        dash_found = dash_status.get(task_id, "")
        if dash_found and dash_found != expected:
            add_violation(
                _rel_to(dashboard_path, repo_root),
                dash_found,
                expected,
                "dashboard status mismatch (derived view appears stale)",
            )

        # Check QuestStack doc status.
        qs_abs = (repo_root / t_path).resolve()
        if qs_abs.exists():
            try:
                qs_text = qs_abs.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                qs_text = ""
            qs_found = _extract_status_from_markdown(qs_text)
            if qs_found and qs_found != expected:
                add_violation(_rel_to(qs_abs, repo_root), qs_found, expected, "QuestStack status mismatch")
            if not qs_found:
                add_violation(_rel_to(qs_abs, repo_root), "(missing)", expected, "QuestStack status not found")

            # Check referenced job docs + job report statuses.
            for rel in _extract_backticked_paths(qs_text):
                rel_norm = rel.replace("\\", "/")
                # Only check repo-relative paths.
                if rel_norm.startswith("http://") or rel_norm.startswith("https://"):
                    continue

                is_status_bearing = False
                if rel_norm.startswith("jobs/"):
                    is_status_bearing = True
                if rel_norm.startswith(rel_project + "/jobs/"):
                    is_status_bearing = True
                if rel_norm.startswith("docs/reports/operations/JOB_REPORT_"):
                    is_status_bearing = True

                # Avoid false positives: only enforce status sync for known status-bearing docs.
                if not is_status_bearing:
                    continue

                doc_abs = (repo_root / rel_norm).resolve()
                if not doc_abs.exists():
                    continue

                # Only files can carry a status field; ignore directory references like `jobs/`.
                if not doc_abs.is_file():
                    continue

                suffix = doc_abs.suffix.lower()
                found = ""
                if suffix == ".md":
                    try:
                        found = _extract_status_from_markdown(doc_abs.read_text(encoding="utf-8", errors="ignore"))
                    except Exception:
                        found = ""
                elif suffix == ".json":
                    try:
                        obj = json.loads(doc_abs.read_text(encoding="utf-8", errors="ignore") or "{}")
                        if isinstance(obj, dict):
                            found = _norm_status(str(obj.get("status") or ""))
                    except Exception:
                        found = ""

                if is_status_bearing and not found:
                    add_violation(rel_norm, "(missing)", expected, "status not found in referenced job document")
                if found and found != expected:
                    add_violation(rel_norm, found, expected, "referenced job document status mismatch")

    return result


def _detect_redundant_dirs(project_root: Path, repo_root: Path) -> List[str]:
    """Heuristic: top-level dirs that are empty or contain no tracked files."""
    allow = {
        "assets",
        "docs",
        "jobs",
        "launchers",
        "planning",
        "queststacks",
        "src",
        "template_library",
        "tools",
        "local_untracked",
    }

    candidates: List[str] = []
    try:
        for child in sorted(project_root.iterdir()):
            if not child.is_dir():
                continue
            name = child.name
            if name.startswith("."):
                continue
            if name in allow:
                continue

            tracked_under = _git_ls_files(repo_root, _rel_to(child, repo_root))
            has_tracked = bool(tracked_under)

            # Consider "empty" as no non-hidden entries.
            try:
                entries = [p for p in child.iterdir() if not p.name.startswith(".")]
            except Exception:
                entries = []

            if (not has_tracked) and (not entries):
                candidates.append(f"{_rel_to(child, project_root)}/ (empty, no tracked files)")
            elif not has_tracked:
                candidates.append(f"{_rel_to(child, project_root)}/ (no tracked files; consider local_untracked/)")
    except Exception as e:
        candidates.append(f"[ERR] redundant-dir scan failed: {e}")

    # Explicit reminders for known drift patterns.
    if (project_root / "src" / "docs" / "audits").exists():
        candidates.append("src/docs/audits/ (consider removing or keeping empty by design; outputs belong in local_untracked/)")

    return candidates


def _ensure_manifest(project_root: Path) -> Tuple[Path, bool, bool, str]:
    """Ensures a manifest exists. Returns (path, existed, created, error)."""
    manifest = project_root / "PROJECT_MANIFEST.json"
    existed = manifest.exists()
    created = False
    err = ""

    if existed:
        return manifest, True, False, ""

    # Minimal, safe default.
    try:
        stub = {
            "project": {
                "id": "calamum-moltbook-observer",
                "name": "Calamum Moltbook Observer",
                "scope": "projects/calamum-moltbook-observer",
                "created_utc": _utc_now(),
            },
            "layout": {
                "tracked_roots": ["tools/", "template_library/", "src/"],
                "ignored_roots": ["local_untracked/"],
            },
            "version": "1.0",
        }
        _write_json(manifest, stub)
        created = True
    except Exception as e:
        err = repr(e)

    return manifest, False, created, err


def audit_repo_health(
    repo_root: Path,
    project_root: Path,
    template_rel: str,
    out_dir_rel: str,
    jsonl_rel: str,
    set_baseline: bool,
    dry_run: bool,
) -> Dict[str, Any]:
    ts = _utc_now()
    run_id = uuid.uuid4().hex

    git = _git_info(repo_root)

    tpl_path = (repo_root / template_rel).resolve()
    out_dir = (project_root / out_dir_rel).resolve()
    jsonl_path = (project_root / jsonl_rel).resolve()

    index_path = (project_root / "local_untracked" / "audit_log" / "audit_index.json").resolve()

    if not dry_run:
        _safe_mkdir(out_dir)
        _safe_mkdir(jsonl_path.parent)
        _safe_mkdir(index_path.parent)

    report_path = out_dir / f"calamum_repo_health_audit_{ts.replace(':', '').replace('-', '').replace('Z', 'Z')}.md"
    evidence_path = out_dir / (report_path.stem + ".evidence.json")

    manifest_path = (project_root / "PROJECT_MANIFEST.json").resolve()
    manifest_existed = manifest_path.exists()
    manifest_created = False
    manifest_err = ""
    if not manifest_existed and not dry_run:
        manifest_path, manifest_existed, manifest_created, manifest_err = _ensure_manifest(project_root)

    # Tracked files under this project.
    rel_project = _rel_to(project_root, repo_root)
    tracked = _git_ls_files(repo_root, rel_project)

    deny_substrings = [
        "/local_untracked/",
        "/src/logs/",
        "/src/.agent_session/",
        "/logs/",
        "/archive/",  # historical drift pattern
    ]
    deny_ext = [".log", ".jsonl", ".sqlite", ".db", ".pid", ".pem", ".key"]

    tracked_should_not: List[str] = []
    for p in tracked:
        p_norm = p.replace("\\", "/")
        if any(s in p_norm for s in deny_substrings):
            tracked_should_not.append(p_norm)
            continue
        if any(p_norm.lower().endswith(ext) for ext in deny_ext):
            tracked_should_not.append(p_norm)

    # Ignored-policy checks (best-effort using git).
    expect_ignored = [
        f"{rel_project}/local_untracked",
        f"{rel_project}/local_untracked/",
    ]
    ignored_map = _git_check_ignore(repo_root, expect_ignored)
    ignore_policy_violations = [p for p, ok in ignored_map.items() if not ok]

    redundant_dirs = _detect_redundant_dirs(project_root, repo_root)

    job_status_sync = _check_job_status_sync(repo_root, project_root)
    job_status_violations = job_status_sync.get("violations")
    job_status_violations_count = len(job_status_violations) if isinstance(job_status_violations, list) else 0

    # Recommendations (simple, school-friendly, but grounded).
    recs: List[str] = []
    if tracked_should_not:
        recs.append("De-track the listed paths and move them under local_untracked/. Add/adjust .gitignore as needed.")
    if ignore_policy_violations:
        recs.append("Fix .gitignore so local_untracked/ is always ignored (git check-ignore should succeed).")
    if redundant_dirs:
        recs.append("Consider consolidating untracked-only directories into local_untracked/ to keep the published tree minimal.")
    if job_status_violations_count:
        recs.append("Job status sync findings: align job/QuestStack/job-report statuses with operations/tasks.json (SSOT).")
    if not manifest_existed and manifest_created:
        recs.append("Review the generated PROJECT_MANIFEST.json and expand tracked/ignored roots to match intended layout.")
    if manifest_err:
        recs.append(f"Manifest creation failed: {manifest_err}")

    summary_ok = (not tracked_should_not) and (not ignore_policy_violations) and (job_status_violations_count == 0)
    summary_line = "[OK] repo hygiene looks consistent" if summary_ok else "[WARN] repo hygiene findings present"

    evidence: Dict[str, Any] = {
        "timestamp_utc": ts,
        "run_id": run_id,
        "auditor": AUDITOR,
        "dry_run": bool(dry_run),
        "repo_root": str(repo_root),
        "project_root": str(project_root),
        "git": {
            "ok": git.ok,
            "head": git.head,
            "branch": git.branch,
            "is_dirty": git.is_dirty,
            "error": git.error,
        },
        "manifest": {
            "path": str(manifest_path),
            "existed": manifest_existed,
            "created": manifest_created,
            "error": manifest_err,
        },
        "checks": {
            "tracked_file_count": len(tracked),
            "tracked_should_not_be_tracked": tracked_should_not,
            "ignore_policy_violations": ignore_policy_violations,
            "redundant_dir_candidates": redundant_dirs,
            "job_status_sync": job_status_sync,
        },
        "outputs": {
            "report_path": str(report_path),
            "evidence_path": str(evidence_path),
            "audit_jsonl_path": str(jsonl_path),
            "audit_index_path": str(index_path),
        },
        "recommendations": recs,
    }

    # Render report.
    try:
        tpl = _load_template(tpl_path)
    except Exception as e:
        tpl = "# Repo Health Audit\n\n[ERR] Could not load template: {{ template_path }}\n"
        evidence["template_error"] = repr(e)

    report_vars: Dict[str, Any] = {
        "timestamp_utc": ts,
        "run_id": run_id,
        "auditor": AUDITOR,
        "repo_root": str(repo_root),
        "project_root": str(project_root),
        "git_branch": git.branch,
        "git_head": git.head,
        "git_is_dirty": str(bool(git.is_dirty)),
        "summary_line": summary_line,
        "tracked_should_not_be_tracked_block": _block(tracked_should_not),
        "ignore_policy_violations_block": _block(ignore_policy_violations),
        "redundant_dir_candidates_block": _block(redundant_dirs),
        "job_status_sync_summary": "[OK] job status appears consistent" if job_status_violations_count == 0 else f"[WARN] job status drift detected ({job_status_violations_count} mismatches)",
        "job_status_sync_block": _block(
            [
                f"{v.get('task_id','?')}: expected={v.get('expected','?')} found={v.get('found','?')} doc={v.get('doc','?')} reason={v.get('reason','?')}"
                for v in (job_status_violations if isinstance(job_status_violations, list) else [])
            ],
            empty_msg="(no mismatches found)",
        ),
        "manifest_path": str(manifest_path),
        "manifest_existed": str(bool(manifest_existed)),
        "manifest_created": str(bool(manifest_created)),
        "recommendations_block": _block(recs, empty_msg="(no recommendations)"),
        "evidence_path": str(evidence_path),
        "audit_jsonl_path": str(jsonl_path),
        "template_path": str(tpl_path),
    }

    report_text = _render_template(tpl, report_vars)
    if not dry_run:
        _write_text(report_path, report_text)
        _write_json(evidence_path, evidence)

    # Append JSONL snapshot + optional baseline.
    jsonl_snapshot = {
        "kind": "snapshot",
        "timestamp_utc": ts,
        "run_id": run_id,
        "auditor": AUDITOR,
        "git": {
            "head": git.head,
            "branch": git.branch,
            "is_dirty": git.is_dirty,
        },
        "checks": evidence["checks"],
        "manifest": evidence["manifest"],
        "report": str(report_path),
        "evidence": str(evidence_path),
        "summary": summary_line,
    }
    if not dry_run:
        _append_jsonl(jsonl_path, jsonl_snapshot)

    if set_baseline and not dry_run:
        jsonl_baseline = dict(jsonl_snapshot)
        jsonl_baseline["kind"] = "baseline"
        jsonl_baseline["baseline_id"] = uuid.uuid4().hex
        _append_jsonl(jsonl_path, jsonl_baseline)

    # Central audit index (untracked convenience pointer).
    if not dry_run:
        try:
            existing: Dict[str, Any] = {}
            if index_path.exists():
                existing = json.loads(index_path.read_text(encoding="utf-8", errors="ignore") or "{}")
            if not isinstance(existing, dict):
                existing = {}
        except Exception:
            existing = {}

        audits_raw = existing.get("audits")
        audits: Dict[str, Any] = audits_raw if isinstance(audits_raw, dict) else {}
        audits["repo_health"] = {
            "timestamp_utc": ts,
            "run_id": run_id,
            "git": {"head": git.head, "branch": git.branch, "is_dirty": git.is_dirty},
            "report": _rel_to(report_path, repo_root),
            "evidence": _rel_to(evidence_path, repo_root),
            "jsonl": _rel_to(jsonl_path, repo_root),
        }
        existing["updated_at_utc"] = ts
        existing["git"] = {"head": git.head, "branch": git.branch, "is_dirty": git.is_dirty}
        existing["audits"] = audits

        try:
            _write_json(index_path, existing)
        except Exception:
            pass

    return evidence


def _repo_root_from_here(here: Path) -> Tuple[Path, Path]:
    # .../projects/calamum-moltbook-observer/tools/audit_repo_health.py
    project_root = here.resolve().parents[1]
    repo_root = here.resolve().parents[3]
    return repo_root, project_root


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Calamum repo health audit")
    ap.add_argument(
        "--template",
        default="projects/calamum-moltbook-observer/template_library/reports/CALAMUM_REPO_HEALTH_AUDIT_TEMPLATE.md.template",
        help="Repo-relative path to the markdown template",
    )
    ap.add_argument(
        "--out-dir",
        default="local_untracked/audits/repo_health",
        help="Project-relative output directory (should be ignored)",
    )
    ap.add_argument(
        "--jsonl",
        default="local_untracked/audit_log/repo_health_audit.jsonl",
        help="Project-relative JSONL audit log (append-only, should be ignored)",
    )
    ap.add_argument(
        "--set-baseline",
        action="store_true",
        help="Also append a baseline entry to the JSONL audit log",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute findings and print would-be output paths, but do not write any files",
    )
    ap.add_argument(
        "--print-job-status-drift",
        action="store_true",
        help="Print job status drift mismatches to stdout (names-only; safe in --dry-run)",
    )
    args = ap.parse_args(argv)

    repo_root, project_root = _repo_root_from_here(Path(__file__))

    evidence = audit_repo_health(
        repo_root=repo_root,
        project_root=project_root,
        template_rel=str(args.template),
        out_dir_rel=str(args.out_dir),
        jsonl_rel=str(args.jsonl),
        set_baseline=bool(args.set_baseline),
        dry_run=bool(args.dry_run),
    )

    # Console summary (ASCII-only).
    summary = str(evidence.get("recommendations") or [])
    if args.dry_run:
        print("Calamum repo health audit DRY-RUN complete")
    else:
        print("Calamum repo health audit complete")
    print(f"project_root: {project_root}")
    print(f"report:       {evidence['outputs']['report_path']}")
    print(f"evidence:     {evidence['outputs']['evidence_path']}")
    print(f"audit_jsonl:  {evidence['outputs']['audit_jsonl_path']}")
    print(f"audit_index:  {evidence['outputs'].get('audit_index_path', '')}")
    print(f"summary:      {evidence.get('checks', {}).get('tracked_file_count', '?')} tracked files scanned")
    if evidence.get("checks", {}).get("tracked_should_not_be_tracked"):
        cnt = len(evidence.get("checks", {}).get("tracked_should_not_be_tracked") or [])
        print(f"[WARN] tracked files that look untracked-only were found ({cnt}; see report)")
    if evidence.get("checks", {}).get("ignore_policy_violations"):
        print("[WARN] ignore policy violations found (see report)")
    js = (evidence.get("checks", {}) or {}).get("job_status_sync")
    if isinstance(js, dict):
        viol = js.get("violations")
        if isinstance(viol, list) and viol:
            print(f"[WARN] job status drift detected ({len(viol)} mismatches; see report)")

    if bool(getattr(args, "print_job_status_drift", False)):
        js = (evidence.get("checks", {}) or {}).get("job_status_sync")
        viol = js.get("violations") if isinstance(js, dict) else None
        if isinstance(viol, list) and viol:
            print("\njob status drift details (names-only):")
            for v in viol:
                if not isinstance(v, dict):
                    continue
                task_id = str(v.get("task_id") or "?")
                expected = str(v.get("expected") or "?")
                found = str(v.get("found") or "?")
                doc = str(v.get("doc") or "?")
                reason = str(v.get("reason") or "?")
                print(f"- {task_id}: expected={expected} found={found} doc={doc} reason={reason}")
        else:
            print("\njob status drift details (names-only): (none)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
