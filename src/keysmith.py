"""Calamum KEYSMITH

KEYSMITH is a sandbox-oriented utility to mint a Moltbook agent API key without
exposing secrets to humans.

Security posture (non-negotiable):
- Never print or log secret values (api_key).
- Never write secret values to tracked paths.
- Prefer names-only evidence (paths + presence + lengths).

This module is intentionally dependency-light and deterministic.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as _dt
import json
import os
import secrets
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple
from urllib.parse import urlparse


KEYSMITH_VERSION = "1.0.0"


class KeysmithError(RuntimeError):
    """Non-secret-bearing error for KEYSMITH failures."""


@dataclasses.dataclass(frozen=True)
class KeysmithConfig:
    base_url: str
    register_path: str
    output_dir: Path
    dry_run: bool
    allowed_hosts: Tuple[str, ...]
    agent_metadata: Dict[str, Any]
    timeout_sec: int = 20


@dataclasses.dataclass(frozen=True)
class KeysmithArtifacts:
    output_dir: Path
    result_json: Path
    claim_url_txt: Path
    sealed_drop_bin: Path
    audit_jsonl: Path


def _utc_timestamp_compact() -> str:
    # Example: 20260212T053012Z
    return _dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


def _project_root() -> Path:
    # keysmith.py lives in <project_root>/src/
    return Path(__file__).resolve().parent.parent


def _local_untracked_root() -> Path:
    return _project_root() / "local_untracked"


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def ensure_safe_output_dir(output_dir: Path) -> None:
    """Reject writing secrets into tracked paths.

    Allowed:
    - <project_root>/local_untracked/** (gitignored)
    - Any path outside the Calamum project root

    Denied:
    - Any path inside <project_root> that is NOT under local_untracked
    """

    project_root = _project_root()
    lu_root = _local_untracked_root()

    out = output_dir.resolve()

    if _is_within(out, project_root) and not _is_within(out, lu_root):
        raise KeysmithError(
            "Refusing to write KEYSMITH artifacts inside the project tree outside local_untracked/. "
            f"output_dir={out} project_root={project_root}"
        )


def ensure_allowlisted_host(base_url: str, allowed_hosts: Iterable[str]) -> str:
    parsed = urlparse(base_url)
    host = (parsed.hostname or "").lower().strip()
    if not host:
        raise KeysmithError("base_url must include a hostname")

    allow = {h.lower().strip() for h in allowed_hosts if h.strip()}
    if host not in allow:
        raise KeysmithError(f"base_url host not allowlisted: host={host}")

    return host


def _sandbox_flag() -> bool:
    return os.environ.get("KEYSMITH_SANDBOX", "").strip() == "1"


def _require_sandbox_for_live_mint(*, dry_run: bool) -> None:
    """Fail closed for non-dry-run minting unless explicitly sandboxed.

    Rationale:
    - Policy requires vendor interaction only from a sandbox lane.
    - Prevent accidental host execution that could violate doctrine.
    """

    if dry_run:
        return

    if _sandbox_flag():
        return

    raise KeysmithError(
        "Refusing non-dry-run KEYSMITH outside the KEYSMITH sandbox/container lane. "
        "Run live mint only with KEYSMITH_SANDBOX=1 inside the container lane."
    )


def _mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(payload, sort_keys=True) + "\n")


def _seal_drop_write(path: Path, secret_value: str) -> int:
    """Write the secret bytes to a sealed-drop file.

    Notes:
    - This is plaintext-at-rest by design for a short window (Option A).
    - The caller must ensure the path is safe (local_untracked or outside repo).
    """

    data = secret_value.encode("utf-8")

    # Best-effort restrictive permissions on POSIX.
    if os.name == "posix":
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        fd = os.open(str(path), flags, 0o600)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
        finally:
            try:
                os.close(fd)
            except Exception:
                pass
    else:
        with path.open("wb") as f:
            f.write(data)

    return len(data)


def _default_allowed_hosts() -> Tuple[str, ...]:
    # Conservative by default; can be extended via CLI flags.
    return (
        "api.moltbook.com",
        "moltbook.com",
    ) # Note: be kind to others


def _default_base_url() -> str:
    return os.environ.get("MOLTBOOK_HOST", "https://api.moltbook.com/v1")


def _default_register_path() -> str:
    # Vendor path is intentionally configurable; this default matches proposal text.
    return os.environ.get("MOLTBOOK_KEYSMITH_REGISTER_PATH", "agents/register")


def _default_output_dir() -> Path:
    # Default to a sandbox-internal ephemeral location when running in sandbox.
    # For non-sandbox dry-runs, preserve local_untracked for developer ergonomics.
    if _sandbox_flag():
        root = Path(os.environ.get("KEYSMITH_SANDBOX_OUTPUT_ROOT", "/tmp/calamum_keysmith_exports"))
        return root / _utc_timestamp_compact()
    return _local_untracked_root() / "keysmith_exports" / _utc_timestamp_compact()


def _render_import_helper_ps1(sealed_drop_path: Path) -> str:
    # Important: this script must never print the secret.
    # It prints presence-only evidence.
    return (
        "# KEYSMITH import helper (names-only)\n"
        "# Reads a sealed-drop file and sets MOLTBOOK_API_KEY in the current PowerShell session.\n"
        "# WARNING: Do not open the sealed-drop file in an editor.\n"
        "\n"
        f"$sealedDropPath = '{sealed_drop_path.as_posix()}'\n"
        "if (-not (Test-Path -LiteralPath $sealedDropPath)) {\n"
        "  Write-Error 'Sealed-drop file not found'\n"
        "  exit 2\n"
        "}\n"
        "$bytes = [System.IO.File]::ReadAllBytes($sealedDropPath)\n"
        "$value = [System.Text.Encoding]::UTF8.GetString($bytes)\n"
        "$env:MOLTBOOK_API_KEY = $value\n"
        "Write-Output 'MOLTBOOK_API_KEY present: true'\n"
    )


def _render_persist_user_env_ps1(sealed_drop_path: Path) -> str:
    # Important: this script must never print the secret.
    # It prints presence-only evidence.
    return (
        "# KEYSMITH persistence helper (names-only)\n"
        "# Reads a sealed-drop file and persists MOLTBOOK_API_KEY to the current user environment (Windows).\n"
        "# WARNING: Do not open the sealed-drop file in an editor.\n"
        "# NOTE: This stores the key in the user environment so it can be used by future sessions.\n"
        "\n"
        f"$sealedDropPath = '{sealed_drop_path.as_posix()}'\n"
        "if (-not (Test-Path -LiteralPath $sealedDropPath)) {\n"
        "  Write-Error 'Sealed-drop file not found'\n"
        "  exit 2\n"
        "}\n"
        "$bytes = [System.IO.File]::ReadAllBytes($sealedDropPath)\n"
        "$value = [System.Text.Encoding]::UTF8.GetString($bytes)\n"
        "[System.Environment]::SetEnvironmentVariable('MOLTBOOK_API_KEY', $value, 'User')\n"
        "$env:MOLTBOOK_API_KEY = $value\n"
        "Write-Output 'MOLTBOOK_API_KEY persisted to User env: true'\n"
    )


def moltbook_register(
    *,
    base_url: str,
    register_path: str,
    agent_metadata: Dict[str, Any],
    timeout_sec: int,
) -> Tuple[str, str]:
    """Perform the vendor registration call.

    Returns:
      (claim_url, api_key)

    Security: must never log/print api_key or entire response.
    """

    try:
        import requests  # local import; dependency already present in this subtree
    except Exception as e:
        raise KeysmithError("requests is required for non-dry-run KEYSMITH") from e

    base = base_url.rstrip("/")
    path = register_path.lstrip("/")
    url = f"{base}/{path}"

    # DO NOT include secrets in metadata; metadata is names-only.
    try:
        resp = requests.post(url, json=agent_metadata, timeout=timeout_sec)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        # Never include response body; it may contain secrets.
        raise KeysmithError(f"Registration request failed: url={url}") from e

    claim_url = data.get("claim_url")
    api_key = data.get("api_key")
    if not isinstance(claim_url, str) or not claim_url.strip():
        raise KeysmithError("Registration response missing claim_url")
    if not isinstance(api_key, str) or not api_key.strip():
        raise KeysmithError("Registration response missing api_key")

    return claim_url.strip(), api_key


def run_keysmith(config: KeysmithConfig) -> KeysmithArtifacts:
    ensure_safe_output_dir(config.output_dir)
    host = ensure_allowlisted_host(config.base_url, config.allowed_hosts)
    _require_sandbox_for_live_mint(dry_run=config.dry_run)

    # Fail closed for sandbox lane: require a sandbox-local output root.
    # This prevents writing sealed-drop artifacts to likely host-mounted targets.
    if _sandbox_flag():
        sandbox_root = Path(os.environ.get("KEYSMITH_SANDBOX_OUTPUT_ROOT", "/tmp/calamum_keysmith_exports")).resolve()
        out = config.output_dir.resolve()
        if not _is_within(out, sandbox_root):
            raise KeysmithError(
                "Refusing sandbox KEYSMITH output_dir outside KEYSMITH_SANDBOX_OUTPUT_ROOT. "
                f"output_dir={out} sandbox_root={sandbox_root}"
            )

    if config.output_dir.exists():
        # Fail closed to avoid overwriting or reusing sealed-drop artifacts.
        try:
            has_any = any(config.output_dir.iterdir())
        except Exception:
            has_any = True
        if has_any:
            raise KeysmithError(f"output_dir must be empty or non-existent: output_dir={config.output_dir.resolve()}")

    _mkdir(config.output_dir)

    artifacts = KeysmithArtifacts(
        output_dir=config.output_dir,
        result_json=config.output_dir / "keysmith_result.json",
        claim_url_txt=config.output_dir / "claim_url.txt",
        sealed_drop_bin=config.output_dir / "sealed_drop.bin",
        audit_jsonl=config.output_dir / "keysmith_audit.jsonl",
    )

    _append_jsonl(
        artifacts.audit_jsonl,
        {
            "event": "keysmith_start",
            "ts_utc": _utc_timestamp_compact(),
            "keysmith_version": KEYSMITH_VERSION,
            "dry_run": config.dry_run,
            "sandbox": _sandbox_flag(),
            "base_url_host": host,
            "output_dir": str(artifacts.output_dir.as_posix()),
        },
    )

    if config.dry_run:
        # Produce a deterministic-shaped output without creating a real vendor key.
        claim_url = f"https://moltbook.com/claim/dryrun-{secrets.token_hex(8)}"
        api_key = "DRY_RUN_PLACEHOLDER_DO_NOT_USE"
    else:
        claim_url, api_key = moltbook_register(
            base_url=config.base_url,
            register_path=config.register_path,
            agent_metadata=config.agent_metadata,
            timeout_sec=config.timeout_sec,
        )

    # Persist allowlisted artifacts.
    _write_text(artifacts.claim_url_txt, claim_url + "\n")
    secret_len = _seal_drop_write(artifacts.sealed_drop_bin, api_key)

    _append_jsonl(
        artifacts.audit_jsonl,
        {
            "event": "artifacts_written",
            "ts_utc": _utc_timestamp_compact(),
            "claim_url_path": str(artifacts.claim_url_txt.as_posix()),
            "sealed_drop_path": str(artifacts.sealed_drop_bin.as_posix()),
            "sealed_drop_len_bytes": int(secret_len),
            "handoff_model": "sandbox-contained sealed_drop",
        },
    )

    _write_json(
        artifacts.result_json,
        {
            "keysmith_version": KEYSMITH_VERSION,
            "ts_utc": _utc_timestamp_compact(),
            "dry_run": config.dry_run,
            "base_url": config.base_url,
            "base_url_host": host,
            "register_path": config.register_path,
            "artifacts": {
                "output_dir": str(artifacts.output_dir.as_posix()),
                "claim_url_txt": str(artifacts.claim_url_txt.as_posix()),
                "sealed_drop_bin": str(artifacts.sealed_drop_bin.as_posix()),
                "audit_jsonl": str(artifacts.audit_jsonl.as_posix()),
            },
            "notes": {
                "secrets": "api_key is stored only in sealed_drop_bin; never printed/logged",
                "claim_url": "claim_url is non-secret and stored in claim_url.txt",
                "host_helpers": "No host import/persist helper scripts are emitted by KEYSMITH.",
            },
        },
    )

    _append_jsonl(
        artifacts.audit_jsonl,
        {
            "event": "keysmith_complete",
            "ts_utc": _utc_timestamp_compact(),
            "success": True,
        },
    )

    return artifacts


def _parse_agent_metadata_json(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {
            "agent_name": "calamum-keysmith",
            "purpose": "moltbook_agent_registration",
            "operator": "ORACL-Prime",
        }

    p = Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise KeysmithError("Failed to read agent metadata JSON") from e

    if not isinstance(data, dict):
        raise KeysmithError("Agent metadata JSON must be an object")

    return data


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="keysmith",
        description="KEYSMITH: sandboxed Moltbook key minting (claim_url-only humans; sealed-drop secrets)",
    )

    sub = p.add_subparsers(dest="cmd", required=True)

    mint = sub.add_parser("mint", help="Mint a claim_url + sealed-drop api_key")
    mint.add_argument("--base-url", default=_default_base_url())
    mint.add_argument("--register-path", default=_default_register_path())
    mint.add_argument("--output-dir", default=str(_default_output_dir()))
    mint.add_argument("--dry-run", action="store_true")
    mint.add_argument("--allow-host", action="append", default=list(_default_allowed_hosts()))
    mint.add_argument("--agent-metadata-json", default=None)
    mint.add_argument("--timeout-sec", type=int, default=20)

    return p


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)

    if args.cmd == "mint":
        cfg = KeysmithConfig(
            base_url=str(args.base_url),
            register_path=str(args.register_path),
            output_dir=Path(str(args.output_dir)),
            dry_run=bool(args.dry_run),
            allowed_hosts=tuple(args.allow_host or []),
            agent_metadata=_parse_agent_metadata_json(args.agent_metadata_json),
            timeout_sec=int(args.timeout_sec),
        )

        artifacts = run_keysmith(cfg)

        # Print names-only evidence to stdout (no claim_url and no secret).
        print("[OK] KEYSMITH artifacts written")
        print(f"output_dir={artifacts.output_dir.as_posix()}")
        print(f"claim_url_path={artifacts.claim_url_txt.as_posix()}")
        print(f"sealed_drop_path={artifacts.sealed_drop_bin.as_posix()}")
        print(f"audit_path={artifacts.audit_jsonl.as_posix()}")
        return 0

    raise KeysmithError("Unknown command")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeysmithError as e:
        # Critical: do not print secrets. Errors are designed to be non-secret-bearing.
        print(f"[FAIL] {e}", file=sys.stderr)
        raise SystemExit(2)
