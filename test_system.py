import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone, timedelta

from app import app, _engine
from schemas import QueryEvent, QueryState, EventType
from engine import QueryEngine
from replay import ReplayEngine


client = TestClient(app)


# ── Reset global engine before each test ─────────────────────

@pytest.fixture(autouse=True)
def reset_engine():
    _engine.reset()
    yield


# ── Fixtures ──────────────────────────────────────────────────

def make_event(
    event_id: str,
    query_id: str,
    query_text: str,
    source: str,
    timestamp: datetime,
    version: int,
):
    return {
        "event_id": event_id,
        "query_id": query_id,
        "query_text": query_text,
        "source": source,
        "timestamp": timestamp.isoformat(),
        "version": version,
    }


BASE_TS = datetime(2026, 8, 16, 8, 0, 0, tzinfo=timezone.utc)

# ── Tests ─────────────────────────────────────────────────────

def test_create_new_query():
    """Fresh query_id → created with GREEN state."""
    event = make_event("e1", "q1", "index=main | stats count", "Analyst", BASE_TS, 1)
    resp = client.post("/queries", json=event)
    assert resp.status_code == 200
    data = resp.json()
    assert data["query_id"] == "q1"
    assert data["state"] == "GREEN"
    assert data["version"] == 1
    assert data["audit_history"][0]["event_type"] == "created"


def test_duplicate_event_idempotent():
    """Same event_id processed twice → second is no-op."""
    event = make_event("e2", "q2", "index=main | stats count", "Analyst", BASE_TS, 1)
    r1 = client.post("/queries", json=event)
    assert r1.status_code == 200

    r2 = client.post("/queries", json=event)
    assert r2.status_code == 200
    assert r2.json()["state"] == r1.json()["state"]

    # Audit should have exactly 1 record
    audit = client.get("/audit").json()
    q2_audits = [a for a in audit if a["query_id"] == "q2"]
    assert len(q2_audits) == 1


def test_conflict_resolution_source_priority():
    """AI-Agent wins over Analyst."""
    analyst = make_event("e3", "q3", "index=main | stats count", "Analyst", BASE_TS, 1)
    agent = make_event("e4", "q3", "index=main | stats count", "AI-Agent", BASE_TS + timedelta(minutes=1), 1)

    r1 = client.post("/queries", json=analyst)
    assert r1.status_code == 200
    assert r1.json()["source"] == "Analyst"

    r2 = client.post("/queries", json=agent)
    assert r2.status_code == 200
    assert r2.json()["source"] == "AI-Agent"
    assert "AI-Agent > Analyst" in r2.json()["conflict_resolution_reason"]


def test_conflict_resolution_version_priority():
    """Higher version wins when same source."""
    v1 = make_event("e5", "q4", "index=main | stats count", "Analyst", BASE_TS, 1)
    v2 = make_event("e6", "q4", "index=main | stats count", "Analyst", BASE_TS + timedelta(minutes=1), 2)

    client.post("/queries", json=v1)
    r2 = client.post("/queries", json=v2)
    assert r2.json()["version"] == 2
    assert "Higher version: 2 > 1" in r2.json()["conflict_resolution_reason"]


def test_conflict_resolution_timestamp_priority():
    """Earlier timestamp wins when same source + same version."""
    late = make_event("e7", "q5", "index=main | stats count", "Analyst", BASE_TS + timedelta(minutes=5), 1)
    early = make_event("e8", "q5", "index=main | stats count", "Analyst", BASE_TS, 1)

    client.post("/queries", json=late)
    r2 = client.post("/queries", json=early)
    assert r2.json()["last_updated"] == BASE_TS.isoformat()
    assert "Earlier timestamp" in r2.json()["conflict_resolution_reason"]


def test_out_of_order_late_event():
    """Late event (older timestamp) still processed if it wins conflict."""
    now = make_event("e9", "q6", "index=main | stats count", "Analyst", BASE_TS + timedelta(hours=2), 1)
    late = make_event("e10", "q6", "index=main | stats count", "AI-Agent", BASE_TS, 2)

    client.post("/queries", json=now)
    r2 = client.post("/queries", json=late)
    # AI-Agent v2 wins despite earlier timestamp because version is higher
    assert r2.json()["source"] == "AI-Agent"
    assert r2.json()["version"] == 2


def test_spl_validation_red_deprecated():
    """Deprecated syntax → RED state."""
    event = make_event("e11", "q7", "eval a=1 | eval b=2", "Analyst", BASE_TS, 1)
    resp = client.post("/queries", json=event)
    assert resp.json()["state"] == "RED"


def test_spl_validation_amber_unknown_index():
    """Unknown index → AMBER state."""
    event = make_event("e12", "q8", "index=unknown_db | stats count", "Analyst", BASE_TS, 1)
    resp = client.post("/queries", json=event)
    assert resp.json()["state"] == "AMBER"


def test_spl_validation_red_depth():
    """Pipe depth > 5 → RED state."""
    deep = "index=main " + "| stats count " * 10
    event = make_event("e13", "q9", deep, "Analyst", BASE_TS, 1)
    resp = client.post("/queries", json=event)
    assert resp.json()["state"] == "RED"


def test_malformed_input_rejected():
    """Missing fields or bad timestamp → 400."""
    bad = {"event_id": "e14", "query_id": "q10"}  # missing required fields
    resp = client.post("/queries", json=bad)
    assert resp.status_code == 400


def test_invalid_source_rejected():
    """Source not Analyst or AI-Agent* → 400."""
    event = make_event("e15", "q11", "index=main | stats count", "Hacker", BASE_TS, 1)
    resp = client.post("/queries", json=event)
    assert resp.status_code == 400


def test_get_query_not_found():
    """GET /queries/{id} for non-existent → 404."""
    resp = client.get("/queries/nonexistent")
    assert resp.status_code == 404


def test_replay_determinism():
    """Replay same events twice → identical output."""
    events = [
        make_event("r1", "qr1", "index=main | stats count", "Analyst", BASE_TS, 1),
        make_event("r2", "qr1", "index=main | stats count", "AI-Agent", BASE_TS + timedelta(minutes=1), 1),
        make_event("r3", "qr2", "index=web | stats count", "Analyst", BASE_TS, 1),
    ]
    resp1 = client.post("/events/replay", json={"events": events})
    resp2 = client.post("/events/replay", json={"events": events})
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json() == resp2.json()


def test_replay_isolation():
    """Replay does NOT affect live engine state."""
    live = make_event("live1", "qlive", "index=main | stats count", "Analyst", BASE_TS, 1)
    client.post("/queries", json=live)

    replay_events = [
        make_event("rp1", "qrp", "index=main | stats count", "AI-Agent", BASE_TS, 99),
    ]
    client.post("/events/replay", json={"events": replay_events})

    # Live engine should still only know qlive
    assert _engine.get_state("qlive") is not None
    assert _engine.get_state("qrp") is None  # replay is isolated!


def test_ai_agent_version_priority():
    """AI-Agent-v3 > AI-Agent-v2 > AI-Agent > Analyst."""
    analyst = make_event("av1", "qav", "index=main | stats count", "Analyst", BASE_TS, 1)
    v1 = make_event("av2", "qav", "index=main | stats count", "AI-Agent", BASE_TS, 1)
    v2 = make_event("av3", "qav", "index=main | stats count", "AI-Agent-v2", BASE_TS, 1)
    v3 = make_event("av4", "qav", "index=main | stats count", "AI-Agent-v3", BASE_TS, 1)

    client.post("/queries", json=analyst)
    client.post("/queries", json=v1)
    client.post("/queries", json=v2)
    resp = client.post("/queries", json=v3)

    assert resp.json()["source"] == "AI-Agent-v3"


def test_replay_with_duplicates():
    """Replay handles duplicate event_ids gracefully."""
    events = [
        make_event("dup1", "qd1", "index=main | stats count", "Analyst", BASE_TS, 1),
        make_event("dup1", "qd1", "index=main | stats count", "Analyst", BASE_TS, 1),  # exact dup
    ]
    resp = client.post("/events/replay", json={"events": events})
    data = resp.json()
    assert data["events_processed"] == 1
    assert data["events_deduped"] == 1


def test_boundary_version_zero():
    """version=0 is valid."""
    event = make_event("bz1", "qbz", "index=main | stats count", "Analyst", BASE_TS, 0)
    resp = client.post("/queries", json=event)
    assert resp.status_code == 200
    assert resp.json()["version"] == 0


def test_boundary_midnight_timestamp():
    """Midnight UTC timestamp is valid."""
    midnight = datetime(2026, 8, 16, 0, 0, 0, tzinfo=timezone.utc)
    event = make_event("mid1", "qmid", "index=main | stats count", "Analyst", midnight, 1)
    resp = client.post("/queries", json=event)
    assert resp.status_code == 200