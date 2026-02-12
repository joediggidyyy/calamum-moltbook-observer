import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# Add src to path
current_dir = Path(__file__).resolve().parent
src_dir = current_dir.parent
if str(src_dir) not in sys.path:
    sys.path.append(str(src_dir))

import keysmith  # noqa: E402


def test_keysmith_rejects_non_local_untracked_output_dir_inside_project_tree():
    project_root = keysmith._project_root()  # intentional: test uses implementation root
    unsafe = project_root / "docs" / "keysmith_test_outputs"

    with pytest.raises(keysmith.KeysmithError):
        keysmith.ensure_safe_output_dir(unsafe)


def test_keysmith_rejects_non_allowlisted_host():
    with tempfile.TemporaryDirectory() as td:
        cfg = keysmith.KeysmithConfig(
            base_url="https://evil.example.invalid/v1",
            register_path="agents/register",
            output_dir=Path(td),
            dry_run=True,
            allowed_hosts=("api.moltbook.com",),
            agent_metadata={"agent_name": "test"},
        )

        with pytest.raises(keysmith.KeysmithError):
            keysmith.run_keysmith(cfg)


def test_keysmith_dry_run_writes_artifacts_and_never_prints_secret_placeholder():
    with tempfile.TemporaryDirectory() as td:
        out_dir = Path(td) / "keysmith"

        # Execute via subprocess to capture stdout/stderr safely.
        cmd = [sys.executable, "-c", "import keysmith; raise SystemExit(keysmith.main(['mint','--dry-run','--output-dir',r'{}']))".format(str(out_dir))]
        result = subprocess.run(cmd, cwd=str(src_dir), capture_output=True, text=True)

        assert result.returncode == 0, result.stderr
        assert "DRY_RUN_PLACEHOLDER_DO_NOT_USE" not in result.stdout
        assert "DRY_RUN_PLACEHOLDER_DO_NOT_USE" not in result.stderr

        claim_path = out_dir / "claim_url.txt"
        sealed_path = out_dir / "sealed_drop.bin"
        audit_path = out_dir / "keysmith_audit.jsonl"
        import_ps1 = out_dir / "Import-MoltbookApiKeyFromSealedDrop.ps1"
        result_json = out_dir / "keysmith_result.json"

        assert claim_path.exists()
        assert sealed_path.exists()
        assert audit_path.exists()
        assert import_ps1.exists()
        assert result_json.exists()

        claim_text = claim_path.read_text(encoding="utf-8")
        assert "https://" in claim_text

        # Audit log must never contain the placeholder secret.
        audit_text = audit_path.read_text(encoding="utf-8")
        assert "DRY_RUN_PLACEHOLDER_DO_NOT_USE" not in audit_text


def test_keysmith_non_dry_run_requires_sandbox_env_flag():
    with tempfile.TemporaryDirectory() as td:
        cfg = keysmith.KeysmithConfig(
            base_url="https://api.moltbook.com/v1",
            register_path="agents/register",
            output_dir=Path(td) / "keysmith",
            dry_run=False,
            allowed_hosts=("api.moltbook.com",),
            agent_metadata={"agent_name": "test"},
        )

        with pytest.raises(keysmith.KeysmithError) as e:
            keysmith.run_keysmith(cfg)

        assert "sandbox" in str(e.value).lower()
