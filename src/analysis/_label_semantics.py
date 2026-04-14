from __future__ import annotations

import re
from typing import Any, Iterable, Set


_TV_LABEL_RE = re.compile(r'^tv-(\d+)$', re.IGNORECASE)
_POSITIVE_TEXT = {'anomaly', 'anomalous', 'positive', 'true', 'yes'}
_NEGATIVE_TEXT = {'benign', 'false', 'negative', 'no', 'normal'}


def _normalize_label_token(value: Any) -> str:
    return str(value or '').strip().lower()


def infer_positive_label_tokens(values: Iterable[Any]) -> Set[str]:
    tokens = {
        _normalize_label_token(value)
        for value in values
        if _normalize_label_token(value)
    }
    if not tokens:
        return set()

    tv_tokens = {}
    for token in tokens:
        match = _TV_LABEL_RE.match(token)
        if match is None:
            tv_tokens = {}
            break
        tv_tokens[token] = int(match.group(1))
    if tv_tokens:
        return {token for token, level in tv_tokens.items() if level == 3}

    numeric_tokens = {}
    for token in tokens:
        try:
            numeric_tokens[token] = float(token)
        except (TypeError, ValueError):
            numeric_tokens = {}
            break
    if numeric_tokens:
        numeric_domain = {value for value in numeric_tokens.values()}
        if numeric_domain <= {0.0, 1.0}:
            return {token for token, value in numeric_tokens.items() if value == 1.0}
        if 3.0 in numeric_domain and numeric_domain <= {0.0, 1.0, 2.0, 3.0}:
            return {token for token, value in numeric_tokens.items() if value == 3.0}

    if tokens <= (_POSITIVE_TEXT | _NEGATIVE_TEXT):
        return {token for token in tokens if token in _POSITIVE_TEXT}

    return {'tv-3'} if 'tv-3' in tokens else set()


def label_token_to_binary(value: Any, *, positive_tokens: Set[str]) -> int:
    token = _normalize_label_token(value)
    if not token:
        return 0
    if token in positive_tokens:
        return 1
    if _TV_LABEL_RE.match(token) is not None:
        return 0
    if token in _POSITIVE_TEXT or token in _NEGATIVE_TEXT:
        return 0
    try:
        float(token)
        return 0
    except (TypeError, ValueError):
        return 0
