from __future__ import annotations

import sys
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from calamum_observer_agent import append_record, load_config


def test_load_config_live_noncanary_uses_live_metrics_file(tmp_path: Path, monkeypatch) -> None:
    # Route all Calamum outputs into tmp to avoid touching the repo logs.
    log_dir = tmp_path / "logs"
    monkeypatch.setenv("CALAMUM_LOG_DIR", str(log_dir))

    cfg = load_config(
        argv_repo_root=None,
        mode="honeypot",
        interval_sec=1.0,
        node_id="node-test",
        source="live",
    )

    assert cfg.output_jsonl.name == "moltbook_metrics.jsonl"
    assert cfg.output_jsonl.parts[-4:] == ("observer_derived", "real", "honeypot", "moltbook_metrics.jsonl")


def test_load_config_canary_ignores_live_source_for_output_name(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / "logs"
    monkeypatch.setenv("CALAMUM_LOG_DIR", str(log_dir))

    cfg = load_config(
        argv_repo_root=None,
        mode="canary",
        interval_sec=1.0,
        node_id="node-test",
        source="live",
    )

    assert cfg.output_jsonl.name == "moltbook_metrics.jsonl"
    assert cfg.output_jsonl.parts[-4:] == ("observer_derived", "real", "canary", "moltbook_metrics.jsonl")


def test_append_record_live_source_missing_key_is_noop(tmp_path: Path, monkeypatch) -> None:
    # If live is requested but no MOLTBOOK_API_KEY is present, the agent must not crash.
    monkeypatch.delenv("MOLTBOOK_API_KEY", raising=False)

    data_dir = tmp_path / "logs" / "data" / "calamum"
    control_dir = tmp_path / "logs" / "control" / "calamum"
    data_dir.mkdir(parents=True, exist_ok=True)
    control_dir.mkdir(parents=True, exist_ok=True)

    out = data_dir / "observer_derived" / "real" / "honeypot" / "moltbook_metrics.jsonl"

    append_record(
        jsonl_path=out,
        node_id="node-test",
        mode="honeypot",
        control_dir=control_dir,
        data_dir=data_dir,
        source="live",
    )

    assert not out.exists() or out.read_text(encoding="utf-8").strip() == ""


def test_rotation_prefix_for_live_metrics_file(tmp_path: Path, monkeypatch) -> None:
    # Prove the rotation logic uses the file stem, not a hardcoded canary prefix.
    monkeypatch.setenv("CALAMUM_DATA_SIGNING_KEY", "unit-test-key")

    data_dir = tmp_path / "logs" / "data" / "calamum"
    control_dir = tmp_path / "logs" / "control" / "calamum"
    data_dir.mkdir(parents=True, exist_ok=True)
    control_dir.mkdir(parents=True, exist_ok=True)

    # Force rotation on the very next append.
    (control_dir / "rotation_policy.json").write_text('{"max_bytes": 1}', encoding="utf-8")

    out = data_dir / "observer_derived" / "sim" / "honeypot" / "moltbook_metrics.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("x" * 10, encoding="utf-8")

    append_record(
        jsonl_path=out,
        node_id="node-test",
        mode="honeypot",
        control_dir=control_dir,
        data_dir=data_dir,
        source="sim",
    )

    archive_dir = out.parent / "archive"
    archived = [p.name for p in archive_dir.glob("*.jsonl")]

    assert any(name.startswith("moltbook_") for name in archived), archived
    assert not any(name.startswith("moltbook_canary_") for name in archived), archived
