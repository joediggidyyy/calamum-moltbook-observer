"""Implementation drift audit ("what we say" vs "what exists").

This audit is intentionally *offline* and writes outputs to local_untracked/.
It is designed to complement the Calamum repo-hygiene audit by focusing on
status/contract drift across *the whole repository* while keeping output
names-only and school-friendly.

Outputs:
- A markdown report rendered from a tracked template.
- A JSON evidence bundle (machine-readable details).
- An append-only JSONL audit log (untracked) that stores snapshots and baselines.

No secrets are printed or stored.

Run from repo root:
  .venv-core\\Scripts\\python.exe projects\\calamum-moltbook-observer\\tools\\audit_implementation_drift.py

Optional flags:
  --set-baseline   Also append a baseline entry to the JSONL log.
  --dry-run        Compute findings but do not write any files.

"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
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


def _run(cmd: Sequence[str], cwd: Path, timeout_sec: float = 20.0) -> Tuple[int, str, str]:
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

    rc, out, _err = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root)
    branch = out.strip() if rc == 0 else ""

    rc, out, _err = _run(["git", "status", "--porcelain"], cwd=repo_root)
    is_dirty = bool(out.strip()) if rc == 0 else False

    return GitInfo(ok=True, head=head, branch=branch, is_dirty=is_dirty)


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
    """Normalize status tokens across SSOT + markdown docs.

    Notes:
    - Many docs contain markdown styling (e.g. **completed**) or emoji markers.
    - We normalize to a small, comparable set while preserving uncommon states.
    """
    v = (raw or "").strip().lower()

    # Remove common markdown formatting noise.
    v = v.replace("`", "")
    v = v.replace("*", "")
    v = v.replace("_", "-")

    # Replace non-alphanumerics (including emoji / punctuation) with spaces.
    v = re.sub(r"[^a-z0-9\-\s]", " ", v)

    # Collapse whitespace and hyphens.
    v = re.sub(r"\s+", " ", v).strip()
    v = v.replace(" ", "-")
    v = re.sub(r"-+", "-", v)

    if v in {"", "unknown", "n-a", "na"}:
        return ""

    # Canonicalize variants.
    if v in {"active", "in-progress", "inprogress", "doing", "running"}:
        return "in-progress"
    if v in {"planned", "plan", "todo", "open", "opened", "pending", "queued", "backlog", "draft", "open-pending-approval"}:
        return "open"
    if v in {"paused", "pause", "on-hold", "hold", "blocked", "stuck"}:
        return "blocked"
    if v in {"done", "closed", "complete", "completed"}:
        return "completed"

    # Phrases like "closed-qf4-completed-evidence-recorded" should still be treated as completed.
    if v.startswith("closed") or v.startswith("completed") or v.startswith("complete"):
        return "completed"

    return v


def _norm_status_source_strategy(raw: Any) -> str:
    """Normalize task-level status source strategy.

    - doc_enforced: compare SSOT task status against task path + referenced docs + dashboard.
    - ssot_only: treat operations/tasks.json as authoritative and skip document/dashboard checks.
    """
    v = str(raw or "").strip().lower().replace("-", "_")
    if v in {"ssot_only", "ssot", "ssotonly"}:
        return "ssot_only"
    return "doc_enforced"


def _extract_status_from_markdown(text: str) -> str:
    if not text:
        return ""

    pats = [
        r"\*\*Status\*\*\s*:\s*([^\n\r]+)",
        r"^\-\s*Status\s*:\s*`([^`]+)`",
        r"^\-\s*Status\s*:\s*([^\n\r]+)",
    ]
    for pat in pats:
        m = re.search(pat, text, flags=re.IGNORECASE | re.MULTILINE)
        if not m:
            continue
        raw = (m.group(1) or "").strip().rstrip(" .")
        return _norm_status(raw)
    return ""


def _extract_backticked_paths(text: str) -> List[str]:
    if not text:
        return []
    items = re.findall(r"`([^`]+)`", text)
    out: List[str] = []
    for it in items:
        it = (it or "").strip()
        if not it:
            continue
        if " " in it:
            continue
        out.append(it)
    return out


def _load_jsonc_best_effort(path: Path) -> Any:
    try:
        from codesentinel.utils.jsonc_utils import load_jsonc  # type: ignore

        return load_jsonc(path)
    except Exception:
        raw = path.read_text(encoding="utf-8", errors="ignore")
        return json.loads(raw)


def _load_jobs_dashboard_status(repo_root: Path) -> Dict[str, str]:
    dash_path = (repo_root / "docs" / "dashboards" / "room" / "JOBS_DASHBOARD.md").resolve()
    out: Dict[str, str] = {}
    try:
        dash_text = dash_path.read_text(encoding="utf-8", errors="ignore")
        for ln in dash_text.splitlines():
            if not ln.startswith("|"):
                continue
            parts = [p.strip() for p in ln.strip().strip("|").split("|")]
            # expected columns (at least): id | ... | status
            if len(parts) < 6:
                continue
            task_id = parts[0]
            status_raw = parts[5]
            if task_id and status_raw:
                out[task_id] = _norm_status(status_raw)
    except Exception:
        pass
    return out


def _is_status_bearing_doc(rel_norm: str) -> bool:
    if not rel_norm or rel_norm.endswith("/"):
        return False

    # Most job artifacts follow these conventions.
    if "/jobs/" in rel_norm.replace("\\", "/"):
        return True

    if rel_norm.startswith("docs/reports/operations/JOB_REPORT_"):
        return True

    # Calamum-specific job reports.
    if rel_norm.startswith("projects/calamum-moltbook-observer/docs/reports/") and "JOB_" in rel_norm:
        return True

    return False


def _check_status_sync_global(repo_root: Path) -> Dict[str, Any]:
    tasks_path = (repo_root / "operations" / "tasks.json").resolve()
    dashboard_status = _load_jobs_dashboard_status(repo_root)

    result: Dict[str, Any] = {
        "tasks_path": str(tasks_path),
        "dashboard_path": str((repo_root / "docs" / "dashboards" / "room" / "JOBS_DASHBOARD.md").resolve()),
        "checked_task_count": 0,
        "status_source_strategy_counts": {"doc_enforced": 0, "ssot_only": 0},
        "ssot_only_task_ids": [],
        "violations": [],
        "notes": [],
    }

    try:
        payload = _load_jsonc_best_effort(tasks_path)
    except Exception as e:
        result["notes"].append(f"[ERR] could not load operations/tasks.json: {e}")
        return result

    tasks: List[Dict[str, Any]] = payload if isinstance(payload, list) else []
    result["checked_task_count"] = len([t for t in tasks if isinstance(t, dict) and (t.get("id") and t.get("path") and t.get("status"))])

    for t in tasks:
        if not isinstance(t, dict):
            continue
        task_id = str(t.get("id") or "").strip()
        t_path = str(t.get("path") or "").replace("\\", "/")
        expected = _norm_status(str(t.get("status") or ""))
        if not task_id or not t_path or not expected:
            continue

        strategy = _norm_status_source_strategy(t.get("status_source_strategy") or t.get("status_source"))
        strategy_counts = result.get("status_source_strategy_counts")
        if isinstance(strategy_counts, dict):
            strategy_counts[strategy] = int(strategy_counts.get(strategy, 0) or 0) + 1

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

        if strategy == "ssot_only":
            ids = result.get("ssot_only_task_ids")
            if isinstance(ids, list):
                ids.append(task_id)
            continue

        dash_found = dashboard_status.get(task_id, "")
        if dash_found and dash_found != expected:
            add_violation("docs/dashboards/room/JOBS_DASHBOARD.md", dash_found, expected, "dashboard status mismatch (derived view appears stale)")

        qs_abs = (repo_root / t_path).resolve()
        if not qs_abs.exists() or not qs_abs.is_file():
            add_violation(t_path, "(missing)", expected, "QuestStack/task path missing")
            continue

        try:
            qs_text = qs_abs.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            qs_text = ""

        qs_found = _extract_status_from_markdown(qs_text)
        if qs_found and qs_found != expected:
            add_violation(t_path, qs_found, expected, "QuestStack status mismatch")
        if not qs_found:
            add_violation(t_path, "(missing)", expected, "QuestStack status not found")

        for rel in _extract_backticked_paths(qs_text):
            rel_norm = rel.replace("\\", "/")
            if rel_norm.startswith("http://") or rel_norm.startswith("https://"):
                continue
            if not _is_status_bearing_doc(rel_norm):
                continue

            doc_abs = (repo_root / rel_norm).resolve()
            if not doc_abs.exists() or (not doc_abs.is_file()):
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

            if not found:
                add_violation(rel_norm, "(missing)", expected, "status not found in referenced job document")
            elif found != expected:
                add_violation(rel_norm, found, expected, "referenced job document status mismatch")

    ssot_only_ids = result.get("ssot_only_task_ids")
    if isinstance(ssot_only_ids, list) and ssot_only_ids:
        result["notes"].append(
            f"[INFO] status_source_strategy=ssot_only applied to {len(ssot_only_ids)} task(s); doc/dashboard checks skipped for those ids"
        )

    return result


def _extract_watchdog_scripts(repo_root: Path) -> List[str]:
    watchdog_path = (repo_root / "projects" / "calamum-moltbook-observer" / "src" / "calamum_watchdog.py").resolve()
    if not watchdog_path.exists():
        return []

    try:
        text = watchdog_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []

    found = re.findall(r"script_rel=\"([^\"]+)\"", text)
    out: List[str] = []
    for s in found:
        s = str(s or "").strip()
        if s and s.endswith(".py"):
            out.append(s.replace("\\", "/"))
    # stable order
    return sorted(set(out))


def _check_watchdog_script_integrity(repo_root: Path) -> Dict[str, Any]:
    scripts = _extract_watchdog_scripts(repo_root)
    missing: List[str] = []
    for rel in scripts:
        if not (repo_root / rel).exists():
            missing.append(rel)

    return {
        "script_count": len(scripts),
        "scripts": scripts,
        "missing": missing,
        "missing_count": len(missing),
    }


def _read_text_best_effort(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _stage4_threshold_drift(repo_root: Path) -> Dict[str, Any]:
    """Detect drift between Stage 4 threshold configuration surfaces."""
    cfg_py = (repo_root / "projects" / "calamum-moltbook-observer" / "src" / "calamum_config.py").resolve()
    svc = (repo_root / "projects" / "calamum-moltbook-observer" / "deployment" / "systemd" / "calamum-observer.service").resolve()
    stage4_cfg = (repo_root / "projects" / "calamum-moltbook-observer" / "deployment" / "configs" / "stage4_active.json").resolve()
    job0015 = (repo_root / "projects" / "calamum-moltbook-observer" / "jobs" / "CALAMUM_JOB_0015_MOLTBOOK_OBSERVER_STAGE4_ACTIVATION_20260210.md").resolve()

    found: Dict[str, Any] = {
        "calamum_config": {"path": _rel_to(cfg_py, repo_root), "mentions": []},
        "systemd_observer": {"path": _rel_to(svc, repo_root), "mentions": []},
        "deployment_stage4_active": {"path": _rel_to(stage4_cfg, repo_root), "mentions": []},
        "job0015": {"path": _rel_to(job0015, repo_root), "mentions": []},
    }

    keys = ["CALAMUM_ACTIVE_MAGNET_THRESHOLD", "ACTIVE_MAGNET_THRESHOLD"]

    for label, path in [("calamum_config", cfg_py), ("systemd_observer", svc), ("deployment_stage4_active", stage4_cfg), ("job0015", job0015)]:
        text = _read_text_best_effort(path)
        mentions: List[str] = []
        for k in keys:
            if k in text:
                mentions.append(k)
        found[label]["mentions"] = mentions
        found[label]["exists"] = bool(path.exists())

    # Drift heuristics: prefer namespaced key everywhere, allow legacy only in code for fallback.
    drift: List[str] = []
    if "CALAMUM_ACTIVE_MAGNET_THRESHOLD" not in (found["systemd_observer"].get("mentions") or []):
        drift.append(f"systemd observer unit does not mention CALAMUM_ACTIVE_MAGNET_THRESHOLD: {found['systemd_observer']['path']}")
    if "ACTIVE_MAGNET_THRESHOLD" in (found["deployment_stage4_active"].get("mentions") or []) and "CALAMUM_ACTIVE_MAGNET_THRESHOLD" not in (found["deployment_stage4_active"].get("mentions") or []):
        drift.append(f"deployment config uses legacy ACTIVE_MAGNET_THRESHOLD only: {found['deployment_stage4_active']['path']}")
    if "ACTIVE_MAGNET_THRESHOLD" in (found["job0015"].get("mentions") or []) and "CALAMUM_ACTIVE_MAGNET_THRESHOLD" not in (found["job0015"].get("mentions") or []):
        drift.append(f"job doc references legacy ACTIVE_MAGNET_THRESHOLD only: {found['job0015']['path']}")

    found["drift"] = drift
    found["drift_count"] = len(drift)
    return found


def _walk_files(repo_root: Path, filename: str, exclude_dirs: Iterable[str]) -> List[Path]:
    exclude = set(exclude_dirs)
    out: List[Path] = []
    for root, dirs, files in os.walk(str(repo_root)):
        # mutate dirs in-place
        dirs[:] = [d for d in dirs if d not in exclude and not d.startswith(".")]
        if filename in files:
            out.append(Path(root) / filename)
    return out


def _norm_root_entry(raw: Any) -> str:
    v = str(raw or "").strip().replace("\\", "/")
    if v.startswith("./"):
        v = v[2:]
    v = v.rstrip("/")
    return v


def _git_ls_tree_dirs(repo_root: Path, treeish: str) -> List[str]:
    rc, out, _err = _run(["git", "ls-tree", "--name-only", "-d", treeish], cwd=repo_root)
    if rc != 0:
        return []
    dirs: List[str] = []
    for ln in out.splitlines():
        name = str(ln or "").strip().replace("\\", "/")
        if not name:
            continue
        dirs.append(name)
    return sorted(set(dirs))


def _check_project_manifest_layout(repo_root: Path, project_root: Path) -> Dict[str, Any]:
    manifest_path = (project_root / "PROJECT_MANIFEST.json").resolve()
    project_rel = _rel_to(project_root, repo_root)

    result: Dict[str, Any] = {
        "manifest_path": _rel_to(manifest_path, repo_root),
        "manifest_exists": bool(manifest_path.exists()),
        "manifest_readable": False,
        "project_rel": project_rel,
        "declared_tracked_roots": [],
        "declared_ignored_roots": [],
        "actual_tracked_top_level_dirs": [],
        "missing_from_manifest_tracked_roots": [],
        "manifest_tracked_roots_not_in_git_tree": [],
        "tracked_ignored_overlap": [],
        "required_ignored_roots_missing": [],
        "violations": [],
        "notes": [],
    }

    actual_dirs = _git_ls_tree_dirs(repo_root, f"HEAD:{project_rel}")
    result["actual_tracked_top_level_dirs"] = actual_dirs

    if not manifest_path.exists():
        result["violations"].append("PROJECT_MANIFEST.json missing")
        return result

    try:
        obj = json.loads(manifest_path.read_text(encoding="utf-8", errors="ignore") or "{}")
    except Exception as e:
        result["violations"].append(f"PROJECT_MANIFEST.json unreadable: {e}")
        return result

    if not isinstance(obj, dict):
        result["violations"].append("PROJECT_MANIFEST.json is not a JSON object")
        return result

    result["manifest_readable"] = True

    layout = obj.get("layout")
    if not isinstance(layout, dict):
        result["violations"].append("PROJECT_MANIFEST.json missing layout object")
        return result

    tracked_raw = layout.get("tracked_roots")
    ignored_raw = layout.get("ignored_roots")

    tracked_roots = sorted(set([_norm_root_entry(x) for x in (tracked_raw if isinstance(tracked_raw, list) else []) if _norm_root_entry(x)]))
    ignored_roots = sorted(set([_norm_root_entry(x) for x in (ignored_raw if isinstance(ignored_raw, list) else []) if _norm_root_entry(x)]))

    result["declared_tracked_roots"] = tracked_roots
    result["declared_ignored_roots"] = ignored_roots

    tracked_set = set(tracked_roots)
    ignored_set = set(ignored_roots)
    actual_set = set(actual_dirs)

    missing_from_manifest = sorted(actual_set - tracked_set)
    stale_manifest_entries = sorted(tracked_set - actual_set)
    overlap = sorted(tracked_set & ignored_set)

    required_ignored = {
        "local_untracked",
        "logs",
        "src/logs",
        "src/.agent_session",
    }
    missing_required_ignored = sorted([x for x in required_ignored if x not in ignored_set])

    result["missing_from_manifest_tracked_roots"] = missing_from_manifest
    result["manifest_tracked_roots_not_in_git_tree"] = stale_manifest_entries
    result["tracked_ignored_overlap"] = overlap
    result["required_ignored_roots_missing"] = missing_required_ignored

    if missing_from_manifest:
        result["violations"].append(
            f"tracked top-level dirs missing from layout.tracked_roots: {', '.join(missing_from_manifest)}"
        )
    if stale_manifest_entries:
        result["violations"].append(
            f"layout.tracked_roots entries not present in tracked git tree: {', '.join(stale_manifest_entries)}"
        )
    if overlap:
        result["violations"].append(
            f"layout overlap between tracked_roots and ignored_roots: {', '.join(overlap)}"
        )
    if missing_required_ignored:
        result["violations"].append(
            f"required ignored roots missing from layout.ignored_roots: {', '.join(missing_required_ignored)}"
        )

    if not result["violations"]:
        result["notes"].append("PROJECT_MANIFEST layout is consistent with tracked tree and ignore policy minima")

    return result


def _git_changed_files(repo_root: Path) -> List[str]:
    rc, out, _err = _run(["git", "status", "--porcelain"], cwd=repo_root)
    if rc != 0:
        return []

    paths: List[str] = []
    for ln in out.splitlines():
        line = str(ln or "").rstrip()
        if not line:
            continue
        # Porcelain format: XY <path>  or XY <old> -> <new>
        payload = line[3:] if len(line) >= 4 else ""
        if " -> " in payload:
            payload = payload.split(" -> ", 1)[1]
        p = payload.strip().replace("\\", "/")
        if p:
            paths.append(p)
    return sorted(set(paths))


def _candidate_test_paths_for_module(module_rel: str) -> List[str]:
    rel = module_rel.replace("\\", "/")
    stem = Path(rel).stem

    candidates = [
        f"projects/calamum-moltbook-observer/src/tests/test_{stem}.py",
    ]

    if rel.startswith("projects/calamum-moltbook-observer/src/"):
        src_rel = rel[len("projects/calamum-moltbook-observer/src/") :]
        src_no_ext = str(Path(src_rel).with_suffix(""))
        candidates.append(f"projects/calamum-moltbook-observer/src/tests/test_{src_no_ext.replace('/', '_')}.py")

    return sorted(set(candidates))


def _check_changed_files_unit_test_coverage(repo_root: Path, project_root: Path) -> Dict[str, Any]:
    changed = _git_changed_files(repo_root)
    project_prefix = _rel_to(project_root, repo_root).replace("\\", "/") + "/"

    target_py: List[str] = []
    for rel in changed:
        r = rel.replace("\\", "/")
        if not r.startswith(project_prefix):
            continue
        if not r.endswith(".py"):
            continue
        if "/src/tests/" in r:
            continue
        if r.endswith("/__init__.py"):
            continue
        target_py.append(r)

    missing: List[Dict[str, Any]] = []
    for mod in sorted(set(target_py)):
        candidates = _candidate_test_paths_for_module(mod)
        exists_any = any((repo_root / c).exists() for c in candidates)
        if not exists_any:
            missing.append({"module": mod, "expected_any_of": candidates})

    return {
        "scope": "changed_python_files_only",
        "changed_python_files_checked": sorted(set(target_py)),
        "missing_unit_tests": missing,
        "missing_unit_tests_count": len(missing),
        "notes": [
            "Heuristic check: for each changed python module, expect a corresponding test_* file under src/tests/.",
            "This does not prove behavioral coverage; it enforces minimum test-presence hygiene.",
        ],
    }


def _check_agent_instruction_pairs(repo_root: Path) -> Dict[str, Any]:
    exclude = {
        ".git",
        ".venv",
        ".venv-core",
        "__pycache__",
        "node_modules",
        "archive",
        "quarantine_legacy_archive",
        "logs",
        "local_untracked",
        "semantics_vault",
        "report_tmp",
    }
    md_files = _walk_files(repo_root, "AGENT_INSTRUCTIONS.md", exclude)

    missing_json: List[str] = []
    for md in md_files:
        js = md.with_suffix(".json")
        if not js.exists():
            missing_json.append(_rel_to(md, repo_root))
            continue
        # Parseability check (best-effort).
        try:
            raw = js.read_text(encoding="utf-8", errors="ignore")
            obj = json.loads(raw or "{}")
            if not isinstance(obj, dict):
                missing_json.append(_rel_to(md, repo_root) + " (json not an object)")
        except Exception:
            missing_json.append(_rel_to(md, repo_root) + " (json unreadable)")

    return {
        "md_count": len(md_files),
        "missing_json": missing_json,
        "missing_json_count": len(missing_json),
    }


def audit_implementation_drift(
    *,
    repo_root: Path,
    project_root: Path,
    template_rel: str,
    out_dir_rel: str,
    jsonl_rel: str,
    set_baseline: bool,
    dry_run: bool,
    max_report_violations: int,
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

    report_path = out_dir / f"implementation_drift_audit_{ts.replace(':', '').replace('-', '').replace('Z', 'Z')}.md"
    evidence_path = out_dir / (report_path.stem + ".evidence.json")

    ssot = _check_status_sync_global(repo_root)
    watchdog = _check_watchdog_script_integrity(repo_root)
    stage4 = _stage4_threshold_drift(repo_root)
    instr = _check_agent_instruction_pairs(repo_root)
    manifest_layout = _check_project_manifest_layout(repo_root, project_root)
    test_coverage = _check_changed_files_unit_test_coverage(repo_root, project_root)

    ssot_violations = ssot.get("violations") if isinstance(ssot, dict) else None
    ssot_viol_list: List[Dict[str, Any]] = ssot_violations if isinstance(ssot_violations, list) else []

    # Recommendations
    recs: List[str] = []
    if ssot_viol_list:
        recs.append("Align QuestStack/job/job-report statuses with operations/tasks.json (SSOT), then refresh Jobs Dashboard.")
    if (watchdog.get("missing") or []):
        recs.append("Restore missing watchdog-scheduled scripts or update watchdog schedule only via an explicit job (do not hot-edit paths).")
    if stage4.get("drift"):
        recs.append("Normalize Stage 4 threshold env var naming across deployment configs/docs to prefer CALAMUM_ACTIVE_MAGNET_THRESHOLD.")
    if instr.get("missing_json"):
        recs.append("Ensure every AGENT_INSTRUCTIONS.md has a parseable .json sidecar (CI gate expects pairing).")
    if manifest_layout.get("violations"):
        recs.append("Align PROJECT_MANIFEST layout.tracked_roots/ignored_roots with the actual tracked tree and approved ignore-policy roots.")
    if test_coverage.get("missing_unit_tests"):
        recs.append("Add unit tests for changed python modules before baseline/close; maintain src/tests/test_<module>.py parity.")

    summary_ok = (
        (not ssot_viol_list)
        and (not (watchdog.get("missing") or []))
        and (not stage4.get("drift"))
        and (not instr.get("missing_json"))
        and (not (manifest_layout.get("violations") or []))
        and (not (test_coverage.get("missing_unit_tests") or []))
    )
    summary_line = "[OK] no implementation drift findings detected" if summary_ok else "[WARN] implementation drift findings present"

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
        "checks": {
            "ssot_status_sync": ssot,
            "watchdog_script_integrity": watchdog,
            "stage4_threshold_contract": stage4,
            "agent_instruction_pairs": instr,
            "project_manifest_layout": manifest_layout,
            "changed_files_unit_test_coverage": test_coverage,
        },
        "outputs": {
            "report_path": str(report_path),
            "evidence_path": str(evidence_path),
            "audit_jsonl_path": str(jsonl_path),
            "audit_index_path": str(index_path),
        },
        "recommendations": recs,
        "summary": summary_line,
    }

    # Render report.
    try:
        tpl = _load_template(tpl_path)
    except Exception as e:
        tpl = "# Implementation Drift Audit\n\n[ERR] Could not load template: {{ template_path }}\n"
        evidence["template_error"] = repr(e)

    # Keep report readable: show top N SSOT violations.
    viol_lines: List[str] = []
    for v in ssot_viol_list[: max(0, int(max_report_violations))]:
        if not isinstance(v, dict):
            continue
        viol_lines.append(
            f"{v.get('task_id','?')}: expected={v.get('expected','?')} found={v.get('found','?')} doc={v.get('doc','?')} reason={v.get('reason','?')}"
        )

    watchdog_missing = watchdog.get("missing") if isinstance(watchdog, dict) else None
    watchdog_missing_list: List[str] = watchdog_missing if isinstance(watchdog_missing, list) else []

    stage4_lines: List[str] = []
    stage4_drift = stage4.get("drift") if isinstance(stage4, dict) else None
    if isinstance(stage4_drift, list) and stage4_drift:
        stage4_lines.extend([str(x) for x in stage4_drift])
    else:
        stage4_lines.append("(no drift detected)")

    instr_missing = instr.get("missing_json") if isinstance(instr, dict) else None
    instr_missing_list: List[str] = instr_missing if isinstance(instr_missing, list) else []

    manifest_viol = manifest_layout.get("violations") if isinstance(manifest_layout, dict) else None
    manifest_viol_list: List[str] = manifest_viol if isinstance(manifest_viol, list) else []

    manifest_missing = manifest_layout.get("missing_from_manifest_tracked_roots") if isinstance(manifest_layout, dict) else None
    manifest_missing_list: List[str] = manifest_missing if isinstance(manifest_missing, list) else []

    manifest_stale = manifest_layout.get("manifest_tracked_roots_not_in_git_tree") if isinstance(manifest_layout, dict) else None
    manifest_stale_list: List[str] = manifest_stale if isinstance(manifest_stale, list) else []

    test_missing_raw = test_coverage.get("missing_unit_tests") if isinstance(test_coverage, dict) else None
    test_missing_list: List[Dict[str, Any]] = test_missing_raw if isinstance(test_missing_raw, list) else []
    test_missing_lines: List[str] = []
    for row in test_missing_list:
        if not isinstance(row, dict):
            continue
        mod = str(row.get("module") or "?")
        exp = row.get("expected_any_of")
        exp_items = [str(x) for x in exp] if isinstance(exp, list) else []
        test_missing_lines.append(f"{mod} -> expected any of: {', '.join(exp_items) if exp_items else '(none)'}")

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
        "ssot_checked_task_count": str(ssot.get("checked_task_count", "?")),
        "ssot_strategy_doc_enforced_count": str(((ssot.get("status_source_strategy_counts") or {}).get("doc_enforced", 0) if isinstance(ssot, dict) else 0)),
        "ssot_strategy_ssot_only_count": str(((ssot.get("status_source_strategy_counts") or {}).get("ssot_only", 0) if isinstance(ssot, dict) else 0)),
        "ssot_violation_count": str(len(ssot_viol_list)),
        "ssot_violations_block": _block(viol_lines, empty_msg="(no mismatches found)"),
        "ssot_ssot_only_ids_block": _block(
            [str(x) for x in (ssot.get("ssot_only_task_ids") or [])] if isinstance(ssot, dict) else [],
            empty_msg="(none)",
        ),
        "watchdog_script_count": str(watchdog.get("script_count", "?")),
        "watchdog_missing_count": str(len(watchdog_missing_list)),
        "watchdog_missing_block": _block(watchdog_missing_list, empty_msg="(none missing)"),
        "stage4_threshold_drift_block": _block(stage4_lines, empty_msg="(no drift detected)"),
        "instruction_md_count": str(instr.get("md_count", "?")),
        "instruction_missing_json_count": str(len(instr_missing_list)),
        "instruction_missing_json_block": _block(instr_missing_list, empty_msg="(none missing)"),
        "manifest_path": str(manifest_layout.get("manifest_path", "")),
        "manifest_violation_count": str(len(manifest_viol_list)),
        "manifest_violations_block": _block(manifest_viol_list, empty_msg="(no drift detected)"),
        "manifest_missing_tracked_roots_block": _block(manifest_missing_list, empty_msg="(none)"),
        "manifest_stale_tracked_roots_block": _block(manifest_stale_list, empty_msg="(none)"),
        "changed_py_files_checked_count": str(len(test_coverage.get("changed_python_files_checked") or []) if isinstance(test_coverage, dict) else 0),
        "missing_unit_tests_count": str(len(test_missing_list)),
        "missing_unit_tests_block": _block(test_missing_lines, empty_msg="(none)"),
        "recommendations_block": _block(recs, empty_msg="(no recommendations)"),
        "evidence_path": str(evidence_path),
        "audit_jsonl_path": str(jsonl_path),
        "template_path": str(tpl_path),
    }

    report_text = _render_template(tpl, report_vars)

    if not dry_run:
        _write_text(report_path, report_text)
        _write_json(evidence_path, evidence)

        jsonl_snapshot = {
            "kind": "snapshot",
            "timestamp_utc": ts,
            "run_id": run_id,
            "auditor": AUDITOR,
            "git": {"head": git.head, "branch": git.branch, "is_dirty": git.is_dirty},
            "checks": evidence["checks"],
            "report": str(report_path),
            "evidence": str(evidence_path),
            "summary": summary_line,
        }
        _append_jsonl(jsonl_path, jsonl_snapshot)

        if set_baseline:
            jsonl_baseline = dict(jsonl_snapshot)
            jsonl_baseline["kind"] = "baseline"
            jsonl_baseline["baseline_id"] = uuid.uuid4().hex
            _append_jsonl(jsonl_path, jsonl_baseline)

        # Central audit index.
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
        audits["implementation_drift"] = {
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
    # .../projects/calamum-moltbook-observer/tools/audit_implementation_drift.py
    project_root = here.resolve().parents[1]
    repo_root = here.resolve().parents[3]
    return repo_root, project_root


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Implementation drift audit")
    ap.add_argument(
        "--template",
        default="projects/calamum-moltbook-observer/template_library/reports/CALAMUM_IMPLEMENTATION_DRIFT_AUDIT_TEMPLATE.md.template",
        help="Repo-relative path to the markdown template",
    )
    ap.add_argument(
        "--out-dir",
        default="local_untracked/audits/implementation_drift",
        help="Project-relative output directory (should be ignored)",
    )
    ap.add_argument(
        "--jsonl",
        default="local_untracked/audit_log/implementation_drift_audit.jsonl",
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
        "--max-report-violations",
        type=int,
        default=50,
        help="Limit how many SSOT status violations are rendered into the markdown report",
    )
    args = ap.parse_args(argv)

    repo_root, project_root = _repo_root_from_here(Path(__file__))

    evidence = audit_implementation_drift(
        repo_root=repo_root,
        project_root=project_root,
        template_rel=str(args.template),
        out_dir_rel=str(args.out_dir),
        jsonl_rel=str(args.jsonl),
        set_baseline=bool(args.set_baseline),
        dry_run=bool(args.dry_run),
        max_report_violations=int(args.max_report_violations),
    )

    if bool(args.dry_run):
        print("Implementation drift audit DRY-RUN complete")
    else:
        print("Implementation drift audit complete")
    print(f"project_root: {project_root}")
    print(f"report:       {evidence['outputs']['report_path']}")
    print(f"evidence:     {evidence['outputs']['evidence_path']}")
    print(f"audit_jsonl:  {evidence['outputs']['audit_jsonl_path']}")
    print(f"audit_index:  {evidence['outputs'].get('audit_index_path', '')}")

    # Small, safe summary.
    ssot = (evidence.get("checks", {}) or {}).get("ssot_status_sync")
    viol = ssot.get("violations") if isinstance(ssot, dict) else None
    if isinstance(viol, list) and viol:
        print(f"[WARN] SSOT status drift detected ({len(viol)} mismatches; see evidence)")

    wd = (evidence.get("checks", {}) or {}).get("watchdog_script_integrity")
    missing = wd.get("missing") if isinstance(wd, dict) else None
    if isinstance(missing, list) and missing:
        print(f"[WARN] watchdog scheduled scripts missing ({len(missing)}; see evidence)")

    stage4 = (evidence.get("checks", {}) or {}).get("stage4_threshold_contract")
    drift = stage4.get("drift") if isinstance(stage4, dict) else None
    if isinstance(drift, list) and drift:
        print(f"[WARN] Stage 4 threshold contract drift findings ({len(drift)}; see evidence)")

    instr = (evidence.get("checks", {}) or {}).get("agent_instruction_pairs")
    missing_json = instr.get("missing_json") if isinstance(instr, dict) else None
    if isinstance(missing_json, list) and missing_json:
        print(f"[WARN] AGENT_INSTRUCTIONS pairing issues ({len(missing_json)}; see evidence)")

    manifest_layout = (evidence.get("checks", {}) or {}).get("project_manifest_layout")
    manifest_viol = manifest_layout.get("violations") if isinstance(manifest_layout, dict) else None
    if isinstance(manifest_viol, list) and manifest_viol:
        print(f"[WARN] PROJECT_MANIFEST layout drift findings ({len(manifest_viol)}; see evidence)")

    t_cov = (evidence.get("checks", {}) or {}).get("changed_files_unit_test_coverage")
    t_missing = t_cov.get("missing_unit_tests") if isinstance(t_cov, dict) else None
    if isinstance(t_missing, list) and t_missing:
        print(f"[WARN] missing unit tests for changed python files ({len(t_missing)}; see evidence)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
