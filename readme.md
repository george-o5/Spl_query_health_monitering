
readme_content = '''# 🔍 SPL Query Health Monitor

> **Real-Time SPL Query Health Monitoring with Agentic Conflict Resolution & Immutable Audit-Replay**
>
> Built for **myOnsite Ascend Hackathon 2026** — Deterministic. Auditable. Replayable.

---

## 🎯 What This Is

A production-grade, in-memory event-sourcing engine that ingests Splunk Query Language (SPL) updates from multiple sources, validates them against deterministic rules, resolves conflicts using a strict priority hierarchy, and maintains an **immutable, replayable audit trail** of every decision.

No databases. No message queues. No cloud dependencies. Just pure, deterministic Python.

---

## ✨ Key Features

| Feature | Implementation |
|---------|---------------|
| **🔄 Event Ingestion** | `POST /queries` — strict Pydantic validation, ISO 8601 UTC enforcement |
| **🧠 State Machine** | In-memory deterministic engine with `RED` / `AMBER` / `GREEN` health states |
| **⚔️ Conflict Resolution** | 4-tier hierarchy: `AI-Agent-v{N}` > `AI-Agent` > `Analyst` → version → timestamp → alphabetical |
| **🛡️ Idempotency** | Duplicate `event_id`s are silently deduplicated — zero state corruption |
| **📜 Immutable Audit** | Append-only `audit_log` with full decision trace — no updates, no deletes |
| **🎬 Deterministic Replay** | `POST /events/replay` spins a **fresh isolated engine**, rebuilds identical state every time |
| **🧪 Comprehensive Tests** | 18 pytest cases covering conflicts, late events, duplicates, boundaries, replay parity |

---

## 🏗️ Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  POST /queries  │────▶│   Pydantic   │────▶│  QueryEngine    │
│  (Event Ingest) │     │  Validation  │     │  State Machine  │
└─────────────────┘     └──────────────┘     └─────────────────┘
                                                      │
                       ┌──────────────────────────────┼──────────────┐
                       ▼                              ▼              ▼
              ┌─────────────────┐           ┌─────────────────┐  ┌─────────────┐
              │  ConflictResolver│           │  AuditTrail     │  │  SPL Validator│
              │  (Deterministic) │           │  (Append-Only)  │  │  (Regex-based)│
              └─────────────────┘           └─────────────────┘  └─────────────┘
                       │
                       ▼
              ┌─────────────────┐
              │  GET /queries   │
              │  GET /audit     │
              │  POST /replay   │
              └─────────────────┘
```

### Core Design Principles

1. **Determinism First** — All ordering uses explicit event timestamps. Never `time.now()` for decisions.
2. **Event Sourcing** — Every state transition is an immutable audit record. Full traceability.
3. **Zero Side Effects on Replay** — Replay runs on a completely isolated engine instance. Live state is untouched.
4. **Fail Fast** — Malformed payloads rejected immediately with `400 Bad Request`.

---

## ⚔️ Conflict Resolution Hierarchy

When two events target the same `query_id` with different states, the winner is decided **deterministically**:

```
Step 1: Source Reliability
        AI-Agent-v3 (rank 3) > AI-Agent-v2 (rank 2) > AI-Agent (rank 1) > Analyst (rank 0)

Step 2: Version Priority
        Higher version always wins

Step 3: Temporal Precedence
        Earlier timestamp wins (chronological, not arrival order)

Step 4: Deterministic Tiebreak
        Alphabetical query_id comparison (guarantees total ordering)
```

Every resolution generates an explicit `conflict_resolution_reason` in the audit trail.

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- `pip` or `uv`

### 1. Clone & Setup

```bash
git clone https://github.com/george-o5/Spl_query_health_monitering.git
cd Spl_query_health_monitering

# Create virtual environment
python -m venv venv

# Activate (macOS/Linux)
source venv/bin/activate

# Activate (Windows)
venv\\Scripts\\activate

# Install dependencies
pip install -r requirments.txt
```

### 2. Launch Server

```bash
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

Server starts at `http://localhost:8000`

Interactive docs: `http://localhost:8000/docs`

### 3. Run Tests

```bash
pytest test_system.py -v
```

**Expected:** 18 tests, all passing ✅

---

## 📡 API Reference

### `POST /queries` — Ingest Event

```bash
curl -X POST http://localhost:8000/queries \\
  -H "Content-Type: application/json" \\
  -d '{
    "event_id": "evt-001",
    "query_id": "query-alpha",
    "query_text": "index=main | stats count by host",
    "source": "Analyst",
    "timestamp": "2026-08-16T08:00:00+00:00",
    "version": 1
  }'
```

**Response:**
```json
{
  "query_id": "query-alpha",
  "state": "GREEN",
  "query_text": "index=main | stats count by host",
  "last_updated": "2026-08-16T08:00:00+00:00",
  "source": "Analyst",
  "version": 1,
  "conflict_resolution_reason": null,
  "audit_history": [
    {
      "audit_id": "audit-query-alpha-evt-001-...",
      "event_type": "created",
      "state_before": null,
      "state_after": "GREEN",
      "conflict_resolution_reason": null
    }
  ]
}
```

### `GET /queries/{query_id}` — Get State + Audit

```bash
curl http://localhost:8000/queries/query-alpha
```

### `GET /audit` — Full Audit Trail

```bash
curl http://localhost:8000/audit
```

### `POST /events/replay` — Deterministic Replay

```bash
curl -X POST http://localhost:8000/events/replay \\
  -H "Content-Type: application/json" \\
  -d '{
    "events": [
      {
        "event_id": "r1",
        "query_id": "qr1",
        "query_text": "index=main | stats count",
        "source": "Analyst",
        "timestamp": "2026-08-16T08:00:00+00:00",
        "version": 1
      },
      {
        "event_id": "r2",
        "query_id": "qr1",
        "query_text": "index=main | stats count",
        "source": "AI-Agent",
        "timestamp": "2026-08-16T08:05:00+00:00",
        "version": 1
      }
    ]
  }'
```

**Key behavior:** Returns rebuilt state + audit. **Does NOT affect live engine.**

---

## 🧪 Test Coverage

| Test Category | Count | Cases |
|--------------|-------|-------|
| **Creation & Basic Flow** | 3 | New query, duplicate idempotency, version zero |
| **Conflict Resolution** | 5 | Source priority, version priority, timestamp priority, agent versions, alphabetical tiebreak |
| **SPL Validation** | 3 | Deprecated syntax → RED, unknown index → AMBER, pipe depth → RED |
| **Edge Cases** | 4 | Late events, out-of-order, midnight timestamp, malformed input rejection |
| **Replay & Determinism** | 3 | Replay parity, replay isolation, replay with duplicates |

Run with:
```bash
pytest test_system.py -v --tb=short
```

---

## 📁 Project Structure

```
Spl_query_health_monitering/
├── app.py              # FastAPI application — routes, error handlers
├── engine.py           # Core state machine + conflict resolver
├── schemas.py          # Pydantic models — strict validation, enums
├── audit.py            # Immutable append-only audit trail
├── replay.py           # Isolated replay engine (fresh instance per call)
├── utils.py            # SPL syntax validator + deterministic helpers
├── test_system.py      # 18 pytest cases — correctness, determinism, edge cases
├── fixtures.json       # 8 real-world edge-case scenarios with expected outcomes
├── requirments.txt     # Pinned Python dependencies
└── readme.md           # This file
```

---

## 🔬 SPL Validation Rules

| Rule | Trigger | Result |
|------|---------|--------|
| Deprecated syntax | `eval ... | eval`, `inputcsv`, `outputcsv`, `join type=outer`, unlimited `mvexpand` | `RED` |
| Pipe depth > 5 | More than 5 `|` operators | `RED` |
| Unknown index | `index=` value not in `{main, web, security, firewall, dns, proxy}` | `AMBER` |
| Trivial/empty query | < 3 characters or empty | `RED` |
| Default | None of above | `GREEN` |

---

## 🏆 Hackathon Alignment

| Requirement | Status |
|------------|--------|
| ✅ In-memory event sourcing | `QueryEngine` + `AuditTrail` |
| ✅ Strict input validation | Pydantic schemas with `field_validator` |
| ✅ Deterministic conflict resolution | 4-tier hierarchy, fully documented |
| ✅ Idempotency | `event_id` deduplication in `_seen_events` |
| ✅ Immutable audit trail | Append-only, no update/delete, `GET /audit` |
| ✅ Deterministic replay | `POST /events/replay` with isolated engine |
| ✅ Automated tests | 18 pytest cases |
| ✅ Fixture data | 8 edge cases in `fixtures.json` |
| ✅ README with runbook | This file |

---

## 📝 License

Built for **myOnsite Ascend Hackathon 2026**.

---

> *"Determinism is not a feature. It is the foundation."*
'''

with open('/mnt/agents/output/readme.md', 'w') as f:
    f.write(readme_content)

print("README created successfully!")
print(f"Length: {len(readme_content)} characters")
