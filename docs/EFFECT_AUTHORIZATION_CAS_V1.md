# DriftGuard Effect Authorization CAS / Durable Fence Design V1

Status: **DRAFT DESIGN ONLY / NO PROVIDER EFFECT / NO RUNTIME AUTHORITY**

Exact design base:

`thebrazenbeard/driftguard@9df4800d81ab2e937ffa97263b8095305a845661`

Stacked source subject:

- PR #31: atomic reload-currentness re-admission;
- claim: `SINGLE_SQLITE_BEGIN_IMMEDIATE_CURRENTNESS_SNAPSHOT_ONLY`.

This document defines a possible next boundary. It does not implement it.

## Problem

PR #31 closes the intra-validation race.

Subject-currentness, the durable evaluation, and the durable session row are read
inside one SQLite `BEGIN IMMEDIATE` transaction. A concurrent subject/session writer
cannot commit inside that re-admission window.

That is necessary, but it is not sufficient for an actual provider effect.

The database transaction must end before a network call. After it ends, the local
session or monitored subject could otherwise move before or while the provider
operation is attempted.

Holding a SQLite write reservation across network I/O is rejected:

- network latency would hold the local writer lock;
- a hung provider could stall unrelated durable state;
- crash recovery would be harder to reason about;
- a database lock is not provider-side idempotency;
- it would still not prove provider application.

The next boundary therefore needs a durable **effect fence**, not a long database
transaction.

## Core invariants

A future effect-authorizing consumer must preserve all of these invariants.

1. **Separate authority from mechanics.**
   A DriftGuard reservation is never human/project authority to perform a protected
   effect. Separate live/current authority remains required.

2. **One unresolved attempt per exact directive.**
   The same reload directive cannot acquire multiple concurrent provider attempts.

3. **Fence local invalidation.**
   While an attempt is unresolved, local mutations that would supersede its bound
   session generation or monitored-subject epoch must fail closed.

4. **Write uncertainty before network I/O.**
   Durable state must say that an effect may be attempted before the provider call
   can occur.

5. **Reconcile before retry.**
   Crash, timeout, connection loss, or a generic provider status never grants retry
   authority.

6. **Provider idempotency is explicit.**
   When a provider supports idempotency, the exact attempt digest supplies or binds
   the provider idempotency key. If the provider cannot supply equivalent semantics,
   automatic retry is not safe.

7. **Generic receipts remain non-authoritative.**
   `APPLIED`, `NOT_APPLIED`, and `UNKNOWN` on the existing generic
   `ActuatorReceipt` remain transport/readback evidence only.

8. **Application is not recovery.**
   Independently verified provider application may support a native
   `ReloadAcknowledgement`; it still does not establish behavioral recovery.

## Proposed durable object: EffectAttemptReservation

A reservation would bind at least:

- reservation/attempt id;
- reload directive id and digest;
- PR #31 currentness-readback digest;
- session id;
- exact session generation;
- exact evaluation digest;
- exact state digest;
- exact monitored-subject digest/epoch when subject-bound;
- provider target/configuration digest;
- deterministic provider idempotency key or an explicit
  `NO_PROVIDER_IDEMPOTENCY` capability;
- current attempt state;
- immutable reservation digest.

The reservation should be factory-gated. A caller must not be able to instantiate a
digest-bearing reservation and present it as ledger evidence.

A reservation is **mechanical single-attempt eligibility only**. It is necessary but
never sufficient authority for a protected provider effect.

## Proposed attempt state machine

The minimal conservative states are:

`RESERVED`

The exact directive/currentness tuple has acquired the durable effect fence. No
provider call may have happened yet.

`DISPATCH_UNCERTAIN`

The ledger records this state **before** network I/O. From this point onward the
provider call may or may not have occurred.

A process crash immediately after this write is intentionally treated as uncertain
rather than as safe-to-retry.

`READBACK_REQUIRED`

A response, timeout, crash recovery, or generic actuator receipt is insufficient to
prove the provider outcome. The fence remains active.

`VERIFIED_NOT_APPLIED`

A provider-specific authenticated readback proves that this exact attempt did not
apply. The fence may be released. A later retry requires a new currentness
re-admission and a new reservation.

`VERIFIED_APPLIED`

A provider-specific authenticated readback proves application of this exact attempt.
The generic layer still does not manufacture a reload acknowledgement. Native
acknowledgement admission remains a separate ledger operation.

`CLOSED`

The attempt is terminal and cannot be reused.

There is deliberately no timeout transition from an uncertain state to
`VERIFIED_NOT_APPLIED`.

Wall-clock expiry must never manufacture retry authority.

## Reservation transaction

A future `reserve_effect_attempt(...)` operation should use one
`BEGIN IMMEDIATE` transaction and:

1. re-admit the exact reload directive using the same currentness facts as PR #31;
2. reject any unresolved reservation for that directive or bound
   session-generation/evaluation;
3. verify no incompatible effect fence already exists for the session/subject;
4. insert the immutable reservation at `RESERVED`;
5. read it back;
6. commit.

The unique constraints, not caller convention, must prevent duplicate live
reservations.

## Pre-dispatch transition

Immediately before network I/O, the adapter performs an exact compare-and-swap:

`RESERVED -> DISPATCH_UNCERTAIN`

The CAS binds the reservation digest and expected status.

Only after that durable transition succeeds may the provider call be attempted.

This ordering intentionally creates a conservative crash window:

- ledger says `DISPATCH_UNCERTAIN`;
- process crashes before the actual network send;
- recovery still requires provider reconciliation.

That false-positive uncertainty is safer than a false-negative “nothing happened”
claim followed by a duplicate effect.

## Durable effect fence

While a reservation is in any unresolved state, operations that would invalidate its
preconditions must fail closed.

At minimum, the fence applies to:

- subject-epoch transition for the bound subject;
- session generation movement that would supersede the directive;
- replacement of the session's last evaluation;
- any future effect attempt on the same directive/session-generation pair.

A verified-applied finalization may combine the appropriate local state advancement
with fence closure in one ledger transaction.

A verified-not-applied finalization may release the fence without advancing the
reload acknowledgement state.

## Provider adapter contract

The neutral DriftGuard layer must not infer provider truth from an arbitrary JSON
receipt.

A provider-specific adapter would need to establish its own evidence contract,
including:

- exact provider/account/target binding;
- attempt/reservation digest;
- provider idempotency key;
- provider operation id when one exists;
- authenticated or independently retrievable provider readback;
- exact outcome classification;
- raw-response digest/provenance sufficient for later audit.

A future digest-bearing `ProviderEffectVerification` should be factory-gated in the
same way as DriftGuard qualification, attestation, and PR #31 currentness receipts.

The provider adapter must document the strongest claim its evidence supports.

For a provider without trustworthy idempotency/readback, an uncertain attempt can
remain permanently non-retriable without explicit external recovery.

## Finalization CAS

Provider verification does not directly mutate session state.

A future finalizer should use one `BEGIN IMMEDIATE` transaction and compare:

- reservation id/digest;
- reservation expected state;
- directive digest;
- session id/generation;
- evaluation digest;
- state digest;
- subject digest/epoch;
- provider-verification attempt binding.

The finalizer then performs exactly one allowed transition.

For verified non-application:

- mark the attempt `VERIFIED_NOT_APPLIED`;
- release its durable fence;
- do not create a reload acknowledgement;
- do not retry automatically.

For verified application:

- mark the attempt `VERIFIED_APPLIED`;
- preserve the provider verification;
- only a separately valid native acknowledgement path may advance the reload anchor;
- behavioral recovery remains a later evidence class.

## Recovery after crash

Startup/recovery must enumerate every unresolved effect attempt before permitting
another attempt on the same fence domain.

Recovery rules:

- `RESERVED`: no provider call should have occurred, but the reservation still
  requires an explicit cancellation/release transaction before replacement;
- `DISPATCH_UNCERTAIN`: reconcile against provider state before any retry;
- `READBACK_REQUIRED`: reconcile against provider state before any retry;
- ambiguous provider readback: remain fenced;
- verified non-application: release fence, then require a fresh reservation;
- verified application: proceed only through native acknowledgement/recovery
  evidence.

No crash path silently converts uncertainty into non-application.

## Hostile tests required before implementation can qualify

A future implementation should include at least these adversarial cases:

1. two processes race to reserve the same directive: exactly one succeeds;
2. subject transition races reservation: one side wins atomically; the loser fails;
3. session-generation advance races reservation: one side wins atomically;
4. process crashes after `DISPATCH_UNCERTAIN` but before network send: retry is
   still forbidden without reconciliation;
5. provider applies but client times out: retry is forbidden;
6. generic `APPLIED` receipt cannot close the fence;
7. generic `NOT_APPLIED` receipt cannot release the fence;
8. a provider verification for attempt A cannot resolve attempt B;
9. replay of a previously consumed provider verification fails;
10. verified-not-applied closes the old fence but does not itself authorize a retry;
11. verified-applied cannot manufacture behavioral recovery;
12. an old reservation cannot survive a subject/session transition after the fence is
    properly closed;
13. direct construction of reservation/verification receipts fails;
14. provider without idempotency cannot be automatically retried from an uncertain
    state;
15. process restart reconstructs unresolved fences solely from durable state.

## Relationship to Discovery effect-envelope work

Historical Discovery exploration described a neutral effect-attempt envelope with:

- exact target/precondition;
- post-effect uncertainty;
- receipts/readback;
- reconcile-before-retry.

That is compatible with this design as an interchange surface only.

It must not become DriftGuard's authority source, retry policy, state machine, or
proof of provider application.

DriftGuard native evidence remains authoritative for DriftGuard semantics.

## Claim ceiling

This design can define a fail-closed future protocol for composing local durable
currentness with uncertain provider I/O.

It does not:

- authorize any protected effect;
- implement provider calls;
- establish provider honesty;
- establish distributed consensus;
- make SQLite a cross-host lock service;
- prove a provider supports idempotency;
- prove an effect happened;
- grant retry authority;
- prove behavioral recovery;
- authorize merge or deployment.

The key safety rule is:

**reserve and fence locally, record uncertainty before I/O, reconcile provider truth,
then finalize by exact CAS; never infer retry safety from silence or a generic
receipt.**
