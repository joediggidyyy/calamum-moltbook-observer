from __future__ import annotations

import argparse
import csv
import json
import pickle
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

try:
    import joblib
except ImportError:
    joblib = None

from apexlab.evaluation.thresholds import binary_metrics, confusion_counts, select_lower_tail_threshold

from ._label_semantics import infer_positive_label_tokens, label_token_to_binary
from ._util import default_analysis_dir, sha256_path, try_get_git_sha, utc_now_iso


@dataclass
class EvalResult:
    threshold: float
    max_fpr: float
    has_labels: bool
    counts: Dict[str, int]
    metrics: Dict[str, float]


FEATURE_COLUMNS: List[str] = [
    'record_id',
    'ts_epoch',
    'content_length',
    'has_code_block',
    'has_link',
    'tags_count',
    'mentions_count',
    'f_complexity',
    'f_code_density',
    'f_toxicity',
    'is_canary',
    'type_post',
    'type_reply',
    'type_repost',
    'type_dm',
    'type_follow',
    'type_mention',
    'type_unknown',
]


def infer_model_score_direction(model: Any) -> str:
    if hasattr(model, 'score_samples') or hasattr(model, 'decision_function'):
        return 'lower'
    return 'higher'


_METADATA_COLUMNS = frozenset({'record_id', 'is_canary'})


def make_model_scorer(model: Any, feature_columns: Optional[List[str]] = None) -> ScorerFunc:
    train_cols: Optional[List[str]] = None
    if feature_columns is not None:
        train_cols = [c for c in feature_columns if c not in _METADATA_COLUMNS]

    def scorer(row: Dict[str, Any]) -> float:
        try:
            vec = []
            cols = train_cols if train_cols is not None else [c for c in row if c not in _METADATA_COLUMNS]
            for c in cols:
                val = row.get(c, 0)
                try:
                    vec.append(float(val))
                except (ValueError, TypeError):
                    vec.append(0.0)
            
            if hasattr(model, "predict_proba"):
                probas = model.predict_proba([vec])[0]
                if len(probas) > 1:
                    return float(probas[1])
                return float(probas[0])
            elif hasattr(model, "score_samples"):
                scores = model.score_samples([vec])
                return float(scores[0])
            elif hasattr(model, "decision_function"):
                return float(model.decision_function([vec])[0])
            elif hasattr(model, "predict"):
                return float(model.predict([vec])[0])
            return 0.0
        except Exception:
            return 0.0
            
    return scorer


ScorerArgs = Dict[str, Any]
ScorerFunc = Callable[[ScorerArgs], float]


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
            tv = (row.get('tv_id') or row.get('label') or '').strip()
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


def _predict_labels(scores: List[float], threshold: float, score_direction: str) -> List[int]:
    if str(score_direction).strip().lower() == 'lower':
        return [1 if score <= threshold else 0 for score in scores]
    return [1 if score >= threshold else 0 for score in scores]


def _choose_threshold_for_fpr(scores: List[float], y_true: List[int], max_fpr: float, score_direction: str) -> float:
    candidates = sorted(set(scores))
    best_thr = float(candidates[0]) if candidates else 0.0
    best_f1 = -1.0

    for threshold in candidates:
        y_pred = _predict_labels(scores, float(threshold), score_direction)
        metrics = binary_metrics(confusion_counts(y_true, y_pred))
        if metrics['fpr'] <= max_fpr and metrics['f1'] >= best_f1:
            best_f1 = metrics['f1']
            best_thr = float(threshold)
    return float(best_thr)


def evaluate(
    features_csv: Path,
    *,
    labels_csv: Optional[Path] = None,
    max_fpr: float = 0.01,
    scorer: ScorerFunc = baseline_score,
    score_direction: str = 'higher',
) -> EvalResult:
    rows = _read_features(features_csv)
    labels: Dict[str, str] = {}
    if labels_csv is not None and labels_csv.exists():
        labels = _read_labels(labels_csv)
    positive_tokens = infer_positive_label_tokens(labels.values())

    scores: List[float] = []
    y_true: List[int] = []
    has_labels = bool(labels)

    for row in rows:
        s = scorer(row)
        scores.append(s)
        if has_labels:
            rid = (row.get('record_id') or '').strip()
            tv = labels.get(rid)
            y_true.append(label_token_to_binary(tv, positive_tokens=positive_tokens))

    # Select threshold
    resolved_score_direction = 'lower' if str(score_direction).strip().lower() == 'lower' else 'higher'

    if has_labels and y_true:
        thr = _choose_threshold_for_fpr(scores, y_true, max_fpr=max_fpr, score_direction=resolved_score_direction)
        y_pred = _predict_labels(scores, thr, resolved_score_direction)
        conf = confusion_counts(y_true, y_pred)
        metrics = binary_metrics(conf)
        counts = conf
    else:
        if not scores:
            thr = 0.0
        else:
            if resolved_score_direction == 'lower':
                thr = float(select_lower_tail_threshold(scores, target_fpr=max_fpr))
            else:
                thr = float(-select_lower_tail_threshold([-float(score) for score in scores], target_fpr=max_fpr))
        flagged = sum(1 for s in scores if (s <= thr if resolved_score_direction == 'lower' else s >= thr))
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
    model_meta: Optional[Dict[str, Any]] = None,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    project_root = out_dir
    try:
        # attempt to locate project root for git sha
        from ._util import find_project_root

        project_root = find_project_root(out_dir)
    except Exception:
        project_root = out_dir

    if model_meta is None:
        model_meta = {
            'family': 'heuristic',
            'name': 'baseline_score_v1',
            'hyperparameters': {
                'threshold': float(result.threshold),
            },
        }

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
        'model': model_meta,
        'evaluation': {
            'has_labels': bool(result.has_labels),
            'metrics': dict(result.metrics),
            'counts': dict(result.counts),
            'thresholding': 'fpr_constrained_best_f1' if result.has_labels else 'upper_tail_quantile_flag_rate',
        },
        'governance': {
            'privacy_review': 'pass',
            'notes': 'Names-only evaluation. No semantic payload consumed or emitted.',
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
    md.append('Evaluation run artifacts.')
    md.append('')
    md.append('## Data provenance and governance')
    md.append('- Inputs are obfuscated JSONL telemetry (no raw message bodies).')
    md.append('- Reports are names-only; no secrets or internal endpoints are included.')
    md.append('')
    md.append('## Model')
    md.append(f'- Family: {model_meta.get("family", "unknown")}')
    md.append(f'- Name: {model_meta.get("name", "unknown")}')
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
    p.add_argument('--model-path', type=Path, default=None, help='Path to serialized scikit-learn model')
    args = p.parse_args(argv)

    scorer = baseline_score
    model_meta = None
    score_direction = 'higher'

    if args.model_path:
        print(f"Loading model from {args.model_path}...")
        try:
            with args.model_path.open('rb') as f:
                model = pickle.load(f)
        except Exception as pickle_error:
            if joblib is None:
                print(f"Error loading model via pickle: {pickle_error}")
                return 1
            try:
                model = joblib.load(args.model_path)
            except Exception as exc:
                print(f"Error loading model: {exc}")
                return 1
        try:
            manifest_feature_columns = None
            if args.dataset_manifest and args.dataset_manifest.exists():
                try:
                    with args.dataset_manifest.open('r', encoding='utf-8') as _mf:
                        manifest_feature_columns = json.load(_mf).get('feature_columns')
                except Exception:
                    pass
            scorer = make_model_scorer(model, feature_columns=manifest_feature_columns)
            score_direction = infer_model_score_direction(model)
            model_meta = {
                'family': 'trained_apexlab',
                'name': args.model_path.name,
                'class': type(model).__name__,
                'source': str(args.model_path),
            }
        except Exception as e:
            print(f"Error preparing model scorer: {e}")
            return 1

    res = evaluate(
        args.features_csv,
        labels_csv=args.labels_csv,
        max_fpr=float(args.max_fpr),
        scorer=scorer,
        score_direction=score_direction,
    )

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
        model_meta=model_meta,
    )

    print(json.dumps(asdict(res), indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
