from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from typing import List, Optional
from datetime import datetime, timezone

from schemas import (
    QueryEvent,
    QueryResponse,
    AuditRecord,
    ReplayRequest,
    QueryStateSnapshot,
)
from engine import QueryEngine
from audit import AuditTrail
from utils import now_utc


# ── App & Global State ────────────────────────────────────────

app = FastAPI(
    title="SPL Query Health Monitor",
    description="Real-time SPL query monitoring with deterministic conflict resolution and audit-replay",
    version="1.0.0",
)

# Global in-memory engine (production would use dependency injection)
_engine = QueryEngine()


# ── Helper: Snapshot → Response ─────────────────────────────

def _to_response(snapshot: QueryStateSnapshot) -> QueryResponse:
    audit_records = _engine.get_audit_trail().get_by_query(snapshot.query_id)
    return QueryResponse(
        query_id=snapshot.query_id,
        state=snapshot.state,
        query_text=snapshot.query_text,
        last_updated=snapshot.last_updated,
        source=snapshot.source,
        version=snapshot.version,
        conflict_resolution_reason=snapshot.conflict_resolution_reason,
        audit_history=audit_records,
    )


# ── Routes ────────────────────────────────────────────────────

@app.post("/queries", status_code=status.HTTP_200_OK)
def post_query(event: QueryEvent):
    """
    Ingest a query event. Idempotent.
    Creates new query or resolves conflict vs existing state.
    """
    try:
        snapshot = _engine.process_event(event)
        return _to_response(snapshot)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/queries/{query_id}", status_code=status.HTTP_200_OK)
def get_query(query_id: str):
    """
    Get current state and full audit history for a query.
    """
    snapshot = _engine.get_state(query_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"Query {query_id} not found")
    return _to_response(snapshot)


@app.get("/audit", status_code=status.HTTP_200_OK)
def get_audit():
    """
    Get full immutable audit trail.
    """
    return _engine.get_audit_trail().get_all()


@app.post("/events/replay", status_code=status.HTTP_200_OK)
def post_replay(request: ReplayRequest):
    """
    Replay a list of events on a CLEAN, isolated engine.
    Returns rebuilt audit trail and final states.
    Deterministic: same input → same output every time.
    """
    from replay import ReplayEngine

    replay_engine = ReplayEngine()
    result = replay_engine.replay(request.events)

    return {
        "audit_trail": [r.model_dump() for r in result["audit_trail"]],
        "final_states": {
            qid: snap.model_dump()
            for qid, snap in result["final_states"].items()
        },
        "events_processed": result["events_processed"],
        "events_deduped": result["events_deduped"],
    }


@app.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    return {"status": "healthy", "timestamp": now_utc().isoformat()}


# ── Error Handlers ──────────────────────────────────────────

@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc)},
    )