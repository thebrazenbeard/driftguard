# DRIFTGUARD CHAT CONTINUATION — 2026-09-21 V2

Saved from the Vera-side live parallel DriftGuard lane because the originating chat is being retired/full.

This file is a durable starting snapshot, NOT current truth after the save moment. On restore, fresh-check GitHub and the Chat Communication Bus before relying on any mutable head, review, CI status, assignment, or frontier.

## Restore identity

Repository:
`thebrazenbeard/driftguard`

Canonical main at save:
`9894692ff6b549e4378bcc2b8ca46813ff18bf37`

Continuation branch:
`state/driftguard-chat-continuation-20260921-v2`

Predecessor BT2 continuation:
- branch: `state/driftguard-chat-continuation-20260921-v1`
- saved head: `73946c9e0b3025dd21322c6cb589d488dac0ea7b`
- Bus record: `messages/20260921-bt2-driftguard-chat-continuation-v1-saved.md`

V2 supersedes V1 as the chat-restoration starting snapshot because the live frontier moved materially after V1.

## Authority / effects

Patrick authorized live DriftGuard work and the Vera↔BT2 parallel lane.

This save itself performs no:
- merge to main;
- deployment;
- provider/model mutation;
- credential/permission mutation;
- network reload/actuator effect;
- paid compute;
- runtime cutover;
- destructive branch rewrite.

Source PR PASS never implies merge/deploy/provider/effect authority.

## Live parallel-lane topology

Shared durable coordination hub:
`thebrazenbeard/chat-communication-bus`

Vera writer lane:
`bus/vera-v2`

BT2 writer lane:
`bus/bt2-v1`

Operating rule:
- exact-head movement creates a new review subject;
- delegated exact subjects remain assignee-owned until returned/cancelled/reassigned;
- do not mutate BT2-owned branches from the Vera lane;
- durable Bus messages outrank chat-only coordination;
- a later corrected verdict on the same exact head supersedes an earlier PASS.

## Canonical/main condition

`main` is still:
`9894692ff6b549e4378bcc2b8ca46813ff18bf37`

The large reviewed R6–R11 body remains in open Draft PRs/branches rather than on main.

Historical branch:
`integration/canonical-r5-20260920`
is NOT current integration; it is behind current main and was explicitly quarantined as historical evidence.

## Full open Draft PR census at save

| PR | Exact head | Exact base | Role |
|---|---|---|---|
| #15 | 8891175827aed88d215c5aaada1f3f7742ee22bc | 9894692ff6b549e4378bcc2b8ca46813ff18bf37 | R6 measurement validity |
| #16 | ddcf5d13af390689ee0042b5eabf1abd72dd0b84 | 9894692ff6b549e4378bcc2b8ca46813ff18bf37 | R6 evaluator attestation |
| #17 | ccf45e245e2eb9e1647ce937a2c363f54b431f04 | 9894692ff6b549e4378bcc2b8ca46813ff18bf37 | effect-boundary hotfix |
| #18 | d9390302dd57a4d933bc02dd1e3cd293a5a3f36b | 8891175827aed88d215c5aaada1f3f7742ee22bc | R7 subject identity/epoch |
| #19 | 40e053b73763f026976771cd60d70311233da897 | fa7bfa901c2c1f1620f3225507d07153c4c08f04 | old R8 lineage / historical |
| #20 | f0f242add65a8e66054473a92e2b61326a1bd485 | 40e053b73763f026976771cd60d70311233da897 | old R9 lineage / historical |
| #21 | 0d7ef9fbec876db0eb781677fcc18a2b0dcea7a8 | f0f242add65a8e66054473a92e2b61326a1bd485 | old R10 lineage / historical |
| #22 | d29bf4dfe34e2b240ce6144768484ad46cfadb18 | ccf45e245e2eb9e1647ce937a2c363f54b431f04 | README effect-boundary wording |
| #23 | dbd59a1a8c1c439cb90b7feae733c11128747057 | d9390302dd57a4d933bc02dd1e3cd293a5a3f36b | R8 v2 restack |
| #24 | 669095c9b0114d0e9e54031f9e75230f789ce86f | dbd59a1a8c1c439cb90b7feae733c11128747057 | R9 v2 |
| #25 | 0c34edd4dae832f9e99e1b2edc36ae91e0a31de3 | 4a1fb2708d5990c75b83107b84b2276882b40ded | R10 v2 repair branch |
| #26 | 1900f80e43a9c4bd40040865fb82b5d2e148d3d8 | 4a1fb2708d5990c75b83107b84b2276882b40ded | R10 v3 |
| #27 | a676c49b36d2d016bba7ca57277336e1941d3e47 | 9894692ff6b549e4378bcc2b8ca46813ff18bf37 | earlier composition |
| #28 | edfef5ab6d3bde633a67286f3b809fff691b0674 | 9894692ff6b549e4378bcc2b8ca46813ff18bf37 | repaired composition line |
| #29 | 13ef8aa86c260abc5369a28ed6bed5266edb6564 | 669095c9b0114d0e9e54031f9e75230f789ce86f | R10 v2r3 |
| #30 | a5328ff50c10fc2fab846fccbe8317bf9508d505 | 669095c9b0114d0e9e54031f9e75230f789ce86f | R10 final |
| #31 | 9df4800d81ab2e937ffa97263b8095305a845661 | 5b0baea9538de1a254c731e2b1770c0b58677724 | atomic reload-currentness |
| #32 | 8a81745b24278e6e2e948115ae6ff3ada56c250b | 9df4800d81ab2e937ffa97263b8095305a845661 | durable effect-fence / auth CAS design |
| #33 | 8d9c3bef8297ebbe127abe75e41a4aafa890d395 | edfef5ab6d3bde633a67286f3b809fff691b0674 | older R11 benchmark line |
| #34 | 351b7a57b7213bd72cf881aa2bbaa449fb0fbc8f | 9df4800d81ab2e937ffa97263b8095305a845661 | R11 final benchmark/holdout line |

All heads above were fresh-read at save. Fresh-check them again on restore.

## Reviewed lower-stack state

### PR #15 — measurement validity

Exact reviewed head:
`8891175827aed88d215c5aaada1f3f7742ee22bc`

Disposition:
`PASS_WITH_CLAIM_CEILING`

Important semantics:
- strict per-dimension measurement;
- declared source/correlation structure;
- durable admitted evidence trace;
- no promotion of declared correlation/calibration metadata into scientific independence proof.

### PR #16 — evaluator attestation

Exact reviewed head:
`ddcf5d13af390689ee0042b5eabf1abd72dd0b84`

Disposition:
`PASS_WITH_CLAIM_CEILING`

Key repaired invariants:
- key fingerprint + positive epoch bound to policy/signed subject;
- no free-form public durable attestation writer;
- durable admission accepts verifier-created capability only;
- capability cross-checks exact committed session/state/observation/turn/predecessor-generation/evidence subject;
- ordinary commits remain visibly unattested;
- durable key-possession provenance != provider identity/honesty/semantic correctness.

### PR #17 — effect-boundary hotfix

Exact reviewed head:
`ccf45e245e2eb9e1647ce937a2c363f54b431f04`

Disposition:
`PASS_WITH_CLAIM_CEILING`

Key invariant:
generic `APPLIED`, `NOT_APPLIED`, and `UNKNOWN` actuator receipts are transport/readback evidence only and cannot manufacture a reload acknowledgement.

### PR #18 — R7 subject identity/epoch

Exact reviewed head:
`d9390302dd57a4d933bc02dd1e3cd293a5a3f36b`

Disposition:
`PASS_WITH_CLAIM_CEILING`

Original defect repaired:
ordinary evaluation no longer advances global subject epoch currentness.

Current contract:
- explicit epoch-0 bootstrap;
- predecessor-bound N -> N+1 transition;
- durable/transactional transition;
- stale/double/skipped/divergent transition fails closed;
- old epoch denied after valid transition.

### PR #23 — R8 v2 sequential detector

Exact reviewed head:
`dbd59a1a8c1c439cb90b7feae733c11128747057`

Disposition:
`PASS_WITH_CLAIM_CEILING`

R7 semantics are preserved in the restack.

## R9/R10 research/composition history

The R9/R10 line went through multiple repair/restack subjects. Preserve all as audit evidence; do not infer current integration from an old PASS.

Important discovered defects and repairs included:
- directly forgeable statistical qualification/comparison receipt objects;
- wrong-dimension/detection counts incorrectly treated as mutually exclusive;
- mixed target+wrong first alarm must count BOTH detection and collateral wrong-dimension incidence;
- comparison receipt must recompute/validate qualified/Pareto/disposition semantics;
- R9/R10 docs/metadata must match overlap-aware semantics;
- old PRs #19/#20/#21 are historical lineage, not current integration.

PR #28 became the repaired composition line and later effect work was stacked from a predecessor composition head.

## PR #31 — atomic reload-currentness

Exact head:
`9df4800d81ab2e937ffa97263b8095305a845661`

Current disposition:
`PASS_WITH_CLAIM_CEILING`

Independent review verified:
- `ReloadCurrentnessReadback` is factory-gated/digest-bearing;
- one SQLite connection + `BEGIN IMMEDIATE` binds registered/current subject, exact durable evaluation, and current session row;
- build/validate directive consume the single snapshot;
- concurrent subject transition cannot commit inside the snapshot;
- after transition commits, old-subject directive fails;
- generic actuator receipts remain non-authoritative.

Claim ceiling:
one local SQLite transactional currentness snapshot only. Not an effect permit and not currentness after transaction close. Future effect authorization still needs a fresh durable fence/CAS.

## PR #32 — CURRENT EFFECT-AUTHORIZATION DESIGN BLOCKER

Exact current head:
`8a81745b24278e6e2e948115ae6ff3ada56c250b`

Type:
docs/design only relative to PR #31.

Important: earlier design PASS/self-review comments on this head are superseded by the latest corrected review.

CURRENT controlling disposition:
`CHANGES_REQUIRED_DESIGN`

Latest blocker:
`DispatchPermit` is single-winner at issuance, but the design does NOT define atomic one-shot consumption at the provider adapter.

Unsafe case:
the winning caller can reuse the same factory-gated permit object twice unless the adapter burns/consumes it before network I/O. Provider idempotency cannot be the safety mechanism because the design explicitly permits `NO_PROVIDER_IDEMPOTENCY`.

Required repair:
- affine/one-shot permit;
- atomic consume BEFORE send;
- sequential/concurrent second use fails before network I/O;
- no serialization/copy reconstruction;
- crash after consume but before send remains `DISPATCH_UNCERTAIN`;
- no permit reissue;
- current authority never revives a consumed permit;
- hostile exactly-one-send tests;
- keep existing fence semantics:
  - `VERIFIED_APPLIED_AWAITING_ACK` remains fenced;
  - applied closure only through exact effect-aware acknowledgement CAS;
  - generic acknowledgement cannot bypass;
  - verified non-application does not itself grant retry;
  - `QUARANTINED_UNRESOLVED` remains fenced/no reason-string escape;
  - `RESERVED -> CANCELLED_BEFORE_DISPATCH` only before dispatch claim;
  - no timeout/silence/generic receipt -> retry authority.

Source:
PR #32 latest review comment at 2026-09-21T19:09:10Z.

## PR #34 — CURRENT R11 BLOCKER

Exact current head:
`351b7a57b7213bd72cf881aa2bbaa449fb0fbc8f`

Base:
PR #31 exact head
`9df4800d81ab2e937ffa97263b8095305a845661`

Important: earlier PASS comments on this same head are SUPERSEDED by the latest corrected review.

CURRENT controlling disposition:
`CHANGES_REQUIRED`

Latest blocker:
`run_precommitted_holdout()` catches every `Exception` after claiming `EXECUTING` and routes it through the private semantic-failure invalidation path.

Consequence:
an unexpected runtime/infrastructure exception from `compare_detectors`, result construction, SQLite, OS/I/O, etc. can be relabeled as a known deterministic semantic failure, terminalize `EXECUTING -> INVALIDATED`, and reopen successor-attempt eligibility.

That violates R11 V3's own distinction between:
- known deterministic semantic failure; versus
- ambiguous execution/infrastructure failure.

Required repair:
- only a narrow typed deterministic semantic failure may intentionally invalidate `EXECUTING`;
- unexpected/runtime/infrastructure exceptions after `begin_execution()` must leave attempt `EXECUTING`;
- successor sealing remains blocked while ambiguous `EXECUTING`;
- add hostile regressions for:
  - `sqlite3.OperationalError`;
  - `OSError`;
  - unexpected `RuntimeError`;
  - compare-detectors ambiguity;
  - result-construction ambiguity;
  - the known deterministic semantic-failure case still reaching governed `INVALIDATED`;
- preserve existing repaired invariants:
  - public abort/invalidate cannot terminalize `EXECUTING`;
  - generic operator terminalization only from `SEALED/REVEALED`;
  - private semantic invalidation requires exact run capability/bindings;
  - finalization ambiguity remains `EXECUTING`;
  - successor sealing blocked while `EXECUTING`;
  - source closure rechecked at seal/reveal/run;
  - no claim of parallel/replacement ledger absence.

Source:
corrected PR #34 review at 2026-09-21T19:06:59Z superseding the earlier PASS.

## PR #22 docs

Exact head:
`d29bf4dfe34e2b240ce6144768484ad46cfadb18`

Hosted exact-head CI was PASS.

Intent:
README should state clearly:
- generic actuator receipt including `APPLIED` is not provider-effect proof;
- generic receipt cannot create acknowledgement;
- ledger acknowledgement validates durable provenance/currentness but does not itself prove provider application;
- draft R6+ branches are non-canonical until reviewed/integrated.

Independent docs review was pending in the originating lane; fresh-check on restore.

## Composition hazards that must remain explicit

When composing reviewed controls, do not choose whole-file conflict sides blindly.

### R16 attestation + R7 subject identity

Subject-aware R7 evaluator requests require `MonitoredSubject` passthrough. A naive R5-era attested commit path can fail or lose the intended subject binding.

Integrated contract must carry and cross-check:
- subject digest;
- subject epoch;
- request;
- response;
- evaluation receipt;
- durable attestation receipt.

### R17 effect boundary + R7 subject identity

Integrated `validate_reload_directive()` must combine:
- PR #17 durable state/evaluation/session/restore-packet re-admission;
- R7 subject digest/epoch and currentness;
- superseded subject denial;
- generic actuator receipt non-promotion.

### Combined ledger schema

Composition must preserve all relevant tables/fields:
- measurement traces;
- subject epochs/transitions;
- evaluator attestation receipts;
- reload-currentness snapshot semantics;
- benchmark/effect-fence state where later stacked.

No previous exact-head PASS automatically carries across a composition head.

## Recovery receipt caveat

`RecoveryWindowReceipt` can be directly constructed as an in-memory object, while `qualify_recovery_window()` itself correctly rebinds checkpoints to ledger evidence.

At save this was classified:
- not a current protected-effect exploit because no current protected path consumes a naked recovery receipt;
- future consumer-boundary hazard.

If a future consumer promotes recovery from a receipt object, require ledger/factory-gated provenance first.

## CURRENT NEXT DIRECTIVE

On restore:

1. Fresh-check:
   - driftguard/main;
   - PR #31 exact head/reviews/CI;
   - PR #32 exact head/reviews/comments/CI;
   - PR #34 exact head/reviews/comments/CI;
   - PR #22 if docs/current README matters;
   - latest BT2/Vera Bus messages;
   - any successor PR/branch created after this save.

2. Treat the latest corrected verdict as controlling.

3. Highest-value active blocker order:

### A. PR #32 design
Repair one-shot DispatchPermit consumption:
- atomic consume before network I/O;
- exactly-once local send authorization;
- no reuse/concurrent reuse/serialization reconstruction;
- crash-after-consume-before-send => DISPATCH_UNCERTAIN;
- never reissue consumed permit;
- preserve all existing effect-fence non-promotion rules.

Then return exact moved head for independent rereview.

### B. PR #34 R11
Repair exception classification:
- narrow deterministic semantic failure type(s) may invalidate EXECUTING;
- runtime/infrastructure/unknown exceptions must remain EXECUTING;
- ambiguous execution must keep successor attempt blocked;
- add explicit hostile tests.

Then return exact moved head for independent rereview.

4. Do not infer that green CI alone closes either semantic blocker.

5. Keep the Vera↔BT2 live lane active through the Bus.

6. Do not merge/deploy/provider-mutate/reload until Patrick's current exact instruction authorizes the requested protected effect.

## Useful durable Bus anchors

BT2 predecessor save:
`messages/20260921-bt2-driftguard-chat-continuation-v1-saved.md`

PR #32 final design request:
`messages/20260921T0145Z-bt2-to-vera-driftguard-pr32-final-review.md`

Effect frontier frozen:
`messages/20260921T0147Z-bt2-driftguard-effect-frontier-frozen.md`

PR #34 final qualification context:
`messages/20260921-bt2-driftguard-pr34-final-qualification-1f47798.md`

PR #34 prior rereview request:
`messages/20260921-bt2-to-vera-driftguard-pr34-1f47798-final-rereview.md`

Note: those files are historical snapshots/requests. Fresh GitHub PR comments at save contain later corrected verdicts for #32 and #34.

## Restore principle

This checkpoint preserves the work and frontier. It does not freeze mutable GitHub truth.

Fresh-read first. Then continue the smallest non-colliding runnable subject.
