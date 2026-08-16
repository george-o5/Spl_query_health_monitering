from datetime import datetime
from typing import Dict, Optional, List, Set
import uuid

from schemas import QueryEvent, QueryState, QueryStateSnapshot, AuditRecord, EventType
from audit import AuditTrail
from utils import validate_spl, generate_audit_id, now_utc


class QueryEngine:
    """
    Deterministic state machine for SPL query health monitoring.
    In-memory only. Event-sourced with conflict resolution.
    """

    def __init__(self, audit_trail: Optional[AuditTrail] = None):
        self._state: Dict[str, QueryStateSnapshot] = {}   # query_id -> snapshot
        self._seen_events: Set[str] = set()                # event_id dedup
        self._audit: AuditTrail = audit_trail or AuditTrail()

    # ── Public API ──────────────────────────────────────────────

    def process_event(self, event: QueryEvent) -> QueryStateSnapshot:
        """
        Main entry. Idempotent. Deterministic.
        Returns the resolved snapshot for this query_id.
        """
        # Idempotency: exact duplicate event_id → no-op, return current state
        if event.event_id in self._seen_events:
            existing = self._state.get(event.query_id)
            if existing:
                return existing
            # Edge: dup event_id but query never existed? Return synthetic.
            return self._synthetic_snapshot(event)

        # Mark seen immediately (prevents re-entrant issues)
        self._seen_events.add(event.event_id)

        current = self._state.get(event.query_id)

        if current is None:
            # ── CREATE ──────────────────────────────────────────
            new_state = validate_spl(event.query_text)
            snapshot = QueryStateSnapshot(
                query_id=event.query_id,
                state=new_state,
                query_text=event.query_text,
                last_updated=event.timestamp,
                source=event.source,
                version=event.version,
                conflict_resolution_reason=None,
                audit_history=[],
            )
            self._state[event.query_id] = snapshot
            self._log_audit(event, EventType.CREATED, None, new_state, None)
            return snapshot

        # ── CONFLICT DETECTION & RESOLUTION ───────────────────
        # Determine if incoming event wins over current state
        winner_event, reason = self._resolve_conflict(current, event)

        if winner_event == "current":
            # Current wins → no state change, but still log as resolved (traceability)
            self._log_audit(
                event, EventType.RESOLVED, current.state, current.state,
                f"REJECTED: {reason}"
            )
            return current

        # Incoming wins → compute new state from its query_text
        new_state = validate_spl(event.query_text)
        old_state = current.state

        snapshot = QueryStateSnapshot(
            query_id=event.query_id,
            state=new_state,
            query_text=event.query_text,
            last_updated=event.timestamp,
            source=event.source,
            version=event.version,
            conflict_resolution_reason=reason,
            audit_history=current.audit_history + [],  # copy
        )
        self._state[event.query_id] = snapshot
        self._log_audit(event, EventType.UPDATED, old_state, new_state, reason)
        return snapshot

    def get_state(self, query_id: str) -> Optional[QueryStateSnapshot]:
        return self._state.get(query_id)

    def get_audit_trail(self) -> AuditTrail:
        return self._audit

    def get_all_states(self) -> Dict[str, QueryStateSnapshot]:
        return dict(self._state)

    def reset(self) -> None:
        """Clean slate. Used by replay."""
        self._state.clear()
        self._seen_events.clear()
        self._audit.clear()

    # ── Conflict Resolution ─────────────────────────────────────

    def _resolve_conflict(
        self,
        current: QueryStateSnapshot,
        incoming: QueryEvent,
    ) -> tuple[str, Optional[str]]:
        """
        Deterministic priority hierarchy:
        1. Source reliability: AI-Agent > Analyst
        2. Higher version wins
        3. Earlier timestamp wins
        4. Alphabetical query_id fallback (deterministic tiebreak)
        
        Returns ("current" | "incoming", reason_string)
        """
        # If same source, same version, same timestamp → idempotent update path
        if (current.source == incoming.source and
            current.version == incoming.version and
            current.last_updated == incoming.timestamp):
            return ("incoming", "Same source/version/timestamp — accepted as idempotent refresh")

        # Priority 1: Source reliability
        current_source_rank = self._source_rank(current.source)
        incoming_source_rank = self._source_rank(incoming.source)

        if incoming_source_rank > current_source_rank:
            return ("incoming", f"Source priority: {incoming.source} > {current.source}")
        if incoming_source_rank < current_source_rank:
            return ("current", f"Source priority: {current.source} > {incoming.source}")

        # Priority 2: Higher version wins
        if incoming.version > current.version:
            return ("incoming", f"Higher version: {incoming.version} > {current.version}")
        if incoming.version < current.version:
            return ("current", f"Higher version: {current.version} > {incoming.version}")

        # Priority 3: Earlier timestamp wins
        if incoming.timestamp < current.last_updated:
            return ("incoming", f"Earlier timestamp: {incoming.timestamp.isoformat()} < {current.last_updated.isoformat()}")
        if incoming.timestamp > current.last_updated:
            return ("current", f"Earlier timestamp: {current.last_updated.isoformat()} < {incoming.timestamp.isoformat()}")

        # Priority 4: Alphabetical fallback (deterministic)
        if incoming.query_id <= current.query_id:
            return ("incoming", f"Alphabetical tiebreak: {incoming.query_id} <= {current.query_id}")
        return ("current", f"Alphabetical tiebreak: {current.query_id} < {incoming.query_id}")

    def _source_rank(self, source: str) -> int:
        """
        AI-Agent with higher suffix wins over lower suffix.
        Analyst = 0.
        AI-Agent = 1, AI-Agent-v2 = 2, AI-Agent-v3 = 3, etc.
        """
        if source == "Analyst":
            return 0
        if source == "AI-Agent":
            return 1
        if source.startswith("AI-Agent-v"):
            try:
                suffix = int(source.split("-v")[1])
                return suffix
            except (ValueError, IndexError):
                return 1
        return 0  # fallback for unknown

    # ── Audit Logging ─────────────────────────────────────────

    def _log_audit(
        self,
        event: QueryEvent,
        event_type: EventType,
        state_before: Optional[QueryState],
        state_after: QueryState,
        reason: Optional[str],
    ) -> AuditRecord:
        audit_id = generate_audit_id(event.query_id, event.event_id, event.timestamp)
        record = AuditRecord(
            audit_id=audit_id,
            query_id=event.query_id,
            event_type=event_type,
            event_id=event.event_id,
            state_before=state_before,
            state_after=state_after,
            conflict_resolution_reason=reason,
            timestamp=event.timestamp,
            source=event.source,
            version=event.version,
        )
        self._audit.append(record)
        # Also attach audit_id to snapshot's history
        snap = self._state.get(event.query_id)
        if snap and audit_id not in snap.audit_history:
            snap.audit_history.append(audit_id)
        return record

    def _synthetic_snapshot(self, event: QueryEvent) -> QueryStateSnapshot:
        """Fallback for dedup event on non-existent query (shouldn't happen)."""
        return QueryStateSnapshot(
            query_id=event.query_id,
            state=validate_spl(event.query_text),
            query_text=event.query_text,
            last_updated=event.timestamp,
            source=event.source,
            version=event.version,
            conflict_resolution_reason="Synthetic: dedup event on missing query",
            audit_history=[],
        )