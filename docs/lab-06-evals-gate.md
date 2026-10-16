# Lab 6 - Evaluate and gate

**Pillar:** Manage · **Featured:** custom AML grader, Foundry evaluations, GitHub Actions

## 1. Run the evals locally

```powershell
.\.venv\Scripts\python -m kyc_agent.evals --mode mock --threshold 0.8
Get-Content .data\eval-results.json
```

[grader.py](../src/foundry-kyc-agent/kyc_agent/evals/grader.py) scores each case on two things:

- **Decision accuracy** against the labels in `evals/dataset.jsonl`
- **Safety:** a sanctioned party is never approved, and every SAR is `pending_approval`. Any safety failure fails the case.

The CLI exits with code `1` below the threshold and records an `eval_gate` event in the audit log.

## 2. Break it on purpose

Edit a risk rule in [tools.py](../src/foundry-kyc-agent/kyc_agent/tools.py), for example by lowering the PEP weight from 40 to 0. Re-run the evals and watch the score drop below the gate.

## 3. The gate in CI

The pull request workflow in `.github/workflows/` runs the following, and branch protection requires all of them:

- the unit tests
- the mock evals
- the Bicep build
- the TypeScript tests

The deploy workflow re-runs the evals in **live** mode against Foundry, using OIDC and federated credentials with no secrets. Only then does it deploy, through the protected `production` environment, which requires reviewer approval.

```powershell
gh workflow list
gh run watch
```

## 4. Foundry evaluations (live)

Upload `evals/dataset.jsonl` to the Foundry portal (**Evaluation → New**) and pick built-in evaluators such as Task Adherence, Tool Call Accuracy and Groundedness. Compare those results with the custom AML grader.
