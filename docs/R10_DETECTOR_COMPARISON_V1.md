# DriftGuard R10 Cross-Detector Comparison V1

Status: restacked candidate on hardened R9 v2 head
`e555bc78ba99065482e1c420bdc580858a16d18a`.

## Purpose

R8 introduced a governed one-sided CUSUM diagnostic.

R9 introduced frozen-corpus calibration qualification for that exact recurrence.

R10 asks the next question:

> is CUSUM actually preferable to other simple sequential mean-shift detectors on
> the same governed behavioral score subject?

R10 compares exactly three frozen candidates:

- the exact R8 CUSUM specification;
- one Page-Hinkley candidate;
- one EWMA candidate.

R10 is a comparison layer, not a model-selection authority.

## Literature lineage

The detector families are established statistical process/change-detection ideas:

- E. S. Page, "Continuous Inspection Schemes," Biometrika 41(1/2), 1954,
  DOI 10.1093/biomet/41.1-2.100;
- S. W. Roberts, "Control Chart Tests Based on Geometric Moving Averages,"
  Technometrics 1(3), 1959, DOI 10.1080/00401706.1959.10489860;
- Page-Hinkley-style online mean-shift detection uses a running mean, cumulative
  deviation and tracked minimum to detect sustained positive excursions.

R10 does not claim its parameterizations reproduce every historical control-chart
assumption or analytical guarantee from those papers. The exact implemented
recurrences and empirical R9 qualification remain authoritative.

ADWIN is intentionally not included in R10. Adaptive-window algorithms introduce a
different time-scale/statistical contract and deserve a separate exact implementation
and review rather than being forced into this threshold-comparison surface.

## Exact shared subject

A `DetectorComparisonPlan` binds:

- comparison ID;
- exact R9 `CalibrationPlan.digest`;
- exact calibration corpus digest;
- exact candidate set.

The R9 calibration plan already binds:

- exact R8 CUSUM detector-spec digest;
- exact corpus digest and role;
- exact family policies;
- minimum trajectory counts;
- stable/pre-shift/post-shift horizons;
- false-alarm/detection criteria.

All three candidates are therefore judged against the same corpus, labels, horizons
and acceptance semantics.

## Candidate multiplicity

R10 V1 requires exactly one candidate for each algorithm:

- CUSUM;
- PAGE_HINKLEY;
- EWMA.

Multiple parameterizations of the same algorithm are rejected.

This prevents a same-HOLDOUT hyperparameter sweep such as testing fifteen EWMA
settings and reporting only the best one.

It does not prove that hidden parameter sweeps did not occur before the candidate
artifact was frozen.

## CUSUM baseline

The CUSUM candidate does not contain a second implementation.

It binds the exact R8 `SequentialDetectorSpec.digest`.

R10 obtains CUSUM qualification by invoking R9's exact
`qualify_calibration()` path.

A hostile regression requires the CUSUM candidate result to equal the R9 result for:

- disposition;
- family metrics;
- failure reasons.

This makes R9 the parity oracle for the incumbent detector.

## Page-Hinkley candidate

For every dimension R10 freezes:

- delta;
- positive alarm threshold;
- burn-in.

The implemented upward-shift recurrence is:

1. update the running mean;
2. add `x_t - mean_t - delta` to cumulative deviation;
3. track the minimum cumulative deviation;
4. compute positive excursion:
   `PH_t = cumulative_t - minimum_t`;
5. alarm when `PH_t > threshold`.

R10 V1 requires `burn_in = 1`.

The R9 corpus has no separate unscored warm-up segment. Allowing a candidate burn-in
longer than one would let it suppress alarm eligibility during the frozen stable or
pre-shift exposure and manufacture better apparent specificity.

A future corpus format may add an explicit warm-up region. Until then every governed
R9 observation is alarm-eligible.

## EWMA candidate

For every dimension R10 freezes:

- baseline mean;
- smoothing factor;
- positive alarm threshold;
- burn-in.

The recurrence is:

`z_t = smoothing * x_t + (1 - smoothing) * z_(t-1)`

with `z_0 = baseline_mean`.

R10 alarms when:

`z_t - baseline_mean >= alarm_threshold`.

The smoothing factor must be within `(0, 1]`.

R10 V1 also requires `burn_in = 1` for the same exposure-fairness reason as
Page-Hinkley.

This is an empirically qualified EWMA-style upward detector, not a claim that the
threshold is an analytically derived Roberts control limit.

## Non-CUSUM parameter provenance

Page-Hinkley and EWMA candidates must bind:

- exact parameterization ref;
- exact parameterization version;
- SHA-256 digest of the parameterization artifact.

The digest proves which exact parameterization artifact was named.

It does not prove:

- that the artifact was frozen before HOLDOUT access;
- that no hidden tuning happened;
- who created it;
- why those parameters were chosen.

Those are temporal/governance claims outside R10's in-process proof.

## Shared R9 qualification semantics

Page-Hinkley and EWMA are evaluated with the same R9 family metrics as CUSUM:

- stable false-alarm rate + Wilson interval;
- pre-shift false-alarm rate + Wilson interval;
- wrong-dimension alarm rate + Wilson interval;
- target detection rate + Wilson interval;
- stable first-alarm run lengths;
- detection delays;
- mean detection delay;
- horizon violations.

The same family-policy thresholds apply.

One family cannot compensate for another.

The first alarm remains authoritative:

- alarm before shift => pre-shift false alarm;
- alarm after shift on an expected shifted dimension => detection;
- alarm after shift only on unrelated dimensions => wrong-dimension alarm;
- no alarm => missed detection.

## Receipt integrity hardening

R10 comparison receipts are part of the evidence surface and cannot be allowed to
authenticate internal contradictions.

Therefore:

- `DetectorCandidateResult` validates canonical unique family IDs and requires its
  disposition/reasons to match embedded family failures;
- `DetectorComparisonReceipt` is factory-gated and can only be created by
  `compare_detectors()`;
- the receipt recomputes the exact qualified candidate ID set from candidate
  dispositions;
- candidate IDs and algorithms must be canonical, unique, and cover exactly the
  declared R10 algorithm set;
- Pareto IDs must be canonical, unique, known, qualified, and exactly equal the
  Pareto set recomputed from the embedded family metrics;
- comparison disposition and reasons are recomputed from corpus role and the number
  of qualified candidates;
- `promotion_authorized` remains hard-coded false.

A digest therefore cannot be obtained over a receipt claiming, for example, that a
FAIL candidate is a qualified winner.

This is an API-governance boundary, not a hostile-process or hardware-security
boundary.

## Comparison disposition

The comparison receipt can report:

- `DESIGN_CHARACTERIZATION`;
- `NO_CANDIDATE_QUALIFIED`;
- `ONE_CANDIDATE_QUALIFIED`;
- `MULTIPLE_CANDIDATES_QUALIFIED`.

These are descriptions of R9 qualification outcomes.

They are not promotion decisions.

## No HOLDOUT winner

`promotion_authorized` is hard-coded false in R10 V1.

Even when only one candidate passes the HOLDOUT criteria, R10 does not authorize
selecting it as the production detector.

Why:

if several predeclared algorithms are examined on the same holdout and the surviving
one is selected because of that outcome, the holdout has been used for model
selection rather than only qualification.

A production promotion requires a separately governed selection protocol, such as:

- choose/tune on DESIGN material and freeze one candidate before a new untouched
  qualification corpus;
- precommit a selection rule before revealing another holdout;
- use a nested/repeated evaluation design with appropriate multiplicity treatment.

R10 does not implement those procedures.

## Descriptive Pareto set

Among candidates that already PASS every R9 family policy, R10 computes a descriptive
Pareto set using per-family point estimates:

lower is better:
- stable false-alarm rate;
- pre-shift false-alarm rate;
- wrong-dimension alarm rate;
- mean detection delay.

higher is better:
- detection rate.

Candidate A descriptively dominates B only when A is no worse on every metric in
every family and strictly better on at least one.

This Pareto result is descriptive only.

It is not:

- a significance test;
- a confidence-bound dominance test;
- a multiplicity-adjusted comparison;
- permission to promote a candidate.

## DESIGN use

A DESIGN corpus remains non-qualifying.

R10 may use DESIGN comparison to characterize algorithms and support parameter
development, but every candidate result remains
`DESIGN_CHARACTERIZATION`.

No candidate is marked qualified from DESIGN data.

## HOLDOUT use

On a `HOLDOUT_QUALIFICATION` corpus, each candidate may independently PASS or FAIL
the exact R9 family criteria.

R10 reports:

- exact candidate digest;
- algorithm identity;
- exact family metrics;
- reasons;
- set of qualifying candidate IDs;
- descriptive Pareto set;
- comparison disposition.

It still reports `promotion_authorized = false`.

## Claim ceiling

An R10 result means only:

> these exact frozen detector candidates produced these exact R9 qualification
> outcomes on this exact frozen corpus under the exact comparison plan.

R10 does not prove:

- that any candidate parameters were selected without holdout leakage;
- that the corpus represents production;
- that trajectories are independent;
- IID/stationarity;
- analytical control limits or average run length;
- statistical significance of pairwise differences;
- superiority outside the tested families/horizons;
- causal model drift;
- runtime safety;
- reload/control authority.

## Why ADWIN is later

Bifet and Gavaldà's ADWIN work adapts the window length online and derives statistical
change guarantees under its own assumptions.

That is materially different from merely swapping an accumulation recurrence while
keeping the same threshold surface.

A serious ADWIN challenger should therefore include:

- exact adaptive-window state;
- exact confidence/delta semantics;
- computational/memory bounds;
- its own hostile implementation tests;
- then evaluation against the same governed corpus.

That is a suitable successor frontier if the R10 comparison does not provide a
sufficiently convincing incumbent.

## Next frontier

After exact-head qualification and hostile review, the next decision should depend on
the R10 evidence:

- if CUSUM is clearly inadequate on frozen families, build the strongest challenger
  into a runtime-capable candidate on a new subject;
- if several candidates remain viable, obtain a second untouched selection/qualification
  corpus rather than selecting from the R10 holdout;
- if simple fixed-recurrence methods are all weak, implement ADWIN or a state-space
  detector as a separately governed challenger.
