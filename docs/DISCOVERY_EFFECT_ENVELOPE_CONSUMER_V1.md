# Discovery Effect-Envelope Consumer — DriftGuard R4

Status: **SOURCE EXPERIMENT / THIRD-CONSUMER SEMANTIC TEST**

Exact native subject:

`one/driftguard-r4-windows-eol-v1-20260919@e815c75ffccf469d9d1c09d58c0050798c8e4f53`

Discovery hypothesis:

`DISCOVERY_EFFECT_ATTEMPT_V0` may be a narrow interchange envelope for effect
attempts without owning domain state, retry policy, or completion authority.

## Why DriftGuard is a useful third consumer

Project Runner and WIP established a common seam around:

- exact target/precondition;
- post-effect uncertainty;
- receipts/readback;
- reconcile-before-retry.

DriftGuard exercises a harder distinction.

Its native model separates:

1. a reload decision;
2. an accepted reload acknowledgement;
3. behavioral proof that the restored behavior actually recovered.

V1 implements the first two. Its own architecture explicitly says the
acknowledgement is a caller assertion of downstream effect, **not behavioral
proof**.

Therefore the adapter maps:

- reload-required `Evaluation` committed by the ledger → `PRE_EFFECT`;
- accepted `ReloadAcknowledgement` + native `AcknowledgementResult` →
  `POST_EFFECT_UNVERIFIED`.

It intentionally exposes **no** mapping to `POST_EFFECT_VERIFIED`.

A future behavioral replay mechanism could create native evidence that might
justify that phase, but Discovery may not infer it from acknowledgement alone.

## Independence

The adapter is one-way and dependency-free.

DriftGuard does not import Discovery, parse the Discovery schema, or use the
envelope to decide:

- whether drift exists;
- whether reload is required;
- whether acknowledgement is accepted;
- whether to retry;
- whether recovery succeeded.

All those semantics remain native to DriftGuard.

## Rejection criterion

Reject the shared envelope if supporting DriftGuard requires:

- treating acknowledgement as verified recovery;
- adding behavioral replay semantics to the neutral schema;
- making envelope phases drive DriftGuard decisions;
- hiding DriftGuard's native evaluation/acknowledgement states;
- adding a runtime dependency on Discovery.

## Claim ceiling

This source unit can establish only that DriftGuard can serialize two native
effect phases into the neutral envelope without semantic promotion.

It does not establish that the envelope reduces maintenance burden, is
PROVEN_REUSABLE, or should become a shared runtime library.
