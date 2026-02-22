from __future__ import annotations

import json
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from calamum_observer_agent import append_record


def test_append_record_canary_uses_notification_schema(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-key')
    # Arrange
    data_dir = tmp_path / 'logs' / 'data' / 'calamum'
    control_dir = tmp_path / 'logs' / 'control' / 'calamum'
    data_dir.mkdir(parents=True, exist_ok=True)
    control_dir.mkdir(parents=True, exist_ok=True)

    jsonl_path = data_dir / 'observer_derived' / 'sim' / 'canary' / 'moltbook_metrics.jsonl'

    # Act
    append_record(
        jsonl_path=jsonl_path,
        node_id='node-test',
        mode='canary',
        control_dir=control_dir,
        data_dir=data_dir,
    )

    # Assert
    lines = jsonl_path.read_text(encoding='utf-8').splitlines()
    assert lines, 'expected at least one JSONL record'

    rec = json.loads(lines[-1])
    assert rec.get('mode') == 'CANARY'
    assert rec.get('kind') == 'obfuscated_inbound_event'

    # Canary records should be inbound-only (dm/follow/mention)
    assert 'event_type' in rec
    assert 'sender_hash' in rec

    # Keep a stable type field for downstream consumers
    assert rec.get('type') == rec.get('event_type')

    # Signed records are required
    assert 'signature' in rec
