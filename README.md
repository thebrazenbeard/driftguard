# DriftGuard

Monitor AI-model behavioral drift by pinning a versioned behavioral save-state, admitting independently sourced drift evidence, and deterministically deciding when the state should be reloaded.

DriftGuard does **not** claim to inspect hidden model state or prove identity continuity. It monitors observable behavior against an explicit contract.

## V1

V1 provides:

- immutable, SHA-256 digest-bound behavioral save-states;
- weighted multi-dimensional drift rather than one opaque similarity score;
- critical dimensions that cannot disappear inside an average;
- evaluator source/version authority scoped to exact dimensions and maximum independence;
- evidence bound to the exact save-state, observation bytes, and turn;
- fail-closed UNKNOWN status for missing, duplicate, stale, under-independent, overclaimed, or ungoverned evidence;
- a reload directive that is separate from epistemic status, so periodic reload cannot be disabled by making evidence UNKNOWN;
- periodic reload plus threshold-triggered reload;
- decision cooldown without confusing a reload decision for a restore effect;
- explicit digest-bound reload acknowledgements as the only path that advances the restore anchor;
- digest-bound post-reload recovery verification that accepts only the first committed replay after an acknowledgement and separates behavioral stability from reload scheduling;
- deterministic restore packets bound to the exact save-state digest;
- SQLite persistence with monotonic generations, turn ordering, state pinning, legacy-safe migration, and append-only receipts;
- no third-party runtime dependencies.

See `docs/HOSTILE_REVIEW_V1.md` for the adversarial design pass and `docs/ARCHITECTURE_V1.md` for the contract.

## Quick start

```bash
python -m pip install -e .
python -m unittest discover -s tests -v

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
```

When `reload_required` is true, the result contains the exact restore packet that should be delivered. That is a directive, not proof of delivery or behavioral recovery.

After a downstream loader has actually consumed that exact packet, create a reload acknowledgement bound to the returned `evaluation_digest`, `state_digest`, and `turn_index`, then persist it:

```bash
driftguard ack-reload \
  --state examples/save_state.json \
  --ack ./reload-ack.json \
  --db ./driftguard.db \
  --session demo \
  --expected-generation <current-generation>
```

The acknowledgement records a caller assertion that the reload effect occurred. It still does not prove provider honesty or behavioral recovery.

For a stronger behavioral claim, commit the **first post-acknowledgement observation** through the normal `evaluate` path, then bind that exact evaluation as the recovery replay:

```bash
driftguard verify-recovery \
  --state examples/save_state.json \
  --db ./driftguard.db \
  --session demo \
  --ack-id <accepted-ack-id> \
  --replay-evaluation-digest <first-post-ack-evaluation-digest> \
  --expected-generation <current-generation>
```

Recovery status is one of `VERIFIED_STABLE`, `NOT_STABLE`, or `UNKNOWN`. A verified result means the first admitted post-reload replay is behaviorally within the save-state's stable policy. It does **not** prove the reload caused that behavior, and periodic reload scheduling remains a separate operational clock.

## Evidence model

A probe source is part of the save-state and declares:

- exact source reference + version;
- maximum independence it may claim;
- exact behavioral dimensions it may judge.

Each V1 evidence item must use exactly one governed probe source and bind itself to the exact save-state digest, observation digest, and turn. This prevents stale clean evidence, cross-dimension evaluator promotion, and independence-class laundering at the admission boundary.

## Current claim ceiling

DriftGuard V1 proves deterministic admission, scheduling, fencing, reload-decision behavior, and digest-bound classification of the first post-acknowledgement behavioral replay for its supplied inputs. It does not prove that a claimed external evaluator was genuinely independent, that a downstream provider actually applied a restore packet, that the reload caused a later stable replay, or that the model's hidden state/identity remained unchanged.
