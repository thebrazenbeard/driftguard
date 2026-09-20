# DriftGuard R8 Sequential CUSUM V1

Status: stacked candidate on R7 subject-identity head `fa7bfa901c2c1f1620f3225507d07153c4c08f04`.

## Purpose

R6 creates calibrated, durable per-dimension behavioral score streams.

R7 prevents model/provider/instruction/tool/runtime identity changes from contaminating one subject epoch.

R8 adds a diagnostic sequential detector over those score streams.

The goal is to detect sustained upward movement that may remain below any single-point reload threshold.

R8 does not actuate reloads.

## Detector

R8 implements a one-sided upper CUSUM independently for every governed behavior dimension.

For a score `x_t`, frozen baseline mean `mu`, allowance `k`, and previous statistic `S_(t-1)`:

`S_t = max(0, S_(t-1) + x_t - mu - k)`

A dimension alarms when its CUSUM reaches its frozen alarm threshold `h`.

The implementation rounds the accumulated statistic to 12 decimal places only to canonicalize insignificant floating representation noise.

## Precommitted detector specification

A `SequentialDetectorSpec` binds:

- detector ID;
- ledger session ID;
- exact save-state digest;
- exact R6 measurement digest;
- exact R7 subject configuration digest;
- exact subject epoch;
- detector calibration ref/version;
- detector calibration SHA-256 digest;
- maximum consecutive UNKNOWN evaluations;
- maximum allowed turn gap;
- for every behavior dimension:
  - baseline mean;
  - allowance;
  - alarm threshold.

Changing any governed detector parameter changes the detector-spec digest.

The calibration digest proves which calibration artifact was named. It does not prove that the calibration procedure was scientifically valid.

## Future-only registration

Detector registration is a precommitment operation.

Registration anchors at the latest durable evaluation event that already exists for the session.

That anchor is never processed by the detector.

Only evaluation events created after registration are eligible.

The registration receipt binds:

- detector spec digest;
- session generation at registration;
- anchor evaluation event ID;
- anchor evaluation digest;
- subject digest;
- subject epoch.

This prevents selecting CUSUM parameters after viewing historical outcomes and then claiming the historical replay was prospective detection.

## Exact-order processing

The detector processes the exact next durable evaluation event after its current frontier.

A caller cannot skip an inconvenient event and process a later one.

Every detector advance is generation compare-and-swap protected.

Sequential detection events are append-only receipts.

## Session continuity

R8 binds sequential continuity to the DriftGuard session generation.

After each consumed evaluation, the detector expects the next evaluation's `generation_before` to equal the preceding evaluation's `generation_after`.

A reload acknowledgement, recovery verification, or other session mutation between sequential observations therefore creates a session-generation discontinuity.

That discontinuity permanently marks the detector run `INVALID_GAP`.

This is intentionally conservative. A behavioral process interrupted by an intervention is not silently treated as the same uninterrupted CUSUM stream.

## Turn-gap continuity

The detector spec freezes `max_turn_gap`.

For each consumed evaluation:

`turn_gap = current_turn - previous_consumed_turn`

If `turn_gap > max_turn_gap`, the detector becomes `INVALID_GAP`.

Turn gap is a logical turn-count bound, not elapsed wall-clock time.

## UNKNOWN evidence budget

UNKNOWN behavioral evaluations are consumed in order but do not update the CUSUM statistic or observation count.

The detector freezes `max_consecutive_unknown`.

If the consecutive UNKNOWN count exceeds that budget, the detector becomes `INVALID_GAP` irreversibly.

This prevents prolonged missing/invalid evidence from being used as a silent anti-alarm strategy.

If a CUSUM alarm was already latched, an UNKNOWN evaluation does not erase that alarm while the UNKNOWN budget remains valid.

## Alarm latching

Once a dimension alarms, its alarm remains latched for the life of that detector run.

Later low scores do not silently reset the alarm.

There is no in-place detector reset.

Only one governed sequential detector may bind one DriftGuard session.

Changing detector ID does not create a clean slate inside the same session.

Starting another session creates an explicit new time-series boundary; it does not erase the durable alarm history of the prior session.

## Subject and measurement binding

Sequential registration and advancement require:

- `CALIBRATED_QUORUM` measurement mode;
- exact save-state digest;
- exact R6 measurement digest;
- exact R7 subject configuration digest;
- exact R7 subject epoch;
- latest/current subject epoch.

A superseded subject epoch cannot continue a detector.

The detector dimension set must exactly match the save-state dimension set.

## Diagnostic only

`SequentialStatus.ALARM` has no actuator side effect.

It does not:

- set the session reload clock;
- acknowledge a reload;
- build a reload directive;
- claim behavioral relapse was proven;
- prove model-weight drift;
- prove a causal source of the score shift.

A future governed policy may decide what to do with a sequential alarm. R8 itself deliberately does not.

## Statistical claim ceiling

A passing R8 implementation proves deterministic execution of the specified recurrence and governance rules.

It does not establish:

- that the baseline mean is correct;
- that the allowance or alarm threshold has a desired average run length;
- a calibrated false-positive rate;
- statistical independence of observations;
- stationarity or IID assumptions;
- absence of autocorrelation;
- evaluator stationarity;
- calibration validity merely because its digest is frozen;
- causality;
- superiority of CUSUM over Page-Hinkley, EWMA, ADWIN, or another method.

Those properties require empirical/simulation calibration against the actual measurement process.

## Why CUSUM first

CUSUM is deliberately small and inspectable.

It gives DriftGuard a deterministic test bed for:

- prospective sequential precommitment;
- anti-cherry-pick ordering;
- durable detector state;
- missing-evidence governance;
- intervention-boundary invalidation;
- alarm latching;
- calibration binding.

Those controls remain useful even if the eventual statistical detector is replaced.

## Next frontier

The next statistical task is not adding another algorithm immediately.

It is calibration qualification:

- simulate or replay representative stable score processes;
- characterize false-alarm behavior under autocorrelation and evaluator noise;
- characterize detection delay for known synthetic shifts;
- validate UNKNOWN and turn-gap budgets;
- compare CUSUM with alternatives on the same frozen observation corpus.

Until that qualification exists, R8 should be described as a governed sequential diagnostic mechanism, not a statistically validated model-drift detector.
