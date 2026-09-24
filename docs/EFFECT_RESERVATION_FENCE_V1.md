# DriftGuard Effect Reservation + Fence V1

Status: CURRENT-MAIN-NATIVE SOURCE CANDIDATE / LOCAL MECHANICAL FENCE ONLY

## Purpose

This slice implements the first executable part of the former effect-authorization CAS design on current DriftGuard main.

It prevents a current reload-required decision from being turned into repeated or concurrent provider attempts merely because a caller can replay a directive.

It does **not** perform provider I/O and does **not** manufacture protected-effect authority.

## Implemented state

One exact reload effect may be durably reserved as:

`RESERVED`

The reservation and currentness predicates execute under one SQLite `BEGIN IMMEDIATE` transaction. The same transaction verifies:

- the durable session exists;
- the exact session generation is current;
- the exact state digest is current;
- the exact evaluation is still the session frontier;
- the evaluation is reload-required;
- the evaluation generation transition matches the requested generation;
- monitored-subject digest/epoch, when present, remain exact and current;
- no unresolved effect fence already owns the session.

The transaction then writes both:

- `effect_attempts`;
- `effect_fences`.

A second unresolved reservation for the same session fails closed.

## Pre-dispatch cancellation

Only:

`RESERVED -> CANCELLED_BEFORE_DISPATCH`

may release the fence without provider reconciliation.

Cancellation verifies exact fence ownership and performs the attempt transition plus fence deletion in one transaction.

An attempt ID is durable history and cannot be reused.

## Single-use dispatch claim

`claim_effect_dispatch(...)` performs the one-way transition:

`RESERVED -> DISPATCH_UNCERTAIN`

and returns an in-process `EffectDispatchPermit` whose explicit claim is:

`MECHANICAL_SINGLE_USE_DISPATCH_PERMIT_ONLY`

The permit cannot be constructed through its public constructor, cannot be reissued after the durable state leaves `RESERVED`, and does not release the fence.

A crash after the durable claim but before provider I/O therefore leaves `DISPATCH_UNCERTAIN` fenced. It does not recreate retry authority.

## Acknowledgement boundary

The pre-existing generic `DriftLedger.acknowledge_reload(...)` now rejects any session with an active effect fence.

That prevents the ordinary acknowledgement path from advancing session generation while an unresolved effect attempt is still fenced.

A future effect-aware provider-verification + acknowledgement transaction must close the attempt before the fence can be released after dispatch.

## Deliberately not implemented in this slice

The following states and effects remain future work:

- provider network dispatch;
- external protected-effect authority verification;
- `VERIFIED_APPLIED_AWAITING_ACK`;
- `VERIFIED_NOT_APPLIED`;
- `QUARANTINED_UNRESOLVED`;
- effect-aware atomic acknowledgement and fence release;
- provider honesty/idempotency/readback guarantees;
- retry authorization;
- deployment or runtime activation.

A real provider adapter must eventually require both:

`CURRENT_PROTECTED_EFFECT_AUTHORITY AND EXACT_SINGLE_USE_DISPATCH_PERMIT`

before any network effect.

## Claim ceiling

Passing source/tests for this slice proves only local durable reservation/fence mechanics on the tested DriftLedger implementation.

It does not prove provider effect, authorization, distributed locking, external currentness, deployment, or behavioral recovery.
