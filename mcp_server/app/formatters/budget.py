"""
Real token counting + hard budget enforcement.

Uses tiktoken's cl100k_base encoder (matches GPT-4/Claude closely enough for budgeting).
Falls back to a char-based estimate if tiktoken isn't installed so the server
keeps running on minimal deps.
"""
from __future__ import annotations
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

_enc = None
_enc_available: Optional[bool] = None


def _get_encoder():
    """Lazy-load tiktoken; cache result so the fallback isn't probed repeatedly."""
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
    except Exception as exc:
        logger.info("tiktoken unavailable (%s) — falling back to char-based estimate", exc)
        _enc_available = False
        return None


def count_tokens(text: str) -> int:
    """
    Return a reasonably accurate token count.
    Fallback heuristic: 1 token ≈ 4 characters (a bit conservative).
    """
    if not text:
        return 0
    enc = _get_encoder()
    if enc is not None:
        return len(enc.encode(text, disallowed_special=()))
    return max(1, len(text) // 4)


def enforce_budget(
    lines: List[str],
    max_tokens: int,
    truncated_marker: str = "… [truncated to stay under token budget]",
) -> str:
    """
    Assemble `lines` into a response that fits within `max_tokens`.

    Drops trailing lines first (preserving the header/summary), then tries to
    truncate the last retained line to get under budget. Appends a marker so
    the agent knows the response was clipped.
    """
    if max_tokens <= 0:
        return "\n".join(lines)

    # Fast path: is the full text already under budget?
    text = "\n".join(lines)
    if count_tokens(text) <= max_tokens:
        return text

    # Otherwise, build up greedily until we'd overflow.
    marker_cost = count_tokens(truncated_marker) + 2  # + newline + safety
    kept: List[str] = []
    used = 0
    for line in lines:
        line_cost = count_tokens(line) + 1  # +1 for the joining newline
        if used + line_cost + marker_cost > max_tokens:
            break
        kept.append(line)
        used += line_cost

    if not kept:
        # Degenerate: even the first line overflows. Hard-truncate it by chars.
        enc = _get_encoder()
        if enc is not None:
            tokens = enc.encode(lines[0], disallowed_special=())[: max_tokens - marker_cost]
            first = enc.decode(tokens)
        else:
            first = lines[0][: max_tokens * 4 - len(truncated_marker)]
        return f"{first}\n{truncated_marker}"

    kept.append(truncated_marker)
    return "\n".join(kept)
