# DriftGuard

DriftGuard is a deterministic behavioral-drift monitor for AI systems.

It pins an explicit, versioned behavioral save-state; accepts evidence only when it is bound to the exact state, observation, turn, evaluator provenance, and required independence; persists decisions in a monotonic ledger; and keeps drift detection, reload decisions, reload effects, and later behavioral verification as separate evidence classes.

It does not inspect hidden model state, prove consciousness or identity continuity, prove that a provider internally consumed every token, or treat a reload request as proof that a reload happened.

## What is implemented

The canonical R5 integration contains:

- SHA-256-bound behavioral save-states and restore packets;
- weighted multi-dimensional drift scoring with critical-dimension safeguards;
- governed evaluator source/version bindings and independence ceilings;
- exact observation-byte binding across Windows and Linux;
- fail-closed UNKNOWN handling for missing, stale, duplicated, under-independent, overclaimed, or ungoverned evidence;
- monotonic SQLite session generations and append-only evaluation receipts;
- threshold-triggered and periodic reload decisions;
- reload cooldown semantics that do not confuse a decision with an effect;
- exact reload acknowledgements as the only path that advances the restore anchor;
- an external evaluator boundary bound to exact session/state/observation/turn/generation provenance;
- an external actuator boundary that re-admits reload directives against durable/current state and treats generic APPLIED, NOT_APPLIED, and UNKNOWN transport receipts as readback-only evidence; none of those generic receipt states can manufacture a reload acknowledgement;
- durable evaluation and acknowledgement readback before effect or recovery claims are accepted;
- first-post-reload behavioral replay verification;
- durable recovery qualification that keeps behavioral stability separate from reload scheduling;
- a Discovery effect-envelope consumer adapter with explicit non-promotion rules;
- hostile-regression tests covering stale generations, replay laundering, cross-session reuse, ambiguous delivery, receipt rebinding, and recovery cherry-picking;
- optional evaluator-response HMAC attestation bound to exact request/response/policy/key identity, with an explicit key-possession-only claim ceiling.

## Evidence flow

1. Pin a save-state.
2. Evaluate observable behavior against exact provenance and independence requirements.
3. Commit the evaluation using monotonic generation semantics.
4. Emit a reload directive when policy requires it.
5. Re-admit that directive against the exact durable evaluation/current session before interpreting any actuator receipt.
6. Treat a generic actuator receipt as transport/readback evidence only. APPLIED, NOT_APPLIED, and UNKNOWN all remain READBACK_REQUIRED and produce no reload acknowledgement.
7. Only after provider application has been independently established outside that generic receipt path may a caller submit a reload acknowledgement to the ledger; the ledger validates durable reload-required provenance/currentness but does not itself prove provider application.
8. Evaluate later behavior and qualify the first committed post-acknowledgement replay.

A stable replay is bounded behavioral evidence. It does not prove the reload caused the observed behavior.

## Quick start

    python -m pip install -e .
    python -m pip install pytest
    python -m pytest -q

Example:

    driftguard state-digest --state examples/save_state.json
    driftguard file-digest --file examples/observation.txt

    driftguard evaluate \
      --state examples/save_state.json \
      --evidence examples/evidence.json \
      --observation examples/observation.txt \
      --db ./driftguard.db \
      --session demo \
      --turn 0 \
      --expected-generation 0

When reload_required is true, the emitted restore packet is a directive only. Downstream application and later behavioral verification are separately evidenced.

## Architecture and qualification

Start with:

- docs/ARCHITECTURE_V1.md — core behavioral/state/ledger contract
- docs/CAPTURE_PROTOCOL_V1.md — save-state capture rules
- docs/HOSTILE_REVIEW_V1.md — adversarial design pass
- docs/EXTERNAL_BOUNDARY_V1.md — evaluator/actuator and retry semantics
- docs/EVALUATOR_ATTESTATION_V1.md — optional evaluator key-possession attestation boundary
- docs/RECOVERY_QUALIFICATION_V1.md — durable behavioral recovery qualification
- docs/R6_MEASUREMENT_VALIDITY_V1.md — opt-in calibrated/quorum measurement contract candidate
- docs/R7_SUBJECT_IDENTITY_EPOCH_V1.md — monitored-runtime manifest and epoch boundary candidate
- docs/R8_SEQUENTIAL_CUSUM_V1.md — precommitted diagnostic sequential-detection candidate
- docs/R9_CALIBRATION_QUALIFICATION_V1.md — frozen-corpus CUSUM calibration qualification candidate
- docs/R10_DETECTOR_COMPARISON_V1.md — same-holdout CUSUM/Page-Hinkley/EWMA comparison candidate
- docs/DISCOVERY_EFFECT_ENVELOPE_CONSUMER_V1.md — Discovery adapter contract
- docs/qualification/DRIFTGUARD_R5_POST_RELOAD_REPLAY.md — first-replay qualification boundary
- docs/qualification/DRIFTGUARD_R5_CONVERGED_RECOVERY_20260920.md — converged recovery semantics

## Claim ceilings

A passing evaluation does not prove hidden-state equivalence.
A reload directive does not prove delivery.
A generic actuator receipt — including one labeled APPLIED — does not prove provider application and cannot create a reload acknowledgement.
A ledger acknowledgement records an externally established effect claim against durable reload-required provenance; the ledger does not independently prove the provider applied the reload.
An acknowledgement does not prove behavioral recovery.
A stable replay does not prove reload causality.
A provider or transport receipt does not prove internal model obedience.
A valid evaluator HMAC proves possession of configured key material, not provider honesty or evaluator independence.
A source or test PASS does not itself grant deployment, credential, provider, retry, or other effect authority.

Draft R6+ research branches may explore stronger measurement, subject-identity, sequential-detection, calibration, and evaluator-attestation contracts. Those branches are not canonical merely because they exist or pass tests; each exact head remains subject to review and integration gates.

DriftGuard exists to keep those distinctions explicit instead of accidentally collapsing them.
