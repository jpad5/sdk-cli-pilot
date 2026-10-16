from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    PROHIBITED = "prohibited"


class CustomerProfile(BaseModel):
    customer_id: str
    full_name: str
    dob: str | None = None
    country: str
    occupation: str | None = None
    customer_type: Literal["individual", "entity"] = "individual"
    expected_monthly_volume_usd: float = 0
    source_of_funds: str | None = None


class ScreeningHit(BaseModel):
    matched_name: str
    list_name: str
    match_type: Literal["exact", "alias", "fuzzy"]
    score: float = Field(ge=0, le=1)
    hit_type: Literal["sanction", "pep", "adverse_media"]
    country: str | None = None


class ScreeningResult(BaseModel):
    query_name: str
    hits: list[ScreeningHit] = []
    sources_checked: list[str] = []
    screened_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def has_sanction_hit(self) -> bool:
        return any(h.hit_type == "sanction" and h.score >= 0.85 for h in self.hits)

    @property
    def has_pep_hit(self) -> bool:
        return any(h.hit_type == "pep" and h.score >= 0.85 for h in self.hits)


class RiskAssessment(BaseModel):
    customer_id: str
    score: int = Field(ge=0, le=100)
    level: RiskLevel
    factors: list[str] = []


class KycDecision(str, Enum):
    APPROVE = "approve"
    ENHANCED_DUE_DILIGENCE = "enhanced_due_diligence"
    ESCALATE_SAR = "escalate_sar"
    REJECT = "reject"


class SarDraft(BaseModel):
    sar_id: str
    customer_id: str
    summary: str
    indicators: list[str]
    status: Literal["draft", "pending_approval", "approved", "rejected"] = "draft"
    approved_by: str | None = None


class AgentReply(BaseModel):
    text: str
    decision: KycDecision | None = None
    risk: RiskAssessment | None = None
    screening: ScreeningResult | None = None
    sar: SarDraft | None = None
    tool_calls: list[str] = []
    trace_id: str | None = None
