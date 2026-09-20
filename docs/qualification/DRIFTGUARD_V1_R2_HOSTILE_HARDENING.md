# DriftGuard V1 R2 Hostile Hardening Qualification

Status: LOCAL BUILD / TEST / CLI SMOKE PASS; HOSTED EXECUTABLE-HEAD CI PASS; FINAL DOCUMENTATION-HEAD CI PENDING.

## Exact ancestry

- repository: `thebrazenbeard/driftguard`
- base main: `2772aff77929ef1310b8bcf0b5103c466c8c8010`
- design commit: `d0feefe102636035899ad1126df141e5df1a067c`
- initial executable candidate: `fda5343c5e92951e91ad083d10084a3a33797984`
- cleanup head: `69ccec5f5aadd9f0b3cc1653778de79f1e9a0a4d`
- frozen RED: `8b34d488eb32281b7fa60a830f7d4d92dc385404`
- executable repair head: `5284c94acf04af87c427564dfc3fdf560dcce695`

## Frozen RED

Commit `8b34d488eb32281b7fa60a830f7d4d92dc385404` added a hostile regression proving that the initial V1 ledger advanced its reload clock when it merely *decided* to reload.

Observed failure:

`last_reload_turn = 5` after a periodic reload decision at turn 5, even though no downstream restore effect had been established.

Disposition:

`RELOAD_DECISION_EFFECT_CONFLATION = FAIL / CHANGES_REQUIRED`

The failed exact subject remains in history.

## Repair

Executable head `5284c94acf04af87c427564dfc3fdf560dcce695` separates:

- `restore_anchor_turn`: session-start or acknowledged restore effect anchor;
- `last_reload_decision_turn`: decision/cooldown state.

A reload decision no longer advances the restore anchor.

A digest-bound explicit reload acknowledgement is the only mutation path that advances the restore anchor. It binds exact:

- session;
- state digest;
- evaluation digest;
- turn;
- expected generation.

The acknowledgement is intentionally classified as a caller assertion of downstream consumption, not behavioral proof.

## Additional hostile hardening on the repair head

### Stale-clean-evidence replay

Evidence now binds exact:

- save-state digest;
- observation-byte digest;
- turn index.

State, observation, or turn mismatch fails closed to `UNKNOWN`.

### Evaluator authority laundering

Probe sources are part of the save-state digest and bind:

- exact source ref/version;
- maximum independence class;
- exact dimensions the source may judge.

Cross-dimension use and independence overclaim both fail closed.

### Evidence-denial against periodic reload

Epistemic decision and operational reload directive are separate.

A periodic reload may set `reload_required=true` while evidence status remains `UNKNOWN`. Missing evidence can no longer suppress scheduled restoration.

### Legacy state migration

The original V1 conflated `last_reload_turn` cannot be safely promoted into a confirmed restore effect.

Migration therefore uses the legacy session's first turn as the restore anchor and treats a later legacy reload value only as a prior decision timestamp.

### Parser hardening

CLI JSON rejects duplicate object keys and non-finite numeric constants.

Probe dimension scope must be a real JSON array rather than a string coerced into character entries.

## Local exact-head qualification

On exact executable head `5284c94acf04af87c427564dfc3fdf560dcce695`:

- `python -m compileall -q src tests`: PASS
- `python -m unittest discover -s tests -v`: **33/33 PASS**
- `git diff --check`: PASS
- executable example CLI smoke: PASS
- example state digest: `40f9ad63572843acdc10c5065a3b248b31cb01502aa681f8a879937c5ab12740`
- example observation digest: `37f991657e3eb8442fe7eb044db9f7f44d4efa600209d36bacf3fd3f7436f6c2`

## Hosted CI

GitHub Actions run for exact executable head `5284c94acf04af87c427564dfc3fdf560dcce695`:

- run: `35473429285`
- status: `completed`
- conclusion: `success`
- exact head: `5284c94acf04af87c427564dfc3fdf560dcce695`

Do not carry this hosted PASS forward onto a changed documentation head without a fresh exact-head run.

## Remaining trust boundaries

This repair does not establish:

- cryptographic proof that a claimed evaluator identity is genuine;
- proof that claimed evaluator independence was actually achieved;
- automatic scoring of raw conversation text;
- downstream provider delivery/consumption of a restore packet;
- post-reload behavioral recovery;
- tamper-evident protection against an administrator who can rewrite the local SQLite database;
- personal identity, consciousness, or hidden-state continuity.

## Integration status

Draft PR #1 only.

No merge, deployment, provider mutation, credential change, or other protected effect is authorized or implied.
