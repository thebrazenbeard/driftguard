# DriftGuard R10 + Attestation + Effect Composition / R9 Mixed-Alarm V2

Status: DRAFT COMPOSITION SUBJECT — NOT MERGED, DEPLOYED, OR CANONICAL.

## Exact source bindings

This composition is rebuilt from the current repaired R9 subject rather than the
older intermediate mixed-alarm head.

- canonical main base: `9894692ff6b549e4378bcc2b8ca46813ff18bf37`
- repaired R9 / PR #24 base:
  `669095c9b0114d0e9e54031f9e75230f789ce86f`
- clean R10 comparison delta source:
  `bt2/r10-detector-comparison-r9-mixed-repair-v2r2@0c34edd4dae832f9e99e1b2edc36ae91e0a31de3`
- attestation/effect integration source pinned for layering:
  `bt2/composition-r10-attestation-effect-v1-20260920@40a992a2a5a56a0d0d7980a8c50a0ddc14ebc6af`
- composition branch:
  `bt2/composition-r10-attestation-effect-r9-mixed-v2-20260920`

## Mixed-alarm semantics carried from R9

Post-shift target detection and collateral wrong-dimension incidence are separate
trajectory-level facts.

For one first alarm:

- target-only => detection yes / wrong-dimension no;
- wrong-only => detection no / wrong-dimension yes;
- mixed target + unrelated => detection yes / wrong-dimension yes;
- multiple unrelated alarm dimensions still count one trajectory-level
  wrong-dimension incidence.

The family receipt carries an explicit
`mixed_target_wrong_dimension_alarms` overlap count so detection and collateral
wrong-dimension statistics may overlap without permitting impossible first-alarm
totals.

The current #24 adversarial regression that freezes one wrong incidence per
trajectory with multiple collateral dimensions is preserved byte-for-byte in this
composition.

## R10 propagation

CUSUM, Page-Hinkley, and EWMA comparison paths use the same overlap-aware
first-alarm semantics and family receipt contract.

No comparison candidate may receive a clean detection merely because an expected
shifted dimension appears alongside unrelated alarm dimensions.

R10 remains comparison-only. It does not authorize candidate promotion.

## Evaluator-attestation composition

The optional evaluator-attestation path remains bounded to exact request/response,
policy, key identity, durable evaluation provenance, and current monitored-subject
identity/epoch.

The strong claim remains key-possession/provenance only. It does not establish
provider honesty, evaluator independence, semantic correctness, or hardware-rooted
identity.

## Effect-boundary composition

Reload directives are re-admitted against durable/current provenance, including
subject identity where present.

Generic actuator receipts remain transport/readback evidence only. APPLIED,
NOT_APPLIED, and UNKNOWN generic receipts cannot manufacture a reload
acknowledgement.

A superseded monitored subject invalidates an existing subject-bound reload
directive.

Reload acknowledgement, later behavioral recovery evidence, and causal recovery
remain separate evidence classes.

## Evidence state

- PR #24 current repaired exact head has hosted CI success.
- The fresh composition preserves the current R9 documentation and hostile
  regression bytes from PR #24.
- R10, attestation, and effect integration content is layered from the exact pinned
  source subjects above.
- Whole-composition CI/review is required on the final exact composition head.
- A prior local R10 focused run reached 46/46 PASS on an earlier repaired R10 head;
  that evidence is not promoted to this new composition subject.
- Local full-suite execution for this final composition was not completed because
  the remote execution tool quota was exhausted; hosted CI is therefore the
  qualification path for this exact head.

## Claim ceiling

This composition can establish only deterministic source-level composition and,
after exact-head CI/review, bounded behavioral/provenance semantics represented by
the included contracts.

It does not prove production representativeness, unseen holdout status, IID or
stationarity, evaluator honesty/independence, hidden provider state, actual provider
application of a reload, reload causality, merge readiness, deployment readiness,
or protected-effect authority.
