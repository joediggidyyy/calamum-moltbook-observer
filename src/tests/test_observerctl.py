from __future__ import annotations

import json
import sys
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from observerctl import (  # noqa: E402
    build_evidence_pack,
    collect_runtime_status,
    evaluate_gate_decision,
    main,
)


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"status":"ok"}\n', encoding='utf-8')


def test_gate_check_go_in_sim_mode(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')

    status = collect_runtime_status(source='sim')
    gate = evaluate_gate_decision(status)
    assert gate['decision'] == 'go'
    assert gate['reason_codes'] == []


def test_gate_check_real_requires_api_key(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    monkeypatch.delenv('MOLTBOOK_API_KEY', raising=False)

    status = collect_runtime_status(source='real')
    gate = evaluate_gate_decision(status)
    assert gate['decision'] == 'no-go'
    assert 'critical_check_failed:env.moltbook_api_key' in gate['reason_codes']


def test_evidence_pack_writes_publish_grade_packet(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')

    output = tmp_path / 'evidence.json'
    rc = main(['ops', 'evidence', 'pack', '--source', 'sim', '--output', str(output), '--json'])
    assert rc == 0
    assert output.exists()

    payload = json.loads(output.read_text(encoding='utf-8'))
    assert payload['runtime_cli_surface'] == 'observerctl'
    assert 'provenance' in payload
    assert 'methodology' in payload
    assert 'process' in payload
    assert payload['provenance']['artifact_sha256']


def test_ops_mode_gate_and_set_flow(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')

    rc_gate = main(['ops', 'mode', 'gate', '--to', 'canary', '--source', 'sim', '--json'])
    assert rc_gate == 0

    rc_set = main(['ops', 'mode', 'set', '--to', 'canary', '--source', 'sim', '--json'])
    assert rc_set == 0

    rc_current = main(['ops', 'mode', 'current', '--json'])
    assert rc_current == 0


def test_ops_evidence_verify_schema_failure(tmp_path: Path, monkeypatch) -> None:
    bad_packet = tmp_path / 'bad_packet.json'
    bad_packet.write_text('{"timestamp_utc":"2026-02-21T00:00:00Z"}\n', encoding='utf-8')

    rc = main(['ops', 'evidence', 'verify', '--packet', str(bad_packet), '--json'])
    assert rc == 2


def test_baseline_librarian_watchdog_health_policy_commands(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')

    assert main(['baseline', 'status', '--json']) == 0
    assert main(['baseline', 'check', '--json']) in (0, 2)
    assert main(['baseline', 'set', '--id', 'baseline-ci', '--json']) == 0

    assert main(['librarian', 'stats', '--json']) == 0
    assert main(['librarian', 'stores', '--json']) == 0
    assert main(['librarian', 'rotate', '--mode', 'watch', '--json']) == 0
    assert main(['librarian', 'compact', '--mode', 'watch', '--json']) == 0
    assert main(['librarian', 'verify', '--mode', 'watch', '--json']) == 0

    assert main(['watchdog', 'status', '--json']) == 0
    assert main(['watchdog', 'check', '--json']) in (0, 2)
    assert main(['watchdog', 'reasons', '--json']) == 0
    assert main(['watchdog', 'ack', '--code', 'critical_check_failed:watchdog_heartbeat_stale', '--json']) == 0

    assert main(['health', 'quick', '--json']) in (0, 2)
    assert main(['health', 'full', '--json']) in (0, 2)
    assert main(['health', 'explain', '--code', 'critical_check_failed:real_key_missing', '--json']) == 0

    assert main(['policy', 'show', '--json']) == 0
    assert main(['policy', 'validate', '--json']) in (0, 2)
