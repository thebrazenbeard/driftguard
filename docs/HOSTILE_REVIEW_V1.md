# DriftGuard V1 Hostile Review

This document records the adversarial design pass used before implementation. The point is to make the drift detector difficult to fool, including by the model being monitored.

## Architect lane
Problem: "behavioral save-state" is underspecified. A giant prompt blob becomes an untestable identity charm.
Repair: use an immutable version, exact restore text, explicit behavioral dimensions, policy, governed probe sources, and a canonical digest.

## Rezon / epistemic lane
Problem: the monitored model can simply report that it still follows the baseline. A judge sharing the same contaminated context can fail the same way. Source labels without exact version binding are provenance theater.
Repair: every dimension declares a minimum independence level; self evidence cannot satisfy an independent dimension. Evidence carries non-empty source/version bindings and a unique execution identity. Unknown or ungoverned provenance fails closed.
Remaining weakness: V1 structurally records independence but does not cryptographically prove it. A dishonest caller can forge JSON. That is an explicit claim ceiling.

## Project Runner / orchestration lane
Problem: concurrent evaluators race; process restart restores old counters; retries can duplicate restoration; the baseline can change during monitoring.
Repair: SQLite session state uses monotonic generations and compare-and-swap, monotonic turn indexes, state-digest pinning, and append-only evaluation receipts. V1 records reload decisions only; it does not claim provider-side reload completion.
Future: if DriftGuard gains a provider actuator, add a durable execution journal with ADMITTED -> EFFECT_RECORDED -> VERIFIED plus reconciliation of ambiguous effects before retry.

## Skeptic lane
Problem: style drift is not behavioral drift. Perfect stylistic mimicry can hide changed truthfulness or authority behavior.
Repair: dimensions are explicit and weighted independently. Style can be low weight; truthfulness, authority, safety, or other invariant dimensions can be critical.

## Benchmark-overfit lane
Problem: fixed probes become a test the model learns to ace while drifting elsewhere.
Repair: probe source/version is externalized and versioned so deployments can rotate probe families, use hidden holdouts, and compare multiple evaluators. Evidence IDs and execution IDs must be unique.

## Prompt-injection lane
Problem: monitored conversation text can tell an evaluator to ignore the baseline or report a low score.
Repair: the V1 engine never executes monitored text. It consumes scored evidence as data. Probe implementations must preserve observation/instruction separation.

## Poisoning lane
Problem: slow drift gets written back into the save-state until the new behavior becomes normal.
Repair: no automatic baseline learning. Save-state digest is pinned for a session. Intentional evolution requires an explicit new version.

## Oscillation lane
Problem: noisy scores around a threshold repeatedly reload the state and make the monitor a source of instability.
Repair: warning and reload thresholds are separate and cooldown suppresses non-critical repeat reloads. Critical dimensions can bypass cooldown.

## Missing-evidence lane
Problem: averaging only dimensions that reported can hide failure of the hardest probe.
Repair: every declared dimension requires exactly one admissible evidence item in V1. Missing, duplicate, insufficiently independent, or ungoverned evidence yields UNKNOWN.

## Aggregation lane
Problem: one severe failure disappears inside an average.
Repair: critical dimensions have their own reload threshold independent of the weighted aggregate.

## Distribution-shift lane
Problem: task/context changes look like personality drift.
Repair: dimensions should describe invariants, not preferred answer content. Context-specific profiles should be separate save-state versions.

## Monitor-drift lane
Problem: if the same model both acts and judges, detector and target can drift together.
Repair: dimensions can require SEPARATE_CONTEXT or EXTERNAL evidence. High-stakes dimensions should use a distinct evaluator/provider or deterministic check.

## Restore-effect lane
Problem: generating a restore prompt is mistaken for actually restoring behavior.
Repair: RELOAD means only that deterministic policy requires a digest-bound restore packet. A post-reload evaluation is required to establish behavioral effect.

## Security/privacy lane
Problem: storing entire conversations creates an unnecessary private-data reservoir.
Repair: the durable ledger stores decision/evidence digests and scores, not raw conversation text or restore text.

## Final V1 claim ceiling
DriftGuard V1 is a deterministic behavioral-drift admission and decision engine with durable session fencing. It is not proof of personal identity, consciousness, hidden-state continuity, evaluator honesty, or successful provider-side restoration.
