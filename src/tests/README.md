# Calamum Observer Tests

This directory contains `pytest` suites for the Calamum architecture.

## Suites

-   `test_librarian.py`: Tests the `calamum_librarian.py` daemon.
    -   File compression and hashing.
    -   Manifest integrity.
    -   Corrupt file quarantine.
    -   Adaptive Policy calculations.
-   `test_obfuscator.py`: Tests the `obfuscator_lib.py`.
    -   PII stripping.
    -   HMAC-SHA256 signing.
-   `test_client.py`: (Legacy) Tests for the Moltbook client simulator.

## Running Tests

From the repo root:

```powershell
pytest projects/calamum-moltbook-observer/src/tests/
```
