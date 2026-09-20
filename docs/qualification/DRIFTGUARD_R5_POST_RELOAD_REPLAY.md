# DriftGuard R5 — Post-Reload Behavioral Replay

Status: **CANDIDATE / SOURCE-ONLY / UNMERGED**

## Exact lineage

Base R4:

`e815c75ffccf469d9d1c09d58c0050798c8e4f53`

Executable + hostile-test subject:

`4621675714f1f45698178f27eba6f92fb7a532d3`

R5 is intentionally stacked on R4 directly. It does not depend on the separate Discovery effect-envelope experiment.

## Added native boundary

R4 already separated:

1. reload decision;
2. caller acknowledgement of downstream reload effect.

R5 adds a third native state:

3. digest-bound classification of the first post-acknowledgement behavioral replay.

A recovery verification binds:

- exact acknowledged reload ID;
- exact acknowledged reload-required evaluation digest;
- exact replay evaluation digest;
- pinned save-state digest;
- replay observation digest;
- replay evidence-set digest;
- replay turn;
- exact ledger generation.

The replay must be the first ledger mutation after acknowledgement and must remain the latest committed ledger mutation when verification is recorded. This prevents a caller from ignoring an early bad replay and cherry-picking a later clean observation.

## Status vocabulary

- `VERIFIED_STABLE`
- `NOT_STABLE`
- `UNKNOWN`

`VERIFIED_STABLE` is a behavioral statement only: the admitted first replay is below the warning threshold and has no critical-dimension breach.

It does **not** mean:

- the provider is honest;
- the provider actually consumed the restore packet;
- the reload caused the stable replay;
- hidden model state was restored;
- identity or consciousness was preserved.

## Scheduling separation defect caught during implementation

The first R5 classifier draft treated any replay with an operational `RELOAD` decision as not recovered.

That was wrong because DriftGuard intentionally separates behavioral evidence from reload scheduling. A replay may be behaviorally clean while an independent periodic reload is due.

Repair:

- recovery classification ignores the periodic reload clock and reload-decision cooldown;
- `UNKNOWN` is driven by failed/incomplete evidence admission;
- `NOT_STABLE` is driven by warning-or-worse behavioral drift or a critical breach;
- otherwise the replay is `VERIFIED_STABLE`, even if periodic policy independently requests another reload.

Regression:
`test_periodic_reload_clock_does_not_negate_stable_recovery`.

## Local exact-subject qualification

Environment:

- Windows
- Python 3.11
- isolated fresh checkout
- `PYTHONPATH` explicitly bound to that checkout

The explicit `PYTHONPATH` binding matters because the first attempted run discovered a pre-existing editable DriftGuard checkout elsewhere on the machine. That contaminated import path was rejected as qualification evidence; no code conclusion was drawn from it.

Clean exact-subject commands:

```text
python -m compileall -q src tests
python -m unittest discover -s tests -v
git diff --check e815c75ffccf469d9d1c09d58c0050798c8e4f53 HEAD
```

Result on executable/test head `4621675714f1f45698178f27eba6f92fb7a532d3`:

- compileall: PASS
- unittest: **46/46 PASS**
- diff-check: PASS

The suite includes:

- stable first replay -> VERIFIED_STABLE;
- incomplete first replay -> UNKNOWN;
- WARN/RELOAD behavioral replay -> NOT_STABLE;
- periodic-only reload does not negate stable behavioral recovery;
- acknowledgement evaluation itself cannot masquerade as post-reload replay;
- later clean replay cannot be cherry-picked after an earlier replay;
- replay must remain the latest mutation;
- acknowledgement can be recovery-verified only once;
- stale generation fails closed;
- `verify-recovery` CLI emits a digest-bound durable receipt.

## Remaining gates

Before any integration decision:

- hosted Ubuntu + Windows qualification of the final exact PR head;
- independent hostile exact-head review;
- preserve source/build/review/merge/runtime claims separately.

## Non-effects

No merge, deployment, provider call, reload delivery, credential/permission change, model mutation, Project Settings change, or other protected effect is performed or authorized by this candidate.
