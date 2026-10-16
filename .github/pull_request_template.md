## Summary

<!-- What changed and why? Link the issue / lab. -->

## Agent change checklist

- [ ] **Evals run** — `python -m kyc_agent.evals --mode mock --threshold 0.8` passes locally (and `--mode live` if prompts/tools/model changed). Eval-gate comment on this PR is green.
- [ ] **Tool allow-list impact** — no change to `KYC_ALLOWED_TOOLS` / MCP tool surface, **or** the new/changed tools are listed here with justification:
- [ ] **Data classification** — no new data fields, sources, or logging of customer PII; synthetic data only in tests/mocks. Classification of any new data:
- [ ] **HITL unaffected** — SARs still require human approval (`SAR_AUTO_APPROVE=false`); no path files or submits a SAR without a named approver.
- [ ] Audit events (`.data/audit.jsonl`) still emitted for decisions, tool calls and approvals.
- [ ] Infra / permissions changes (if any) follow least privilege and were reviewed by CODEOWNERS.

## Test evidence

<!-- Paste eval summary / test output. -->
