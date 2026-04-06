import subprocess
import sys
import tempfile
import types
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
        cmd = [sys.executable, "-c", "import keysmith; raise SystemExit(keysmith.main(['mint','--dry-run','--output-dir',r'{}']))".format(out_dir.as_posix())]
        result = subprocess.run(cmd, cwd=str(src_dir), capture_output=True, text=True)

        assert result.returncode == 0, result.stderr
        assert "DRY_RUN_PLACEHOLDER_DO_NOT_USE" not in result.stdout
        assert "DRY_RUN_PLACEHOLDER_DO_NOT_USE" not in result.stderr

        claim_path = out_dir / "claim_url.txt"
        sealed_path = out_dir / "sealed_drop.bin"
        audit_path = out_dir / "keysmith_audit.jsonl"
        result_json = out_dir / "keysmith_result.json"
        import_helper = out_dir / "Import-MoltbookApiKeyFromSealedDrop.ps1"
        persist_helper = out_dir / "Persist-MoltbookApiKeyToUserEnv.ps1"

        assert claim_path.exists()
        assert sealed_path.exists()
        assert audit_path.exists()
        assert result_json.exists()
        assert import_helper.exists()
        assert persist_helper.exists()

        claim_text = claim_path.read_text(encoding="utf-8")
        assert "https://" in claim_text

        # Audit log must never contain the placeholder secret.
        audit_text = audit_path.read_text(encoding="utf-8")
        assert "DRY_RUN_PLACEHOLDER_DO_NOT_USE" not in audit_text

        helper_text = import_helper.read_text(encoding="utf-8") + persist_helper.read_text(encoding="utf-8")
        assert "DRY_RUN_PLACEHOLDER_DO_NOT_USE" not in helper_text
        assert "MOLTBOOK_API_KEY" in helper_text


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


def test_keysmith_sandbox_rejects_output_outside_sandbox_root(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        sandbox_root = Path(td) / "sandbox"
        sandbox_root.mkdir(parents=True, exist_ok=True)
        unsafe = Path(td) / "outside"

        monkeypatch.setenv("KEYSMITH_SANDBOX", "1")
        monkeypatch.setenv("KEYSMITH_SANDBOX_OUTPUT_ROOT", str(sandbox_root))

        cfg = keysmith.KeysmithConfig(
            base_url="https://api.moltbook.com/v1",
            register_path="agents/register",
            output_dir=unsafe,
            dry_run=True,
            allowed_hosts=("api.moltbook.com",),
            agent_metadata={"agent_name": "test"},
        )

        with pytest.raises(keysmith.KeysmithError) as e:
            keysmith.run_keysmith(cfg)

        assert "sandbox_output_root" in str(e.value).lower() or "sandbox" in str(e.value).lower()


def test_moltbook_register_accepts_nested_agent_response(monkeypatch) -> None:
    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {
                "agent": {
                    "api_key": "moltbook_test_key",
                    "claim_url": "https://www.moltbook.com/claim/moltbook_claim_test",
                    "verification_code": "reef-X4B2",
                },
                "important": "SAVE YOUR API KEY",
            }

    fake_requests = types.SimpleNamespace(
        post=lambda url, json, timeout: _FakeResponse(),
    )

    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    claim_url, api_key = keysmith.moltbook_register(
        base_url="https://www.moltbook.com/api/v1",
        register_path="agents/register",
        agent_metadata={"name": "calamum-keysmith", "description": "test"},
        timeout_sec=20,
    )

    assert claim_url == "https://www.moltbook.com/claim/moltbook_claim_test"
    assert api_key == "moltbook_test_key"


def test_moltbook_register_retries_default_name_on_conflict(monkeypatch) -> None:
    captured_payloads = []

    class _FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise RuntimeError(f"status={self.status_code}")

        def json(self):
            return self._payload

    def _fake_post(url, json, timeout):
        captured_payloads.append(dict(json))
        if len(captured_payloads) == 1:
            return _FakeResponse(
                409,
                {"statusCode": 409, "message": "Agent name already taken"},
            )
        return _FakeResponse(
            201,
            {
                "agent": {
                    "api_key": "moltbook_test_key_retry",
                    "claim_url": "https://www.moltbook.com/claim/moltbook_claim_retry",
                }
            },
        )

    fake_requests = types.SimpleNamespace(post=_fake_post)
    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    claim_url, api_key = keysmith.moltbook_register(
        base_url="https://www.moltbook.com/api/v1",
        register_path="agents/register",
        agent_metadata=keysmith._default_agent_metadata(),
        timeout_sec=20,
    )

    assert claim_url == "https://www.moltbook.com/claim/moltbook_claim_retry"
    assert api_key == "moltbook_test_key_retry"
    assert captured_payloads[0]["name"] == keysmith.DEFAULT_AGENT_NAME
    assert captured_payloads[1]["name"].startswith(f"{keysmith.DEFAULT_AGENT_NAME}-")
    assert captured_payloads[1]["name"] != captured_payloads[0]["name"]
