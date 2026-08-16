from datetime import datetime
from typing import List, Optional, Dict
from schemas import AuditRecord, QueryState, EventType


class AuditTrail:
    """
    Append-only, immutable audit log.
    All reads are O(n) over in-memory list — fine for hackathon scale.
    """
    def __init__(self):
        self._records: List[AuditRecord] = []
        self._by_query: Dict[str, List[str]] = {}   # query_id -> list of audit_id
        self._by_audit_id: Dict[str, AuditRecord] = {}

    def append(self, record: AuditRecord) -> None:
        """Immutable append. Never update or delete."""
        if record.audit_id in self._by_audit_id:
            return  # silent dedup at audit level (defensive)
        self._records.append(record)
        self._by_audit_id[record.audit_id] = record
        self._by_query.setdefault(record.query_id, []).append(record.audit_id)

    def get_all(self) -> List[AuditRecord]:
        """Return full audit trail in chronological order."""
        return list(self._records)

    def get_by_query(self, query_id: str) -> List[AuditRecord]:
        """Return audit records for a specific query, chronological."""
        audit_ids = self._by_query.get(query_id, [])
        return [self._by_audit_id[aid] for aid in audit_ids]

    def get_by_audit_id(self, audit_id: str) -> Optional[AuditRecord]:
        return self._by_audit_id.get(audit_id)

    def clear(self) -> None:
        """Used ONLY for replay isolation. Resets to empty."""
        self._records.clear()
        self._by_query.clear()
        self._by_audit_id.clear()