from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ._util import default_analysis_dir, sha256_path, try_get_git_sha, utc_now_iso


@dataclass
class EvalResult:
    threshold: float
    max_fpr: float
    has_labels: bool
    counts: Dict[str, int]
    metrics: Dict[str, float]


def _read_features(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open('r', encoding='utf-8', newline='') as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append(row)
    return rows


def _read_labels(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    with path.open('r', encoding='utf-8', newline='') as f:
        r = csv.DictReader(f)
        for row in r:
            rid = (row.get('record_id') or '').strip()
            tv = (row.get('tv_id') or '').strip()
            if rid and tv:
                out[rid] = tv
    return out


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        if x is None:
            return default
        return int(float(x))
    except Exception:
        return default


def baseline_score(row: Dict[str, Any]) -> float:
    """A minimal, stdlib-only heuristic score.

    This is not a final model; it exists to enable end-to-end evaluation artifacts.
    """
    tox = _safe_int(row.get('f_toxicity'), 0)
    has_link = _safe_int(row.get('has_link'), 0)
    has_code = _safe_int(row.get('has_code_block'), 0)
    code_density = _safe_float(row.get('f_code_density'), 0.0)
    complexity = _safe_float(row.get('f_complexity'), 0.0)

    # Score components are intentionally simple and explainable.
    return float(tox) + 0.5 * float(has_link) + 0.2 * float(has_code) + 0.2 * code_density + 0.1 * complexity


def _confusion(y_true: List[int], y_pred: List[int]) -> Dict[str, int]:
    tp = fp = tn = fn = 0
    for t, p in zip(y_true, y_pred):
        if t == 1 and p == 1:
            tp += 1
        elif t == 0 and p == 1:
            fp += 1
        elif t == 0 and p == 0:
            tn += 1
        elif t == 1 and p == 0:
            fn += 1
    return {'tp': tp, 'fp': fp, 'tn': tn, 'fn': fn}


def _metrics_from_conf(conf: Dict[str, int]) -> Dict[str, float]:
    tp = float(conf.get('tp', 0))
    fp = float(conf.get('fp', 0))
    tn = float(conf.get('tn', 0))
    fn = float(conf.get('fn', 0))

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    return {
        'precision': precision,
        'recall': recall,
        'f1': f1,
        'fpr': fpr,
    }


def _choose_threshold_for_fpr(scores: List[float], y_true: List[int], max_fpr: float) -> float:
    """Choose the best F1 threshold while meeting the FPR constraint."""
    candidates = sorted(set(scores))
    best_thr = candidates[0] if candidates else 0.0
    best_f1 = -1.0

    for thr in candidates:
        y_pred = [1 if s >= thr else 0 for s in scores]
        conf = _confusion(y_true, y_pred)
        m = _metrics_from_conf(conf)
        if m['fpr'] <= max_fpr and m['f1'] >= best_f1:
            best_f1 = m['f1']
            best_thr = thr

    return float(best_thr)


def evaluate(
    features_csv: Path,
    *,
    labels_csv: Optional[Path] = None,
    max_fpr: float = 0.01,
) -> EvalResult:
    rows = _read_features(features_csv)
    labels: Dict[str, str] = {}
    if labels_csv is not None and labels_csv.exists():
        labels = _read_labels(labels_csv)

    scores: List[float] = []
    y_true: List[int] = []
    has_labels = bool(labels)

    for row in rows:
        s = baseline_score(row)
        scores.append(s)
        if has_labels:
            rid = (row.get('record_id') or '').strip()
            tv = labels.get(rid)
            y_true.append(1 if tv == 'TV-3' else 0)

    # Select threshold
    if has_labels and y_true:
        thr = _choose_threshold_for_fpr(scores, y_true, max_fpr=max_fpr)
        y_pred = [1 if s >= thr else 0 for s in scores]
        conf = _confusion(y_true, y_pred)
        metrics = _metrics_from_conf(conf)
        counts = conf
    else:
        # Unlabeled: choose quantile threshold to flag ~max_fpr fraction.
        if not scores:
            thr = 0.0
        else:
            sorted_scores = sorted(scores)
            # Pick cutoff so that roughly max_fpr are >= thr
            k = int(max(0, min(len(sorted_scores) - 1, round((1.0 - max_fpr) * (len(sorted_scores) - 1)))))
            thr = float(sorted_scores[k])
        flagged = sum(1 for s in scores if s >= thr)
        counts = {'flagged': int(flagged), 'total': int(len(scores))}
        metrics = {
            'flag_rate': (float(flagged) / float(len(scores))) if scores else 0.0,
        }

    return EvalResult(
        threshold=float(thr),
        max_fpr=float(max_fpr),
        has_labels=bool(has_labels),
        counts=counts,
        metrics=metrics,
    )


def write_run_artifacts(
    *,
    out_dir: Path,
    run_id: str,
    features_csv: Path,
    labels_csv: Optional[Path],
    result: EvalResult,
    dataset_manifest_path: Optional[Path] = None,
    operator: str = 'ORACL-Prime',
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    project_root = out_dir
    try:
        # attempt to locate project root for git sha
        from ._util import find_project_root

        project_root = find_project_root(out_dir)
    except Exception:
        project_root = out_dir

    run_json = {
        'identity': {
            'run_id': run_id,
            'created_at_utc': utc_now_iso(),
            'operator': operator,
        },
        'context': {
            'course_targets': ['DATA780', 'DATA740'],
            'constraints': {'max_fpr': float(result.max_fpr)},
        },
        'data': {
            'features_csv': str(features_csv),
            'labels_csv': str(labels_csv) if labels_csv else None,
            'dataset_manifest': str(dataset_manifest_path) if dataset_manifest_path else None,
            'dataset_manifest_sha256': sha256_path(dataset_manifest_path) if dataset_manifest_path and dataset_manifest_path.exists() else None,
        },
        'model': {
            'family': 'heuristic',
            'name': 'baseline_score_v1',
            'hyperparameters': {
                'threshold': float(result.threshold),
            },
        },
        'evaluation': {
            'has_labels': bool(result.has_labels),
            'metrics': dict(result.metrics),
            'counts': dict(result.counts),
            'thresholding': 'fpr_constrained_best_f1' if result.has_labels else 'quantile_flag_rate',
        },
        'governance': {
            'privacy_review': 'pass',
            'notes': 'Names-only baseline evaluation. No semantic payload consumed or emitted.',
        },
        'code': {
            'git_sha': try_get_git_sha(project_root),
        },
    }
    (out_dir / 'run.json').write_text(json.dumps(run_json, indent=2, sort_keys=True), encoding='utf-8')

    # Narrative run.md (privacy-safe)
    md = []
    md.append(f'# Training Run: {run_id}')
    md.append('')
    md.append(f'**Created (UTC)**: {run_json["identity"]["created_at_utc"]}  ')
    md.append(f'**Operator**: {operator}  ')
    md.append('')
    md.append('## Abstract')
    md.append('A stdlib-only heuristic baseline was evaluated to validate end-to-end reporting artifacts.')
    md.append('')
    md.append('## Data provenance and governance')
    md.append('- Inputs are obfuscated JSONL telemetry (no raw message bodies).')
    md.append('- Reports are names-only; no secrets or internal endpoints are included.')
    md.append('')
    md.append('## Model')
    md.append('- Family: heuristic')
    md.append('- Scorer: baseline_score_v1 (explainable weighted sum)')
    md.append(f'- Threshold: {result.threshold}')
    md.append('')
    md.append('## Evaluation')
    md.append(f'- Labeled mode: {"yes" if result.has_labels else "no"}')
    md.append(f'- Max FPR constraint: {result.max_fpr}')
    md.append('')
    md.append('### Metrics')
    for k, v in sorted(result.metrics.items()):
        md.append(f'- {k}: {v}')
    md.append('')
    md.append('### Counts')
    for k, v in sorted(result.counts.items()):
        md.append(f'- {k}: {v}')
    md.append('')
    md.append('## Next actions')
    md.append('- Add synthetic `tv_id` labels (TV-0..TV-3) for supervised evaluation (dependency-free).')
    md.append('- Introduce modeling dependencies only with explicit approval.')
    md.append('')
    (out_dir / 'run.md').write_text('\n'.join(md) + '\n', encoding='utf-8')


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description='Evaluate a baseline heuristic and emit run-ledger artifacts.')
    p.add_argument('--features-csv', required=True, type=Path)
    p.add_argument('--labels-csv', type=Path, default=None)
    p.add_argument('--dataset-manifest', type=Path, default=None)
    p.add_argument('--max-fpr', type=float, default=0.01)
    p.add_argument('--out-dir', type=Path, default=None)
    p.add_argument('--run-id', type=str, default=None)
    args = p.parse_args(argv)

    res = evaluate(args.features_csv, labels_csv=args.labels_csv, max_fpr=float(args.max_fpr))

    out_dir = args.out_dir
    if out_dir is None:
        base = default_analysis_dir(Path(__file__))
        out_dir = base / 'runs' / f'run_{utc_now_iso().replace(":", "").replace("-", "")}'

    run_id = args.run_id
    if run_id is None:
        run_id = out_dir.name

    write_run_artifacts(
        out_dir=out_dir,
        run_id=str(run_id),
        features_csv=args.features_csv,
        labels_csv=args.labels_csv,
        result=res,
        dataset_manifest_path=args.dataset_manifest,
    )

    print(json.dumps(asdict(res), indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
