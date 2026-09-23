# DriftGuard

**Deterministic regression admission for AI agents.**

Your evaluator tells you how a candidate behaved. DriftGuard answers a different question:

> **Is this behavioral change allowed into production?**

DriftGuard compares candidate evaluation metrics with an accepted baseline under an explicit versioned policy and returns one of four states:

`PASS` · `WARN` · `BLOCK` · `UNKNOWN`

The decision is deterministic and bound to the exact policy, baseline, candidate report, per-metric reasons, and a canonical SHA-256 result digest.

DriftGuard does **not** need your model API key and does not care which evaluator produced the metrics.

## Five-minute Agent CI

Create `driftguard.toml`:

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

Check in an accepted baseline:

```json
{
  "schema": "DRIFTGUARD_CI_REPORT_V1",
  "run_id": "accepted-main",
  "subject": "checkout-agent",
  "metrics": {
    "task_success": 0.95,
    "latency_ms": 1000
  }
}
```

Have your existing eval harness write the candidate report in the same schema, then:

```bash
python -m pip install .
driftguard ci \
  --policy driftguard.toml \
  --baseline driftguard-baseline.json \
  --candidate driftguard-candidate.json \
  --output driftguard-result.json \
  --summary driftguard-summary.md
```

Exit codes:

- `0` — PASS or WARN
- `1` — BLOCK
- `2` — UNKNOWN

Missing evidence is not silently converted into a pass.

See [Agent CI V1](docs/AGENT_CI_V1.md) and the runnable files under [examples/ci](examples/ci).

## GitHub Action

Once your evaluator has produced `driftguard-candidate.json`:

```yaml
- uses: thebrazenbeard/driftguard@main
  id: driftguard
  with:
    policy: driftguard.toml
    baseline: driftguard-baseline.json
    candidate: driftguard-candidate.json
```

DriftGuard writes a Markdown metric table to the Actions job summary and exposes `decision`, `result-digest`, and `trusted-ref` outputs.

By default, pull requests read the policy and accepted baseline from the **base commit**, not from the proposed checkout. A PR therefore cannot weaken its own policy or rewrite its own baseline to make itself pass.

For production use, pin an immutable release tag or commit instead of `main`.

## What makes this different

DriftGuard is intentionally not another prompt runner or LLM judge.

Use whatever generates useful measurements for your system: unit tests, replay harnesses, human labels, Promptfoo, LangSmith, Braintrust, custom graders, production telemetry, or something you wrote yourself.

DriftGuard sits **after** measurement.

Its job is admission governance:

```text
evaluator / benchmark / replay
            |
            v
       candidate metrics
            |
            +---- accepted baseline
            |          |
            v          v
         exact DriftGuard policy
                  |
                  v
       PASS / WARN / BLOCK / UNKNOWN
                  |
                  v
           result digest
```

That separation prevents a convenient evaluator result from automatically becoming deployment authority.

## Baseline ratcheting is deliberately forbidden

V1 does not auto-promote a passing candidate into the next baseline.

Suppose a policy tolerates a 2% regression. Automatically replacing the baseline after every passing run could allow repeated 2% degradations to accumulate while every individual pull request still passes.

Baseline promotion is therefore a separate reviewable effect.

## Behavioral-drift engine

Agent CI is the simple product surface. Under it, DriftGuard also contains a more rigorous behavioral-drift system for long-running agents and model-backed applications.

The integrated research stack includes:

- SHA-256-bound behavioral save-states and restore packets;
- multi-dimensional drift scoring and critical-dimension safeguards;
- calibrated/quorum measurement semantics;
- evaluator provenance and optional HMAC key-possession attestation;
- monitored-subject identity and explicit epochs;
- monotonic SQLite generations and append-only receipts;
- sequential CUSUM diagnostics;
- calibration qualification;
- detector comparison;
- atomic current-subject readback for reload admission;
- strict separation among detection, requested effect, observed effect, acknowledgement, and later behavioral recovery.

The deeper machinery exists for systems where a single PR gate is not enough.

## Core evidence rules

DriftGuard is built around a few deliberately annoying distinctions:

`OBSERVATION != INFERENCE`

`EVALUATOR_OUTPUT != TRUTH`

`PASS != GLOBAL_SUPERIORITY`

`RELOAD_REQUEST != RELOAD_EFFECT`

`TRANSPORT_RECEIPT != PROVIDER_APPLICATION`

`ACKNOWLEDGEMENT != BEHAVIORAL_RECOVERY`

`SOURCE_PASS != DEPLOYMENT_AUTHORITY`

Those distinctions are the product, not documentation decoration.

## Existing behavioral workflow

For stateful behavioral monitoring:

```bash
driftguard state-digest --state examples/save_state.json

driftguard evaluate \
  --state examples/save_state.json \
  --evidence examples/evidence.json \
  --observation examples/observation.txt \
  --db ./driftguard.db \
  --session demo \
  --turn 0 \
  --expected-generation 0
```

A reload decision is only a directive. Provider application and later behavioral recovery remain separately evidenced.

## Architecture

Start here:

- [Agent CI V1](docs/AGENT_CI_V1.md)
- [Architecture V1](docs/ARCHITECTURE_V1.md)
- [Measurement validity](docs/R6_MEASUREMENT_VALIDITY_V1.md)
- [Subject identity and epochs](docs/R7_SUBJECT_IDENTITY_EPOCH_V1.md)
- [Sequential CUSUM](docs/R8_SEQUENTIAL_CUSUM_V1.md)
- [Calibration qualification](docs/R9_CALIBRATION_QUALIFICATION_V1.md)
- [Detector comparison](docs/R10_DETECTOR_COMPARISON_V1.md)
- [External boundary](docs/EXTERNAL_BOUNDARY_V1.md)
- [Evaluator attestation](docs/EVALUATOR_ATTESTATION_V1.md)
- [Hostile review](docs/HOSTILE_REVIEW_V1.md)

R11 governed-benchmark work remains a separate research line until its outstanding study/holdout-governance questions are resolved. It is not required for Agent CI.

## Claim ceiling

A DriftGuard CI PASS means only that the supplied candidate metrics satisfied the exact supplied policy relative to the exact supplied baseline.

It does not prove evaluator correctness, benchmark representativeness, causal drift, global model quality, production safety, or hidden-state equivalence.

That modest claim is intentional. It is reproducible enough to put in CI.
