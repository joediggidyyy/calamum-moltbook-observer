from __future__ import annotations

from pathlib import Path
import sys


SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from ops_dashboard import normalize_mode  # noqa: E402


def test_normalize_mode_aliases_and_fallback() -> None:
    assert normalize_mode('passive') == 'PASSIVE_LISTENER'
    assert normalize_mode('chaos') == 'CHAOS_MODE'
    assert normalize_mode('unknown-mode') == 'CANARY'