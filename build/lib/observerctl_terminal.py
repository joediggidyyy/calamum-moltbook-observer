from __future__ import annotations

import os
import re
import sys

from typing import Optional, TextIO


_RESET = '\x1b[0m'
_STYLE_CODES = {
    'dim': '\x1b[90m',
    'structure': '\x1b[36m',
    'advisory': '\x1b[33m',
    'positive': '\x1b[32m',
    'negative': '\x1b[31m',
}
_ANSI_ESCAPE_RE = re.compile(r'\x1b\[[0-9;]*m')


def colors_enabled(stream: Optional[TextIO] = None) -> bool:
    if str(os.getenv('NO_COLOR', '') or '').strip():
        return False

    mode = str(os.getenv('OBSERVERCTL_COLOR', '') or '').strip().lower()
    if mode in ('0', 'false', 'never', 'off'):
        return False
    if mode in ('1', 'true', 'always', 'on'):
        return True

    target = stream or sys.stdout
    try:
        if not bool(target.isatty()):
            return False
    except Exception:
        return False

    if str(os.getenv('TERM', '') or '').strip().lower() == 'dumb':
        return False
    return True


def style_text(text: str, role: str, stream: Optional[TextIO] = None) -> str:
    content = str(text or '')
    code = _STYLE_CODES.get(str(role or '').strip().lower())
    if not content or not code or not colors_enabled(stream=stream):
        return content
    return '{0}{1}{2}'.format(code, content, _RESET)


def style_heading(text: str, stream: Optional[TextIO] = None) -> str:
    return style_text(text, 'structure', stream=stream)


def strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE_RE.sub('', str(text or ''))


def visible_len(text: str) -> int:
    return len(strip_ansi(text))


def ljust_ansi(text: str, width: int) -> str:
    content = str(text or '')
    padding = max(0, int(width) - visible_len(content))
    return '{0}{1}'.format(content, ' ' * padding)


def rjust_ansi(text: str, width: int) -> str:
    content = str(text or '')
    padding = max(0, int(width) - visible_len(content))
    return '{0}{1}'.format(' ' * padding, content)
