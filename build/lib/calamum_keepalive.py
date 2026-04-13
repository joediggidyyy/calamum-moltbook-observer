"""
calamum_keepalive.py

Standardized, rate-limited keepalive emitter for Calamum services.
Provides "active logging" visibility (provenance: stdout/stderr) without
flooding logs or obscuring the authoritative JSONL telemetry.

Policy:
- Names-only: No printing of secrets or raw payload content.
- Rate-limited: Default behavior is sparse (e.g. once per minute).
- Safe-formatted: ISO8601 UTC timestamps.
"""

import sys
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, TextIO

class KeepaliveHelper:
    def __init__(
        self, 
        service_name: str, 
        interval_seconds: float = 60.0, 
        stream: TextIO = sys.stdout
    ):
        """
        Initialize the KeepaliveHelper.

        Args:
            service_name: Name of the service (e.g., 'CalamumObserver').
            interval_seconds: Minimum seconds between automatic emits.
            stream: Output stream (default: sys.stdout).
        """
        self.service_name = service_name
        self.interval_seconds = interval_seconds
        self.stream = stream
        self.last_emit_time = 0.0

    def emit(self, status: str = "ALIVE", metrics: Optional[Dict[str, Any]] = None) -> None:
        """
        Emit a keepalive message if the time interval has passed.

        Args:
            status: A short status string (default: "ALIVE").
            metrics: Optional dictionary of safe, low-cardinality metrics to include.
        """
        now = time.time()
        if now - self.last_emit_time >= self.interval_seconds:
            self._write(now, status, metrics)
            self.last_emit_time = now

    def force_emit(self, status: str = "FORCED", metrics: Optional[Dict[str, Any]] = None) -> None:
        """
        Force emit a keepalive message regardless of the time interval.
        Useful for startup, shutdown, or critical state changes.
        """
        now = time.time()
        self._write(now, status, metrics)
        # Update last_emit_time to prevent immediate subsequent rate-limited emit
        self.last_emit_time = now

    def _write(self, timestamp: float, status: str, metrics: Optional[Dict[str, Any]]) -> None:
        """
        Internal writer. Formats and flushes the message.
        """
        # Timezone-aware UTC timestamp (Policy: UTC correctness)
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        ts_str = dt.isoformat()

        # Build metric string
        metrics_part = ""
        if metrics:
            # Simple k=v formatting; specific metric values must follow names-only policy
            safe_metrics = [f"{k}={v}" for k, v in metrics.items()]
            metrics_part = " | " + ", ".join(safe_metrics)

        # Output format: [TIMESTAMP] [SERVICE] STATUS | metrics...
        # flush=True ensures reliability when redirected to files
        print(f"[{ts_str}] [{self.service_name}] {status}{metrics_part}", file=self.stream, flush=True)

if __name__ == "__main__":
    # Self-test / Demo
    print("Initializing KeepaliveHelper test...")
    helper = KeepaliveHelper("TestService", interval_seconds=2)
    
    helper.force_emit("STARTUP", {"version": "1.0.1"})
    time.sleep(0.5)
    helper.emit("IGNORED") # Should be skipped due to rate limit
    time.sleep(2.0)
    helper.emit("RUNNING", {"items_processed": 42})
