from __future__ import annotations

from pathlib import Path
from typing import Tuple


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _classify(path: Path, operations_root: Path) -> Tuple[str, str]:
    name = path.name
    rel = path.relative_to(operations_root)

    if rel.parent == Path('.'):
        if name.startswith('JOB_REPORT_'):
            return 'KEEP', 'canonical execution report'
        if name.startswith('INCIDENT_REPORT_'):
            return 'KEEP', 'canonical incident artifact'

    if name.startswith('CALAMUM_REPORT_PATH_MIGRATION_INDEX_'):
        return 'KEEP_OR_BUCKET', 'historical migration index artifact'
    if name.startswith('OBSERVERCTL_') and ('_VALIDATION_' in name or '_RUN_' in name):
        return 'KEEP_OR_BUCKET', 'observer compatibility evidence packet'
    if any(token in name for token in ('_AUDIT_', '_ANALYSIS_', '_INVESTIGATION_', '_SNAPSHOT_', '_STANDARD_')):
        return 'KEEP_OR_BUCKET', 'typed operational artifact'
    if '_PLAN_' in name:
        return 'REVIEW_MOVE', 'plan docs should live in planning surfaces'
    return 'REVIEW_REPLACE', 'free-floating naming outside primary schema'


def test_operations_docs_have_no_review_replace_items() -> None:
    root = _project_root()
    operations_root = root / 'docs' / 'reports' / 'operations'
    assert operations_root.exists(), 'operations reports root must exist'

    offending = []
    for p in operations_root.rglob('*'):
        if not p.is_file():
            continue
        action, reason = _classify(p, operations_root)
        if action == 'REVIEW_REPLACE':
            offending.append((str(p.relative_to(operations_root)), reason))

    assert not offending, f'Unexpected REVIEW_REPLACE artifacts: {offending}'


def test_operations_docs_use_approved_bucket_subfolders() -> None:
    root = _project_root()
    operations_root = root / 'docs' / 'reports' / 'operations'

    allowed_subfolders = {
        'audits',
        'standards',
        'migration_indexes',
        'compat_packets',
    }

    top_level_noncanonical = []
    disallowed_bucket_paths = []

    for p in operations_root.rglob('*'):
        if not p.is_file():
            continue
        rel = p.relative_to(operations_root)

        if rel.parent == Path('.'):
            if not (p.name.startswith('JOB_REPORT_') or p.name.startswith('INCIDENT_REPORT_')):
                top_level_noncanonical.append(rel.as_posix())
            continue

        first = rel.parts[0]
        if first not in allowed_subfolders:
            disallowed_bucket_paths.append(rel.as_posix())

    assert not top_level_noncanonical, (
        'Non-canonical files must be bucketed under approved subfolders: '
        f'{top_level_noncanonical}'
    )
    assert not disallowed_bucket_paths, (
        'Found files under unapproved operations subfolders: '
        f'{disallowed_bucket_paths}'
    )
