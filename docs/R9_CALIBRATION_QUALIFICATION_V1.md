# DriftGuard R9 Calibration Qualification V1

Status: restacked candidate on R8-over-repaired-R7 sequential-diagnostic head `dbd59a1a8c1c439cb90b7feae733c11128747057`.

## Purpose

R8 gives DriftGuard a governed sequential CUSUM mechanism.

R9 addresses the next problem: the detector parameters are not scientifically meaningful merely because they are frozen.

A baseline mean, allowance, and alarm threshold must be qualified against an explicit score corpus and explicit acceptance criteria before DriftGuard can make a bounded calibration claim.

R9 is an offline deterministic qualification layer.

It does not mutate runtime detector state and it does not authorize a reload.

## Frozen corpus

A `CalibrationCorpus` binds:

- corpus ID;
- version;
- corpus role;
- every trajectory;
- every trajectory family;
- every observation score;
- stable/shifted regime labels;
- shift index;
- expected shifted dimensions.

The corpus digest changes if any governed observation or label changes.

Trajectory order is canonicalized by trajectory ID, so file/list ordering does not create a new scientific subject.

## Corpus roles

R9 has two corpus roles:

- `DESIGN`;
- `HOLDOUT_QUALIFICATION`.

A DESIGN corpus may be characterized, but it can never produce a qualification PASS.

Its disposition is always:

`DESIGN_CHARACTERIZATION`

Only an exact `HOLDOUT_QUALIFICATION` corpus can produce PASS or FAIL.

This distinction is semantic and digest-bound.

The code does not prove that a holdout corpus was truly unseen by the parameter designer. Temporal precommitment and access control require external governance such as Git history, signed commitments, or another trusted timestamped store.

## Frozen qualification plan

A `CalibrationPlan` binds:

- plan ID;
- exact R8 detector-spec digest;
- exact corpus digest;
- exact expected corpus role;
- exact family policies.

Every family policy freezes:

- minimum stable trajectory count;
- minimum shifted trajectory count;
- exact stable exposure horizon;
- exact pre-shift horizon;
- exact post-shift horizon;
- maximum stable false-alarm rate;
- maximum pre-shift false-alarm rate;
- maximum wrong-dimension alarm rate;
- minimum detection rate;
- maximum mean detection delay.

Changing any acceptance criterion changes the plan digest.

## Why exact horizons matter

False-alarm probability depends on exposure.

A stable trajectory with three observations and a stable trajectory with 3,000 observations are not equivalent tests of a sequential detector.

R9 therefore requires exact exposure horizons for each family.

A stable trajectory must have exactly the frozen stable horizon.

A shifted trajectory must have exactly the frozen pre-shift and post-shift horizons.

Horizon mismatch is a qualification failure.

This prevents artificially short stable windows from inflating apparent specificity.

## Family stratification

Every corpus family must have an exact matching family policy.

The set of corpus families and plan families must be identical.

Qualification is evaluated independently for each family.

One good family cannot compensate for a failing family.

This is intended for regimes such as:

- low-noise evaluator output;
- autocorrelated output;
- bursty/noisy output;
- different task distributions;
- different context-exposure profiles;
- different evaluator ensembles.

R9 does not define which families are representative. That remains a corpus-design obligation.

## Stable false-alarm qualification

For every stable trajectory, R9 replays the exact R8 CUSUM recurrence from zero.

Any alarm is a stable false alarm.

R9 records:

- stable trajectory count;
- stable false-alarm count;
- false-alarm rate;
- first-alarm run lengths;
- 95% Wilson confidence interval.

The acceptance check uses the **upper 95% Wilson bound**, not merely the point estimate.

Therefore:

`0 false alarms / 3 trajectories != demonstrated 0% false-alarm behavior`

Small sample size remains visible as wide uncertainty and can fail qualification.

## Shift qualification

For every shifted trajectory:

- an alarm before the declared shift is a pre-shift false alarm;
- no alarm is a missed detection;
- an alarm after shift counts as detection if the first alarm includes an expected shifted dimension;
- any unrelated dimension present on that same first post-shift alarm is also recorded as a wrong-dimension alarm;
- therefore a mixed first alarm containing both expected and unrelated dimensions counts as both a detection and a collateral wrong-dimension alarm;
- an alarm on only unrelated dimensions is recorded as a wrong-dimension alarm and is not counted as a successful detection.

R9 records:

- pre-shift false-alarm rate + 95% Wilson interval;
- wrong-dimension alarm rate + 95% Wilson interval;
- detection rate + 95% Wilson interval;
- detection delays;
- mean detection delay.

Acceptance uses:

- the **upper** Wilson bound for pre-shift false alarms;
- the **upper** Wilson bound for wrong-dimension alarms;
- the **lower** Wilson bound for detection rate;
- the observed mean delay against its frozen maximum.

## Confidence-bound semantics

Wilson bounds are used because point estimates alone can create false confidence at small sample sizes.

R9 uses a fixed two-sided 95% Wilson interval with:

`z = 1.959963984540054`

This does not make the trajectories statistically independent.

If trajectories are correlated or duplicated, the confidence interpretation may be optimistic.

Corpus independence remains a scientific-governance requirement outside the code's current proof.

## First-alarm semantics

R9 evaluates the first alarm produced by a trajectory.

For stable trajectories, the first alarm determines the false-alarm run length.

For shifted trajectories:

- first alarm before shift => pre-shift false alarm;
- first alarm after shift containing an expected shifted dimension => detection;
- any unrelated dimension on that same post-shift first alarm => wrong-dimension alarm;
- mixed expected + unrelated first alarms therefore count in both detection and wrong-dimension statistics;
- first alarm after shift only on unrelated dimensions => wrong-dimension failure without detection.

This avoids laundering an early false alarm by pointing to a later correct alarm.

## Deterministic reuse of R8

R9 calls the exact R8 `advance_cusum()` recurrence.

It does not maintain a separate statistical implementation.

The calibration result therefore qualifies the exact deterministic recurrence used by the runtime candidate, subject to the exact detector-spec digest.

## Receipt integrity hardening

R9 qualification objects are themselves part of the evidence surface.

A SHA-256 digest must not authenticate impossible caller-supplied statistics.

Therefore:

- `BinomialEstimate` recomputes the exact 95% Wilson rate/interval from
  `successes + trials` and rejects contradictory direct construction;
- `CalibrationFamilyMetrics` validates shifted trial-count agreement,
  mutually exclusive first-alarm outcome counts, stable-alarm run-length counts,
  detection-delay counts/mean, wrong-dimension counts, horizon counts, and failure
  tuple shape;
- `CalibrationQualificationReceipt` is factory-gated and can only be emitted by
  `qualify_calibration()` through the governed calculation path;
- the receipt still validates corpus-role/disposition/reason coherence and canonical
  unique family ordering.

This is an API-governance boundary, not a hardware/process sandbox. Python code with
arbitrary access to module-private implementation details remains outside the claim
ceiling.

## Qualification receipt

A `CalibrationQualificationReceipt` binds:

- plan digest;
- corpus digest;
- detector-spec digest;
- corpus role;
- disposition;
- family metrics, including explicit mixed target/wrong-dimension overlap counts;
- failure reasons.

Possible dispositions:

- `DESIGN_CHARACTERIZATION`;
- `PASS`;
- `FAIL`.

A HOLDOUT PASS requires every family to satisfy every frozen criterion.

## What PASS means

An R9 PASS means only:

> the exact R8 detector specification satisfied the exact frozen R9 family criteria
> on the exact frozen HOLDOUT_QUALIFICATION corpus and horizons.

It does not mean:

- the corpus represents production;
- the holdout was genuinely unseen;
- samples or trajectories are independent;
- production scores are stationary;
- the evaluator is stationary;
- the detector has a universal false-alarm probability;
- the same parameters generalize to another model, subject epoch, measurement scale, or task distribution;
- the detected shift is causal model drift;
- a reload should occur.

## P-hacking boundary

R9 makes post-hoc mutation detectable because these objects move their digests:

- corpus observations;
- regime/shift labels;
- detector parameters;
- acceptance thresholds;
- exposure horizons;
- corpus role.

R9 does not itself prove that the plan digest existed before the analyst saw the holdout outcomes.

That requires an externally timestamped commitment.

## Non-goals

R9 does not yet:

- synthesize random calibration corpora;
- tune detector parameters automatically;
- choose between CUSUM, Page-Hinkley, EWMA, or ADWIN;
- model serial correlation explicitly;
- estimate effective sample size;
- calibrate UNKNOWN-budget behavior statistically;
- calibrate logical turn-gap behavior statistically;
- prove production representativeness;
- couple a qualification result to runtime control.

## Next frontier

After exact-head qualification and independent review, the strongest next statistical frontier is comparative detector validation on the same frozen corpus.

Candidate detectors should be judged against identical:

- corpus;
- family splits;
- horizons;
- acceptance criteria;
- shift labels;
- confidence treatment.

Only then is it meaningful to ask whether CUSUM should remain DriftGuard's sequential mechanism or be replaced/augmented by Page-Hinkley, EWMA, adaptive-window methods, or a state-space approach.
