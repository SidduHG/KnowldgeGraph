"""Token counting + hard budget enforcement.

Same interface as the original ``mcp_server/app/formatters/budget.py`` but
moved into the unified package. Falls back to a char-based estimate if
``tiktoken`` isn't installed so the server stays runnable on minimal deps.
"""
from __future__ import annotations

from typing import List, Optional

from ckg.observability import get_logger

logger = get_logger(__name__)

_enc = None
_enc_available: Optional[bool] = None


def _encoder():
    global _enc, _enc_available
    if _enc_available is False:
        return None
    if _enc is not None:
        return _enc
    try:
        import tiktoken  # type: ignore
        _enc = tiktoken.get_encoding("cl100k_base")
        _enc_available = True
        return _enc
    except Exception as exc:  # pragma: no cover
        logger.info("tiktoken unavailable (%s) — falling back to char estimator", exc)
        _enc_available = False
        return None


def count_tokens(text: str) -> int:
    if not text:
        return 0
    enc = _encoder()
    if enc is not None:
        return len(enc.encode(text, disallowed_special=()))
    return max(1, len(text) // 4)


def enforce_budget(
    lines: List[str],
    max_tokens: int,
    truncated_marker: str = "… [truncated to stay under token budget]",
) -> str:
    """Pack ``lines`` into a string ≤ ``max_tokens`` tokens.

    Drops trailing lines first; appends a marker so the caller knows the
    response was clipped.
    """
    if max_tokens <= 0:
        return "\n".join(lines)

    text = "\n".join(lines)
    if count_tokens(text) <= max_tokens:
        return text

    marker_cost = count_tokens(truncated_marker) + 2
    kept: List[str] = []
    used = 0
    for line in lines:
        line_cost = count_tokens(line) + 1
        if used + line_cost + marker_cost > max_tokens:
            break
        kept.append(line)
        used += line_cost

    if not kept:
        enc = _encoder()
        if enc is not None:
            tokens = enc.encode(lines[0], disallowed_special=())[: max_tokens - marker_cost]
            first = enc.decode(tokens)
        else:
            first = lines[0][: max_tokens * 4 - len(truncated_marker)]
        return f"{first}\n{truncated_marker}"

    kept.append(truncated_marker)
    return "\n".join(kept)
