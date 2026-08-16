from datetime import datetime
from enum import Enum
from typing import Optional, List, Literal
from pydantic import BaseModel, Field, field_validator


class SourceType(str, Enum):
    AI_AGENT = "AI-Agent"
    ANALYST = "Analyst"


class QueryState(str, Enum):
    RED = "RED"
    AMBER = "AMBER"
    GREEN = "GREEN"


class EventType(str, Enum):
    CREATED = "created"
    UPDATED = "updated"
    RESOLVED = "resolved"


# ── Input Models ──────────────────────────────────────────────

class QueryEvent(BaseModel):
    event_id: str = Field(..., min_length=1, description="Unique event identifier")
    query_id: str = Field(..., min_length=1)
    query_text: str = Field(..., min_length=1)
    source: str = Field(..., description="e.g. 'AI-Agent' or 'Analyst'")
    timestamp: datetime = Field(..., description="ISO 8601 UTC")
    version: int = Field(..., ge=0)

    @field_validator("source")
    @classmethod
    def validate_source(cls, v: str) -> str:
        # Allow AI-Agent with optional suffix (v2, v3, etc.) and Analyst
        if v == "Analyst" or v.startswith("AI-Agent"):
            return v
        raise ValueError(f"Invalid source: {v}. Must be 'Analyst' or 'AI-Agent*'")

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("Timestamp must be timezone-aware (UTC)")
        return v


class ReplayRequest(BaseModel):
    events: List[QueryEvent]


# ── Internal / Output Models ──────────────────────────────────

class AuditRecord(BaseModel):
    audit_id: str
    query_id: str
    event_type: EventType
    event_id: str
    state_before: Optional[QueryState]
    state_after: QueryState
    conflict_resolution_reason: Optional[str] = None
    timestamp: datetime
    source: str
    version: int


class QueryStateSnapshot(BaseModel):
    query_id: str
    state: QueryState
    query_text: str
    last_updated: datetime
    source: str
    version: int
    conflict_resolution_reason: Optional[str] = None
    audit_history: List[str] = Field(default_factory=list)  # list of audit_ids


class QueryResponse(BaseModel):
    query_id: str
    state: QueryState
    query_text: str
    last_updated: datetime
    source: str
    version: int
    conflict_resolution_reason: Optional[str] = None
    audit_history: List[AuditRecord] = Field(default_factory=list)