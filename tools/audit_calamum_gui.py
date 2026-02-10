"""Audit the Calamum NiceGUI dashboard and write a templated report.

Outputs (default; all ignored under local_untracked/):
- A markdown report rendered from a tracked template.
- A JSON evidence bundle (names-only; no raw HTTP bodies).
- An append-only JSONL audit log (untracked) for provenance snapshots/baselines.
- A central audit index (untracked) pointing to the latest artifacts.

Security:
- No secrets are logged.
- Raw HTTP bodies are not persisted (only hashes/lengths/status).

Network controls:
- Use --no-network to skip ALL network I/O (HTTP + TCP probes).

Usage:
        python projects/calamum-moltbook-observer/tools/audit_calamum_gui.py

Optional env:
    CALAMUM_GUI_URL  (default: http://127.0.0.1:8899)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import uuid
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class HttpResult:
    ok: bool
    status: int
    content_type: str
    body: bytes
    error: Optional[str] = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _run(cmd: list[str], cwd: Path, timeout_sec: float = 8.0) -> Tuple[int, str, str]:
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


def _read_http(url: str, timeout_sec: float = 3.5) -> HttpResult:
    req = Request(url, headers={"User-Agent": "calamum-gui-audit/1.0"})
    try:
        with urlopen(req, timeout=timeout_sec) as resp:
            status = int(getattr(resp, "status", 200))
            ct = str(resp.headers.get("Content-Type") or "")
            body = resp.read() or b""
            return HttpResult(ok=(200 <= status < 300), status=status, content_type=ct, body=body)
    except HTTPError as e:
        try:
            body = e.read() or b""
        except Exception:
            body = b""
        return HttpResult(ok=False, status=int(getattr(e, "code", 0) or 0), content_type=str(getattr(e, "headers", {}).get("Content-Type") if getattr(e, "headers", None) else ""), body=body, error=repr(e))
    except URLError as e:
        return HttpResult(ok=False, status=0, content_type="", body=b"", error=repr(e))
    except Exception as e:
        return HttpResult(ok=False, status=0, content_type="", body=b"", error=repr(e))


def _safe_text(b: bytes, limit: int = 200_000) -> str:
    b = b[: max(0, int(limit))]
    return b.decode("utf-8", errors="replace")


def _sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _tcp_probe(host: str, port: int, timeout_sec: float = 1.5) -> Tuple[bool, str]:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout_sec):
            return True, "ok"
    except Exception as e:
        return False, repr(e)


def _render_template(tpl: str, data: Dict[str, Any]) -> str:
    out = str(tpl)
    for k, v in data.items():
        # Replace {{ key }} (allow whitespace)
        pat = re.compile(r"\{\{\s*" + re.escape(str(k)) + r"\s*\}\}")
        # IMPORTANT (Windows): use a replacement function so backslashes in paths
        # (e.g., C:\Users\...) are not treated as regex escapes.
        out = pat.sub(lambda _m, _v=str(v): _v, out)
    return out


def _repo_root_from_here(here: Path) -> Path:
    project_root = here.resolve().parents[1]
    return project_root.parents[1]


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--url",
        default=os.getenv("CALAMUM_GUI_URL", "http://127.0.0.1:8899"),
        help="Base URL for the GUI (default: env CALAMUM_GUI_URL or http://127.0.0.1:8899)",
    )
    ap.add_argument(
        "--template",
        default="projects/calamum-moltbook-observer/template_library/reports/CALAMUM_GUI_AUDIT_TEMPLATE.md.template",
        help="Repo-relative path to the markdown template",
    )
    ap.add_argument(
        "--out-dir",
        default="projects/calamum-moltbook-observer/local_untracked/audits/gui",
        help="Repo-relative output directory (should be ignored)",
    )
    ap.add_argument(
        "--jsonl",
        default="projects/calamum-moltbook-observer/local_untracked/audit_log/gui_audit.jsonl",
        help="Repo-relative JSONL provenance log (append-only, should be ignored)",
    )
    ap.add_argument(
        "--set-baseline",
        action="store_true",
        help="Also append a baseline record to the provenance JSONL log",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute findings and print would-be output paths, but do not write any files",
    )
    ap.add_argument(
        "--no-network",
        action="store_true",
        help="Disable ALL network I/O (skip HTTP requests and TCP probes)",
    )
    args = ap.parse_args(argv)

    base = str(args.url).rstrip("/")
    here = Path(__file__)
    repo_root = _repo_root_from_here(here)

    tpl_path = (repo_root / str(args.template)).resolve()
    out_dir = (repo_root / str(args.out_dir)).resolve()
    jsonl_path = (repo_root / str(args.jsonl)).resolve()
    index_path = (repo_root / "projects" / "calamum-moltbook-observer" / "local_untracked" / "audit_log" / "audit_index.json").resolve()

    if not bool(args.dry_run):
        out_dir.mkdir(parents=True, exist_ok=True)
        jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.parent.mkdir(parents=True, exist_ok=True)

    ts = _utc_now()
    ts_slug = ts.replace(":", "").replace("-", "").replace("Z", "Z").replace(".", "")
    run_id = uuid.uuid4().hex
    git = _git_info(repo_root)

    report_path = out_dir / f"calamum_gui_audit_{ts_slug}.md"
    evidence_path = out_dir / f"calamum_gui_audit_{ts_slug}.evidence.json"

    evidence: Dict[str, Any] = {
        "timestamp_utc": ts,
        "run_id": run_id,
        "auditor": "ORACL-Prime",
        "dry_run": bool(args.dry_run),
        "git": git,
        "target_url": base,
        "network_policy": {
            "no_network": bool(args.no_network),
            "tcp_attempted": False,
            "http_attempted": False,
        },
        "probes": {},
        "http": {},
    }

    # Basic TCP probe (no ICMP/ping)
    host = "127.0.0.1"
    port = 8899
    try:
        m = re.match(r"^https?://([^/:]+)(?::(\d+))?", base)
        if m:
            host = str(m.group(1))
            if m.group(2):
                port = int(m.group(2))
    except Exception:
        pass

    tcp_ok = False
    tcp_msg = "skipped"
    if not bool(args.no_network):
        tcp_ok, tcp_msg = _tcp_probe(host, port)
        evidence["network_policy"]["tcp_attempted"] = True
    evidence["probes"]["tcp"] = {"host": host, "port": port, "ok": bool(tcp_ok), "detail": tcp_msg}

    # Endpoints (skipped under --no-network)
    if bool(args.no_network):
        r_root = HttpResult(ok=False, status=0, content_type="", body=b"", error="skipped_no_network")
        r_snap = HttpResult(ok=False, status=0, content_type="", body=b"", error="skipped_no_network")
        r_js_tail = HttpResult(ok=False, status=0, content_type="", body=b"", error="skipped_no_network")
        r_diag = HttpResult(ok=False, status=0, content_type="", body=b"", error="skipped_no_network")
        r_runtime = HttpResult(ok=False, status=0, content_type="", body=b"", error="skipped_no_network")
    else:
        evidence["network_policy"]["http_attempted"] = True
        r_root = _read_http(f"{base}/")
        r_snap = _read_http(f"{base}/_ghost_console/snapshot")
        r_js_tail = _read_http(f"{base}/_ghost_console/js_error_tail?lines=80")
        r_diag = _read_http(f"{base}/_ghost_console/diag_paths")
        r_runtime = _read_http(f"{base}/_ghost_console/runtime_log_test")

    # Branding tile path (served by ops_dashboard.py static mount)
    tile_path = "//_calamum_brand/calamum_tile.png"
    tile_url = f"{base}{tile_path}"
    r_tile = _read_http(tile_url) if not bool(args.no_network) else HttpResult(ok=False, status=0, content_type="", body=b"", error="skipped_no_network")

    def pack_http(name: str, r: HttpResult) -> None:
        evidence["http"][name] = {
            "ok": r.ok,
            "status": r.status,
            "content_type": r.content_type,
            "error": r.error,
            "body_sha256": _sha256_hex(r.body),
            "body_len": len(r.body),
        }

    pack_http("root", r_root)
    pack_http("snapshot", r_snap)
    pack_http("js_error_tail", r_js_tail)
    pack_http("diag_paths", r_diag)
    pack_http("runtime_log_test", r_runtime)
    pack_http("tile", r_tile)

    # Parse snapshot JSON (best-effort)
    snap: Dict[str, Any] = {}
    if r_snap.ok and not bool(args.no_network):
        try:
            snap = json.loads(_safe_text(r_snap.body, limit=5_000_000))
        except Exception:
            snap = {}

    # Parse js error tail
    js_tail_note = "(omitted by policy; see evidence for body_sha256/body_len)"

    # Head tag checks
    html = _safe_text(r_root.body, limit=800_000) if r_root.ok and not bool(args.no_network) else ""
    head_has_ms = ("msapplication-TileImage" in html)
    head_has_favicon = ("rel=\"icon\"" in html) or ("rel='icon'" in html) or ("shortcut icon" in html)
    head_refs_tile = ("calamum_tile.png" in html)

    # Tile checks
    tile_ct = (r_tile.content_type or "").split(";")[0].strip().lower()
    tile_sha = _sha256_hex(r_tile.body) if r_tile.body else ""

    findings = []
    if not tcp_ok:
        if bool(args.no_network):
            findings.append("TCP probe skipped (--no-network)")
        else:
            findings.append(f"TCP probe failed: {host}:{port} -> {tcp_msg}")
    if not r_root.ok:
        if bool(args.no_network):
            findings.append("GET / skipped (--no-network)")
        else:
            findings.append(f"GET / failed: status={r_root.status} err={r_root.error}")
    if not r_snap.ok:
        if bool(args.no_network):
            findings.append("GET /_ghost_console/snapshot skipped (--no-network)")
        else:
            findings.append(f"GET /_ghost_console/snapshot failed: status={r_snap.status} err={r_snap.error}")
    if r_tile.ok and tile_ct and ("png" not in tile_ct):
        findings.append(f"Tile content-type unexpected: {tile_ct}")
    if r_tile.ok and not head_refs_tile:
        findings.append("Tile fetched OK but HTML does not reference calamum_tile.png (head injection missing?)")

    if bool(args.no_network):
        summary = "[INFO] network checks skipped (--no-network)"
    else:
        summary = "[OK]" if (r_root.ok and r_snap.ok) else "[WARN]"

    data = {
        "timestamp_utc": ts,
        "target_url": base,
        "audit_scope": "NiceGUI dashboard reachability, branding tile, and diagnostics endpoints",
        "auditor": "ORACL-Prime",
        "summary": summary,
        "http_root_status": r_root.status,
        "http_snapshot_status": r_snap.status,
        "http_js_tail_status": r_js_tail.status,
        "tile_path": tile_path,
        "tile_http_status": r_tile.status,
        "tile_content_type": tile_ct,
        "tile_sha256": tile_sha,
        "head_has_ms_tile_image": str(bool(head_has_ms)),
        "head_has_favicon": str(bool(head_has_favicon)),
        "head_refs_tile_png": str(bool(head_refs_tile)),
        "snapshot_server_boot_id": snap.get("server_boot_id", ""),
        "snapshot_cpu": snap.get("cpu", ""),
        "snapshot_mem": snap.get("mem", ""),
        "snapshot_total_records": snap.get("total_records", ""),
        "snapshot_new_records": snap.get("new_records", ""),
        "snapshot_watchdog_active": snap.get("watchdog_active", ""),
        "snapshot_observer_active": snap.get("observer_active", ""),
        "snapshot_librarian_active": snap.get("librarian_active", ""),
        "snapshot_scores_json": json.dumps(snap.get("scores", {}), sort_keys=True),
        "snapshot_js_diag_json": json.dumps(snap.get("js_diag", {}), sort_keys=True),
        "js_error_tail_note": js_tail_note,
        "js_error_tail_sha256": str(evidence.get("http", {}).get("js_error_tail", {}).get("body_sha256", "")),
        "js_error_tail_len": str(evidence.get("http", {}).get("js_error_tail", {}).get("body_len", "")),
        "findings": "\n".join([f"- {x}" for x in findings]) if findings else "- (none)",
        "evidence_json_path": str(evidence_path),
        "report_path": str(report_path),
    }

    # Load template
    try:
        tpl = tpl_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"[ERR] failed to read template: {tpl_path} -> {e!r}")
        return 2

    rendered = _render_template(tpl, data)

    if bool(args.dry_run):
        print("Calamum GUI audit DRY-RUN complete")
        print(f"would_write_report:  {report_path}")
        print(f"would_write_evidence:{evidence_path}")
        print(f"would_append_jsonl:  {jsonl_path}")
        print(f"would_update_index:  {index_path}")
        return 0

    # Write evidence first (so report can point to it)
    try:
        evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except Exception as e:
        print(f"[WARN] failed to write evidence: {evidence_path} -> {e!r}")

    report_path.write_text(rendered, encoding="utf-8")

    # Append provenance JSONL (untracked).
    snapshot = {
        "kind": "snapshot",
        "timestamp_utc": ts,
        "run_id": run_id,
        "auditor": "ORACL-Prime",
        "git": {"head": git.get("head", ""), "branch": git.get("branch", ""), "is_dirty": git.get("is_dirty", False)},
        "target_url": base,
        "summary": summary,
        "report": str(report_path).replace("\\", "/"),
        "evidence": str(evidence_path).replace("\\", "/"),
    }
    try:
        with jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(snapshot, sort_keys=True, ensure_ascii=True) + "\n")
            if bool(args.set_baseline):
                baseline = dict(snapshot)
                baseline["kind"] = "baseline"
                baseline["baseline_id"] = uuid.uuid4().hex
                f.write(json.dumps(baseline, sort_keys=True, ensure_ascii=True) + "\n")
    except Exception:
        pass

    # Update central audit index (untracked convenience pointer).
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
    audits["gui"] = {
        "timestamp_utc": ts,
        "run_id": run_id,
        "git": {"head": git.get("head", ""), "branch": git.get("branch", ""), "is_dirty": git.get("is_dirty", False)},
        "report": str(report_path.relative_to(repo_root)).replace("\\", "/"),
        "evidence": str(evidence_path.relative_to(repo_root)).replace("\\", "/"),
        "jsonl": str(jsonl_path.relative_to(repo_root)).replace("\\", "/"),
    }
    existing["updated_at_utc"] = ts
    existing["git"] = {"head": git.get("head", ""), "branch": git.get("branch", ""), "is_dirty": git.get("is_dirty", False)}
    existing["audits"] = audits

    try:
        index_path.write_text(json.dumps(existing, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except Exception:
        pass

    print(f"[OK] wrote report: {report_path}")
    print(f"[OK] wrote evidence: {evidence_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
