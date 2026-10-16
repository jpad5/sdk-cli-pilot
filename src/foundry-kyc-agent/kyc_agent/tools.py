"""Governed KYC tools. Every call passes the allow-list, is audited and traced."""

from __future__ import annotations

import functools
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, TypeVar

from kyc_core.config import Settings, settings
from kyc_core.governance import AuditLog, ToolPolicy, require_approval
from kyc_core.models import (
    CustomerProfile,
    KycDecision,
    RiskAssessment,
    RiskLevel,
    SarDraft,
    ScreeningResult,
)
from kyc_core.telemetry import span

F = TypeVar("F", bound=Callable[..., Any])

HIGH_RISK_COUNTRIES = frozenset({"IR", "KP", "SY", "RU", "BY", "VG", "MM", "AF", "CU", "VE"})
SUSPICIOUS_TERMS = {
    "cash-intensive business": ("cash",),
    "opaque ownership / shell indicators": ("shell", "opaque", "nominee", "no employees"),
    "unexplained source of funds": ("unexplained", "third-party transfers"),
}


def governed(tool_name: str) -> Callable[[F], F]:
    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, cfg: Settings | None = None, **kwargs: Any) -> Any:
            cfg = cfg or settings()
            ToolPolicy(cfg=cfg).check(tool_name)
            with span(f"tool.{tool_name}", **{"gen_ai.tool.name": tool_name, "kyc.mode": cfg.demo_mode}):
                result = fn(*args, **kwargs)
            AuditLog(cfg=cfg).write("tool_call", tool=tool_name)
            return result

        return wrapper  # type: ignore[return-value]

    return decorator


@governed("lookup_customer")
def lookup_customer(customer_id_or_name: str) -> CustomerProfile | None:
    from kyc_sanctions.customers import lookup_customer as _lookup

    return _lookup(customer_id_or_name)


@governed("screen_name")
def screen_name(name: str, dob: str | None = None, country: str | None = None) -> ScreeningResult:
    from kyc_sanctions.screening import screen

    return screen(name, dob=dob, country=country)


def suspicious_indicators(profile: CustomerProfile) -> list[str]:
    text = f"{profile.occupation or ''} {profile.source_of_funds or ''}".casefold()
    return [label for label, terms in SUSPICIOUS_TERMS.items() if any(t in text for t in terms)]


@governed("risk_score")
def risk_score(profile: CustomerProfile, screening: ScreeningResult) -> RiskAssessment:
    """Transparent, rule-based score so analysts and auditors can explain every point."""
    if screening.has_sanction_hit:
        hit = next(h for h in screening.hits if h.hit_type == "sanction")
        return RiskAssessment(
            customer_id=profile.customer_id, score=100, level=RiskLevel.PROHIBITED,
            factors=[f"sanctions match: {hit.matched_name} on {hit.list_name} ({hit.match_type}, {hit.score:.2f})"],
        )
    score, factors = 0, []
    if screening.has_pep_hit:
        score += 40
        factors.append("politically exposed person (+40)")
    if any(h.hit_type == "adverse_media" and h.score >= 0.85 for h in screening.hits):
        score += 25
        factors.append("adverse media (+25)")
    if profile.country.upper() in HIGH_RISK_COUNTRIES:
        score += 30
        factors.append(f"high-risk jurisdiction {profile.country} (+30)")
    if profile.expected_monthly_volume_usd > 50_000:
        score += 20
        factors.append(f"expected monthly volume ${profile.expected_monthly_volume_usd:,.0f} (+20)")
    if profile.customer_type == "entity" and not profile.source_of_funds:
        score += 15
        factors.append("entity without declared source of funds (+15)")
    for indicator in suspicious_indicators(profile):
        score += 20
        factors.append(f"{indicator} (+20)")
    score = min(score, 99)
    level = RiskLevel.LOW if score < 30 else RiskLevel.MEDIUM if score < 60 else RiskLevel.HIGH
    return RiskAssessment(customer_id=profile.customer_id, score=score, level=level, factors=factors)


def decide(profile: CustomerProfile, screening: ScreeningResult, risk: RiskAssessment) -> KycDecision:
    if risk.level == RiskLevel.PROHIBITED:
        return KycDecision.REJECT
    if risk.level == RiskLevel.HIGH and suspicious_indicators(profile):
        return KycDecision.ESCALATE_SAR
    if risk.level in (RiskLevel.HIGH, RiskLevel.MEDIUM) or screening.has_pep_hit:
        return KycDecision.ENHANCED_DUE_DILIGENCE
    return KycDecision.APPROVE


@governed("draft_sar")
def draft_sar(profile: CustomerProfile, screening: ScreeningResult, risk: RiskAssessment) -> SarDraft:
    sar_id = "SAR-" + hashlib.sha256(f"{profile.customer_id}|{risk.score}".encode()).hexdigest()[:8].upper()
    indicators = list(risk.factors) + [f"screening hit: {h.matched_name} ({h.list_name})" for h in screening.hits[:3]]
    summary = (
        f"Synthetic SAR draft for {profile.full_name} ({profile.customer_id}, {profile.country}). "
        f"Risk {risk.score}/100 ({risk.level.value}). Sources checked: {', '.join(screening.sources_checked) or 'none'}."
    )
    return SarDraft(sar_id=sar_id, customer_id=profile.customer_id, summary=summary, indicators=indicators)


class SarStore:
    """Tiny JSON store so a SAR can be approved in a later turn (human-in-the-loop)."""

    def __init__(self, cfg: Settings | None = None):
        cfg = cfg or settings()
        self.path: Path = cfg.data_dir / "sars.json"

    def _load(self) -> dict[str, dict[str, Any]]:
        return json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

    def save(self, sar: SarDraft) -> None:
        data = self._load()
        data[sar.sar_id] = sar.model_dump()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def get(self, sar_id: str) -> SarDraft | None:
        raw = self._load().get(sar_id.upper())
        return SarDraft.model_validate(raw) if raw else None


def submit_sar(sar: SarDraft, cfg: Settings | None = None) -> SarDraft:
    """Route a drafted SAR through the HITL gate and persist it."""
    cfg = cfg or settings()
    existing = SarStore(cfg).get(sar.sar_id)
    if existing and existing.status in ("approved", "rejected"):
        return existing
    sar = require_approval(sar, cfg=cfg)
    SarStore(cfg).save(sar)
    return sar


def approve_sar(sar_id: str, approver: str, cfg: Settings | None = None) -> SarDraft | None:
    cfg = cfg or settings()
    store = SarStore(cfg)
    sar = store.get(sar_id)
    if sar is None:
        return None
    sar = require_approval(sar, approver=approver, cfg=cfg)
    store.save(sar)
    return sar
