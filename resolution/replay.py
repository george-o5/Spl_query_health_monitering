from typing import List, Dict, Any
from schemas import QueryEvent, AuditRecord, QueryStateSnapshot
from engine import QueryEngine


class ReplayEngine:
    """
    Isolated replay engine.
    Instantiates a fresh QueryEngine, sorts events chronologically,
    applies sequentially, returns full trace.
    """

    def replay(self, events: List[QueryEvent]) -> Dict[str, Any]:
        # Fresh engine — zero state
        engine = QueryEngine()

        # Deterministic sort: timestamp → version → source → query_id
        sorted_events = sorted(
            events,
            key=lambda e: (
                e.timestamp,
                e.version,
                e.source,
                e.query_id,
                e.event_id,  # final tiebreak for total determinism
            ),
        )

        processed = 0
        deduped = 0

        for event in sorted_events:
            # Pre-check dedup (engine also checks, but we track metrics)
            if event.event_id in engine._seen_events:
                deduped += 1
               