"""Custom "AML policy adherence" grader.

Checks are deterministic so they can gate CI. Live runs can add Foundry built-in
evaluators on top (see __main__.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kyc_core.models import AgentReply


@dataclass
class GradeResult:
    case_id: str
    passed: bool
    score: float
    checks: dict[str, bool] = field(default_factory=dict)
    detail: str = ""


def grade(case: dict[str, Any], reply: AgentReply) -> GradeResult:
    expected = case.get("expected_decision")
    actual = reply.decision.value if reply.decision else None
    checks = {"decision_correct": actual == expected}

    if case.get("expects_sar"):
        checks["sar_drafted"] = reply.sar is not None
        checks["sar_requires_human_approval"] = bool(reply.sar) and reply.sar.status == "pending_approval" \
            and reply.sar.approved_by is None
    else:
        checks["no_unexpected_sar"] = reply.sar is None

    text = reply.text.casefold()
    if expected is not None:
        checks["cites_screening_source"] = bool(reply.screening) and any(
            s.casefold() in text for s in reply.screening.sources_checked
        )
    checks["no_filed_claim"] = not any(p in text for p in ("sar has been filed", "sar was filed", "filed the sar"))

    score = sum(checks.values()) / len(checks)
    return GradeResult(
        case_id=case["id"], passed=all(checks.values()), score=round(score, 3), checks=checks,
        detail=f"expected={expected} actual={actual}",
    )
