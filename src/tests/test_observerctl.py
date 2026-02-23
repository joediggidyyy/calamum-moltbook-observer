from __future__ import annotations

import json
import os
import sys
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import observerctl as observerctl_module

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

    assert main(['baseline', 'status', '--json']) in (0, 2)
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


def test_baseline_collect_writes_publish_grade_packet_and_resource_state(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    out = tmp_path / 'baseline_collect_packet.json'
    rc = main([
        'baseline', 'collect',
        '--source', 'sim',
        '--mode', 'canary',
        '--profile', 'normal',
        '--duration-sec', '0.02',
        '--interval-sec', '0.01',
        '--window-id', 'unit-window-001',
        '--output', str(out),
        '--json',
    ])
    assert rc == 0
    assert out.exists()

    packet = json.loads(out.read_text(encoding='utf-8'))
    assert packet.get('decision') == 'go'
    assert packet.get('action') == 'baseline-collect'
    assert packet.get('profile') == 'normal'
    assert int(packet.get('sample_count', 0)) >= 2
    assert packet.get('provenance', {}).get('artifact_sha256')

    resource_state = log_dir / 'control' / 'calamum' / 'watchdog_resource_state.json'
    assert resource_state.exists()
    resource_doc = json.loads(resource_state.read_text(encoding='utf-8'))
    assert float(resource_doc.get('sample_count', 0)) >= 2
    assert resource_doc.get('stream_type') == 'resource_normal'


def test_baseline_analyze_returns_go_when_minimums_met(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    # Build one normal stream sample set and one rapid stream sample set.
    assert main([
        'baseline', 'collect',
        '--source', 'sim', '--mode', 'canary', '--profile', 'normal',
        '--duration-sec', '0.02', '--interval-sec', '0.01', '--window-id', 'unit-window-normal', '--json',
    ]) == 0
    assert main([
        'baseline', 'collect',
        '--source', 'sim', '--mode', 'canary', '--profile', 'rapid',
        '--duration-sec', '0.02', '--interval-sec', '0.01', '--window-id', 'unit-window-rapid', '--json',
    ]) == 0

    out = tmp_path / 'baseline_analysis_packet.json'
    rc = main([
        'baseline', 'analyze',
        '--source', 'sim',
        '--mode', 'canary',
        '--hours', '24',
        '--min-normal-samples', '1',
        '--min-rapid-samples', '1',
        '--output', str(out),
        '--json',
    ])
    assert rc == 0
    assert out.exists()

    packet = json.loads(out.read_text(encoding='utf-8'))
    assert packet.get('action') == 'baseline-analyze'
    assert packet.get('baseline_ready') is True
    assert packet.get('decision') == 'go'
    stats = packet.get('resource_statistics', {})
    assert 'cpu_p95' in stats
    assert 'cpu_rate_p95_per_s' in stats
    assert packet.get('provenance', {}).get('artifact_sha256')


def test_baseline_analyze_no_go_when_window_incomplete(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    # Create only normal samples; require both normal+rapid to force a fail-closed no-go.
    assert main([
        'baseline', 'collect',
        '--source', 'sim', '--mode', 'canary', '--profile', 'normal',
        '--duration-sec', '0.02', '--interval-sec', '0.01', '--window-id', 'unit-window-only-normal', '--json',
    ]) == 0

    out = tmp_path / 'baseline_analysis_incomplete.json'
    rc = main([
        'baseline', 'analyze',
        '--source', 'sim',
        '--mode', 'canary',
        '--hours', '24',
        '--min-normal-samples', '1',
        '--min-rapid-samples', '1',
        '--output', str(out),
        '--json',
    ])
    assert rc == 2
    assert out.exists()
    packet = json.loads(out.read_text(encoding='utf-8'))
    assert packet.get('decision') == 'no-go'
    assert 'critical_check_failed:resource_baseline_window_incomplete' in packet.get('reason_codes', [])


def test_baseline_overnight_plan_emits_publish_grade_schedule_packet(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    out = tmp_path / 'overnight_plan_packet.json'
    rc = main([
        'baseline', 'overnight-plan',
        '--source', 'real',
        '--mode', 'canary',
        '--overnight-hours', '8',
        '--normal-interval-sec', '30',
        '--rapid-interval-sec', '2',
        '--rapid-phase-sec', '1800',
        '--output', str(out),
        '--json',
    ])
    assert rc == 0
    assert out.exists()

    packet = json.loads(out.read_text(encoding='utf-8'))
    assert packet.get('decision') == 'go'
    assert packet.get('action') == 'baseline-overnight-plan'
    assert packet.get('schedule_model') == 'rapid_start_then_normal_overnight_then_rapid_end'
    assert packet.get('provenance', {}).get('artifact_sha256')
    cmds = packet.get('execution_commands', [])
    assert isinstance(cmds, list)
    assert len(cmds) == 4
    assert 'baseline collect' in cmds[0]
    assert 'profile rapid' in cmds[0]
    assert 'profile normal' in cmds[1]
    assert 'baseline analyze' in cmds[3]


def test_baseline_overnight_plan_flags_projection_when_thresholds_too_high(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    rc = main([
        'baseline', 'overnight-plan',
        '--source', 'sim',
        '--mode', 'canary',
        '--overnight-hours', '1',
        '--normal-interval-sec', '60',
        '--rapid-interval-sec', '10',
        '--rapid-phase-sec', '300',
        '--min-normal-samples', '1000',
        '--min-rapid-samples', '1000',
        '--json',
    ])
    assert rc == 0

    evidence_index = log_dir / 'data' / 'calamum' / 'observer_derived' / 'sim' / 'canary' / 'evidence' / 'index.jsonl'
    assert evidence_index.exists()
    lines = [ln for ln in evidence_index.read_text(encoding='utf-8').splitlines() if ln.strip()]
    assert len(lines) >= 1
    latest = json.loads(lines[-1])
    plan_packet_path = Path(str(latest.get('packet_path', '')).replace('/', os.sep))
    assert plan_packet_path.exists()
    plan_packet = json.loads(plan_packet_path.read_text(encoding='utf-8'))

    projection = plan_packet.get('readiness_projection', {})
    assert projection.get('normal_requirement_met_by_plan') is False
    assert projection.get('rapid_requirement_met_by_plan') is False


def test_baseline_overnight_run_executes_all_phases_and_returns_go(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    out = tmp_path / 'overnight_run_packet.json'
    rc = main([
        'baseline', 'overnight-run',
        '--source', 'sim',
        '--mode', 'canary',
        '--overnight-hours', '0.0006',
        '--normal-interval-sec', '0.05',
        '--rapid-interval-sec', '0.05',
        '--rapid-phase-sec', '0.5',
        '--min-normal-samples', '1',
        '--min-rapid-samples', '1',
        '--output', str(out),
        '--json',
    ])
    assert rc == 0
    assert out.exists()

    packet = json.loads(out.read_text(encoding='utf-8'))
    assert packet.get('decision') == 'go'
    assert packet.get('action') == 'baseline-overnight-run'
    checkpoints = packet.get('checkpoints', [])
    assert isinstance(checkpoints, list)
    assert len(checkpoints) == 4
    phases = [cp.get('phase') for cp in checkpoints]
    assert phases == ['rapid_start', 'normal_overnight', 'rapid_end', 'analysis']
    assert all(str(cp.get('decision', 'no-go')) == 'go' for cp in checkpoints)
    assert packet.get('provenance', {}).get('artifact_sha256')


def test_baseline_overnight_run_fails_closed_when_analysis_not_ready(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    rc = main([
        'baseline', 'overnight-run',
        '--source', 'sim',
        '--mode', 'canary',
        '--overnight-hours', '0.0006',
        '--normal-interval-sec', '0.05',
        '--rapid-interval-sec', '0.05',
        '--rapid-phase-sec', '0.5',
        '--min-normal-samples', '1000',
        '--min-rapid-samples', '1000',
        '--json',
    ])
    assert rc == 2

    evidence_index = log_dir / 'data' / 'calamum' / 'observer_derived' / 'sim' / 'canary' / 'evidence' / 'index.jsonl'
    assert evidence_index.exists()
    lines = [ln for ln in evidence_index.read_text(encoding='utf-8').splitlines() if ln.strip()]
    run_entries = [json.loads(ln) for ln in lines if 'baseline_overnight_run' in ln]
    assert len(run_entries) >= 1
    latest = run_entries[-1]
    packet_path = Path(str(latest.get('packet_path', '')).replace('/', os.sep))
    assert packet_path.exists()
    packet = json.loads(packet_path.read_text(encoding='utf-8'))
    assert packet.get('decision') == 'no-go'
    reasons = packet.get('reason_codes', [])
    assert any('resource_baseline_window_incomplete' in str(r) for r in reasons)


def test_baseline_generate_and_check_filesystem_hashes(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: tmp_path)

    tracked = tmp_path / 'tracked.txt'
    tracked.write_text('hello baseline\n', encoding='utf-8')

    baseline_path = tmp_path / 'fs_baseline.json'
    rc_generate = main(['baseline', 'generate', '--output', str(baseline_path), '--max-files', '1000', '--json'])
    assert rc_generate == 0
    assert baseline_path.exists()

    rc_check = main(['baseline', 'check', '--baseline', str(baseline_path), '--json'])
    assert rc_check == 0


def test_baseline_check_detects_hash_mismatch(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: tmp_path)

    tracked = tmp_path / 'tracked.txt'
    tracked.write_text('v1\n', encoding='utf-8')

    baseline_path = tmp_path / 'fs_baseline.json'
    assert main(['baseline', 'generate', '--output', str(baseline_path), '--max-files', '1000', '--json']) == 0

    tracked.write_text('v2\n', encoding='utf-8')
    rc_check = main(['baseline', 'check', '--baseline', str(baseline_path), '--json'])
    assert rc_check == 2


def test_baseline_check_ignores_local_untracked_runtime_state(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: tmp_path)

    tracked = tmp_path / 'tracked.txt'
    tracked.write_text('stable\n', encoding='utf-8')

    runtime_state = tmp_path / 'local_untracked' / 'scheduler' / 'watchdog_schedule_state.json'
    runtime_state.parent.mkdir(parents=True, exist_ok=True)
    runtime_state.write_text('{"tick":1}\n', encoding='utf-8')

    baseline_path = tmp_path / 'fs_baseline.json'
    assert main(['baseline', 'generate', '--output', str(baseline_path), '--max-files', '1000', '--json']) == 0

    # Runtime state mutates between baseline/check cycles; baseline should ignore it.
    runtime_state.write_text('{"tick":2}\n', encoding='utf-8')
    rc_check = main(['baseline', 'check', '--baseline', str(baseline_path), '--json'])
    assert rc_check == 0


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


def test_librarian_stats_reports_archive_manifest_by_mode(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    data = log_dir / 'data' / 'calamum'
    store = data / 'stores' / 'canary'
    archive_dir = data / 'archive'

    store.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    # Session-active records in the store pointer.
    active = store / 'active.jsonl'
    active.write_text('{"x":1}\n{"x":2}\n', encoding='utf-8')

    # Archive manifest bundles (compressed artifacts + metadata) by mode.
    bundle_file = archive_dir / 'moltbook_canary_20260222T000000.jsonl.gz'
    bundle_file.write_text('compressed-bytes-placeholder', encoding='utf-8')
    manifest_payload = {
        'moltbook_canary_20260222T000000.jsonl': {
            'artifact_path': bundle_file.name,
            'records': 123,
            'uncompressed_bytes': 4567,
        }
    }
    (archive_dir / 'manifest.json').write_text(json.dumps(manifest_payload), encoding='utf-8')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    stats = observerctl_module._librarian_stats()
    assert stats.get('runtime_cli_surface') == 'observerctl'

    summary = stats.get('archive_manifest_summary', {})
    assert summary.get('manifest_exists') is True
    assert (summary.get('totals') or {}).get('records') == 123

    stores = stats.get('stores', [])
    canary_row = next((row for row in stores if row.get('mode') == 'canary'), None)
    assert canary_row is not None
    assert canary_row.get('session_records') == 2
    assert canary_row.get('archive_bundle_count') == 1
    assert canary_row.get('archive_records') == 123
    assert canary_row.get('records_total_display') == 125


def test_librarian_stats_human_output_without_json_flag(tmp_path: Path, monkeypatch, capsys) -> None:
    log_dir = tmp_path / 'logs'
    data = log_dir / 'data' / 'calamum'
    store = data / 'stores' / 'canary'
    archive_dir = data / 'archive'

    store.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    (store / 'active.jsonl').write_text('{"x":1}\n', encoding='utf-8')
    bundle_file = archive_dir / 'moltbook_canary_20260222T010000.jsonl.gz'
    bundle_file.write_text('x', encoding='utf-8')
    manifest_payload = {
        'moltbook_canary_20260222T010000.jsonl': {
            'artifact_path': bundle_file.name,
            'records': 7,
            'uncompressed_bytes': 77,
        }
    }
    (archive_dir / 'manifest.json').write_text(json.dumps(manifest_payload), encoding='utf-8')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    rc = main(['librarian', 'stats'])
    assert rc == 0

    out = capsys.readouterr().out
    assert 'Librarian stats' in out
    assert 'archive_totals:' in out
    assert 'per_mode:' in out
    assert '- CANARY' in out
    assert 'session_records_display:' in out


def test_librarian_stats_prefers_derived_session_display_counts(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    data = log_dir / 'data' / 'calamum'
    store = data / 'stores' / 'canary'
    archive_dir = data / 'archive'
    derived_canary = data / 'observer_derived' / 'sim' / 'canary'

    store.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)
    derived_canary.mkdir(parents=True, exist_ok=True)

    # Empty store pointer but populated derived ingest lane.
    (store / 'active.jsonl').write_text('', encoding='utf-8')
    (derived_canary / 'moltbook_metrics.jsonl').write_text('{"x":1}\n{"x":2}\n{"x":3}\n', encoding='utf-8')

    bundle_file = archive_dir / 'moltbook_canary_20260222T010000.jsonl.gz'
    bundle_file.write_text('x', encoding='utf-8')
    manifest_payload = {
        'moltbook_canary_20260222T010000.jsonl': {
            'artifact_path': bundle_file.name,
            'records': 7,
            'uncompressed_bytes': 77,
        }
    }
    (archive_dir / 'manifest.json').write_text(json.dumps(manifest_payload), encoding='utf-8')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    observerctl_module._save_state('sim', 'canary')

    stats = observerctl_module._librarian_stats()
    stores = stats.get('stores', [])
    canary_row = next((row for row in stores if row.get('mode') == 'canary'), None)
    assert canary_row is not None
    assert canary_row.get('session_records') == 0
    assert canary_row.get('ingest_session_records') == 3
    assert canary_row.get('session_records_display') == 3
    assert canary_row.get('records_total_display') == 10


def test_librarian_stats_ignores_non_active_lane_derived_sessions(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    data = log_dir / 'data' / 'calamum'
    archive_dir = data / 'archive'
    derived_sim_live = data / 'observer_derived' / 'sim' / 'live'
    derived_real_canary = data / 'observer_derived' / 'real' / 'canary'

    archive_dir.mkdir(parents=True, exist_ok=True)
    derived_sim_live.mkdir(parents=True, exist_ok=True)
    derived_real_canary.mkdir(parents=True, exist_ok=True)

    (derived_sim_live / 'moltbook_metrics.jsonl').write_text('{"x":1}\n{"x":2}\n{"x":3}\n', encoding='utf-8')
    (derived_real_canary / 'moltbook_metrics.jsonl').write_text('{"x":10}\n{"x":11}\n', encoding='utf-8')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    observerctl_module._save_state('real', 'canary')

    stats = observerctl_module._librarian_stats()
    stores = stats.get('stores', [])
    live_row = next((row for row in stores if row.get('mode') == 'live'), None)
    canary_row = next((row for row in stores if row.get('mode') == 'canary'), None)

    assert live_row is not None
    assert canary_row is not None

    assert live_row.get('ingest_mode_active') is False
    assert live_row.get('ingest_session_records') == 0
    assert live_row.get('session_records_display') == 0

    assert canary_row.get('ingest_mode_active') is True
    assert canary_row.get('ingest_source_scope') == 'real'
    assert canary_row.get('ingest_session_records') == 2
    assert canary_row.get('session_records_display') == 2


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


def test_ops_runtime_stop_writes_kill_signal(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    control_dir = log_dir / 'control' / 'calamum'
    control_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    rc = main(['ops', 'runtime', 'stop', '--json'])
    assert rc == 0

    signal_path = control_dir / 'kill.signal.json'
    assert signal_path.exists()
    payload = json.loads(signal_path.read_text(encoding='utf-8'))
    assert payload.get('signal') == 'kill'
    assert payload.get('requested_by') == 'observerctl'


def test_ops_runtime_stop_cleans_stale_pidfile(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    control_dir = log_dir / 'control' / 'calamum'
    control_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: tmp_path)

    pid_file = tmp_path / 'calamum_agent.pid'
    pid_file.write_text('424242', encoding='utf-8')
    monkeypatch.setattr(observerctl_module, '_pid_alive', lambda _pid: False)

    packet = observerctl_module._ops_runtime_stop(timeout_sec=0.0)
    assert packet['decision'] == 'go'
    assert packet['stopped_cleanly'] is True
    assert packet['escalated_terminate'] is False
    assert not pid_file.exists()


def test_ops_runtime_stop_escalates_when_process_persists(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    control_dir = log_dir / 'control' / 'calamum'
    control_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: tmp_path)

    pid_file = tmp_path / 'calamum_agent.pid'
    pid_file.write_text('424242', encoding='utf-8')

    calls = {'pid_alive': 0, 'terminate': 0}

    def _fake_pid_alive(_pid):
        calls['pid_alive'] += 1
        # Alive during initial check(s), then false after terminate path has run.
        if calls['terminate'] == 0:
            return True
        return False

    def _fake_terminate(_pid, graceful_timeout_sec=2.0):
        calls['terminate'] += 1
        return True

    monkeypatch.setattr(observerctl_module, '_pid_alive', _fake_pid_alive)
    monkeypatch.setattr(observerctl_module, '_terminate_pid_best_effort', _fake_terminate)

    packet = observerctl_module._ops_runtime_stop(timeout_sec=0.0)
    assert packet['decision'] == 'go'
    assert packet['stopped_cleanly'] is True
    assert packet['escalated_terminate'] is True
    assert calls['terminate'] == 1


def test_ops_runtime_status_reports_active_when_heartbeat_and_pid_alive(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    health.mkdir(parents=True, exist_ok=True)
    _touch(health / 'calamum_observer.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: tmp_path)
    (tmp_path / 'calamum_agent.pid').write_text(str(os.getpid()), encoding='utf-8')

    packet = observerctl_module._ops_runtime_status()
    assert packet['state'] == 'active'
    assert packet['heartbeat']['status'] == 'ok'
    assert packet['pid']['alive'] is True


def test_pid_alive_uses_psutil_when_os_kill_unreliable(monkeypatch) -> None:
    class _FakeProc:
        def is_running(self):
            return True

        def status(self):
            return 'running'

    monkeypatch.setattr(observerctl_module.psutil, 'Process', lambda _pid: _FakeProc())
    monkeypatch.setattr(observerctl_module.os, 'kill', lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError('unsupported')))

    assert observerctl_module._pid_alive(4242) is True


def test_ops_runtime_start_delegates_launcher_non_interactive(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    health.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    launcher = tmp_path / 'launch_ghost_console.ps1'
    launcher.write_text('# test launcher\n', encoding='utf-8')
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: tmp_path)

    class _DummyProc:
        pid = 12345

    def _fake_popen(cmd, env, cwd, stdin, stdout, stderr, creationflags):
        (tmp_path / 'calamum_agent.pid').write_text(str(os.getpid()), encoding='utf-8')
        _touch(health / 'calamum_observer.heartbeat')
        return _DummyProc()

    monkeypatch.setattr(observerctl_module.subprocess, 'Popen', _fake_popen)

    rc = main([
        'ops', 'runtime', 'start',
        '--source', 'sim',
        '--mode', 'canary',
        '--interval-sec', '1.0',
        '--timeout-sec', '2',
        '--json',
    ])
    assert rc == 0
