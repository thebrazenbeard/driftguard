# DriftGuard R6 Controlled Longitudinal Benchmark V0.1

Status: **RESEARCH BENCHMARK CONTRACT / NO DETECTOR ADMISSION / NO RUNTIME EFFECT**

Parent architecture:
`docs/research/DRIFTGUARD_R6_LONGITUDINAL_DRIFT_ARCHITECTURE_V0_1.md`

Methods review:
`docs/research/DRIFTGUARD_R6_MEASUREMENT_METHODS_SOURCE_REVIEW_V0_1.md`

## Purpose

Define a controlled, replayable benchmark that future DriftGuard detector candidates must survive before any method is admitted as a reference implementation.

This benchmark deliberately does **not** choose CUSUM, EWMA, change-point detection, hysteresis, consecutive-breach rules, or another algorithm.

Its job is to make future method comparisons falsifiable.

`BENCHMARK_PASS != ALGORITHM_ADMISSION`

`ALGORITHM_ADMISSION != PRODUCTION_READINESS`

`SYNTHETIC_DETECTION_SUCCESS != REAL_WORLD_VALIDATION`

## Experimental separation

Every benchmark campaign has three distinct stages:

1. **DESIGN**
   - define scenario families, metrics, and reporting rules;
   - no confirmatory outcomes are visible.

2. **CALIBRATION**
   - tune candidate parameters only on declared calibration material;
   - calibration data and method version are frozen.

3. **CONFIRMATORY**
   - run the frozen candidate over held-out benchmark instances;
   - no threshold, parameter, aggregation, missingness, reset, ancestry, or subject-identity rule may change after outcomes are visible.

`CONFIRMATORY_DATA != CALIBRATION_DATA`

`POST_OUTCOME_TUNING != CONFIRMATORY_EVIDENCE`

## Candidate freeze

Before confirmatory execution, a candidate record must bind:

- detector identifier and version;
- implementation/source digest or equivalent immutable subject;
- exact parameter set;
- warning/reload/change-point semantics;
- reset/stopping behavior;
- missing-evidence behavior;
- subject-manifest version;
- evaluator/calibration version;
- provenance/independence policy;
- benchmark-suite version;
- random seed set if randomness exists;
- acceptance criteria, if any.

A result without a pre-existing candidate freeze is exploratory only.

## Required scenario families

### BM-01 — no-drift control

The target and evaluator remain stable.

Purpose:
measure false-alert behavior and verify repeated monitoring does not manufacture a target-drift claim merely through repeated testing.

Expected claim behavior:
`CONTROL_NO_TARGET_DRIFT_CLAIM`.

This does not require a detector to emit no warnings ever; any acceptable false-alert tolerance must be separately precommitted.

### BM-02 — abrupt target drift

The evaluator remains stable while target behavior changes sharply at a known hidden injection point.

Purpose:
measure detection delay and missed-detection behavior without evaluator confounding.

Expected:
`TARGET_DRIFT_DETECTABLE`.

The benchmark knows the injection point; the detector must not receive it as input.

### BM-03 — gradual target drift

The target changes progressively while evaluator/calibration stays fixed.

Purpose:
test whether the detector preserves accumulating evidence rather than requiring one dramatic point breach.

Expected:
`GRADUAL_CHANGE_EVIDENCE_PRESERVED`.

### BM-04 — recurring target drift

The target leaves the baseline regime, returns, then later departs again.

Purpose:
test reset/history semantics and prevent the first recovery from erasing later recurrence.

Expected:
`RECURRING_DRIFT_PATTERN_PRESERVED`.

### BM-05 — evaluator-only drift

The target stays fixed while evaluator version/calibration behavior changes.

Purpose:
detect measurement-instrument change without laundering it into target drift.

Expected:
`EVALUATOR_DRIFT_OR_MEASUREMENT_INVALID`.

`EVALUATOR_CHANGE != TARGET_CHANGE`.

### BM-06 — target drift with stable evaluator

The evaluator remains fixed and calibrated while target behavior changes.

Purpose:
ensure evaluator stability is not treated as evidence the target is stable.

Expected:
`TARGET_DRIFT_NOT_ERASED_BY_EVALUATOR_STABILITY`.

### BM-07 — correlated/shared-root probes

Several probe outputs vary together but share one represented ancestry root or common generation channel.

Purpose:
test provenance-aware evidence accounting.

Expected:
`NO_INDEPENDENCE_ESCALATION`.

Three correlated observations remain three observations, not automatically three independent corroborations.

`SOURCE_COUNT != INDEPENDENT_EVIDENCE_COUNT`.

### BM-08 — missing evidence

One or more required evidence channels disappear while no valid critical evidence resolves the state.

Expected:
`INDETERMINATE_NOT_STABLE`.

Missing data must not silently lower aggregate drift or convert UNKNOWN into STABLE.

### BM-09 — periodic reload without behavioral drift

The operational periodic-reload clock fires while admitted behavioral evidence remains stable.

Expected:
`OPERATIONAL_RELOAD_NOT_BEHAVIORAL_DRIFT`.

This freezes the R5 decision/action separation into longitudinal evaluation.

### BM-10 — baseline successor epoch

An intentional, reviewed baseline successor becomes effective at a known transition.

Expected:
`NEW_BASELINE_EPOCH`.

The detector must not silently splice predecessor and successor baselines into one homogeneous target series.

### BM-11 — subject epoch change

A behaviorally material runtime configuration changes without a baseline rewrite: model/provider version, instruction contract, tool set, memory/retrieval configuration, or another subject-manifest component.

Expected:
`INVALIDATED_SUBJECT_OR_POLICY_CHANGE`.

Same session is insufficient to continue the same longitudinal subject.

### BM-12 — post-hoc policy mutation

A candidate first fails or produces an inconvenient result, then its threshold/parameters/missingness/reset rules are changed using confirmatory outcomes.

Expected:
`INVALID_EXPERIMENT_POST_HOC_POLICY`.

The altered run may become a new exploratory/calibration candidate, but it cannot inherit confirmatory status.

## Required measurements

Every detector-candidate report must preserve, where applicable:

- false alerts on no-drift controls;
- detection delay relative to hidden target injection;
- missed target-drift events;
- evaluator-drift/target-drift confusion;
- UNKNOWN/missing-evidence behavior;
- provenance/independence escalations;
- operational-reload/behavioral-drift conflations;
- subject/baseline epoch invalidations;
- all failed or aborted runs;
- exact candidate freeze identity;
- exact scenario instance identity.

A single aggregate score must never replace per-scenario evidence.

## Invalid benchmark states

The campaign is invalid for confirmatory claims if any of these occur:

- `POST_HOC_POLICY_CHANGE`;
- `CONFIRMATORY_LEAKAGE`;
- `OUTCOME_DROPPED_FROM_REPORT`;
- `EVALUATOR_DRIFT_MISLABELED_TARGET_DRIFT`;
- `MISSING_EVIDENCE_CLASSIFIED_STABLE`;
- `SHARED_ROOT_COUNTED_INDEPENDENT`;
- `BASELINE_MUTATED_TO_ERASE_DRIFT`;
- `SUBJECT_CHANGE_CONTINUED_AS_SAME_SERIES`;
- `PERIODIC_RELOAD_LABELED_BEHAVIORAL_DRIFT`.

These are validity failures, not merely poor performance scores.

## Statistical claim ceiling

This benchmark specifies experimental controls and required reporting, not universal statistical thresholds.

No default false-positive rate, detection-delay target, CUSUM parameter, EWMA smoothing constant, significance threshold, or acceptance score is canonized here.

Any quantitative acceptance criterion must itself be:

- method-specific;
- justified;
- precommitted before confirmatory outcomes;
- versioned with the candidate.

## Reproducibility

Scenario instances should be deterministic where possible and must bind exact:

- scenario ID/version;
- subject epoch;
- baseline/save-state digest;
- evaluator/calibration epoch;
- provenance topology;
- turn sequence;
- injection schedule hidden from the detector;
- evidence-completeness schedule;
- operational reload schedule;
- expected claim class.

If randomness is used, exact seeds are part of the frozen subject.

## Claim ceiling

A benchmark PASS can show only that an exact detector candidate behaved acceptably under the exact precommitted synthetic/replay benchmark and criteria.

It does not establish:

- real-world generalization;
- evaluator honesty;
- provider honesty;
- hidden-state equivalence;
- personal identity continuity;
- permanent recovery;
- external scientific validation;
- production readiness;
- merge or deployment authority.
