# DriftGuard R6 Measurement Validity V1

Status: candidate strict measurement contract. Legacy R5 behavior remains supported.

## Problem

R5 has strong provenance and effect-fencing semantics, but its default decision engine treats evaluator-produced values in `[0,1]` as directly comparable measurements and combines different behavioral dimensions with a weighted arithmetic mean.

That is safe only if the score scales are calibrated and commensurable. A source/version label or an `EXTERNAL` independence ordinal does not establish either fact.

R6 therefore separates three identities:

`BEHAVIOR_SPEC != MEASUREMENT_SPEC != DETECTION_POLICY != CONTROL_POLICY`

Changing an evaluator or calibration must not silently mean the desired behavior changed. Changing an alert threshold must not silently mean the measurement instrument changed.

## Strict mode

`MeasurementMode.CALIBRATED_QUORUM` is opt-in. The legacy mode remains the default so historical R5 save-state digests and receipts are not silently invalidated.

Strict mode requires every measured dimension to declare:

- an explicit score scale;
- a calibration-derived maximum tolerated source spread;
- an explicit warning threshold;
- an explicit reload threshold;
- an explicit critical threshold when the dimension is critical;
- a minimum source quorum;
- a minimum distinct correlation-group quorum.

Every eligible probe source must declare:

- exact source ref/version;
- an exact calibration ref/version plus immutable calibration-artifact SHA-256 digest;
- a correlation group;
- the score scale it emits;
- its existing maximum independence ceiling and dimension scope.

A score is admitted only when source scope, observation/state/turn binding, independence, calibration metadata/digest, score scale, source uniqueness, source quorum, correlation-group quorum, and frozen disagreement tolerance all satisfy the save-state.

Measurement-triggered critical reloads do not bypass the declared source/correlation quorum. Once the dimension quorum is satisfied, a critical member breach remains a conservative fail-safe.

## No cross-dimension arithmetic

Strict mode does not compute an aggregate drift score and rejects legacy dimension weights rather than retaining an inert weighting knob.

Each dimension is evaluated on its own governed calibrated scale and against its own frozen thresholds. Multiple admitted sources for one dimension are combined by a deterministic median after quorum admission.

This removes the unsupported assumption that, for example, `0.4` truthfulness drift and `0.4` style drift are cardinally interchangeable.

The median is not a truth oracle. It is a bounded deterministic estimator over already-admitted measurements. If admitted calibrated sources disagree beyond the frozen per-dimension spread tolerance, strict behavior is epistemically `UNKNOWN` rather than allowing the median to wash the disagreement away.

## Independence semantics

`EXTERNAL` remains only a source capability/structural ceiling.

Actual corroboration is now represented separately by:

- distinct source bindings;
- distinct execution IDs;
- explicit correlation groups;
- per-dimension source quorum;
- per-dimension correlation-group quorum.

Two probes with the same ancestry/correlation group cannot satisfy a two-group requirement merely because they have different names. A flat correlation group is still only governed provenance metadata, not proof of statistical independence.

`DIFFERENT_SOURCE_ID != INDEPENDENT_EVIDENCE`

## Split digests

Strict save-states expose:

- `behavior_digest` — the measured behavioral dimension contract only;
- `measurement_digest` — measurement mode, source/calibration/correlation contracts, score scales, and quorum requirements;
- `detection_policy_digest` — criticality, per-dimension thresholds, and scheduling/cooldown policy;
- `control_policy_digest` — the restore/control text used when an intervention is requested.

The full save-state digest still binds all four for session pinning. Changing restore wording therefore changes the control/full-state identity without pretending that the measured behavior itself changed.

External evaluator request V2 binds all three split digests in addition to the full state, observation, turn, generation, and probe contract.

## Durable longitudinal evidence

Strict evaluation receipts persist both the calibrated per-dimension scores and the admitted per-source score/provenance trace. The raw trace is digest-bound into the Evaluation and stored in the durable ledger.

This prevents a future sequential detector from receiving only a final label or an irreversible evidence hash. Evaluator disagreement remains inspectable after the original call.

## Typed behavioral disposition

Strict evaluations persist a typed `behavioral_decision` separately from the operational `decision`.

This matters when periodic reload scheduling says `RELOAD` while observed behavior is still `STABLE`. Strict recovery classification consumes the typed field rather than parsing human-readable reason strings or requiring a cross-dimension aggregate.

Historical receipts without that field retain the bounded legacy classifier.

## Compatibility

Legacy `LEGACY_WEIGHTED` mode remains the default.

When all new optional fields remain at legacy defaults, canonical V1 save-state serialization is unchanged. This is deliberate: adding a safer measurement mode must not rewrite old evidence into a new subject.

## Claim ceiling

This candidate improves measurement admission and semantic separation. It does not establish:

- that a referenced calibration artifact is scientifically valid merely because its exact digest is bound;
- cryptographic evaluator identity or provider honesty;
- statistical independence merely from declared correlation metadata;
- exact monitored-runtime/model/instruction/tool/memory identity over time;
- sequential change-point validity or false-alarm guarantees;
- evaluator-drift detection;
- context-rot diagnosis;
- provider-side restore application;
- causal behavioral recovery;
- a closed-loop behavioral controller.

Those remain separate subjects.

## Next architectural gates

The next high-value gates are:

1. exact monitored-subject manifest and epoching;
2. executable calibration artifact/schema plus frozen challenge-set qualification;
3. provenance ancestry richer than a flat correlation-group label;
4. precommitted sequential/change-point detection over the admitted per-dimension series;
5. context-exposure telemetry to distinguish subject drift from context degradation;
6. governed baseline evolution;
7. only then, experimental closed-loop corrective control.

Do not collapse any of those into this branch's qualification.
