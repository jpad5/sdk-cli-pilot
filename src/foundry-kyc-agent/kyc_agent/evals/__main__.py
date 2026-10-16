from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from kyc_core.config import settings
from kyc_core.governance import AuditLog
from kyc_core.telemetry import init_telemetry

from . import run


def foundry_builtin_evals(replies: list[dict[str, Any]]) -> dict[str, Any]:
    """Optional LLM-judged evaluators from azure-ai-evaluation (live mode only)."""
    try:
        from azure.ai.evaluation import AzureOpenAIModelConfiguration, IntentResolutionEvaluator, TaskAdherenceEvaluator
    except ImportError:
        return {"skipped": "azure-ai-evaluation not installed (pip install -e src/foundry-kyc-agent[live])"}
    import os

    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    if not endpoint:
        return {"skipped": "set AZURE_OPENAI_ENDPOINT (+ judge deployment) to run built-in evaluators"}
    model_config = AzureOpenAIModelConfiguration(
        azure_endpoint=endpoint, azure_deployment=os.environ.get("EVAL_JUDGE_DEPLOYMENT", settings().foundry_model_deployment)
    )
    evaluators = {"intent_resolution": IntentResolutionEvaluator(model_config=model_config),
                  "task_adherence": TaskAdherenceEvaluator(model_config=model_config)}
    scores: dict[str, list[float]] = {k: [] for k in evaluators}
    for r in replies:
        for name, ev in evaluators.items():
            out = ev(query=r["query"], response=r["response"])
            value = next((v for k, v in out.items() if k == name and isinstance(v, (int, float))), None)
            if value is not None:
                scores[name].append(float(value))
    return {k: round(sum(v) / len(v), 2) if v else None for k, v in scores.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m kyc_agent.evals")
    parser.add_argument("--mode", choices=["mock", "live"], default=None)
    parser.add_argument("--threshold", type=float, default=0.8)
    args = parser.parse_args(argv)

    init_telemetry("kyc-agent-evals")
    out = run(args.mode)
    summary = out["summary"]
    if summary["mode"] == "live":
        summary["foundry_builtin"] = foundry_builtin_evals(out["replies"])

    cfg = settings()
    path = cfg.data_dir / "eval-results.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"{'case':<20} {'result':<6} {'score':>5}  detail")
    for c in summary["cases"]:
        failed = [k for k, v in c["checks"].items() if not v]
        print(f"{c['case_id']:<20} {'PASS' if c['passed'] else 'FAIL':<6} {c['score']:>5.2f}  {c['detail']}"
              + (f"  failed={failed}" if failed else ""))
    print(f"\nmode={summary['mode']} pass_rate={summary['pass_rate']:.0%} threshold={args.threshold:.0%} -> {path}")
    if "foundry_builtin" in summary:
        print(f"foundry built-in evaluators: {summary['foundry_builtin']}")

    gate_ok = summary["pass_rate"] >= args.threshold
    AuditLog(cfg=cfg).write("eval_gate", mode=summary["mode"], pass_rate=summary["pass_rate"],
                            threshold=args.threshold, passed=gate_ok)
    return 0 if gate_ok else 1


if __name__ == "__main__":
    sys.exit(main())
