"""Generate an operations parameters report for Calamum Moltbook Observer.

Focus: operational parameters only (safe for school demos)
- Liveness via heartbeats.
- Telemetry volumes and freshness (names-only; counts, sizes, mtimes, hashes).
- Control signal inventory (names-only).
- Service log presence and growth (names-only).
- Environment overrides & integration flags (names-only; never values).
- Path safety checks (keep operational roots project-local).

Outputs (all untracked under project_root/local_untracked/):
- Markdown report (rendered from tracked template).
- JSON evidence bundle.
- Append-only JSONL provenance log.
- Local audit index pointer.

Schema reference (kept in-repo to prevent drift):
    projects/calamum-moltbook-observer/docs/OPS_PARAMETERS_REPORT_SCHEMA.md

Run from workspace repo root:
  .venv-core\\Scripts\\python.exe projects\\calamum-moltbook-observer\\tools\\report_ops_parameters.py

Optional flags:
  --set-baseline   Also append a baseline record to the JSONL log.
  --dry-run        Compute findings but do not write any files.

"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


AUDITOR = "ORACL-Prime"


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


def _git_info(repo_root: Path) -> Dict[str, Any]:
    rc, out, err = _run(["git", "rev-parse", "--verify", "HEAD"], cwd=repo_root)
    if rc != 0:
        return {"ok": False, "head": "", "branch": "", "is_dirty": False, "error": (err.strip() or out.strip() or "git unavailable")}

    head = out.strip()
    rc, out, _ = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root)
    branch = out.strip() if rc == 0 else ""
    rc, out, _ = _run(["git", "status", "--porcelain"], cwd=repo_root)
    is_dirty = bool(out.strip()) if rc == 0 else False
    return {"ok": True, "head": head, "branch": branch, "is_dirty": is_dirty, "error": ""}


def _render_template(tpl: str, data: Dict[str, Any]) -> str:
    out = str(tpl)
    for k, v in data.items():
        pat = re.compile(r"\{\{\s*" + re.escape(str(k)) + r"\s*\}\}")
        out = pat.sub(lambda _m, _v=str(v): _v, out)
    return out


def _rel_to(path: Path, base: Path) -> str:
    try:
        return str(path.resolve().relative_to(base.resolve())).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def _git_is_ignored(repo_root: Path, path: Path) -> Optional[bool]:
    rel = _rel_to(path, repo_root)
    rc, _, _ = _run(["git", "check-ignore", "-q", rel], cwd=repo_root)
    if rc == 0:
        return True
    if rc == 1:
        return False
    return None


@dataclass
class FileStat:
    path: Path
    exists: bool
    size_bytes: int
    mtime: float


def _now() -> float:
    return time.time()


def _safe_stat(path: Path) -> FileStat:
    try:
        st = path.stat()
        return FileStat(path=path, exists=True, size_bytes=int(st.st_size), mtime=float(st.st_mtime))
    except FileNotFoundError:
        return FileStat(path=path, exists=False, size_bytes=0, mtime=0.0)
    except OSError:
        return FileStat(path=path, exists=path.exists(), size_bytes=0, mtime=0.0)


def _age_seconds(mtime: float, now: Optional[float] = None) -> Optional[float]:
    if not mtime:
        return None
    n = _now() if now is None else now
    return max(0.0, n - mtime)


def _fmt_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024.0:.1f} KiB"
    if n < 1024 * 1024 * 1024:
        return f"{n / (1024.0 * 1024.0):.1f} MiB"
    return f"{n / (1024.0 * 1024.0 * 1024.0):.2f} GiB"


def _status_from_age(age_seconds: Optional[float], *, exists: bool, warn_s: Optional[float], err_s: Optional[float]) -> str:
    if not exists:
        return "ERR"
    if age_seconds is None:
        return "WARN"
    if err_s is not None and age_seconds >= float(err_s):
        return "ERR"
    if warn_s is not None and age_seconds >= float(warn_s):
        return "WARN"
    return "OK"


def _sha256_tail(path: Path, max_bytes: int = 64 * 1024) -> str:
    try:
        st = path.stat()
        size = int(st.st_size)
        read_len = min(int(max_bytes), max(0, size))
        with path.open("rb") as f:
            if size > read_len:
                f.seek(size - read_len)
            data = f.read(read_len)
        return hashlib.sha256(data).hexdigest()
    except Exception:
        return ""


def _count_jsonl_lines_fast(path: Path, chunk_size: int = 1024 * 1024) -> Tuple[int, bool]:
    nl = 0
    last_byte: Optional[int] = None
    with path.open("rb") as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            nl += b.count(b"\n")
            last_byte = b[-1]

    had_partial = last_byte is not None and last_byte != ord("\n")
    if had_partial:
        nl += 1
    return int(nl), bool(had_partial)


def _parse_utc_ts(ts: str) -> Optional[datetime]:
    """Parse ISO8601 UTC timestamps emitted by _utc_now()."""
    if not ts:
        return None
    try:
        s = str(ts).strip()
        # _utc_now emits Z suffix; datetime.fromisoformat expects +00:00
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _read_last_provenance_records(jsonl_path: Path) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Return (last_snapshot, last_baseline) from a provenance JSONL.

    Robust to partial/corrupt lines.
    """

    if not jsonl_path.exists():
        return None, None

    try:
        lines = jsonl_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return None, None

    last_snapshot: Optional[Dict[str, Any]] = None
    last_baseline: Optional[Dict[str, Any]] = None
    for raw in reversed(lines):
        raw = raw.strip()
        if not raw:
            continue
        try:
            rec = json.loads(raw)
        except Exception:
            continue
        if not isinstance(rec, dict):
            continue
        kind = str(rec.get("kind") or "")
        if kind == "snapshot" and last_snapshot is None:
            last_snapshot = rec
        elif kind == "baseline" and last_baseline is None:
            last_baseline = rec
        if last_snapshot is not None and last_baseline is not None:
            break

    return last_snapshot, last_baseline


def _md_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    if not headers:
        return ""
    header_row = "| " + " | ".join(headers) + " |"
    sep_row = "| " + " | ".join(["---" for _ in headers]) + " |"
    body_rows = ["| " + " | ".join([str(c) for c in r]) + " |" for r in rows]
    return "\n".join([header_row, sep_row] + body_rows)


def _fmt_rate(rps: Optional[float]) -> str:
    if rps is None:
        return "(n/a)"
    try:
        if rps < 0:
            return f"{rps:.3f} r/s"
        if rps < 0.01:
            return f"{rps:.6f} r/s"
        if rps < 1.0:
            return f"{rps:.3f} r/s"
        return f"{rps:.2f} r/s"
    except Exception:
        return "(n/a)"


def _block(lines: Sequence[str], empty_msg: str = "(none)") -> str:
    if not lines:
        return empty_msg
    return "\n".join([f"- {ln}" for ln in lines])


def _scout_strays(*, project_root: Path, repo_root: Path, max_results: int) -> List[Dict[str, Any]]:
    """Scan for stray runtime artifacts under the project tree (names-only).

    We intentionally skip project_root/logs and project_root/local_untracked.
    """

    exclude_dirs = {
        "local_untracked",
        "logs",
        ".git",
        "__pycache__",
        ".pytest_cache",
        "node_modules",
        "dist",
        "build",
        ".venv",
        ".venv-core",
    }

    suspicious_names = {".env", ".env.local", ".env.dev", ".env.prod"}
    suspicious_suffixes = (".log", ".pid", ".lock", ".sqlite", ".db")
    suspicious_dirs = {"tmp", "temp", "logs"}

    allowed_root_pidfiles = {
        "calamum_agent.pid",
        "calamum_librarian.pid",
        "calamum_watchdog.pid",
        "ghost_console.pid",
    }

    canonical_logs = (project_root / "logs").resolve()

    hits: List[Dict[str, Any]] = []
    stack: List[Path] = [project_root]
    while stack:
        base = stack.pop()
        try:
            entries = sorted(base.iterdir(), key=lambda p: p.name.lower())
        except Exception:
            continue

        for p in entries:
            if p.is_dir():
                if p.name in exclude_dirs:
                    continue
                if p.resolve() == canonical_logs:
                    continue
                if p.name in suspicious_dirs:
                    st = _safe_stat(p)
                    hits.append({"kind": "dir", "path": _rel_to(p, repo_root), "reason": "suspicious_dir", "size_bytes": int(st.size_bytes)})
                    if len(hits) >= int(max_results):
                        return hits
                stack.append(p)
                continue

            st = _safe_stat(p)
            name_l = p.name.lower()
            reason = ""

            # These pidfiles are intentionally stored at the project root by the launcher.
            try:
                if p.parent.resolve() == project_root.resolve() and p.name in allowed_root_pidfiles:
                    continue
            except Exception:
                pass

            if p.name in suspicious_names:
                reason = "env_file"
            elif name_l.endswith(".env") and p.name != ".env.example":
                reason = "env_file"
            elif name_l.endswith(suspicious_suffixes):
                reason = "runtime_file"

            if reason:
                hits.append(
                    {
                        "kind": "file",
                        "path": _rel_to(p, repo_root),
                        "reason": reason,
                        "size_bytes": int(st.size_bytes),
                        "sha256_tail": _sha256_tail(p, max_bytes=(16 * 1024)) if st.exists else "",
                    }
                )
                if len(hits) >= int(max_results):
                    return hits

    return hits


def _repo_root_from_here(here: Path) -> Tuple[Path, Path]:
    # .../projects/calamum-moltbook-observer/tools/report_ops_parameters.py
    project_root = here.resolve().parents[1]
    repo_root = here.resolve().parents[3]
    return repo_root, project_root


def _get_effective_log_paths(project_root: Path) -> Dict[str, Path]:
    """Resolve operational paths, preferring the same logic as runtime code."""

    src_dir = (project_root / "src").resolve()
    if str(src_dir) not in sys.path:
        sys.path.append(str(src_dir))

    log_dir = (project_root / "logs").resolve()
    data_dir = (log_dir / "data" / "calamum").resolve()
    ctrl_dir = (log_dir / "control" / "calamum").resolve()
    health_dir = (log_dir / "health").resolve()

    try:
        # Optional; we keep a safe fallback if imports fail.
        import calamum_config  # type: ignore

        log_dir = calamum_config.get_calamum_log_dir().resolve()
        data_dir = calamum_config.get_calamum_data_dir().resolve()
        ctrl_dir = calamum_config.get_calamum_control_dir().resolve()
        health_dir = calamum_config.get_calamum_health_dir().resolve()
    except Exception:
        pass

    return {
        "log_dir": log_dir,
        "data_dir": data_dir,
        "control_dir": ctrl_dir,
        "health_dir": health_dir,
    }


def report_ops_parameters(
    *,
    repo_root: Path,
    project_root: Path,
    template_rel: str,
    out_dir_rel: str,
    jsonl_rel: str,
    max_tail_bytes: int,
    hb_warn_seconds: Optional[float],
    hb_err_seconds: Optional[float],
    scout_max_results: int,
    set_baseline: bool,
    dry_run: bool,
) -> Dict[str, Any]:
    ts = _utc_now()
    run_id = uuid.uuid4().hex
    git = _git_info(repo_root)

    paths = _get_effective_log_paths(project_root)
    log_dir = paths["log_dir"]
    data_dir = paths["data_dir"]
    ctrl_dir = paths["control_dir"]
    health_dir = paths["health_dir"]

    tpl_path = (repo_root / template_rel).resolve()
    out_dir = (project_root / out_dir_rel).resolve()
    jsonl_path = (project_root / jsonl_rel).resolve()
    index_path = (project_root / "local_untracked" / "audit_log" / "audit_index.json").resolve()

    local_untracked_root = (project_root / "local_untracked").resolve()
    unsafe: List[str] = []
    if not _is_within(out_dir, local_untracked_root):
        unsafe.append(f"out_dir ({out_dir})")
    if not _is_within(jsonl_path, local_untracked_root):
        unsafe.append(f"jsonl ({jsonl_path})")
    if not _is_within(index_path, local_untracked_root):
        unsafe.append(f"audit_index ({index_path})")
    if unsafe:
        raise ValueError(
            "Refusing to write outside project_root/local_untracked/. "
            + "Unsafe output path(s): "
            + ", ".join(unsafe)
        )

    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
        jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.parent.mkdir(parents=True, exist_ok=True)

    ts_slug = ts.replace(":", "").replace("-", "").replace("Z", "Z").replace(".", "")
    report_path = out_dir / f"calamum_ops_parameters_report_{ts_slug}.md"
    evidence_path = out_dir / f"calamum_ops_parameters_report_{ts_slug}.evidence.json"

    now = _now()

    # Environment (names-only; never values)
    #
    # Rationale:
    # - For scheduled runs, this is the quickest way to confirm *which configuration mode* is in effect
    #   (defaults vs env overrides) without leaking secrets.
    # - "Missing" env vars are often normal; they mean "using default effective paths".
    env_names = [
        "CALAMUM_REPO_ROOT",
        "CALAMUM_LOG_DIR",
        "CALAMUM_DATA_DIR",
        "CALAMUM_CONTROL_DIR",
        "MOLTBOOK_API_KEY",
        "MOLTBOOK_HOST",
    ]
    env_presence = {name: bool(os.getenv(name)) for name in env_names}

    def _env_flag(name: str) -> bool:
        return bool(os.getenv(name))

    env_lines: List[str] = []
    env_lines.append("Note: these are optional overrides / feature flags (names-only; values are never printed).")
    env_lines.append("For scheduled runs, treat this section as confirmation of the job's loaded profile.")

    env_lines.append(f"CALAMUM_REPO_ROOT: {'override_set' if _env_flag('CALAMUM_REPO_ROOT') else 'default'} (effective={repo_root})")
    env_lines.append(f"CALAMUM_LOG_DIR: {'override_set' if _env_flag('CALAMUM_LOG_DIR') else 'default'} (effective={log_dir})")
    env_lines.append(f"CALAMUM_DATA_DIR: {'override_set' if _env_flag('CALAMUM_DATA_DIR') else 'default'} (effective={data_dir})")
    env_lines.append(f"CALAMUM_CONTROL_DIR: {'override_set' if _env_flag('CALAMUM_CONTROL_DIR') else 'default'} (effective={ctrl_dir})")

    moltbook_enabled = _env_flag("MOLTBOOK_API_KEY")
    if not moltbook_enabled:
        env_lines.append("MOLTBOOK: disabled (MOLTBOOK_API_KEY not set)")
        env_lines.append(f"MOLTBOOK_HOST: {'set' if _env_flag('MOLTBOOK_HOST') else 'not set'} (OK while disabled)")
    else:
        env_lines.append("MOLTBOOK: enabled (MOLTBOOK_API_KEY present; value redacted)")
        if _env_flag("MOLTBOOK_HOST"):
            env_lines.append("MOLTBOOK_HOST: set")
        else:
            env_lines.append("MOLTBOOK_HOST: NOT SET [WARN] (required when MOLTBOOK is enabled)")

    # Liveness (heartbeats)
    hb_targets = {
        "watchdog": health_dir / "calamum_ops_watchdog.heartbeat",
        "observer": health_dir / "calamum_observer.heartbeat",
        "librarian": health_dir / "calamum_librarian.heartbeat",
    }
    heartbeats: List[Dict[str, Any]] = []
    for name, p in hb_targets.items():
        st = _safe_stat(p)
        age = _age_seconds(st.mtime, now)
        status = _status_from_age(age, exists=bool(st.exists), warn_s=hb_warn_seconds, err_s=hb_err_seconds)
        heartbeats.append(
            {
                "name": name,
                "path": _rel_to(p, repo_root),
                "exists": bool(st.exists),
                "size_bytes": int(st.size_bytes),
                "age_seconds": None if age is None else round(float(age), 3),
                "status": status,
            }
        )

    # Telemetry JSONL (counts only)
    telemetry: List[Dict[str, Any]] = []
    totals: Dict[str, int] = {}
    if data_dir.exists():
        for p in sorted(data_dir.glob("*.jsonl")):
            st = _safe_stat(p)
            if not st.exists:
                continue
            try:
                n, partial = _count_jsonl_lines_fast(p)
            except Exception:
                n, partial = 0, False
            totals[p.name] = int(n)
            telemetry.append(
                {
                    "name": p.name,
                    "path": _rel_to(p, repo_root),
                    "exists": True,
                    "records": int(n),
                    "partial_last_line": bool(partial),
                    "size_bytes": int(st.size_bytes),
                    "age_seconds": None if st.mtime == 0 else round(float(_age_seconds(st.mtime, now) or 0.0), 3),
                    "sha256_tail": _sha256_tail(p, max_bytes=int(max_tail_bytes)),
                }
            )

        manifest = data_dir / "archive" / "manifest.json"
        if manifest.exists():
            try:
                data = json.loads(manifest.read_text(encoding="utf-8", errors="ignore") or "{}")
                archived = 0
                entries = 0
                if isinstance(data, dict):
                    entries = len(data)
                    for _, meta in data.items():
                        if isinstance(meta, dict):
                            archived += int(meta.get("records", 0))
                totals["archive_records"] = int(archived)
                telemetry.append(
                    {
                        "name": "archive/manifest.json",
                        "path": _rel_to(manifest, repo_root),
                        "exists": True,
                        "archived_records": int(archived),
                        "entries": int(entries),
                        "sha256_tail": _sha256_tail(manifest, max_bytes=int(max_tail_bytes)),
                    }
                )
            except Exception:
                telemetry.append({"name": "archive/manifest.json", "path": _rel_to(manifest, repo_root), "exists": True, "error": "unreadable"})
    else:
        telemetry.append({"name": "data_dir", "path": _rel_to(data_dir, repo_root), "exists": False})

    # Control signals inventory
    control: List[Dict[str, Any]] = []
    if ctrl_dir.exists():
        for p in sorted(ctrl_dir.glob("*")):
            st = _safe_stat(p)
            control.append(
                {
                    "name": p.name + ("/" if p.is_dir() else ""),
                    "path": _rel_to(p, repo_root),
                    "is_dir": bool(p.is_dir()),
                    "size_bytes": int(st.size_bytes),
                    "age_seconds": None if st.mtime == 0 else round(float(_age_seconds(st.mtime, now) or 0.0), 3),
                }
            )
    else:
        control.append({"name": "control_dir", "path": _rel_to(ctrl_dir, repo_root), "exists": False})

    # Service logs (names-only; no tail text)
    service_targets = {
        "agent.stderr": log_dir / "calamum_agent.stderr.log",
        "agent.stdout": log_dir / "calamum_agent.stdout.log",
        "librarian.stderr": log_dir / "calamum_librarian.stderr.log",
        "librarian.stdout": log_dir / "calamum_librarian.stdout.log",
        "watchdog.stderr": log_dir / "calamum_watchdog.stderr.log",
        "watchdog.stdout": log_dir / "calamum_watchdog.stdout.log",
        "dashboard.stderr": log_dir / "calamum_dashboard.stderr.log",
        "dashboard.stdout": log_dir / "calamum_dashboard.stdout.log",
        "ghost_console_backend.stderr": log_dir / "ghost_console_backend.stderr.log",
        "ghost_console_backend.stdout": log_dir / "ghost_console_backend.stdout.log",
    }
    service_logs: List[Dict[str, Any]] = []
    for name, p in service_targets.items():
        st = _safe_stat(p)
        age = _age_seconds(st.mtime, now)
        service_logs.append(
            {
                "name": name,
                "path": _rel_to(p, repo_root),
                "exists": bool(st.exists),
                "size_bytes": int(st.size_bytes),
                "age_seconds": None if age is None else round(float(age), 3),
                "sha256_tail": _sha256_tail(p, max_bytes=int(max_tail_bytes)) if st.exists else "",
            }
        )

    # Strays scout (names-only)
    stray_artifacts = _scout_strays(project_root=project_root, repo_root=repo_root, max_results=int(scout_max_results))

    # Path safety + summary status
    canonical_log_dir = (project_root / "logs").resolve()
    log_dir_is_project_local = _is_within(log_dir, project_root)
    log_dir_is_canonical = log_dir.resolve() == canonical_log_dir

    hb_statuses = [str(h.get("status") or "") for h in heartbeats]
    if "ERR" in hb_statuses:
        overall_status = "ERR"
    elif "WARN" in hb_statuses:
        overall_status = "WARN"
    else:
        overall_status = "OK"

    # Figures of interest + derived collection density.
    active_tel = [r for r in telemetry if isinstance(r, dict) and ("records" in r)]
    active_records_by_file: Dict[str, int] = {}
    active_records_total = 0
    active_bytes_total = 0
    active_ages: List[float] = []
    for r in active_tel:
        try:
            name = str(r.get("name") or "")
            rec = int(r.get("records") or 0)
            sz = int(r.get("size_bytes") or 0)
            age = r.get("age_seconds")
            active_records_by_file[name] = rec
            active_records_total += rec
            active_bytes_total += sz
            if isinstance(age, (int, float)):
                active_ages.append(float(age))
        except Exception:
            continue

    archived_records_total = int(totals.get("archive_records") or 0)
    total_records = int(active_records_total + archived_records_total)

    archive_entries: Optional[int] = None
    for r in telemetry:
        if isinstance(r, dict) and r.get("name") == "archive/manifest.json" and ("entries" in r):
            try:
                v = r.get("entries")
                archive_entries = None if v is None else int(v)
            except Exception:
                archive_entries = None
            break

    freshest_tel_age_s = min(active_ages) if active_ages else None
    stalest_tel_age_s = max(active_ages) if active_ages else None
    hb_ages: List[float] = []
    for h in heartbeats:
        age_v = h.get("age_seconds")
        if isinstance(age_v, (int, float)):
            hb_ages.append(float(age_v))
    freshest_hb_age_s = min(hb_ages) if hb_ages else None
    stalest_hb_age_s = max(hb_ages) if hb_ages else None

    bytes_per_record: Optional[float] = None
    if active_records_total > 0 and active_bytes_total >= 0:
        try:
            bytes_per_record = float(active_bytes_total) / float(active_records_total)
        except Exception:
            bytes_per_record = None

    # Report-to-report deltas (density) based on local provenance JSONL.
    prev_snapshot, prev_baseline = _read_last_provenance_records(jsonl_path)
    cur_dt = _parse_utc_ts(ts)

    def _extract_metrics(rec: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not rec or not isinstance(rec, dict):
            return {}
        m = rec.get("metrics")
        return m if isinstance(m, dict) else {}

    prev_metrics = _extract_metrics(prev_snapshot)
    base_metrics = _extract_metrics(prev_baseline)

    def _delta_rate(*, prior_rec: Optional[Dict[str, Any]], prior_metrics: Dict[str, Any]) -> Dict[str, Any]:
        prior_dt = _parse_utc_ts(str((prior_rec or {}).get("timestamp_utc") or ""))
        if cur_dt is None or prior_dt is None:
            return {"ok": False}
        elapsed_s = (cur_dt - prior_dt).total_seconds()
        if elapsed_s <= 0:
            return {"ok": False, "elapsed_s": elapsed_s}
        try:
            prior_active_total = int(prior_metrics.get("active_records_total") or 0)
        except Exception:
            prior_active_total = 0
        try:
            prior_total = int(prior_metrics.get("total_records") or 0)
        except Exception:
            prior_total = 0
        delta_active = int(active_records_total - prior_active_total)
        delta_total = int(total_records - prior_total)
        active_rps = float(delta_active) / float(elapsed_s)
        total_rps = float(delta_total) / float(elapsed_s)

        by_file_prev = prior_metrics.get("active_records_by_file")
        by_file_prev_d = by_file_prev if isinstance(by_file_prev, dict) else {}
        delta_by_file: Dict[str, int] = {}
        for k, v in active_records_by_file.items():
            try:
                prev_v = int(by_file_prev_d.get(k) or 0)
            except Exception:
                prev_v = 0
            delta_by_file[k] = int(v - prev_v)

        return {
            "ok": True,
            "elapsed_s": float(elapsed_s),
            "delta_active_records": int(delta_active),
            "delta_total_records": int(delta_total),
            "active_rps": float(active_rps),
            "total_rps": float(total_rps),
            "delta_active_records_by_file": delta_by_file,
        }

    density_since_prev = _delta_rate(prior_rec=prev_snapshot, prior_metrics=prev_metrics) if prev_snapshot else {"ok": False}
    density_since_baseline = _delta_rate(prior_rec=prev_baseline, prior_metrics=base_metrics) if prev_baseline else {"ok": False}

    figures_rows: List[List[str]] = []
    figures_rows.append(["Active telemetry records (sum)", str(active_records_total), "Across *.jsonl under data_dir"])
    figures_rows.append(["Archived telemetry records", str(archived_records_total), "From archive/manifest.json"])
    figures_rows.append(["Total telemetry records", str(total_records), "Active + archived"])
    figures_rows.append(["Active telemetry size", _fmt_bytes(int(active_bytes_total)), "Sum of active *.jsonl sizes"])
    if bytes_per_record is None:
        figures_rows.append(["Active bytes/record", "(n/a)", "Requires active_records_total > 0"])
    else:
        figures_rows.append(["Active bytes/record", f"{bytes_per_record:.2f}", "Approximate (active only)"])
    if freshest_tel_age_s is None:
        figures_rows.append(["Freshest telemetry age_s", "(n/a)", "No active telemetry files"])
    else:
        figures_rows.append(["Freshest telemetry age_s", f"{freshest_tel_age_s:.3f}", "Lower is fresher"])
    if stalest_tel_age_s is None:
        figures_rows.append(["Stalest telemetry age_s", "(n/a)", "No active telemetry files"])
    else:
        figures_rows.append(["Stalest telemetry age_s", f"{stalest_tel_age_s:.3f}", "Higher suggests staleness"])
    if archive_entries is not None:
        figures_rows.append(["Archive manifest entries", str(archive_entries), "Number of archived shards"])
    if freshest_hb_age_s is not None:
        figures_rows.append(["Freshest heartbeat age_s", f"{freshest_hb_age_s:.3f}", "Lower is fresher"])
    if stalest_hb_age_s is not None:
        figures_rows.append(["Stalest heartbeat age_s", f"{stalest_hb_age_s:.3f}", "Higher suggests staleness"])
    figures_rows.append(["Stray artifacts (scout)", str(len(stray_artifacts)), f"Max {scout_max_results} reported"])

    figures_of_interest_block = _md_table(["Metric", "Value", "Notes"], figures_rows)

    density_rows: List[List[str]] = []
    if density_since_prev.get("ok"):
        density_rows.append(
            [
                "Report-to-report active collection rate",
                _fmt_rate(float(density_since_prev.get("active_rps") or 0.0)),
                f"delta_active={density_since_prev.get('delta_active_records')} over {density_since_prev.get('elapsed_s'):.1f}s",
            ]
        )
        density_rows.append(
            [
                "Report-to-report total collection rate",
                _fmt_rate(float(density_since_prev.get("total_rps") or 0.0)),
                f"delta_total={density_since_prev.get('delta_total_records')} over {density_since_prev.get('elapsed_s'):.1f}s",
            ]
        )
    else:
        density_rows.append(["Report-to-report active collection rate", "(n/a)", "No prior snapshot metrics in provenance JSONL"])

    if density_since_baseline.get("ok"):
        density_rows.append(
            [
                "Since-baseline active collection rate",
                _fmt_rate(float(density_since_baseline.get("active_rps") or 0.0)),
                f"delta_active={density_since_baseline.get('delta_active_records')} over {density_since_baseline.get('elapsed_s'):.1f}s",
            ]
        )
    else:
        density_rows.append(["Since-baseline active collection rate", "(n/a)", "No baseline record present (use --set-baseline)"])

    # Per-stream deltas (if available)
    per_stream_block = ""
    if density_since_prev.get("ok"):
        delta_by_file = density_since_prev.get("delta_active_records_by_file")
        if isinstance(delta_by_file, dict) and delta_by_file:
            per_rows: List[List[str]] = []
            for k in sorted(delta_by_file.keys()):
                try:
                    d = int(delta_by_file.get(k) or 0)
                except Exception:
                    d = 0
                per_rows.append([str(k), str(d), "delta records since previous report"])
            per_stream_block = _md_table(["Stream", "Delta records", "Notes"], per_rows)

    collection_density_block = _md_table(["Metric", "Value", "Notes"], density_rows)
    if per_stream_block:
        collection_density_block = collection_density_block + "\n\n" + per_stream_block

    future_rows: List[List[str]] = [
        ["Label coverage (pct)", "TBD", "analysis/build_dataset.py outputs labels.csv (future)",],
        ["Signature verification pass rate", "TBD", "analysis/validate_jsonl.py (future integration)",],
        ["Baseline FPR at chosen threshold", "TBD", "analysis/evaluate_baseline.py run ledger",],
        ["Drift score (feature distribution)", "TBD", "planned: analysis/drift.py (stdlib-only)",],
        ["Anomalies per 1k records", "TBD", "planned: anomaly flags in telemetry schema",],
    ]
    future_placeholders_block = _md_table(["Placeholder metric", "Value", "Planned source"], future_rows)

    derived_metrics: Dict[str, Any] = {
        "active_records_total": int(active_records_total),
        "archived_records_total": int(archived_records_total),
        "total_records": int(total_records),
        "active_bytes_total": int(active_bytes_total),
        "active_bytes_per_record": None if bytes_per_record is None else float(bytes_per_record),
        "freshest_telemetry_age_s": None if freshest_tel_age_s is None else float(freshest_tel_age_s),
        "stalest_telemetry_age_s": None if stalest_tel_age_s is None else float(stalest_tel_age_s),
        "freshest_heartbeat_age_s": None if freshest_hb_age_s is None else float(freshest_hb_age_s),
        "stalest_heartbeat_age_s": None if stalest_hb_age_s is None else float(stalest_hb_age_s),
        "active_records_by_file": dict(active_records_by_file),
        "density_since_previous": density_since_prev,
        "density_since_baseline": density_since_baseline,
    }

    evidence: Dict[str, Any] = {
        "timestamp_utc": ts,
        "run_id": run_id,
        "auditor": AUDITOR,
        "dry_run": bool(dry_run),
        "git": git,
        "derived_metrics": derived_metrics,
        "paths": {
            "repo_root": str(repo_root),
            "project_root": str(project_root),
            "log_dir": str(log_dir),
            "data_dir": str(data_dir),
            "control_dir": str(ctrl_dir),
            "health_dir": str(health_dir),
            "canonical_log_dir": str(canonical_log_dir),
        },
        "env": {
            "present": env_presence,
            "summary_lines": list(env_lines),
            "moltbook": {
                "enabled": bool(moltbook_enabled),
                "host_present": bool(_env_flag("MOLTBOOK_HOST")),
            },
        },
        "checks": {
            "overall_status": overall_status,
            "path_safety": {
                "log_dir_is_project_local": bool(log_dir_is_project_local),
                "log_dir_is_canonical": bool(log_dir_is_canonical),
                "git_ignored": {
                    "out_dir": _git_is_ignored(repo_root, out_dir),
                    "jsonl": _git_is_ignored(repo_root, jsonl_path),
                    "audit_index": _git_is_ignored(repo_root, index_path),
                },
            },
            "heartbeats": heartbeats,
            "heartbeat_thresholds": {"warn_seconds": hb_warn_seconds, "err_seconds": hb_err_seconds},
            "telemetry": telemetry,
            "control_signals": control,
            "service_logs": service_logs,
            "stray_artifacts": stray_artifacts,
        },
        "outputs": {
            "report_path": str(report_path),
            "evidence_path": str(evidence_path),
            "audit_jsonl_path": str(jsonl_path),
            "audit_index_path": str(index_path),
        },
    }

    # Render report
    try:
        tpl = tpl_path.read_text(encoding="utf-8")
    except Exception:
        tpl = "# Calamum Ops Parameters Report\n\n[ERR] template missing: {{ template_path }}\n"

    safety_lines = [
        f"log_dir_is_project_local: {log_dir_is_project_local}",
        f"log_dir_is_canonical: {log_dir_is_canonical}",
        f"canonical_log_dir: {canonical_log_dir}",
    ]

    hb_lines: List[str] = []
    for row in heartbeats:
        tag = f"[{row.get('status', '')}]"
        if not row.get("exists"):
            hb_lines.append(f"{tag} {row.get('name')}: MISSING ({row.get('path')})")
        else:
            hb_lines.append(
                f"{tag} {row.get('name')}: present | age_s={row.get('age_seconds')} | size={_fmt_bytes(int(row.get('size_bytes') or 0))} | {row.get('path')}"
            )

    tel_lines: List[str] = []
    for row in telemetry:
        if row.get("name") == "data_dir" and not row.get("exists"):
            tel_lines.append(f"data_dir: MISSING ({row.get('path')})")
            continue
        if "records" in row:
            tel_lines.append(
                f"{row.get('name')}: records={row.get('records')} | partial_last_line={row.get('partial_last_line')} | size={_fmt_bytes(int(row.get('size_bytes') or 0))} | age_s={row.get('age_seconds')} | sha256_tail={row.get('sha256_tail')}"
            )
        elif row.get("name") == "archive/manifest.json" and row.get("exists"):
            tel_lines.append(
                f"archive/manifest.json: archived_records={row.get('archived_records')} | entries={row.get('entries')} | sha256_tail={row.get('sha256_tail')}"
            )
        elif row.get("name") == "archive/manifest.json":
            tel_lines.append("archive/manifest.json: unreadable")

    ctrl_lines: List[str] = []
    for row in control:
        if row.get("name") == "control_dir" and not row.get("exists", True):
            ctrl_lines.append(f"control_dir: MISSING ({row.get('path')})")
            continue
        suffix = "dir" if row.get("is_dir") else f"size={_fmt_bytes(int(row.get('size_bytes') or 0))}"
        ctrl_lines.append(f"{row.get('name')}: {suffix} | age_s={row.get('age_seconds')} | {row.get('path')}")

    svc_lines: List[str] = []
    for row in service_logs:
        if not row.get("exists"):
            svc_lines.append(f"{row.get('name')}: MISSING ({row.get('path')})")
        else:
            svc_lines.append(
                f"{row.get('name')}: size={_fmt_bytes(int(row.get('size_bytes') or 0))} | age_s={row.get('age_seconds')} | sha256_tail={row.get('sha256_tail')} | {row.get('path')}"
            )

    stray_lines: List[str] = []
    if not stray_artifacts:
        stray_lines.append("(none found)")
    else:
        for row in stray_artifacts:
            kind = str(row.get("kind", ""))
            reason = str(row.get("reason", ""))
            if kind == "dir":
                stray_lines.append(f"{row.get('path')}: {reason} | size={_fmt_bytes(int(row.get('size_bytes') or 0))}")
            else:
                stray_lines.append(
                    f"{row.get('path')}: {reason} | size={_fmt_bytes(int(row.get('size_bytes') or 0))} | sha256_tail={row.get('sha256_tail')}"
                )

    report_vars: Dict[str, Any] = {
        "timestamp_utc": ts,
        "run_id": run_id,
        "auditor": AUDITOR,
        "overall_status": overall_status,
        "repo_root": str(repo_root),
        "project_root": str(project_root),
        "log_dir": str(log_dir),
        "figures_of_interest_block": figures_of_interest_block,
        "collection_density_block": collection_density_block,
        "future_placeholders_block": future_placeholders_block,
        "env_vars_block": _block(env_lines),
        "path_safety_block": _block(safety_lines),
        "heartbeats_block": _block(hb_lines),
        "telemetry_block": _block(tel_lines),
        "control_signals_block": _block(ctrl_lines),
        "service_logs_block": _block(svc_lines),
        "stray_artifacts_block": _block(stray_lines),
        "evidence_path": str(evidence_path),
        "report_path": str(report_path),
        "audit_jsonl_path": str(jsonl_path),
        "audit_index_path": str(index_path),
        "template_path": str(tpl_path),
    }

    rendered = _render_template(tpl, report_vars)

    if not dry_run:
        evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        report_path.write_text(rendered, encoding="utf-8")

        # Append provenance JSONL
        snapshot_metrics = {
            "active_records_total": int(active_records_total),
            "archived_records_total": int(archived_records_total),
            "total_records": int(total_records),
            "active_bytes_total": int(active_bytes_total),
            "active_records_by_file": dict(active_records_by_file),
        }
        snapshot = {
            "kind": "snapshot",
            "timestamp_utc": ts,
            "run_id": run_id,
            "auditor": AUDITOR,
            "git": {"head": git.get("head", ""), "branch": git.get("branch", ""), "is_dirty": git.get("is_dirty", False)},
            "report": _rel_to(report_path, repo_root),
            "evidence": _rel_to(evidence_path, repo_root),
            "overall_status": overall_status,
            "metrics": snapshot_metrics,
        }
        try:
            with jsonl_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(snapshot, sort_keys=True, ensure_ascii=True) + "\n")
                if set_baseline:
                    baseline = dict(snapshot)
                    baseline["kind"] = "baseline"
                    baseline["baseline_id"] = uuid.uuid4().hex
                    f.write(json.dumps(baseline, sort_keys=True, ensure_ascii=True) + "\n")
        except Exception:
            pass

        # Update local audit index
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
        audits["ops_parameters"] = {
            "timestamp_utc": ts,
            "run_id": run_id,
            "git": {"head": git.get("head", ""), "branch": git.get("branch", ""), "is_dirty": git.get("is_dirty", False)},
            "report": _rel_to(report_path, repo_root),
            "evidence": _rel_to(evidence_path, repo_root),
            "jsonl": _rel_to(jsonl_path, repo_root),
            "overall_status": overall_status,
        }
        existing["updated_at_utc"] = ts
        existing["git"] = {"head": git.get("head", ""), "branch": git.get("branch", ""), "is_dirty": git.get("is_dirty", False)}
        existing["audits"] = audits
        try:
            index_path.write_text(json.dumps(existing, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        except Exception:
            pass

    return evidence


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Calamum operations parameters report")
    ap.add_argument(
        "--template",
        default="projects/calamum-moltbook-observer/template_library/reports/CALAMUM_OPS_PARAMETERS_REPORT_TEMPLATE.md.template",
        help="Repo-relative path to the markdown template",
    )
    ap.add_argument(
        "--out-dir",
        default="local_untracked/reports/ops_parameters",
        help="Project-relative output directory (should be ignored)",
    )
    ap.add_argument(
        "--jsonl",
        default="local_untracked/audit_log/ops_parameters_report.jsonl",
        help="Project-relative JSONL provenance log (append-only, should be ignored)",
    )
    ap.add_argument(
        "--max-tail-bytes",
        type=int,
        default=(64 * 1024),
        help="Max bytes to hash from the end of each file (sha256_tail).",
    )
    ap.add_argument(
        "--hb-warn-seconds",
        type=float,
        default=300.0,
        help="Heartbeat age (seconds) at/above which status becomes WARN.",
    )
    ap.add_argument(
        "--hb-err-seconds",
        type=float,
        default=900.0,
        help="Heartbeat age (seconds) at/above which status becomes ERR.",
    )
    ap.add_argument(
        "--scout-max-results",
        type=int,
        default=50,
        help="Max number of stray artifacts to report.",
    )
    ap.add_argument(
        "--set-baseline",
        action="store_true",
        help="Also append a baseline record to the JSONL provenance log",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute findings and print would-be output paths, but do not write any files",
    )
    args = ap.parse_args(argv)

    repo_root, project_root = _repo_root_from_here(Path(__file__))

    try:
        evidence = report_ops_parameters(
            repo_root=repo_root,
            project_root=project_root,
            template_rel=str(args.template),
            out_dir_rel=str(args.out_dir),
            jsonl_rel=str(args.jsonl),
            max_tail_bytes=int(args.max_tail_bytes),
            hb_warn_seconds=float(args.hb_warn_seconds) if args.hb_warn_seconds is not None else None,
            hb_err_seconds=float(args.hb_err_seconds) if args.hb_err_seconds is not None else None,
            scout_max_results=int(args.scout_max_results),
            set_baseline=bool(args.set_baseline),
            dry_run=bool(args.dry_run),
        )
    except Exception as e:
        print(f"[ERR] ops parameters report failed: {e}")
        return 2

    outputs = evidence.get("outputs", {}) if isinstance(evidence.get("outputs"), dict) else {}
    if bool(args.dry_run):
        print("Calamum ops parameters report DRY-RUN complete")
        print(f"would_write_report:  {outputs.get('report_path', '')}")
        print(f"would_write_evidence:{outputs.get('evidence_path', '')}")
        print(f"would_append_jsonl:  {outputs.get('audit_jsonl_path', '')}")
        print(f"would_update_index:  {outputs.get('audit_index_path', '')}")
    else:
        print("Calamum ops parameters report complete")
        print(f"project_root: {project_root}")
        print(f"report:       {outputs.get('report_path', '')}")
        print(f"evidence:     {outputs.get('evidence_path', '')}")
        print(f"audit_jsonl:  {outputs.get('audit_jsonl_path', '')}")
        print(f"audit_index:  {outputs.get('audit_index_path', '')}")
        overall = (evidence.get('checks', {}) or {}).get('overall_status', '?')
        print(f"overall:      {overall}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
