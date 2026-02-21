"""Audit runtime artifacts for Calamum Moltbook Observer.

This is a best-effort *offline* audit that is safe for school demos:
- Names-only evidence (paths, sizes, mtimes, hashes, counts).
- No raw log tails are embedded in evidence or reports by default.

Outputs (default; all ignored under local_untracked/):
- Markdown report rendered from a tracked template.
- JSON evidence bundle.
- Append-only JSONL provenance log (untracked).
- Central audit index pointer (untracked).

Run from repo root:
    .venv-core\\Scripts\\python.exe projects\\calamum-moltbook-observer\\tools\\audit_runtime_artifacts.py

Refresh modes:
    --watchdog-refresh pre
        Refresh watchdog instance before collecting diagnostics.
    --watchdog-refresh on-stale
        Collect heartbeats first; refresh only if watchdog is WARN/ERR.

Default refresh method uses dashboard restart via launch_ghost_console.ps1
with CALAMUM_SKIP_BROWSER=1. A custom PowerShell refresh command can be
provided when alternate remediation is preferred.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
import uuid
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


AUDITOR = "ORACL-Prime"


def _ensure_project_src_on_path() -> None:
    """Best-effort: allow importing project-local modules without installing the package."""
    try:
        project_root = Path(__file__).resolve().parents[1]
        src_dir = project_root / "src"
        if src_dir.is_dir():
            s = str(src_dir)
            if s not in sys.path:
                sys.path.insert(0, s)
    except Exception:
        pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# Optional: verify watchdog heartbeat signatures when verifier is available.
_ensure_project_src_on_path()
try:
    import obfuscator_lib  # type: ignore
except ImportError:  # pragma: no cover
    obfuscator_lib = None


def _verify_signed_record_best_effort(path: Path) -> Tuple[Optional[bool], str]:
    """Return (signature_valid_or_None_if_unavailable, detail)."""
    if not obfuscator_lib:
        return None, "unavailable"
    if not path.exists():
        return False, "missing"
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
        data = json.loads(raw or "{}")
        if not isinstance(data, dict):
            return False, "not-a-dict"
        ok = bool(obfuscator_lib.Obfuscator.verify_record(data))
        return (True, "ok") if ok else (False, "invalid")
    except Exception:
        return False, "error"



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


def _scout_stray_artifacts(
    *,
    project_root: Path,
    repo_root: Path,
    now: float,
    enabled: bool,
    max_results: int,
) -> List[Dict[str, Any]]:
    if not enabled:
        return []

    # Keep this deliberately small + predictable: scan only within the project tree,
    # excluding known safe/large dirs.
    exclude_dirs = {
        "local_untracked",
        ".git",
        "__pycache__",
        ".pytest_cache",
        "node_modules",
        "dist",
        "build",
        ".venv",
        ".venv-core",
    }

    # Suspicious names/patterns typically created by running services locally.
    suspicious_names = {".env", ".env.local", ".env.dev", ".env.prod"}
    suspicious_suffixes = (".log", ".pid", ".lock", ".sqlite", ".db")
    suspicious_dirs = {"logs", "tmp", "temp"}

    canonical_logs_dir = (project_root / "logs").resolve()
    allowed_root_pidfiles = {
        "calamum_agent.pid",
        "calamum_librarian.pid",
        "calamum_watchdog.pid",
        "ghost_console.pid",
    }

    hits: List[Dict[str, Any]] = []

    # Ensure deterministic traversal order.
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
                # Treat project_root/logs as the canonical runtime location. We do not flag it as stray,
                # and we also avoid descending into it (large/uninteresting for stray scouting).
                if p.name == "logs" and p.resolve() == canonical_logs_dir:
                    continue

                if p.name in suspicious_dirs:
                    st = _safe_stat(p)
                    hits.append(
                        {
                            "kind": "dir",
                            "name": p.name + "/",
                            "path": _rel_to(p, repo_root),
                            "size_bytes": int(st.size_bytes),
                            "age_seconds": None if st.mtime == 0 else round(float(_age_seconds(st.mtime, now) or 0.0), 3),
                            "reason": "suspicious_dir",
                        }
                    )
                    if len(hits) >= int(max_results):
                        return hits

                # Depth-first (deterministic): push children to stack.
                stack.append(p)
                continue

            name_l = p.name.lower()
            st = _safe_stat(p)
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
                        "name": p.name,
                        "path": _rel_to(p, repo_root),
                        "size_bytes": int(st.size_bytes),
                        "age_seconds": None if st.mtime == 0 else round(float(_age_seconds(st.mtime, now) or 0.0), 3),
                        "sha256_tail": _sha256_tail(p, max_bytes=(16 * 1024)) if st.exists else "",
                        "reason": reason,
                    }
                )
                if len(hits) >= int(max_results):
                    return hits

    return hits


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


def _block(lines: Sequence[str], empty_msg: str = "(none)") -> str:
    if not lines:
        return empty_msg
    return "\n".join([f"- {ln}" for ln in lines])


def _repo_root_from_here(here: Path) -> Tuple[Path, Path]:
    # .../projects/calamum-moltbook-observer/tools/audit_runtime_artifacts.py
    project_root = here.resolve().parents[1]
    repo_root = here.resolve().parents[3]
    return repo_root, project_root


def _collect_heartbeats(
    *,
    health_dir: Path,
    repo_root: Path,
    now: float,
    hb_warn_seconds: Optional[float],
    hb_err_seconds: Optional[float],
) -> List[Dict[str, Any]]:
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

        sig_ok: Optional[bool] = None
        sig_detail = "unavailable"
        if name == "watchdog":
            sig_ok, sig_detail = _verify_signed_record_best_effort(p)
            # If signature verification is available and fails, treat watchdog as ERR even if fresh.
            if sig_ok is False:
                status = "ERR"

        heartbeats.append(
            {
                "name": name,
                "path": _rel_to(p, repo_root),
                "exists": bool(st.exists),
                "size_bytes": int(st.size_bytes),
                "age_seconds": None if age is None else round(float(age), 3),
                "status": status,
                "signature_check_available": bool(obfuscator_lib) if name == "watchdog" else False,
                "signature_valid": sig_ok if name == "watchdog" else None,
                "signature_detail": sig_detail if name == "watchdog" else None,
            }
        )
    return heartbeats


def _refresh_watchdog_instance(
    *,
    project_root: Path,
    method: str,
    custom_command: str,
    timeout_sec: float,
    reason: str,
) -> Dict[str, Any]:
    started = _now()

    if method == "dashboard-restart":
        launcher = (project_root / "launch_ghost_console.ps1").resolve()
        if not launcher.exists():
            return {
                "ok": False,
                "method": method,
                "reason": reason,
                "error": f"launcher_missing:{launcher}",
                "duration_s": round(float(_now() - started), 3),
            }
        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(launcher),
        ]
        env = os.environ.copy()
        # Runtime diagnostics should never pop UI windows.
        env["CALAMUM_SKIP_BROWSER"] = "1"
    elif method == "custom-command":
        if not custom_command.strip():
            return {
                "ok": False,
                "method": method,
                "reason": reason,
                "error": "custom_command_missing",
                "duration_s": round(float(_now() - started), 3),
            }
        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            custom_command,
        ]
        env = os.environ.copy()
    else:
        return {
            "ok": False,
            "method": method,
            "reason": reason,
            "error": f"unsupported_method:{method}",
            "duration_s": round(float(_now() - started), 3),
        }

    try:
        p = subprocess.run(
            cmd,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=float(timeout_sec),
            check=False,
            env=env,
        )
        return {
            "ok": int(p.returncode) == 0,
            "method": method,
            "reason": reason,
            "returncode": int(p.returncode),
            "duration_s": round(float(_now() - started), 3),
            "stderr_nonempty": bool((p.stderr or "").strip()),
            "stdout_nonempty": bool((p.stdout or "").strip()),
        }
    except Exception as e:
        return {
            "ok": False,
            "method": method,
            "reason": reason,
            "error": repr(e),
            "duration_s": round(float(_now() - started), 3),
        }


def audit_runtime_artifacts(
    *,
    repo_root: Path,
    project_root: Path,
    template_rel: str,
    out_dir_rel: str,
    jsonl_rel: str,
    max_tail_bytes: int,
    hb_warn_seconds: Optional[float],
    hb_err_seconds: Optional[float],
    watchdog_refresh: str,
    watchdog_refresh_method: str,
    watchdog_refresh_command: str,
    watchdog_refresh_timeout_sec: float,
    watchdog_refresh_settle_sec: float,
    scout_strays: bool,
    scout_max_results: int,
    set_baseline: bool,
    dry_run: bool,
) -> Dict[str, Any]:
    ts = _utc_now()
    run_id = uuid.uuid4().hex
    git = _git_info(repo_root)

    # Calamum operational root is the project root; runtime artifacts live under project_root/logs.
    log_dir = (project_root / "logs").resolve()
    data_dir = (log_dir / "data" / "calamum").resolve()
    health_dir = (log_dir / "health").resolve()
    ctrl_dir = (log_dir / "control" / "calamum").resolve()

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
    report_path = out_dir / f"calamum_runtime_artifacts_audit_{ts_slug}.md"
    evidence_path = out_dir / f"calamum_runtime_artifacts_audit_{ts_slug}.evidence.json"

    now = _now()

    refresh_events: List[Dict[str, Any]] = []
    requested_refresh = str(watchdog_refresh or "none").strip().lower()

    if requested_refresh == "pre":
        evt = _refresh_watchdog_instance(
            project_root=project_root,
            method=str(watchdog_refresh_method),
            custom_command=str(watchdog_refresh_command or ""),
            timeout_sec=float(watchdog_refresh_timeout_sec),
            reason="pre_diagnostic_refresh",
        )
        refresh_events.append(evt)
        if evt.get("ok") and watchdog_refresh_settle_sec > 0:
            time.sleep(float(watchdog_refresh_settle_sec))
        now = _now()

    # Heartbeats
    heartbeats = _collect_heartbeats(
        health_dir=health_dir,
        repo_root=repo_root,
        now=now,
        hb_warn_seconds=hb_warn_seconds,
        hb_err_seconds=hb_err_seconds,
    )

    if requested_refresh == "on-stale":
        watchdog_row = next((row for row in heartbeats if str(row.get("name") or "") == "watchdog"), None)
        stale = False
        if isinstance(watchdog_row, dict):
            status = str(watchdog_row.get("status") or "").upper()
            stale = status in {"WARN", "ERR"}

        if stale:
            evt = _refresh_watchdog_instance(
                project_root=project_root,
                method=str(watchdog_refresh_method),
                custom_command=str(watchdog_refresh_command or ""),
                timeout_sec=float(watchdog_refresh_timeout_sec),
                reason="stale_watchdog_heartbeat",
            )
            refresh_events.append(evt)
            if evt.get("ok") and watchdog_refresh_settle_sec > 0:
                time.sleep(float(watchdog_refresh_settle_sec))
            now = _now()
            heartbeats = _collect_heartbeats(
                health_dir=health_dir,
                repo_root=repo_root,
                now=now,
                hb_warn_seconds=hb_warn_seconds,
                hb_err_seconds=hb_err_seconds,
            )

    # Telemetry JSONL
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

    # Service log stats (no tail text)
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

    canary = int(totals.get("moltbook_canary_metrics.jsonl", 0))
    live = int(totals.get("moltbook_live_metrics.jsonl", 0))
    obf = int(totals.get("moltbook_samples_obfuscated.jsonl", 0))
    archival = int(totals.get("archive_records", 0))
    total_est = int(canary + live + obf + archival)

    # Optional: stray runtime artifacts scout (names-only, project tree only).
    stray_artifacts = _scout_stray_artifacts(
        project_root=project_root,
        repo_root=repo_root,
        now=now,
        enabled=bool(scout_strays),
        max_results=int(scout_max_results),
    )

    evidence: Dict[str, Any] = {
        "timestamp_utc": ts,
        "run_id": run_id,
        "auditor": AUDITOR,
        "dry_run": bool(dry_run),
        "git": git,
        "paths": {
            "repo_root": str(repo_root),
            "project_root": str(project_root),
            "log_dir": str(log_dir),
        },
        "checks": {
            "heartbeats": heartbeats,
            "heartbeat_thresholds": {
                "warn_seconds": hb_warn_seconds,
                "err_seconds": hb_err_seconds,
            },
            "watchdog_refresh": {
                "requested_mode": requested_refresh,
                "method": str(watchdog_refresh_method),
                "command_override_present": bool(str(watchdog_refresh_command or "").strip()),
                "timeout_sec": float(watchdog_refresh_timeout_sec),
                "settle_sec": float(watchdog_refresh_settle_sec),
                "events": refresh_events,
            },
            "telemetry": telemetry,
            "control_signals": control,
            "service_logs": service_logs,
            "stray_artifacts": stray_artifacts,
            "record_volume_hint": {
                "canary": canary,
                "live": live,
                "samples_obfuscated": obf,
                "archive_records": archival,
                "sum_rough": total_est,
            },
            "output_safety": {
                "local_untracked_root": str(local_untracked_root),
                "max_tail_bytes": int(max_tail_bytes),
                "git_ignored": {
                    "out_dir": _git_is_ignored(repo_root, out_dir),
                    "jsonl": _git_is_ignored(repo_root, jsonl_path),
                    "audit_index": _git_is_ignored(repo_root, index_path),
                },
            },
        },
        "outputs": {
            "report_path": str(report_path),
            "evidence_path": str(evidence_path),
            "audit_jsonl_path": str(jsonl_path),
            "audit_index_path": str(index_path),
        },
    }

    # Render report.
    try:
        tpl = tpl_path.read_text(encoding="utf-8")
    except Exception:
        tpl = "# Calamum Runtime Artifacts Audit\n\n[ERR] template missing: {{ template_path }}\n"

    hb_lines = []
    for row in heartbeats:
        tag = f"[{row.get('status', '')}]"
        if not row.get("exists"):
            hb_lines.append(f"{tag} {row.get('name')}: MISSING ({row.get('path')})")
        else:
            hb_lines.append(
                f"{tag} {row.get('name')}: present | age_s={row.get('age_seconds')} | size={_fmt_bytes(int(row.get('size_bytes') or 0))} | {row.get('path')}"
            )

    tel_lines = []
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

    ctrl_lines = []
    for row in control:
        if row.get("name") == "control_dir" and not row.get("exists", True):
            ctrl_lines.append(f"control_dir: MISSING ({row.get('path')})")
            continue
        suffix = "dir" if row.get("is_dir") else f"size={_fmt_bytes(int(row.get('size_bytes') or 0))}"
        ctrl_lines.append(f"{row.get('name')}: {suffix} | age_s={row.get('age_seconds')} | {row.get('path')}")

    svc_lines = []
    for row in service_logs:
        if not row.get("exists"):
            svc_lines.append(f"{row.get('name')}: MISSING ({row.get('path')})")
        else:
            svc_lines.append(
                f"{row.get('name')}: size={_fmt_bytes(int(row.get('size_bytes') or 0))} | age_s={row.get('age_seconds')} | sha256_tail={row.get('sha256_tail')} | {row.get('path')}"
            )

    stray_lines: List[str] = []
    if not scout_strays:
        stray_lines.append("(scout disabled)")
    else:
        if not stray_artifacts:
            stray_lines.append("(none found)")
        else:
            for row in stray_artifacts:
                kind = str(row.get("kind", ""))
                reason = str(row.get("reason", ""))
                if kind == "dir":
                    stray_lines.append(f"{row.get('name')}: {reason} | age_s={row.get('age_seconds')} | {row.get('path')}")
                else:
                    stray_lines.append(
                        f"{row.get('name')}: {reason} | size={_fmt_bytes(int(row.get('size_bytes') or 0))} | age_s={row.get('age_seconds')} | sha256_tail={row.get('sha256_tail')} | {row.get('path')}"
                    )

    report_vars: Dict[str, Any] = {
        "timestamp_utc": ts,
        "run_id": run_id,
        "auditor": AUDITOR,
        "git_branch": str(git.get("branch", "")),
        "git_head": str(git.get("head", "")),
        "git_is_dirty": str(bool(git.get("is_dirty", False))),
        "repo_root": str(repo_root),
        "project_root": str(project_root),
        "log_dir": str(log_dir),
        "heartbeats_block": _block(hb_lines),
        "telemetry_block": _block(tel_lines),
        "control_signals_block": _block(ctrl_lines),
        "service_logs_block": _block(svc_lines),
        "stray_artifacts_block": _block(stray_lines),
        "record_volume_canary": str(canary),
        "record_volume_live": str(live),
        "record_volume_samples_obfuscated": str(obf),
        "record_volume_archive_records": str(archival),
        "record_volume_sum_rough": str(total_est),
        "evidence_path": str(evidence_path),
        "audit_jsonl_path": str(jsonl_path),
        "audit_index_path": str(index_path),
        "template_path": str(tpl_path),
    }

    rendered = _render_template(tpl, report_vars)

    if not dry_run:
        evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        report_path.write_text(rendered, encoding="utf-8")

        # Append provenance JSONL (untracked).
        snapshot = {
            "kind": "snapshot",
            "timestamp_utc": ts,
            "run_id": run_id,
            "auditor": AUDITOR,
            "git": {"head": git.get("head", ""), "branch": git.get("branch", ""), "is_dirty": git.get("is_dirty", False)},
            "report": _rel_to(report_path, repo_root),
            "evidence": _rel_to(evidence_path, repo_root),
            "summary": "[OK]" if log_dir.exists() else "[WARN] logs missing",
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

        # Central audit index update.
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
        audits["runtime"] = {
            "timestamp_utc": ts,
            "run_id": run_id,
            "git": {"head": git.get("head", ""), "branch": git.get("branch", ""), "is_dirty": git.get("is_dirty", False)},
            "report": _rel_to(report_path, repo_root),
            "evidence": _rel_to(evidence_path, repo_root),
            "jsonl": _rel_to(jsonl_path, repo_root),
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
    ap = argparse.ArgumentParser(description="Calamum runtime artifacts audit")
    ap.add_argument(
        "--template",
        default="projects/calamum-moltbook-observer/template_library/reports/CALAMUM_RUNTIME_ARTIFACTS_AUDIT_TEMPLATE.md.template",
        help="Repo-relative path to the markdown template",
    )
    ap.add_argument(
        "--out-dir",
        default="local_untracked/audits/runtime",
        help="Project-relative output directory (should be ignored)",
    )
    ap.add_argument(
        "--jsonl",
        default="local_untracked/audit_log/runtime_artifacts_audit.jsonl",
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
        "--watchdog-refresh",
        choices=["none", "on-stale", "pre"],
        default="none",
        help="Watchdog refresh strategy: none, on-stale (refresh only when watchdog heartbeat is WARN/ERR), or pre (refresh before diagnostics).",
    )
    ap.add_argument(
        "--watchdog-refresh-method",
        choices=["dashboard-restart", "custom-command"],
        default="dashboard-restart",
        help="Refresh method. Default dashboard-restart invokes launch_ghost_console.ps1 with CALAMUM_SKIP_BROWSER=1.",
    )
    ap.add_argument(
        "--watchdog-refresh-command",
        default="",
        help="PowerShell command used when --watchdog-refresh-method custom-command is selected.",
    )
    ap.add_argument(
        "--watchdog-refresh-timeout-sec",
        type=float,
        default=120.0,
        help="Timeout for watchdog refresh action execution.",
    )
    ap.add_argument(
        "--watchdog-refresh-settle-sec",
        type=float,
        default=2.0,
        help="Wait time after a successful refresh before collecting heartbeats.",
    )
    ap.add_argument(
        "--scout-strays",
        action="store_true",
        help="Also scan the project tree for stray runtime artifacts outside logs (names-only).",
    )
    ap.add_argument(
        "--scout-max-results",
        type=int,
        default=50,
        help="Max number of stray artifacts to report when --scout-strays is enabled.",
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
        evidence = audit_runtime_artifacts(
            repo_root=repo_root,
            project_root=project_root,
            template_rel=str(args.template),
            out_dir_rel=str(args.out_dir),
            jsonl_rel=str(args.jsonl),
            max_tail_bytes=int(args.max_tail_bytes),
            hb_warn_seconds=float(args.hb_warn_seconds) if args.hb_warn_seconds is not None else None,
            hb_err_seconds=float(args.hb_err_seconds) if args.hb_err_seconds is not None else None,
            watchdog_refresh=str(args.watchdog_refresh),
            watchdog_refresh_method=str(args.watchdog_refresh_method),
            watchdog_refresh_command=str(args.watchdog_refresh_command),
            watchdog_refresh_timeout_sec=float(args.watchdog_refresh_timeout_sec),
            watchdog_refresh_settle_sec=float(args.watchdog_refresh_settle_sec),
            scout_strays=bool(args.scout_strays),
            scout_max_results=int(args.scout_max_results),
            set_baseline=bool(args.set_baseline),
            dry_run=bool(args.dry_run),
        )
    except Exception as e:
        print(f"[ERR] runtime artifacts audit failed: {e}")
        return 2

    outputs = evidence.get("outputs", {}) if isinstance(evidence.get("outputs"), dict) else {}
    if bool(args.dry_run):
        print("Calamum runtime artifacts audit DRY-RUN complete")
        print(f"would_write_report:  {outputs.get('report_path', '')}")
        print(f"would_write_evidence:{outputs.get('evidence_path', '')}")
        print(f"would_append_jsonl:  {outputs.get('audit_jsonl_path', '')}")
        print(f"would_update_index:  {outputs.get('audit_index_path', '')}")
    else:
        print("Calamum runtime artifacts audit complete")
        print(f"report:   {outputs.get('report_path', '')}")
        print(f"evidence: {outputs.get('evidence_path', '')}")
        print(f"jsonl:    {outputs.get('audit_jsonl_path', '')}")
        print(f"index:    {outputs.get('audit_index_path', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
