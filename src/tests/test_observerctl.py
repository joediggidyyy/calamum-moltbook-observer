from __future__ import annotations

import json
import sys
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from observerctl import (  # noqa: E402
    _default_output_path,
    _evidence_index_path,
    build_evidence_pack,
    collect_runtime_status,
    evaluate_gate_decision,
    main,
)


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"status":"ok"}\n', encoding='utf-8')


def _write_watchdog_posture(control_dir: Path, posture: str, heartbeat_interval: float, baseline_interval: float) -> None:
    payload = {
        'posture_trigger': posture,
        'heartbeat_interval_seconds': heartbeat_interval,
        'baseline_validation_interval_seconds': baseline_interval,
    }
    (control_dir / 'watchdog_posture_state.json').write_text(json.dumps(payload), encoding='utf-8')


def _write_watchdog_resource(control_dir: Path, cpu_now: float, ram_now: float, cpu_p95: float, ram_p95: float, score: float, age_s: float) -> None:
    payload = {
        'cpu_pct_now': cpu_now,
        'ram_pct_now': ram_now,
        'cpu_p95_15m': cpu_p95,
        'ram_p95_15m': ram_p95,
        'resource_spike_score': score,
        'sample_age_seconds': age_s,
    }
    (control_dir / 'watchdog_resource_state.json').write_text(json.dumps(payload), encoding='utf-8')


def _set_security_report_ref(monkeypatch, base_dir: Path) -> Path:
    report = base_dir / 'security_report_test.md'
    report.write_text('# security report\n', encoding='utf-8')
    monkeypatch.setenv('CALAMUM_SECURITY_REPORT_REF', str(report))
    return report


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
    _set_security_report_ref(monkeypatch, log_dir)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    status = collect_runtime_status(source='sim')
    gate = evaluate_gate_decision(status, target_mode='canary')
    assert gate['decision'] == 'go'
    assert gate['reason_codes'] == []


def test_gate_noop_transition_denied(tmp_path: Path, monkeypatch) -> None:
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
    _set_security_report_ref(monkeypatch, log_dir)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    status = collect_runtime_status(source='sim')
    gate = evaluate_gate_decision(status, target_mode='watch')
    assert gate['decision'] == 'no-go'
    assert 'policy_denied:no_op_transition' in gate['reason_codes']


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
    _set_security_report_ref(monkeypatch, log_dir)
    monkeypatch.delenv('MOLTBOOK_API_KEY', raising=False)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

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
    _set_security_report_ref(monkeypatch, log_dir)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

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
    _set_security_report_ref(monkeypatch, log_dir)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    rc_gate = main(['ops', 'mode', 'gate', '--to', 'canary', '--source', 'sim', '--json'])
    assert rc_gate == 0

    rc_set = main(['ops', 'mode', 'set', '--to', 'canary', '--source', 'sim', '--json'])
    assert rc_set == 0

    rc_current = main(['ops', 'mode', 'current', '--json'])
    assert rc_current == 0


def test_ops_mode_transition_atomic_flow(tmp_path: Path, monkeypatch) -> None:
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
    _set_security_report_ref(monkeypatch, log_dir)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    out = tmp_path / 'transition_evidence.json'
    rc = main([
        'ops', 'mode', 'transition',
        '--to', 'canary',
        '--source', 'sim',
        '--event', 'unit-transition',
        '--output', str(out),
        '--json',
    ])
    assert rc == 0
    assert out.exists()


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
    _set_security_report_ref(monkeypatch, log_dir)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

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


def test_librarian_rotate_compact_verify_operational(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    data = log_dir / 'data' / 'calamum'
    store = data / 'stores' / 'watch'
    store.mkdir(parents=True, exist_ok=True)

    active = store / 'active.jsonl'
    active.write_text('{"x":1}\n{"x":2}\n', encoding='utf-8')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')

    control = log_dir / 'control' / 'calamum'
    control.mkdir(parents=True, exist_ok=True)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    assert main(['librarian', 'rotate', '--mode', 'watch', '--json']) == 0

    manifest_path = store / 'manifest.json'
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    assert isinstance(manifest.get('archives'), list)

    # Create another segment then compact archives.
    active.write_text('{"x":3}\n', encoding='utf-8')
    assert main(['librarian', 'rotate', '--mode', 'watch', '--json']) == 0
    assert main(['librarian', 'compact', '--mode', 'watch', '--json']) == 0
    assert main(['librarian', 'verify', '--mode', 'watch', '--json']) == 0

    manifest_after = json.loads(manifest_path.read_text(encoding='utf-8'))
    assert manifest_after.get('archives') == []
    assert len(manifest_after.get('compacted_files', [])) >= 1

    # Ensure former marker-stub artifacts are not used.
    assert list(store.glob('*.marker')) == []


def test_gate_denies_when_security_report_link_missing(tmp_path: Path, monkeypatch) -> None:
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
    monkeypatch.delenv('CALAMUM_SECURITY_REPORT_REF', raising=False)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    status = collect_runtime_status(source='sim')
    gate = evaluate_gate_decision(status, target_mode='canary')
    assert gate['decision'] == 'no-go'
    assert 'critical_check_failed:run_security_report_missing' in gate['reason_codes']


def test_gate_denies_when_security_report_link_unresolvable(tmp_path: Path, monkeypatch) -> None:
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
    monkeypatch.setenv('CALAMUM_SECURITY_REPORT_REF', str(log_dir / 'missing_security_report.md'))
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    status = collect_runtime_status(source='sim')
    gate = evaluate_gate_decision(status, target_mode='canary')
    assert gate['decision'] == 'no-go'
    assert 'critical_check_failed:run_security_report_missing' in gate['reason_codes']


def test_live_lockdown_requires_escalated_cadence(tmp_path: Path, monkeypatch) -> None:
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
    _set_security_report_ref(monkeypatch, log_dir)
    monkeypatch.setenv('MOLTBOOK_API_KEY', 'test-key')

    _write_watchdog_posture(control, posture='lockdown', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)
    status = collect_runtime_status(source='real')
    gate = evaluate_gate_decision(status, target_mode='live')
    assert gate['decision'] == 'no-go'
    assert 'critical_check_failed:lockdown_heartbeat_rate_not_escalated' in gate['reason_codes']
    assert 'critical_check_failed:lockdown_baseline_rate_not_escalated' in gate['reason_codes']


def test_lockdown_cpu_spike_denies_live_and_honeypot_same_standard(tmp_path: Path, monkeypatch) -> None:
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
    _set_security_report_ref(monkeypatch, log_dir)
    monkeypatch.setenv('MOLTBOOK_API_KEY', 'test-key')

    # Cadence escalated correctly for lockdown; denial should come from spike standard.
    _write_watchdog_posture(control, posture='lockdown', heartbeat_interval=4, baseline_interval=45)
    _write_watchdog_resource(control, cpu_now=80, ram_now=70, cpu_p95=50, ram_p95=55, score=0.6, age_s=3)

    live_status = collect_runtime_status(source='real')
    live_gate = evaluate_gate_decision(live_status, target_mode='live')
    honeypot_gate = evaluate_gate_decision(live_status, target_mode='honeypot')

    assert live_gate['decision'] == 'no-go'
    assert honeypot_gate['decision'] == 'no-go'
    assert 'critical_check_failed:cpu_spike_lockdown' in live_gate['reason_codes']
    assert 'critical_check_failed:cpu_spike_lockdown' in honeypot_gate['reason_codes']


def test_ops_mode_set_denies_stale_gate_packet(tmp_path: Path, monkeypatch) -> None:
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
    monkeypatch.setenv('CALAMUM_GATE_PACKET_MAX_AGE_SEC', '1')
    _set_security_report_ref(monkeypatch, log_dir)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    assert main(['ops', 'mode', 'gate', '--to', 'canary', '--source', 'sim', '--json']) == 0

    gate_path = control / 'observerctl_last_gate.json'
    gate_doc = json.loads(gate_path.read_text(encoding='utf-8'))
    gate_doc['timestamp_utc'] = '2000-01-01T00:00:00Z'
    gate_path.write_text(json.dumps(gate_doc), encoding='utf-8')

    assert main(['ops', 'mode', 'set', '--to', 'canary', '--source', 'sim', '--json']) == 2


def test_default_evidence_paths_use_canonical_data_cache(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    data_dir = log_dir / 'data' / 'calamum'
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    out = _default_output_path(source='sim', mode='canary', event='unit-test')
    idx = _evidence_index_path(source='sim', mode='canary')

    expected_dir = data_dir / 'observer_derived' / 'sim' / 'canary' / 'evidence'
    assert out.parent == expected_dir
    assert out.name.startswith('observerctl_unit-test_evidence_')
    assert out.suffix == '.json'
    assert idx == expected_dir / 'index.jsonl'
