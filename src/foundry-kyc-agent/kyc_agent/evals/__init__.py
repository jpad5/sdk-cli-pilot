from __future__ import annotations

import asyncio
import json
import tempfile
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from kyc_core.config import Settings, settings

from .grader import GradeResult, grade

DATASET = Path(__file__).with_name("dataset.jsonl")


def load_dataset(path: Path = DATASET) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


async def run_evals(mode: str | None = None, dataset: Path = DATASET, cfg: Settings | None = None) -> dict[str, Any]:
    from kyc_agent import create_agent

    cfg = cfg or settings()
    if mode:
        cfg = replace(cfg, demo_mode=mode)
    results: list[GradeResult] = []
    replies: list[dict[str, Any]] = []
    # Isolated SAR store/audit so state from earlier demo runs (e.g. an approved SAR) can't skew results.
    with tempfile.TemporaryDirectory(prefix="kyc-evals-") as scratch:
        # Evals must observe the HITL gate, so auto-approval is always off here.
        run_cfg = replace(cfg, sar_auto_approve=False, data_dir=Path(scratch))
        agent = create_agent(run_cfg)
        for case in load_dataset(dataset):
            reply = await agent.run(case["query"], f"eval-{case['id']}", "eval-runner")
            results.append(grade(case, reply))
            replies.append({"id": case["id"], "query": case["query"], "response": reply.text,
                            "tool_calls": reply.tool_calls})
    passed = sum(r.passed for r in results)
    summary = {
        "mode": cfg.demo_mode,
        "agent": cfg.foundry_agent_name,
        "total": len(results),
        "passed": passed,
        "pass_rate": round(passed / len(results), 3) if results else 0.0,
        "mean_score": round(sum(r.score for r in results) / len(results), 3) if results else 0.0,
        "cases": [asdict(r) for r in results],
    }
    return {"summary": summary, "replies": replies}


def run(mode: str | None = None) -> dict[str, Any]:
    return asyncio.run(run_evals(mode))
