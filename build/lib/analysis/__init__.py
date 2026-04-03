"""Calamum Blind ML analysis tooling.

The supported observer ML lane remains names-only and reproducible-first.
It now uses maintainer-approved third-party dependencies for the production
training, evaluation, and visualization path.

Design constraints:
- names-only (no raw Moltbook semantic payload)
- deterministic outputs where feasible (manifests + splits)
"""

from __future__ import annotations
