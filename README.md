# DriftGuard

Monitor AI-model behavioral drift by pinning a versioned behavioral save-state, admitting independently sourced drift evidence, and deterministically deciding when the state should be reloaded.

DriftGuard does **not** claim to inspect hidden model state or prove identity continuity. It monitors observable behavior against an explicit contract.

## V1

V1 provides:

- immutable, SHA-256 digest-bound behavioral save-states;
- weighted multi-dimensional drift rather than one opaque similarity score;
- critical dimensions that cannot disappear inside an average;
- evidence source/version bindings and per-dimension independence requirements;
- fail-closed UNKNOWN results for missing, duplicate, under-independent, or ungoverned evidence;
- periodic reload decisions plus threshold-triggered reloads;
- cooldown behavior to prevent self-induced reload oscillation;
- deterministic restore packets bound to the exact save-state digest;
- SQLite persistence with monotonic session generations, turn ordering, state pinning, and append-only evaluation receipts;
- no third-party runtime dependencies.

See docs/HOSTILE_REVIEW_V1.md for the adversarial design pass and docs/ARCHITECTURE_V1.md for the contract.

## Quick start

```bash
python -m pip install -e .
python -m unittest discover -s tests -v

driftguard state-digest --state examples/save_state.json

driftguard evaluate \
  --state examples/save_state.json \
  --evidence examples/evidence.json \
  --db ./driftguard.db \
  --session demo \
  --turn 0 \
  --expected-generation 0
```

A RELOAD result contains the exact restore packet to deliver. Delivery, provider consumption, and post-reload behavioral recovery are separate effects and require separate verification.
