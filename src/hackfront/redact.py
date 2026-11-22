"""Best-effort masking of credentials in text returned to agents. Not a guarantee: see docs/adr/0001."""

from __future__ import annotations

import re

_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)", re.S),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),  # JWT
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{16,}"),
    re.compile(r"(?i)\b((?:password|passwd|pwd|secret|api[_-]?key|access[_-]?key|token|auth)[\w-]*\s*[:=]\s*)"
               r"[\"']?[^\s\"',;]{6,}"),
]
MASK = "[redacted]"


def redact(text: str | None) -> str | None:
    if not text:
        return text
    for pattern in _PATTERNS[:-1]:
        text = pattern.sub(MASK, text)
    return _PATTERNS[-1].sub(lambda m: m.group(1) + MASK, text)
