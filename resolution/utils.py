import re
from datetime import datetime, timezone
from typing import Set

from schemas import QueryState


# ── SPL Validation Rules ──────────────────────────────────────

DEPRECATED_PATTERNS: list[str] = [
    r"\beval\s+.*\|\s*eval\b",          # chained eval
    r"\bjoin\s+type\s*=\s*outer\b",      # outer join (deprecated in some SPL)
    r"\binputcsv\b",                     # inputcsv (security risk)
    r"\boutputcsv\b",                    # outputcsv (security risk)
    r"\bmvexpand\b.*\blimit\s*=\s*0\b",  # unlimited mvexpand (memory risk)
]

ALLOWED_INDEXES: Set[str] = {"main", "web", "security", "firewall", "dns", "proxy"}

MAX_DEPTH: int = 5


def _count_pipe_depth(query_text: str) -> int:
    """Count pipe depth (number of | separators)."""
    return query_text.count("|")


def _extract_indexes(query_text: str) -> Set[str]:
    """Extract index=... values from query."""
    pattern = r'index\s*=\s*["\']?([a-zA-Z0-9_]+)["\']?'
    return set(re.findall(pattern, query_text, re.IGNORECASE))


def validate_spl(query_text: str) -> QueryState:
    """
    Deterministic SPL validation.
    Returns RED (invalid), AMBER (warning), or GREEN (healthy).
    """
    # Rule 1: Check for deprecated syntax → RED
    for pattern in DEPRECATED_PATTERNS:
        if re.search(pattern, query_text, re.IGNORECASE):
            return QueryState.RED

    # Rule 2: Check pipe depth → RED if exceeded
    if _count_pipe_depth(query_text) > MAX_DEPTH:
        return QueryState.RED

    # Rule 3: Check index availability → AMBER if unknown index
    indexes = _extract_indexes(query_text)
    if indexes and not indexes.issubset(ALLOWED_INDEXES):
        return QueryState.AMBER

    # Rule 4: Empty or trivial query → RED
    stripped = query_text.strip()
    if not stripped or len(stripped) < 3:
        return QueryState.RED

    # Default: GREEN
    return QueryState.GREEN


def now_utc() -> datetime:
    """Return current UTC time with timezone info. Use ONLY for metadata, NOT for ordering."""
    return datetime.now(timezone.utc)


def generate_audit_id(query_id: str, event_id: str, ts: datetime) -> str:
    """Deterministic audit ID based on query + event + timestamp."""
    ts_str = ts.isoformat()
    return f"audit-{query_id}-{event_id}-{hash(ts_str) & 0xFFFFFFFF}"