from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / 'src'
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from calamum_librarian import librarian_report_store_packet  # noqa: E402


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def main() -> int:
    packet = librarian_report_store_packet(PROJECT_ROOT / 'src' / 'observerctl.py', purge=True)
    packet['invoked_from'] = 'semantics_staging/reset_report_collections_20260404.py'
    packet['invoked_at_utc'] = datetime.now(timezone.utc).isoformat()
    packet['helper_generation_stamp'] = _utc_stamp()
    print(json.dumps(packet, indent=2, sort_keys=True))
    return 0 if str(packet.get('decision', 'no-go')).strip().lower() == 'go' else 2


if __name__ == '__main__':
    raise SystemExit(main())
