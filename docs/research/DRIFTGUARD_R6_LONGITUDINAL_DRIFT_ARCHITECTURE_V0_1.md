# DriftGuard R6 Longitudinal Drift Architecture V0.1

Status: **RESEARCH PROPOSAL / NOT IMPLEMENTED / NO RUNTIME EFFECT**

Source issue: #13 — R6 architecture frontier: trustworthy longitudinal drift measurement

Research base: reviewed R4 exact head `e815c75ffccf469d9d1c09d58c0050798c8e4f53`.

## Purpose

R4 provides deterministic evidence admission, drift decisions, reload scheduling, acknowledgement, raw-byte observation binding, and a durable ledger. R5 is separately hardening native post-reload behavioral verification and the external evaluator/actuator boundary.

Longitudinal monitoring adds a different class of failure: a system may execute every local rule correctly and still make invalid drift claims because the measured subject changed, the evaluator changed scale, several probes share one source lineage, thresholds were selected after seeing outcomes, repeated monitoring inflated false-alert risk, or the target silently rewrote its own baseline.

R6 therefore treats **measurement governance** as a first-class architecture layer.

## Epistemic boundaries

`BEHAVIORAL_SIMILARITY != HIDDEN_STATE_EQUIVALENCE`

`RUNTIME_SUBJECT_BINDING != PERSON_IDENTITY`

`SESSION_CONTINUITY != SUBJECT_CONTINUITY`

`CALIBRATED_SCORE != GROUND_TRUTH`

`DIFFERENT_EVALUATORS != INDEPENDENT_EVIDENCE`

`SOURCE_COUNT != INDEPENDENT_EVIDENCE_COUNT`

`REPEATED_MEASUREMENT != INDEPENDENT_REPLICATION`

`PROBE_VERSION_CHANGE != TARGET_DRIFT`

`EVALUATOR_DRIFT != TARGET_DRIFT`

`MISSING_EVIDENCE != STABLE`

`THRESHOLD_BREACH != PROVEN_CHANGE_POINT`

`POST_HOC_THRESHOLD != PRECOMMITTED_DETECTION_POLICY`

`OBSERVED_DRIFT != AUTHORITY_TO_CHANGE_BASELINE`

`BASELINE_CHANGE != RECOVERY`

`FIRST_STABLE_REPLAY != SUSTAINED_RECOVERY`

`PAST_STABLE_WINDOW != CURRENT_STABILITY`

`SUSTAINED_RECOVERY != PERMANENT_RECOVERY`

`ACKNOWLEDGEMENT != PROVIDER_EFFECT_PROOF`

`PROVIDER_RECEIPT != EFFECT_TRUTH_WITHOUT_VERIFIED_READBACK`

`POLICY_SELECTED_AFTER_OUTCOME != PRECOMMITTED_POLICY`

`TAMPER_EVIDENT != TAMPER_IMPOSSIBLE`

## R6A — monitored-subject identity

Drift is always drift **of a bounded subject**. A longitudinal series therefore needs a behavioral subject manifest separate from session identity and separate from personhood.

A subject manifest should bind, directly or through privacy-preserving digests/pointers where necessary:

- stable subject identifier and subject epoch;
- governed save-state digest;
- runtime/model/provider family and version where observable;
- instruction/system-contract identity;
- capability/tool-set identity;
- retrieval/memory configuration identity when behaviorally material;
- inference/decoding configuration when behaviorally material;
- evaluation harness version;
- detection-policy version.

Material changes open a new subject epoch. Examples include a provider model-version change, materially different instructions, tool additions/removals, retrieval or memory-mode changes, or a newly promoted governed baseline.

A matching manifest demonstrates only bounded configuration continuity. It does not prove hidden-state or personal identity.

## R6B — evaluator and probe calibration

A drift score has meaning only inside the measurement contract that produced it. A nominal `0.4` from evaluator A is not assumed equivalent to `0.4` from evaluator B or a later version of A.

A calibration record should bind:

- evaluator/probe source and exact version;
- dimension scope;
- frozen calibration/challenge-set identity;
- calibration method and any score transform;
- expected ordering/range behavior;
- limitations and uncertainty;
- calibration epoch;
- expiration/recalibration conditions;
- provenance/root-family metadata.

Missing or expired calibration yields UNKNOWN for claims that require calibrated comparability. Evaluator upgrades open a new calibration epoch. Target outcomes must not be used post hoc to tune the calibration that judges those same outcomes. Evaluator disagreement remains evidence to preserve, not something to average away automatically.

Calibration demonstrates measurement behavior on a calibration set, not evaluator honesty or objective ground truth.

## R6C — provenance-aware independence

Ordinal independence labels are useful ceilings but cannot by themselves prove independent corroboration. Different probes can share a model family, provider, copied source, training corpus, generated intermediate artifact, or hidden retrieval root.

R6 should support at least:

- `INDEPENDENT_WITHIN_DECLARED_SCOPE`;
- `PARTIALLY_SHARED_ANCESTRY`;
- `SHARED_ROOT_ANCESTRY`;
- `COMMON_GENERATION_CHANNEL`;
- `ANCESTRY_UNKNOWN`.

Unknown ancestry must not be promoted to independent. Different agent instances do not automatically count as independent evidence. Copied descendants do not create new corroborating roots.

This is a mechanism-level contract and does not require runtime coupling to another repository.

## R6D — precommitted sequential detection

Continuous monitoring is not the same statistical problem as one isolated measurement. Repeatedly probing many dimensions until one threshold crosses can create false alerts even if each individual threshold looks reasonable.

Before adopting a sophisticated detector, DriftGuard needs a versioned detection policy fixed **before** the observations it classifies.

The policy should bind:

- included dimensions and probes;
- aggregation method;
- missing-evidence rule;
- warning/reload/change-point rule;
- hysteresis/debounce/consecutive-breach semantics;
- sequential/statistical method if one is used;
- reset/stopping conditions;
- effective subject and calibration epochs;
- policy digest.

Candidate future methods can include deterministic hysteresis, consecutive-breach rules, EWMA/CUSUM-like accumulation, or bounded change-point methods. The architecture requirement comes first: raw admitted observations remain preserved, the policy is precommitted, and missing evidence cannot silently disappear from the decision surface.

## R6E — governed baseline evolution

An intentional behavior change needs a new governed baseline. The monitored runtime may not erase drift by silently rewriting its current save-state.

A baseline transition should bind:

- predecessor and proposed successor state digests/versions;
- machine-readable behavioral diff;
- reason and evidence;
- compatibility/breaking classification;
- review/admission evidence;
- effective subject epoch;
- rollback/predecessor pointer.

History is append/supersede, not destructive rewrite.

`SUCCESSOR_BASELINE != PROOF_PREDECESSOR_WAS_WRONG`

`BASELINE_PROMOTION != RECOVERY`

## R6F — sustained recovery

Native R5 recovery should establish only that the first admitted post-ack replay was behaviorally stable under the pinned policy.

A later sustained-recovery subject must begin with a durable window-opening record created **before** later observations. The opening should bind:

- session and subject epoch;
- save-state digest;
- exact native RecoveryVerification digest;
- start turn and generation;
- exact recovery-window policy digest;
- minimum checkpoint/span requirements;
- checkpoint admission rule;
- invalidation rules.

Later qualification must consume durable ledger evidence rather than caller-constructed result objects.

Operational reload scheduling and behavioral recovery remain separate traces.

Bounded results:

- `PENDING_MORE_OBSERVATION`;
- `SUSTAINED_BOUNDED_RECOVERY`;
- `DEGRADED_DRIFT_RETURNED`;
- `RELAPSE_BEHAVIORAL_DRIFT`;
- `INDETERMINATE_EVIDENCE`;
- `INVALIDATED_SUBJECT_OR_POLICY_CHANGE`.

A historical stable window is not proof of present or permanent stability.

## R6G — provider effect evidence

The generic evaluator/actuator boundary remains provider-neutral and fail closed.

Provider-specific adapters may later produce stronger effect evidence only when they can bind:

- exact DriftGuard attempt/directive;
- provider operation/idempotency identity;
- raw receipt/readback provenance;
- applied/not-applied/ambiguous status;
- reconciliation epoch;
- retry authority, if any, derived only from verified non-application.

A generic caller-provided `NOT_APPLIED` assertion must never manufacture retry authority.

## R6H — tamper evidence

A local ledger and hash-linked receipts improve reconstructability but do not make a privileged local writer powerless.

Optional future anchoring may include signed checkpoints, append-only transparency logs, repository anchors, independent mirrors, or hardware/provider attestation where genuinely available.

`AUTHENTICATED_SOURCE != INDEPENDENT_SOURCE`

## Dependency order

After R5 exact-head review closure:

1. monitored-subject manifest;
2. evaluator/probe calibration;
3. provenance-aware independence;
4. precommitted sequential detection;
5. governed baseline evolution;
6. durable sustained-recovery window;
7. provider-specific actuator/readback adapters;
8. optional external anchoring.

Each implementation stage should receive hostile fixtures before production or behavioral-qualification claims.

## R5 gate before R6 implementation

Before implementing R6:

- obtain canonical independent disposition for PR #8;
- obtain exact-head hostile disposition for PR #11;
- exclude the obsolete external-boundary recovery helper from future core composition;
- keep Discovery interoperability optional rather than making it a mandatory DriftGuard dependency;
- if the #8 and #11 slices pass, compose them freshly on reviewed R4 lineage;
- independently review that exact combined head;
- do not merge or deploy without Patrick's explicit authorization for that exact protected effect.

## Claim ceiling

This research proposal establishes architecture and hostile test requirements only. It does not establish evaluator calibration, statistical validity, provider effects, sustained recovery, hidden-state restoration, personal identity continuity, consciousness, production readiness, merge authority, or deployment authority.
