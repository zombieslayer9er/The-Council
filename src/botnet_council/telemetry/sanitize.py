"""Central policy for safe, low-detail public error messages."""

from __future__ import annotations

import re
from dataclasses import dataclass

_SECRET = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password|credential|authorization)\b\s*[:=]\s*[^\s,;]+"
)
_WINDOWS_PATH = re.compile(r"(?i)(?:[a-z]:\\|\\\\)[^\s\"']+")
_POSIX_PATH = re.compile(r"(?<![\w:])/(?:home|users|root|private|var|etc|opt|tmp)/[^\s\"']+")


@dataclass(frozen=True, slots=True)
class SanitizedError:
    category: str
    code: str
    message: str


def sanitize_exception(error: Exception, *, stage: str) -> SanitizedError:
    """Return a stable public description while retaining no raw exception text."""
    category = type(error).__name__
    code = f"{stage}_failed"
    raw = str(error)
    cleaned = _SECRET.sub(lambda match: f"{match.group(1)}=[REDACTED]", raw)
    cleaned = _WINDOWS_PATH.sub("[PRIVATE_PATH]", cleaned)
    cleaned = _POSIX_PATH.sub("[PRIVATE_PATH]", cleaned)
    if not cleaned.strip() or "[REDACTED]" in cleaned or "[PRIVATE_PATH]" in cleaned:
        cleaned = f"{stage.replace('_', ' ')} failed; inspect local server logs"
    return SanitizedError(category=category, code=code, message=cleaned[:240])
