# Behavioral Save-State Capture Protocol V1

A DriftGuard save-state is a behavioral contract, not a transcript dump and not a claim about hidden model state.

## 1. Define the subject

Name the behavioral referent being preserved and the scope in which it should remain stable. Separate enduring invariants from task-specific content.

Good candidates include truth/evidence discipline, authority boundaries, response style, safety behavior, stable role commitments, and explicit user-governed preferences.

Do not encode a desired answer to future questions as a behavioral invariant.

## 2. Collect baseline evidence

Use multiple examples across materially different contexts. Preserve source/provenance for each example.

Include counterexamples that demonstrate what the behavior must *not* become. This makes a dimension falsifiable instead of aspirational.

Do not treat model self-description as sufficient evidence of its own behavior.

## 3. Write dimensions before thresholds

For each dimension define:

- a unique ID;
- behavioral description;
- whether failure is critical;
- relative weight;
- minimum evidence independence.

Prefer observable behavior. Avoid dimensions such as "is still the same person" that cannot be operationalized from output behavior.

## 4. Register probe authorities

Every evaluator/probe source must be frozen into the save-state with:

- exact source reference;
- exact source version;
- maximum independence class;
- exact dimensions it may judge.

A source should receive the smallest scope it needs. A style evaluator should not automatically receive authority to judge truthfulness or safety.

Critical dimensions should normally have at least one probe source whose independence ceiling meets the strongest available evaluation method.

## 5. Separate probes from restore text

Restore text should state the behavior to preserve.

Probe prompts, holdout examples, adversarial fixtures, scoring keys, and evaluator implementation details should remain outside the restore payload when exposing them would make benchmark gaming easier.

The save-state may bind those probe sources by version without revealing their hidden contents to the monitored model.

## 6. Calibrate thresholds

Do not choose thresholds solely because the numbers look reasonable.

Run baseline examples, benign distribution-shift examples, known-drift examples, and adversarial examples. Record false reloads, missed drift, and uncertainty rates.

Set warning, reload, and critical thresholds against that calibration evidence. Preserve the calibration subject/version separately from the runtime save-state.

## 7. Freeze the state

Once accepted:

1. serialize the save-state canonically;
2. compute its SHA-256 digest;
3. record its version and provenance;
4. start monitoring sessions pinned to that exact digest.

Never mutate a state in place. Intentional behavioral evolution creates a successor version.

## 8. Prevent baseline poisoning

Runtime observations do not automatically become baseline truth.

A drifted or adversarial conversation must not be able to rewrite the state it is being measured against. Candidate evolution should be reviewed outside the active session and promoted as a new version only through an explicit governance decision.

## 9. Use hidden/rotating holdouts

A fixed public probe suite is vulnerable to benchmark overfitting.

Maintain multiple semantically equivalent probe families and hidden holdouts where practical. Rotate evaluator contexts and, for critical dimensions, use externally independent evaluation when available.

Rotation must preserve the source/version binding model so new probes do not silently inherit authority.

## 10. Requalify successor states

A new save-state version is not "better" because it is newer.

Replay the old baseline cases, known-drift cases, adversarial cases, and relevant new behavior. Compare false-positive/false-negative behavior before promoting it for use.

## Claim ceiling

A well-captured behavioral save-state gives DriftGuard a stable observable reference. It still does not prove personal identity, subjective continuity, or inaccessible internal-state equivalence.
