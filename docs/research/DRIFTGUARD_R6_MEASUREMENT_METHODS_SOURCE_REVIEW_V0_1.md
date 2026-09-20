# DriftGuard R6 Measurement Methods Source Review V0.1

Status: **RESEARCH SOURCE REVIEW / NO METHOD ADMISSION / NO RUNTIME EFFECT**

Observed: 2026-09-20

Parent architecture:
`docs/research/DRIFTGUARD_R6_LONGITUDINAL_DRIFT_ARCHITECTURE_V0_1.md`

## Purpose

Review external measurement literature relevant to DriftGuard R6 before selecting any longitudinal detector, calibration strategy, or evaluator policy.

This review distinguishes:

`SOURCE_PRESENCE != METHOD_ADMISSION`

`METHOD_RELEVANCE != DIRECT_DOMAIN_TRANSFER`

`CLASSICAL_PROCESS_MONITORING != VALIDATED_LLM_DRIFT_MONITORING`

`CALIBRATION_METHOD != GROUND_TRUTH`

`LLM_JUDGE_AGREEMENT != JUDGE_IMPARTIALITY`

No source below is adopted as a production algorithm by this document.

## 1. Concept-drift framing

### Source

João Gama, Indrė Žliobaitė, Albert Bifet, Mykola Pechenizkiy, Abdelhamid Bouchachia.

**A Survey on Concept Drift Adaptation.** ACM Computing Surveys 46(4), 2014.

DOI: https://doi.org/10.1145/2523813

### What it supports

The survey treats concept drift as change in a data-generating relationship over time and explicitly includes detection/adaptation strategies and evaluation methodology as part of the problem.

For DriftGuard, the transferable mechanism-level lesson is:

- longitudinal drift is not just a threshold on one observation;
- detector evaluation belongs to the architecture;
- change type, timing, recurrence, and adaptation strategy matter;
- online monitoring requires explicit evaluation methodology.

### What it does not support

The survey is primarily framed around supervised online learning. It does not establish that DriftGuard behavioral scores are statistically equivalent to supervised-learning error streams.

Disposition:

`ADAPT_MEASUREMENT_GOVERNANCE_CONCEPTS_ONLY`

## 2. CUSUM as a candidate sequential detector family

### Source

NIST/SEMATECH Engineering Statistics Handbook.

**CUSUM Control Charts.**

https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc323.htm

### What it supports

NIST describes CUSUM as a sequential monitoring method that accumulates deviations from a target and can outperform a pointwise Shewhart-style rule for relatively small shifts.

The reference explicitly frames design in terms including:

- false-alarm probability;
- missed-detection probability;
- shift magnitude of interest;
- sequential monitoring behavior.

This supports the R6D requirement that a detector policy be precommitted and that false alarms/detection sensitivity be explicit design parameters rather than accidental properties of repeated threshold checks.

### What it does not support

Classical CUSUM assumptions do not automatically hold for DriftGuard scores. LLM-evaluator outputs may be bounded, discrete, correlated, nonstationary, version-dependent, and semantically heterogeneous across dimensions.

Disposition:

`CANDIDATE_METHOD_FAMILY_REQUIRES_DOMAIN_CALIBRATION`

## 3. EWMA as a candidate gradual-drift detector family

### Source

NIST/SEMATECH Engineering Statistics Handbook.

**EWMA Control Charts.**

https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc324.htm

### What it supports

NIST describes EWMA as an exponentially weighted statistic over current and prior observations and notes its usefulness for detecting small or gradual process shifts.

It also states assumptions and setup requirements that matter directly to DriftGuard architecture:

- the historical database used to establish the target should be representative of the in-control process;
- control behavior depends on the weighting parameter;
- standard design tables may assume independent data and a normal population.

Transferable R6 implications:

- a baseline/reference corpus cannot be casually assembled after monitoring begins;
- detector parameters are part of the precommitted policy;
- correlated evaluator observations require special care;
- "good historical data" is itself a governed subject.

### What it does not support

EWMA is not automatically valid for arbitrary LLM-derived drift scores, and common parameter defaults are not a DriftGuard calibration.

Disposition:

`CANDIDATE_METHOD_FAMILY_REQUIRES_DOMAIN_CALIBRATION`

## 4. Calibration is itself a measurement problem

### Source

Chuan Guo, Geoff Pleiss, Yu Sun, Kilian Q. Weinberger.

**On Calibration of Modern Neural Networks.** ICML 2017.

https://proceedings.mlr.press/v70/guo17a.html

### What it supports

The paper demonstrates that modern neural-network confidence estimates can be poorly calibrated and evaluates post-hoc calibration methods.

Transferable R6 lesson:

- a score emitted by a model should not be assumed to have stable probabilistic semantics merely because it is numeric;
- calibration method/version must be part of the measurement contract;
- "0.4" from two evaluators or two evaluator versions is not automatically commensurate.

### What it does not support

DriftGuard's current `drift_score` is not defined as a calibrated probability of correctness. Temperature scaling or other confidence-calibration methods therefore cannot be imported directly without first defining the score semantics and calibration target.

Disposition:

`ADAPT_CALIBRATION_DISCIPLINE_NOT_SPECIFIC_TECHNIQUE`

## 5. Calibration can degrade under distribution shift

### Source

Yaniv Ovadia et al.

**Can You Trust Your Model's Uncertainty? Evaluating Predictive Uncertainty Under Dataset Shift.** NeurIPS 2019.

https://papers.neurips.cc/paper_files/paper/2019/hash/8558cb408c1d76621371888657d2eb1d-Abstract.html

### What it supports

The study evaluates uncertainty/calibration under increasingly shifted data and reports that methods which appear calibrated in-distribution can degrade under dataset shift; traditional post-hoc calibration can fall short.

Transferable R6 implications:

- calibration is epoch/context dependent;
- evaluator calibration must be checked under changed input distributions;
- target drift and evaluator/instrument drift must be distinguished;
- a calibration result obtained under one distribution should not be treated as universal.

### What it does not support

This is not direct evidence about LLM-as-a-judge behavioral scoring or DriftGuard's future score scale.

Disposition:

`ADAPT_SHIFT_SENSITIVITY_REQUIREMENT`

## 6. LLM-as-a-judge bias is a first-class evaluator concern

### Source

Lianmin Zheng et al.

**Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena.** 2023.

https://arxiv.org/abs/2306.05685

### What it supports

The work evaluates strong LLMs as judges and documents limitations including position, verbosity, self-enhancement, and reasoning biases.

Transferable R6 implications:

- evaluator identity/version belongs in the exact measurement subject;
- evaluator bias must not be hidden behind one scalar score;
- prompt/order protocol is part of evaluator configuration;
- separate evaluator instances do not automatically imply independent evidence.

### What it does not support

Reported agreement with human preferences does not make an LLM judge unbiased or universally reliable, and preference evaluation is not identical to DriftGuard behavioral-drift measurement.

Disposition:

`ADAPT_EVALUATOR_BIAS_THREAT_MODEL`

## 7. Position bias varies by judge and task

### Source

Lin Shi, Chiyu Ma, Wenhua Liang, Weicheng Ma, Soroush Vosoughi.

**Judging the Judges: A Systematic Study of Position Bias in LLM-as-a-Judge.** 2024.

https://arxiv.org/abs/2406.07791

### What it supports

The study examines position bias across multiple LLM judges and tasks and finds that the effect varies across judges and task settings rather than behaving like simple random noise.

Transferable R6 implications:

- judge protocol needs explicit repeatability/position checks;
- evaluator calibration should be dimension/task specific where necessary;
- evaluator version replacement can change the measurement instrument;
- disagreement and instability should remain visible in receipts.

### What it does not support

The paper does not provide a DriftGuard-ready calibration protocol or a universal correction factor.

Disposition:

`ADAPT_EVALUATOR_STABILITY_TEST_REQUIREMENT`

## 8. Architecture consequences

This source review strengthens the following R6 requirements without selecting a production detector:

1. **Precommit the detector policy.**
   Sequential monitoring changes the false-alarm problem. The exact aggregation, reset, hysteresis, stopping, and alert rules must be fixed before classified outcomes.

2. **Govern the reference distribution.**
   Classical process-monitoring methods depend on representative in-control history. DriftGuard must version the corpus/reference regime used for calibration rather than letting it silently evolve.

3. **Treat the evaluator as an instrument.**
   Evaluator model, version, prompt protocol, order protocol, and calibration epoch are measurement metadata, not implementation trivia.

4. **Separate evaluator drift from target drift.**
   A changed judge or judge bias can change scores while the monitored runtime remains unchanged.

5. **Preserve raw observations.**
   Future CUSUM/EWMA/change-point policies should operate over immutable admitted observations so policy changes can be audited without rewriting historical evidence.

6. **Do not assume independence.**
   Classical sequential methods may depend on independence assumptions; LLM evaluators can share provider/model/training ancestry and repeated calls can be correlated.

7. **Calibration must survive shift testing.**
   A calibration pass under one reference distribution is not universal evidence of calibration under later subject/input regimes.

## 9. Candidate experimental program before method admission

Before choosing CUSUM, EWMA, hysteresis, or another detector for production/reference implementation, build a synthetic and replayable benchmark with controlled:

- no-drift baseline;
- abrupt drift;
- gradual drift;
- recurring drift;
- evaluator-version drift with stable target;
- target drift with stable evaluator;
- correlated probe families;
- missing evidence;
- periodic operational reload events;
- baseline successor epochs.

For each detector candidate, measure at least:

- false-alert behavior under no drift;
- detection delay under known injected drift;
- behavior under correlated observations;
- behavior under evaluator shift;
- missing-evidence handling;
- sensitivity to policy parameters;
- reproducibility across Windows/Linux where byte-level fixtures are involved.

No detector should be admitted because it is famous, mathematically elegant, or performs well on one handcrafted sequence.

## 10. Current source-admission classification

- Gama et al. 2014: `METHOD_GOVERNANCE_SOURCE_CANDIDATE`
- NIST CUSUM: `SEQUENTIAL_METHOD_SOURCE_CANDIDATE`
- NIST EWMA: `SEQUENTIAL_METHOD_SOURCE_CANDIDATE`
- Guo et al. 2017: `CALIBRATION_DISCIPLINE_SOURCE_CANDIDATE`
- Ovadia et al. 2019: `SHIFT_CALIBRATION_SOURCE_CANDIDATE`
- Zheng et al. 2023: `LLM_EVALUATOR_BIAS_SOURCE_CANDIDATE`
- Shi et al. 2024: `LLM_EVALUATOR_STABILITY_SOURCE_CANDIDATE`

All remain research sources only.

`SOURCE_REVIEW_PASS != ALGORITHM_ADMISSION`

`ALGORITHM_ADMISSION != REFERENCE_IMPLEMENTATION_PASS`

`REFERENCE_IMPLEMENTATION_PASS != PRODUCTION_IMPLEMENTATION_PASS`

`PRODUCTION_IMPLEMENTATION_PASS != BEHAVIORAL_QUALIFICATION`
