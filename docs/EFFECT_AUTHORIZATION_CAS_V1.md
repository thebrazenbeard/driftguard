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

9. **Durable state is not dispatch authority.**
   Only the caller that wins the pre-dispatch CAS may receive the single-use
   dispatch permit. Observing `DISPATCH_UNCERTAIN` never grants a second caller
   permission to send.

10. **Verified application stays fenced until acknowledgement is consumed.**
    Provider-specific proof that the effect applied transitions the attempt to
    `VERIFIED_APPLIED_AWAITING_ACK`. It does **not** release the session/subject
    fence. Only the exact acknowledgement-consuming CAS may advance the reload
    anchor and release that fence.

11. **Permanent provider ambiguity is quarantine, not retry authority.**
    If the provider outcome cannot be proved applied or not-applied, V1 may mark
    the attempt `QUARANTINED_UNRESOLVED`. That state remains fenced, does not
    assert `NOT_APPLIED`, has no V1 operator-clear transition, and cannot authorize
    a successor attempt.

12. **One local SQLite transaction domain.**
    Every authoritative effect-attempt row, fence row, provider-verification binding,
    reload acknowledgement row, session row, evaluation row, and subject-currentness
    row used by a V1 CAS must be co-resident in the same DriftLedger SQLite database
    and mutated/read through the same SQLite connection for that transaction.
    A second SQLite file, sidecar ledger, or separately committed store cannot
    participate in an operation that V1 calls atomic.

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

## Storage topology and atomicity boundary

V1's local atomicity claim is deliberately narrower than a distributed transaction.

The authoritative effect-attempt protocol state must be stored in the **same
DriftLedger SQLite database file** that already contains the bound:

- `sessions`;
- `evaluation_events`;
- `reload_acknowledgements`;
- `subject_epochs` / subject-transition state.

The future effect-attempt schema may use additional tables for reservations, fences,
provider-verification receipts, dispatch events, and attempt-event history, but those
tables must be co-resident in that same database.

For every operation described here as one `BEGIN IMMEDIATE` CAS:

- exactly one DriftLedger SQLite connection opens the transaction;
- every predicate read that participates in admission is read through that
  connection;
- every local mutation that establishes the transition is written through that
  connection;
- the effect-attempt state transition and any session/acknowledgement/fence mutation
  commit or roll back together.

An implementation may expose a separate `EffectAttemptLedger` class or adapter as
an API boundary, but in V1 it may not own a separate SQLite file or independently
committed authoritative store for these transitions.

A sidecar database cannot safely provide the claimed atomic relationship between,
for example, `VERIFIED_APPLIED_AWAITING_ACK` and the session-generation/reload-
acknowledgement update. Two successful local commits are still two failure windows.

Provider network I/O remains outside the SQLite transaction. Provider truth is
represented locally only by the durable, exact provider-verification binding after
external readback has completed.

### Connection-scoped primitive requirement

The exact PR #31 base matters here.

At `9df4800d81ab2e937ffa97263b8095305a845661`,
`DriftLedger.reload_currentness_readback()` opens its own SQLite connection and
starts its own `BEGIN IMMEDIATE`. Public `validate_reload_directive()` calls that
method.

That behavior is correct for PR #31's standalone re-admission claim, but a future
`reserve_effect_attempt(...)` **must not** call the public validator and then open a
second transaction to write the reservation. That would recreate a validation-to-
reservation race after the first transaction closes.

Implementation therefore requires a connection-scoped internal primitive, for
example:

`_validate_reload_directive_in_tx(db, ...)`

or an equivalent exact helper that:

- receives the already-open DriftLedger connection;
- performs subject/evaluation/session/current-generation checks on that connection;
- returns the exact currentness/readback subject needed for reservation binding;
- never commits, rolls back, or opens a nested/fresh connection itself.

The public `validate_reload_directive()` may wrap that primitive in its own
standalone transaction for compatibility. The effect-reservation path must call the
connection-scoped primitive inside the same transaction that inserts the reservation
and fence.

The acknowledgement side has the same rule. The effect-aware acknowledgement
consumer must not call public `DriftLedger.acknowledge_reload()`, because that
method opens its own connection/transaction. Native acknowledgement validation and
mutation must be extracted into or implemented as a connection-scoped primitive on
the already-open effect-aware transaction.

The required atomicity is therefore not merely "same database"; it is **same database,
same connection, same transaction** for every local predicate and mutation in the
claimed CAS.

This requirement does not make SQLite a cross-host lock service and does not claim
distributed consensus. A future multi-host/shared-database design requires a
different concurrency/transaction contract.

## Proposed attempt state machine

The minimal conservative states are:

`RESERVED`

The exact directive/currentness tuple has acquired the durable effect fence. No
provider call may have happened yet. The fence is active.

`CANCELLED_BEFORE_DISPATCH`

The exact reservation was cancelled while still durably `RESERVED`, before any
dispatch CAS could issue a permit. Cancellation and fence release occur atomically.
This state is terminal. It never means provider non-application; it means only that
DriftGuard never consumed the local dispatch claim for this reservation.

`DISPATCH_UNCERTAIN`

The ledger records this state **before** network I/O. From this point onward the
provider call may or may not have occurred. The fence is active.

A process crash immediately after this write is intentionally treated as uncertain
rather than as safe-to-retry.

`READBACK_REQUIRED`

A response, timeout, crash recovery, or generic actuator receipt is insufficient to
prove the provider outcome. The fence remains active.

`VERIFIED_NOT_APPLIED`

A provider-specific authenticated readback proves that this exact attempt did not
apply. The transition into this state is the not-applied finalization CAS: it stores
the exact provider-verification binding and releases the fence atomically.
`VERIFIED_NOT_APPLIED` is terminal for this attempt. It does not itself authorize a
retry; a later attempt requires fresh PR #31 currentness re-admission and a new
reservation.

`VERIFIED_APPLIED_AWAITING_ACK`

A provider-specific authenticated readback proves application of this exact attempt.
This state is deliberately **not terminal** and remains fenced. It cannot be treated
as `CLOSED`, cannot authorize a new reservation, and cannot release subject/session
mutation. The generic layer still cannot manufacture a reload acknowledgement.

Only the exact acknowledgement-consuming transaction may move this state to
`CLOSED_ACKNOWLEDGED_APPLIED`.

`CLOSED_ACKNOWLEDGED_APPLIED`

The provider-applied attempt has been consumed by one valid native acknowledgement
transaction. The reload anchor/session generation advancement and fence release occur
atomically in that same transaction. This state is terminal and cannot be reused.

`QUARANTINED_UNRESOLVED`

Provider outcome is permanently or operationally irreconcilable. This state does
not assert application or non-application. The fence remains active indefinitely,
the attempt is not successor-eligible, and V1 defines no operator/admin reason-string
escape and no automatic retry path.

Allowed outcome transitions are therefore intentionally asymmetric:

- `RESERVED -> CANCELLED_BEFORE_DISPATCH`;
- `RESERVED -> DISPATCH_UNCERTAIN`;
- `DISPATCH_UNCERTAIN -> READBACK_REQUIRED`;
- `DISPATCH_UNCERTAIN|READBACK_REQUIRED -> VERIFIED_NOT_APPLIED`;
- `DISPATCH_UNCERTAIN|READBACK_REQUIRED -> VERIFIED_APPLIED_AWAITING_ACK`;
- `DISPATCH_UNCERTAIN|READBACK_REQUIRED -> QUARANTINED_UNRESOLVED`;
- `VERIFIED_APPLIED_AWAITING_ACK -> CLOSED_ACKNOWLEDGED_APPLIED`.

There is deliberately no timeout transition from an uncertain state to
`VERIFIED_NOT_APPLIED`.

Wall-clock expiry, provider idempotency-window expiry, process restart, or operator
choice must never manufacture retry authority.

## Reservation transaction

A future `reserve_effect_attempt(...)` operation should use one
`BEGIN IMMEDIATE` transaction and:

1. re-admit the exact reload directive through the connection-scoped PR #31
   currentness validator on this already-open transaction; do not call the standalone
   public validator and then reserve in a second transaction;
2. reject any unresolved reservation for that directive or bound
   session-generation/evaluation;
3. verify no incompatible effect fence already exists for the session/subject;
4. insert the immutable reservation at `RESERVED`;
5. read it back;
6. commit.

The unique constraints, not caller convention, must prevent duplicate live
reservations.

## Pre-dispatch cancellation CAS

A reservation that is still exactly `RESERVED` may be abandoned without provider
reconciliation because no dispatch claim has been consumed and no dispatch permit
has ever been issued.

Cancellation must use one `BEGIN IMMEDIATE` transaction that verifies:

- exact reservation id/digest;
- exact current state = `RESERVED`;
- exact directive/session/evaluation/state/subject binding;
- no dispatch event/permit-issuance record exists for the reservation;
- the same fence row being released belongs to this exact reservation.

Only then may it atomically:

1. transition `RESERVED -> CANCELLED_BEFORE_DISPATCH`;
2. release the fence;
3. append the terminal cancellation event;
4. read back the terminal receipt;
5. commit.

Cancellation from `DISPATCH_UNCERTAIN`, `READBACK_REQUIRED`,
`VERIFIED_APPLIED_AWAITING_ACK`, or `QUARANTINED_UNRESOLVED` is forbidden.
Once the dispatch CAS is consumed, reconciliation—not cancellation—is required.

`CANCELLED_BEFORE_DISPATCH` does not authorize replay of the old reservation. Any
later attempt requires fresh PR #31 currentness re-admission and a new reservation.

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

## Single-use dispatch permit

The durable state `DISPATCH_UNCERTAIN` is **not** itself permission to call the provider.

Otherwise, two processes could behave unsafely:

1. process A wins `RESERVED -> DISPATCH_UNCERTAIN`;
2. process B observes the durable `DISPATCH_UNCERTAIN` row;
3. both decide that the state authorizes dispatch;
4. both send the provider operation.

A future `begin_effect_dispatch(...)` operation must therefore combine the exact
status CAS with issuance of a **single-use dispatch permit** returned only to the
caller that won the CAS.

The permit should:

- be factory-gated;
- bind the exact reservation/attempt digest;
- bind the exact provider target and idempotency key;
- be accepted only by the provider adapter's dispatch entry point;
- never be reconstructed merely by reading the durable `DISPATCH_UNCERTAIN` row;
- never be reissued after process restart.

A process that loses the CAS receives no permit and therefore has no valid dispatch
path.

If the winning process crashes after the CAS but before sending the network request,
the permit disappears while durable state remains `DISPATCH_UNCERTAIN`.

That is intentional.

Recovery must reconcile provider state. It must not mint a replacement permit and
guess that the original request was never sent.

This converts the post-CAS crash window into conservative uncertainty rather than a
duplicate-dispatch opportunity.

## Durable effect fence

While a reservation is in any unresolved state, operations that would invalidate its
preconditions must fail closed.

At minimum, the fence applies to:

- subject-epoch transition for the bound subject;
- session generation movement that would supersede the directive;
- replacement of the session's last evaluation;
- any future effect attempt on the same directive/session-generation pair.

Fence-active states are exactly:

- `RESERVED`;
- `DISPATCH_UNCERTAIN`;
- `READBACK_REQUIRED`;
- `VERIFIED_APPLIED_AWAITING_ACK`;
- `QUARANTINED_UNRESOLVED`.

`VERIFIED_NOT_APPLIED` releases its fence only in the exact provider-verification
finalization transaction that proves non-application.

`VERIFIED_APPLIED_AWAITING_ACK` does **not** release its fence. Generic
`acknowledge_reload()` remains blocked by ordinary fence coverage. The sole
exception is the separately defined acknowledgement-consuming transaction below,
which validates the exact applied attempt and performs native acknowledgement,
reload-anchor/session-generation advancement, attempt closure, and fence release
atomically.

`QUARANTINED_UNRESOLVED` never releases its fence in V1.

## Fence coverage audit at the design base

At exact base `9df4800d81ab2e937ffa97263b8095305a845661`, runtime mutations that can invalidate a reservation are centralized in the ledger, but there is more than one path.

A future fence implementation must cover **all** relevant mutation entry points, not only reload acknowledgement.

Session-generation mutation paths observed at the design base include:

- `DriftLedger.evaluate_and_commit()`;
- `DriftLedger.acknowledge_reload()`;
- `DriftLedger.verify_recovery()`.

Monitored-subject currentness advances through:

- `DriftLedger.transition_subject_epoch()`.

The fence check must execute inside the same `BEGIN IMMEDIATE` transaction and on
the same DriftLedger SQLite connection used by each mutation path, before the
mutation can commit. The authoritative fence row therefore must be co-resident in
the same database; a separately committed sidecar fence is rejected.

A partial implementation is rejected. For example, blocking `acknowledge_reload()` while allowing `evaluate_and_commit()` to advance the same fenced session would defeat the reservation contract.

Legacy schema migration updates are initialization/migration behavior, not a supported concurrent runtime mutation path. Running schema migration concurrently with active effect attempts is outside this V1 design and should remain prohibited.

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
- whether the provider result is terminal for the exact operation/idempotency key,
  rather than merely "not currently observed";
- provider idempotency retention/replay semantics when relevant;
- raw-response digest/provenance sufficient for later audit.

A future digest-bearing `ProviderEffectVerification` should be factory-gated in the
same way as DriftGuard qualification, attestation, and PR #31 currentness receipts.

The provider adapter must document the strongest claim its evidence supports.

For a provider without trustworthy idempotency/readback, an uncertain attempt can
remain permanently non-retriable without explicit external recovery.

## Provider-verification finalization CAS

Provider verification does not directly manufacture native acknowledgement.

A future provider-verification finalizer should use one `BEGIN IMMEDIATE`
transaction and compare:

- reservation id/digest;
- reservation expected state;
- directive digest;
- session id/generation;
- evaluation digest;
- state digest;
- subject digest/epoch;
- current session generation and current subject epoch;
- provider-verification attempt binding;
- exact provider target/idempotency binding.

The finalizer then performs exactly one allowed transition.

For verified non-application:

- store the exact provider verification;
- atomically mark the attempt `VERIFIED_NOT_APPLIED`;
- atomically release its durable fence;
- do not create a reload acknowledgement;
- do not retry automatically;
- require fresh PR #31 currentness re-admission plus a new reservation for any later
  attempt.

For verified application:

- store the exact provider verification;
- atomically mark the attempt `VERIFIED_APPLIED_AWAITING_ACK`;
- **do not release the fence**;
- do not advance the reload anchor/session generation;
- do not create or infer a reload acknowledgement;
- block evaluate/commit, recovery verification, subject transition, and new effect
  reservation until the acknowledgement consumer succeeds.

For an outcome that cannot be authoritatively resolved:

- atomically mark the attempt `QUARANTINED_UNRESOLVED` only when the
  provider-specific recovery contract concludes that V1 has no authoritative
  applied/not-applied resolution path;
- preserve all uncertainty evidence;
- keep the fence active;
- do not assert `NOT_APPLIED`;
- do not mint/reissue a dispatch permit;
- do not authorize retry or a successor;
- provide no V1 reason-string/admin escape.

## Acknowledgement-consuming CAS

A verified applied effect is not closed merely because provider truth is known.

The only V1 path that may consume `VERIFIED_APPLIED_AWAITING_ACK` is a dedicated
effect-aware acknowledgement operation using one `BEGIN IMMEDIATE` transaction on
the same DriftLedger SQLite connection that owns the session, reload acknowledgement,
effect-attempt, provider-verification, and fence rows.

That transaction must verify, inside the same snapshot:

- exact reservation id and immutable reservation digest;
- exact current attempt state = `VERIFIED_APPLIED_AWAITING_ACK`;
- exact provider-verification digest and its applied outcome;
- exact reload directive id/digest;
- exact evaluation digest;
- exact state digest;
- exact monitored-subject digest/epoch;
- exact session id and the still-current fenced session generation;
- exact native acknowledgement identity/digest;
- that the acknowledgement belongs to this directive/evaluation/state/subject/session
  tuple and no other attempt;
- that no prior acknowledgement consumption already closed this attempt.

Only after every predicate matches may the transaction:

1. apply the native reload acknowledgement semantics through the connection-scoped
   acknowledgement primitive on this same SQLite connection;
2. advance the reload anchor/session generation exactly once;
3. transition the attempt to `CLOSED_ACKNOWLEDGED_APPLIED`;
4. release the effect fence;
5. persist/read back the resulting acknowledgement + closed-attempt binding;
6. commit.

Any failed predicate, storage error, or transaction rollback leaves the attempt
`VERIFIED_APPLIED_AWAITING_ACK` and the fence active.

The ordinary generic `acknowledge_reload()` entry point must therefore reject while
this fence exists. It cannot bypass the effect-attempt ledger. Only the exact
effect-aware consumer may perform the acknowledgement mutation under the same
transaction that closes the attempt and releases the fence.

Behavioral recovery remains a later evidence class after acknowledgement.

## Recovery after crash

Startup/recovery must enumerate every unresolved effect attempt before permitting
another attempt on the same fence domain.

Recovery rules:

- `RESERVED`: no provider call should have occurred; recovery may either resume
  toward the single dispatch CAS or execute the exact
  `RESERVED -> CANCELLED_BEFORE_DISPATCH` transaction. Cancellation is forbidden
  once the dispatch claim has been consumed;
- `CANCELLED_BEFORE_DISPATCH`: terminal; fence is already released by the exact
  pre-dispatch cancellation CAS and any later attempt starts from fresh currentness;
- `DISPATCH_UNCERTAIN`: reconcile against provider state before any retry;
- `READBACK_REQUIRED`: reconcile against provider state before any retry;
- `VERIFIED_APPLIED_AWAITING_ACK`: do not re-dispatch and do not release the
  fence; resume only the exact acknowledgement-consuming CAS;
- `VERIFIED_NOT_APPLIED`: attempt is terminal and fence is already released by
  its exact verification CAS; any later attempt starts from fresh currentness;
- `QUARANTINED_UNRESOLVED`: restore the fence from durable state and remain
  non-retriable/non-successor-eligible indefinitely under V1;
- `CLOSED_ACKNOWLEDGED_APPLIED`: attempt is terminal; later behavior/recovery
  evidence is separate.

No crash path silently converts uncertainty into non-application, application into
acknowledgement, or quarantine into retry authority.

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
15. process restart reconstructs unresolved fences solely from durable state;
16. two dispatchers race after one CAS winner: only the winner receives a dispatch
    permit and only one provider send path is valid;
17. direct construction or replay of a dispatch permit fails;
18. crash after dispatch CAS but before network send does not permit permit
    reissuance;
19. provider idempotency-window expiry does not manufacture retry authority;
20. a non-terminal "not currently observed" provider response cannot be promoted to
    verified non-application;
21. verified application transitions to `VERIFIED_APPLIED_AWAITING_ACK` and the
    fence still blocks evaluate/commit, recovery verification, subject transition,
    and a new effect reservation;
22. generic `acknowledge_reload()` cannot bypass an applied-awaiting-ack fence;
23. the exact acknowledgement consumer atomically advances the reload anchor/session
    generation, closes the attempt, and releases the fence exactly once;
24. wrong-attempt, wrong-verification, stale-generation, stale-subject, or replayed
    acknowledgement evidence fails with the fence still active;
25. injected acknowledgement transaction failure/rollback leaves
    `VERIFIED_APPLIED_AWAITING_ACK` intact and fenced;
26. verified non-application releases the fence only in the exact
    provider-verification CAS and still requires fresh currentness before a later
    reservation;
27. `QUARANTINED_UNRESOLVED` survives process restart, keeps the fence active,
    rejects successor reservation, and has no V1 operator/admin reason-string
    escape;
28. exact `RESERVED -> CANCELLED_BEFORE_DISPATCH` atomically releases the fence
    only when no dispatch claim/permit issuance exists;
29. cancellation after `DISPATCH_UNCERTAIN` is rejected and cannot be used as a
    reconciliation shortcut;
30. a cancelled pre-dispatch reservation cannot be replayed and any later attempt
    requires fresh currentness plus a new reservation;
31. effect-attempt/fence/provider-verification state stored in a separate SQLite file
    is rejected as non-conforming for any transition claimed atomic with session,
    acknowledgement, evaluation, or subject state;
32. acknowledgement consumption proves attempt closure, reload acknowledgement,
    session-generation advancement, and fence release commit or roll back together
    on one DriftLedger SQLite connection;
33. injected failure between those local writes rolls back the entire transaction
    with `VERIFIED_APPLIED_AWAITING_ACK` still authoritative and fenced;
34. reservation admission that validates through a separate PR #31 readback
    transaction and then writes the reservation in a second transaction is rejected;
35. effect-aware acknowledgement that calls public `acknowledge_reload()` on a
    separate connection is rejected;
36. connection-scoped validation plus reservation insertion are exercised under a
    concurrent session/subject writer and prove the writer cannot commit between
    validation and fence acquisition.

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
- provide atomicity across separately committed databases or sidecar ledgers;
- prove a provider supports idempotency;
- prove an effect happened;
- grant retry authority;
- prove behavioral recovery;
- authorize merge or deployment.

The key safety rule is:

**keep every authoritative local fence/attempt/session/acknowledgement transition in
one DriftLedger SQLite transaction domain; reserve and fence locally, record
uncertainty before I/O, reconcile provider truth, keep verified application fenced
until native acknowledgement is atomically consumed, and quarantine permanently
ambiguous outcomes without retry authority. Never infer retry safety from silence,
generic receipts, timeout, restart, idempotency expiry, or operator choice.**
