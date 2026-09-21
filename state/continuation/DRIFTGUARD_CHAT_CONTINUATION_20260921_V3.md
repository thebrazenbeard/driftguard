# DRIFTGUARD CHAT CONTINUATION — 2026-09-21 V3

Treat this as a starting snapshot only. Fresh Git/CI/Bus evidence outranks it.
Exact-head review semantics apply. No protected effect authority is conveyed here.

## Canonical repository

`thebrazenbeard/driftguard`

Fresh-read main during this run:
`9894692ff6b549e4378bcc2b8ca46813ff18bf37`

## PR #31

Exact head:
`9df4800d81ab2e937ffa97263b8095305a845661`

Still open/draft and exact-head PASS_WITH_CLAIM_CEILING.
No merge was performed.

## PR #34 — resolved/frozen exact subject

Exact head:
`351b7a57b7213bd72cf881aa2bbaa449fb0fbc8f`

Hosted exact-head workflow:
`35611543932`

Results:
- Ubuntu success, 279 tests / OK;
- Windows success, 279 tests / OK;
- compileall PASS;
- diff-check PASS;
- executable smoke PASS.

Vera Bus result:
commit `f9f67c2f5a513fbbc5c7e36b297b349f40a81253`
file `messages/20260921-vera-unbound-to-bt2-driftguard-pr34-351b7a5-pass.md`

Disposition:
`PASS_WITH_CLAIM_CEILING`

Evidence-class caveat:
Vera explicitly calls this a hostile exact-head rereview, NOT independent
corroboration, because Vera had prior R11 exposure. Preserve that ceiling.

PR freeze comment id:
`5762460893`

Any head movement requires fresh qualification/review.

## PR #32 — current repaired effect-CAS design

Current exact head:
`8a81745b24278e6e2e948115ae6ff3ada56c250b`

Branch:
`bt2/effect-authorization-cas-design-v1-20260921`

Base:
`9df4800d81ab2e937ffa97263b8095305a845661`

Prior Vera-reviewed head:
`fb810b21612e6c1a935ff108602f76f4fbdaaf68`
with `CHANGES_REQUIRED_DESIGN`.

Current delta from that head:
- 5 commits ahead / 0 behind;
- docs-only;
- exactly `docs/EFFECT_AUTHORIZATION_CAS_V1.md`.

Repair lineage:
- `c79ed3f14f55388d07b8c0c48455004314ed926f`
  close applied/ack fence and ambiguity sequencing;
- `181f0c1ba60fcddc46a8042fe4684edf999ef9c1`
  define exact pre-dispatch cancellation CAS;
- `169bde3f640603f3dfb9797fc4eec23f7a529559`
  bind effect CAS to one DriftLedger transaction domain;
- `55c38a4213799de89c50ad45bcef7b70ff589741`
  require connection-scoped effect CAS primitives;
- `8a81745b24278e6e2e948115ae6ff3ada56c250b`
  require orthogonal protected-effect authority at dispatch.

### Current state-machine decisions

- verified provider application ->
  `VERIFIED_APPLIED_AWAITING_ACK`;
- applied-awaiting-ack remains fence-active and non-terminal;
- only one exact effect-aware acknowledgement-consuming `BEGIN IMMEDIATE` CAS may
  atomically apply native acknowledgement semantics, advance anchor/session
  generation, close the attempt as `CLOSED_ACKNOWLEDGED_APPLIED`, release the
  fence, persist/read back, and commit;
- failed/stale/replayed ack admission leaves the fence active;
- generic `acknowledge_reload()` cannot bypass the fence;
- verified non-application -> `VERIFIED_NOT_APPLIED` with fence release in the
  same exact provider-verification CAS, but no retry authority;
- permanently ambiguous provider outcome ->
  `QUARANTINED_UNRESOLVED`, indefinitely fenced, non-successor-eligible, no V1
  operator/admin reason-string escape;
- only pre-dispatch no-reconciliation release is
  `RESERVED -> CANCELLED_BEFORE_DISPATCH`;
- cancellation after `DISPATCH_UNCERTAIN` is forbidden.

### Atomicity/storage decision

All authoritative effect-attempt, fence, provider-verification, session,
evaluation, subject-currentness, and reload-ack rows used by a V1 atomic transition
must be co-resident in the same DriftLedger SQLite database and use the same SQLite
connection and transaction.

A separate/sidecar database cannot participate in an operation V1 calls atomic.

### Connection-scoped primitive decision

At exact PR31 base, `reload_currentness_readback()` opens its own connection and
public `validate_reload_directive()` calls it.

Therefore a future reservation CAS may not call public
`validate_reload_directive()` and then reserve in a second transaction. It needs
a connection-scoped validator/readback on the already-open reservation transaction.

Likewise the effect-aware ack consumer may not call public
`acknowledge_reload()` on a fresh connection. Native acknowledgement
validation/mutation must occur on the same effect-aware connection/transaction.

### Protected-effect authority decision

The single-use dispatch permit is mechanical only.

A real provider adapter requires both:

`CURRENT_PROTECTED_EFFECT_AUTHORITY AND EXACT_SINGLE_USE_DISPATCH_PERMIT`

before network I/O.

DriftGuard cannot manufacture protected-effect authority from durable attempt state,
DISPATCH_UNCERTAIN, receipts, idempotency keys, elapsed time, prior authority,
review, or CI. External authority alone also cannot bypass the attempt ledger.

The concrete external-authority mechanism remains outside this design and must be
specified before real provider dispatch can qualify.

## PR #32 exact-head qualification

Exact head:
`8a81745b24278e6e2e948115ae6ff3ada56c250b`

Workflow:
`35616086278`

Results:
- Ubuntu PASS, 246 tests / OK;
- Windows PASS, 246 tests / OK;
- compileall PASS;
- diff-check PASS;
- executable smoke PASS.

BT2 self-hostile exact-head review:
`PASS_WITH_CLAIM_CEILING`

GitHub review id:
`5268228739`

This is not independent corroboration.

## PR #32 Vera rereview routing

The earlier request for head `181f0c1...` is obsolete by head movement.

Current exact-head request is durable on Bus branch `bus/bt2-v1`:

commit:
`62e56114536c2a121ec889986d3690a30462c9ad`

file:
`messages/20260921-bt2-to-vera-driftguard-pr32-8a81745-design-rereview.md`

Requested review subject:
`8a81745b24278e6e2e948115ae6ff3ada56c250b`

Requested result:
`PASS_WITH_CLAIM_CEILING` or `CHANGES_REQUIRED_DESIGN`.

At this checkpoint, the latest observed `bus/vera-v2` head was
`e3fc73ecb5b3510e27b965ea05e95348d96e7af9`; no PR #32 response to the
8a81745 request had been observed yet.

## Lantern limitation in this execution

Project Lantern currentness was required by installed project rules for durable BT2
currentness, but WoWSQL project lookup and projected SQL execution both failed
internally. Lantern currentness is therefore NOT ESTABLISHED for this run.

No Supabase/Git/model-memory fallback was substituted as Lantern state.

The GitHub/Bus facts above are direct GitHub evidence, not claimed Lantern evidence.

## Next frontier

1. Fresh-read PR #32 and `bus/vera-v2`.
2. Consume only a Vera result explicitly bound to
   `8a81745b24278e6e2e948115ae6ff3ada56c250b`.
3. If PASS_WITH_CLAIM_CEILING: freeze that exact design evidence; do not merge.
4. If CHANGES_REQUIRED_DESIGN: repair only the concrete falsifier, rerun exact-head
   Ubuntu/Windows qualification, and request another exact-head rereview.
5. Do not treat design PASS as implementation/effect authorization.

## Authority

No merge, deploy, provider call, retry, reload, acknowledgement execution, runtime
installation, credential/provider/ruleset mutation, or other protected effect is
authorized.

Patrick retains protected-effect authority.
