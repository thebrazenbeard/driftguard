# Agent CI V1

DriftGuard Agent CI is deliberately **evaluator-agnostic**.

It does not call an LLM provider and it does not decide whether a response is "good" by itself. Your existing evaluator, benchmark, test harness, or production replay produces metrics. DriftGuard decides whether the candidate metrics are admissible relative to an accepted baseline under an exact versioned policy.

That separation is intentional:

```text
your eval harness
      |
      v
candidate metrics
      |
      +------ accepted baseline
      |              |
      v              v
        DriftGuard policy
               |
               v
       PASS / WARN / BLOCK / UNKNOWN
               |
               v
       canonical result digest
```

## Why this exists

Most eval systems are good at producing scores. CI still needs answers to different questions:

- Which regressions are allowed?
- Which dimensions are hard gates?
- What happens when evidence is missing?
- Was the baseline for the same subject?
- Can the exact admission decision be reproduced later?
- Can a flaky or unavailable evaluator silently turn into a pass?

DriftGuard treats those as first-class policy questions.

## Policy

`driftguard.toml`:

```toml
schema = "DRIFTGUARD_CI_POLICY_V1"
policy_id = "agent-quality-v1"
unknown = "block"

[[metric]]
name = "task_success"
direction = "higher"
max_regression = 0.03
min_candidate = 0.90
severity = "block"

[[metric]]
name = "latency_ms"
direction = "lower"
max_regression = 250
max_candidate = 2500
severity = "warn"
```

`direction = "higher"` means decreases are regressions.  
`direction = "lower"` means increases are regressions.

`max_regression` is an absolute metric-unit budget, not a relative percentage.

A metric with `severity = "block"` fails the gate when its regression budget or candidate bound is violated. A warning metric produces `WARN` and exit code 0.

Missing required evidence produces `UNKNOWN`. With `unknown = "block"` (the default), UNKNOWN returns exit code 2.

## Metric report

Both baseline and candidate use the same minimal schema:

```json
{
  "schema": "DRIFTGUARD_CI_REPORT_V1",
  "run_id": "pull-request-123",
  "subject": "checkout-agent",
  "metrics": {
    "task_success": 0.94,
    "latency_ms": 1120
  }
}
```

If both reports specify `subject`, the subjects must match exactly.

The evaluator that produced the metrics remains responsible for their semantic meaning. DriftGuard does not upgrade evaluator output into independent truth.

## CLI

```bash
driftguard ci \
  --policy driftguard.toml \
  --baseline driftguard-baseline.json \
  --candidate driftguard-candidate.json \
  --output driftguard-result.json \
  --summary driftguard-summary.md
```

Exit codes:

- `0`: PASS or WARN
- `1`: BLOCK
- `2`: UNKNOWN

The result binds the exact canonical policy, baseline, candidate, per-metric disposition, and claim ceiling with a SHA-256 result digest.

## GitHub Action

Generate the candidate report with whatever evaluator you already use, then:

```yaml
- uses: thebrazenbeard/driftguard@main
  with:
    policy: driftguard.toml
    baseline: driftguard-baseline.json
    candidate: driftguard-candidate.json
```

The action writes a compact Markdown table to the GitHub Actions job summary and exposes `decision` and `result-digest` outputs.

For production use, pin the action to a release tag or immutable commit rather than `main`.

## Baseline governance

V1 intentionally does not auto-update the baseline.

A passing candidate does not automatically become the next baseline. Baseline promotion is a separate effect and should be reviewable.

That prevents a sequence of individually tolerated regressions from silently ratcheting the accepted baseline downward.

## Claim ceiling

A DriftGuard CI PASS means:

> the supplied candidate metrics satisfy the exact supplied policy relative to the exact supplied baseline.

It does not prove:
- the evaluator is correct;
- the benchmark represents production;
- the candidate is globally better;
- a metric change was caused by the code change;
- production behavior will remain stable.
