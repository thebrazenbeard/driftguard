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

Baseline and candidate `subject` values must match exactly. A candidate cannot omit the subject when the accepted baseline binds one.

The evaluator that produced the metrics remains responsible for their semantic meaning. DriftGuard does not upgrade evaluator output into independent truth.

## Build a report from shell metrics

You do not have to hand-author the candidate JSON:

```bash
driftguard report \
  --run-id "$GITHUB_SHA" \
  --subject checkout-agent \
  --metric task_success=0.94 \
  --metric latency_ms=1120 \
  --output driftguard-candidate.json
```

Repeated or non-finite metric assignments are rejected.

## Gate the candidate

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

The action writes a compact Markdown table to the GitHub Actions job summary and exposes `decision`, `result-digest`, and `trusted-ref` outputs.

### Trusted baseline and policy

On pull requests and ordinary pushes, the action defaults to `trusted-ref = "auto"`.

- pull request: policy and baseline are read from the PR base commit;
- push: policy and baseline are read from the pre-push commit;
- other/manual contexts: the action falls back to the workspace.

The candidate report is always read from the current workspace.

That means a change cannot weaken its own DriftGuard policy or rewrite its own baseline and then use the rewritten files to pass the same gate.

For first-time bootstrap or an intentionally isolated test, set:

```yaml
trusted-ref: workspace
```

For a controlled deployment, you can instead provide an exact trusted commit SHA.

This mechanism is still bounded by repository/workflow governance. A party able to replace the required workflow or its action reference may be able to bypass the gate, so branch protection remains outside DriftGuard's claim.

For production use, pin the action to a release tag or immutable commit rather than `main`.

## Baseline governance

DriftGuard intentionally does not auto-update the accepted baseline.

A passing candidate does not automatically become the next baseline. That prevents a sequence of individually tolerated regressions from silently ratcheting the accepted baseline downward.

When a candidate has an exact `PASS`, you can prepare a proposed next baseline:

```bash
driftguard prepare-baseline \
  --policy driftguard.toml \
  --baseline driftguard-baseline.json \
  --candidate driftguard-candidate.json \
  --output driftguard-baseline.next.json
```

The command:
- recomputes the gate from the exact inputs;
- refuses BLOCK, WARN, and UNKNOWN;
- refuses to overwrite the accepted baseline in place;
- writes the proposed baseline atomically;
- reads it back and verifies the candidate digest;
- writes a `.promotion.json` receipt by default.

The repository change that replaces the accepted baseline remains a separate reviewable effect.

## Claim ceiling

A DriftGuard CI PASS means:

> the supplied candidate metrics satisfy the exact supplied policy relative to the exact supplied baseline.

It does not prove:
- the evaluator is correct;
- the benchmark represents production;
- the candidate is globally better;
- a metric change was caused by the code change;
- production behavior will remain stable.
