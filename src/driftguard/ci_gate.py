from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from hashlib import sha256
import json
import math
from pathlib import Path
import tomllib
from typing import Any


class GateDecision(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    BLOCK = "BLOCK"
    UNKNOWN = "UNKNOWN"


class MetricDirection(StrEnum):
    HIGHER = "higher"
    LOWER = "lower"


class MetricSeverity(StrEnum):
    BLOCK = "block"
    WARN = "warn"


def _nonempty(value: Any, label: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _finite(value: Any, label: str) -> float:
    if type(value) not in (int, float) or isinstance(value, bool):
        raise ValueError(f"{label} must be numeric")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    return value


def _canonical_digest(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str):
    raise ValueError(f"non-finite JSON number is not allowed: {value}")


@dataclass(frozen=True)
class MetricPolicy:
    name: str
    direction: MetricDirection
    max_regression: float
    severity: MetricSeverity
    min_candidate: float | None = None
    max_candidate: float | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "MetricPolicy":
        if type(value) is not dict:
            raise ValueError("metric policy must be a table")
        name = _nonempty(value.get("name"), "metric name")
        try:
            direction = MetricDirection(value.get("direction"))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"metric {name} direction must be 'higher' or 'lower'"
            ) from exc
        try:
            severity = MetricSeverity(value.get("severity", "block"))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"metric {name} severity must be 'block' or 'warn'"
            ) from exc
        max_regression = _finite(
            value.get("max_regression", 0.0),
            f"metric {name} max_regression",
        )
        if max_regression < 0:
            raise ValueError(
                f"metric {name} max_regression must be >= 0"
            )
        min_candidate = value.get("min_candidate")
        if min_candidate is not None:
            min_candidate = _finite(
                min_candidate,
                f"metric {name} min_candidate",
            )
        max_candidate = value.get("max_candidate")
        if max_candidate is not None:
            max_candidate = _finite(
                max_candidate,
                f"metric {name} max_candidate",
            )
        if (
            min_candidate is not None
            and max_candidate is not None
            and min_candidate > max_candidate
        ):
            raise ValueError(
                f"metric {name} min_candidate exceeds max_candidate"
            )
        return cls(
            name=name,
            direction=direction,
            max_regression=max_regression,
            severity=severity,
            min_candidate=min_candidate,
            max_candidate=max_candidate,
        )

    def payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "direction": self.direction.value,
            "max_regression": self.max_regression,
            "severity": self.severity.value,
            "min_candidate": self.min_candidate,
            "max_candidate": self.max_candidate,
        }


@dataclass(frozen=True)
class CiPolicy:
    policy_id: str
    unknown: MetricSeverity
    metrics: tuple[MetricPolicy, ...]

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "CiPolicy":
        if type(value) is not dict:
            raise ValueError("CI policy must be a TOML table")
        if value.get("schema") != "DRIFTGUARD_CI_POLICY_V1":
            raise ValueError("wrong CI policy schema")
        policy_id = _nonempty(value.get("policy_id"), "policy_id")
        try:
            unknown = MetricSeverity(value.get("unknown", "block"))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "unknown policy must be 'block' or 'warn'"
            ) from exc
        raw_metrics = value.get("metric")
        if type(raw_metrics) is not list or not raw_metrics:
            raise ValueError("CI policy requires at least one [[metric]]")
        metrics = tuple(MetricPolicy.from_mapping(item) for item in raw_metrics)
        names = [item.name for item in metrics]
        if len(names) != len(set(names)):
            raise ValueError("CI policy metric names must be unique")
        return cls(policy_id=policy_id, unknown=unknown, metrics=metrics)

    @classmethod
    def load(cls, path: str | Path) -> "CiPolicy":
        with Path(path).open("rb") as handle:
            return cls.from_mapping(tomllib.load(handle))

    def payload(self) -> dict[str, Any]:
        return {
            "schema": "DRIFTGUARD_CI_POLICY_V1",
            "policy_id": self.policy_id,
            "unknown": self.unknown.value,
            "metrics": [
                metric.payload()
                for metric in sorted(self.metrics, key=lambda item: item.name)
            ],
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True)
class CiReport:
    run_id: str
    subject: str | None
    metrics: tuple[tuple[str, float], ...]

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "CiReport":
        if type(value) is not dict:
            raise ValueError("CI report must be a JSON object")
        if value.get("schema") != "DRIFTGUARD_CI_REPORT_V1":
            raise ValueError("wrong CI report schema")
        run_id = _nonempty(value.get("run_id"), "report run_id")
        subject = value.get("subject")
        if subject is not None:
            subject = _nonempty(subject, "report subject")
        raw_metrics = value.get("metrics")
        if type(raw_metrics) is not dict or not raw_metrics:
            raise ValueError("CI report metrics must be a non-empty object")
        metrics = []
        for name, raw_score in raw_metrics.items():
            metric_name = _nonempty(name, "report metric name")
            metrics.append(
                (
                    metric_name,
                    _finite(raw_score, f"report metric {metric_name}"),
                )
            )
        metrics.sort(key=lambda item: item[0])
        return cls(run_id=run_id, subject=subject, metrics=tuple(metrics))

    @classmethod
    def load(cls, path: str | Path) -> "CiReport":
        text = Path(path).read_text(encoding="utf-8")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
        return cls.from_mapping(value)

    def payload(self) -> dict[str, Any]:
        return {
            "schema": "DRIFTGUARD_CI_REPORT_V1",
            "run_id": self.run_id,
            "subject": self.subject,
            "metrics": dict(self.metrics),
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True)
class MetricEvaluation:
    name: str
    status: GateDecision
    severity: MetricSeverity
    direction: MetricDirection
    baseline: float | None
    candidate: float | None
    regression: float | None
    max_regression: float
    reasons: tuple[str, ...]

    def payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "severity": self.severity.value,
            "direction": self.direction.value,
            "baseline": self.baseline,
            "candidate": self.candidate,
            "regression": self.regression,
            "max_regression": self.max_regression,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class CiGateResult:
    decision: GateDecision
    policy_id: str
    policy_digest: str
    baseline_digest: str
    candidate_digest: str
    metrics: tuple[MetricEvaluation, ...]
    reasons: tuple[str, ...]

    @property
    def exit_code(self) -> int:
        if self.decision in {GateDecision.PASS, GateDecision.WARN}:
            return 0
        if self.decision is GateDecision.BLOCK:
            return 1
        return 2

    def payload(self) -> dict[str, Any]:
        return {
            "schema": "DRIFTGUARD_CI_GATE_RESULT_V1",
            "decision": self.decision.value,
            "policy_id": self.policy_id,
            "policy_digest": self.policy_digest,
            "baseline_digest": self.baseline_digest,
            "candidate_digest": self.candidate_digest,
            "metrics": [item.payload() for item in self.metrics],
            "reasons": list(self.reasons),
            "claim_ceiling": [
                "Deterministic comparison of supplied baseline/candidate metrics under the exact supplied policy.",
                "Does not prove evaluator correctness, benchmark representativeness, causal drift, or production impact.",
                "A PASS is admission evidence for this policy/input tuple only.",
            ],
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


def evaluate_ci(
    *,
    policy: CiPolicy,
    baseline: CiReport,
    candidate: CiReport,
) -> CiGateResult:
    if baseline.subject and candidate.subject and baseline.subject != candidate.subject:
        return CiGateResult(
            decision=GateDecision.UNKNOWN,
            policy_id=policy.policy_id,
            policy_digest=policy.digest,
            baseline_digest=baseline.digest,
            candidate_digest=candidate.digest,
            metrics=(),
            reasons=("baseline_candidate_subject_mismatch",),
        )

    baseline_values = dict(baseline.metrics)
    candidate_values = dict(candidate.metrics)
    metric_results = []
    saw_block = False
    saw_warn = False
    saw_unknown = False

    for metric in sorted(policy.metrics, key=lambda item: item.name):
        base = baseline_values.get(metric.name)
        cand = candidate_values.get(metric.name)
        if base is None or cand is None:
            missing = []
            if base is None:
                missing.append("baseline")
            if cand is None:
                missing.append("candidate")
            result = MetricEvaluation(
                name=metric.name,
                status=GateDecision.UNKNOWN,
                severity=metric.severity,
                direction=metric.direction,
                baseline=base,
                candidate=cand,
                regression=None,
                max_regression=metric.max_regression,
                reasons=(f"missing_{'_and_'.join(missing)}_metric",),
            )
            metric_results.append(result)
            saw_unknown = True
            continue

        if metric.direction is MetricDirection.HIGHER:
            regression = base - cand
        else:
            regression = cand - base

        reasons = []
        if regression > metric.max_regression:
            reasons.append(
                f"regression_{regression:.12g}_exceeds_{metric.max_regression:.12g}"
            )
        if metric.min_candidate is not None and cand < metric.min_candidate:
            reasons.append(
                f"candidate_{cand:.12g}_below_min_{metric.min_candidate:.12g}"
            )
        if metric.max_candidate is not None and cand > metric.max_candidate:
            reasons.append(
                f"candidate_{cand:.12g}_above_max_{metric.max_candidate:.12g}"
            )

        if reasons:
            status = (
                GateDecision.BLOCK
                if metric.severity is MetricSeverity.BLOCK
                else GateDecision.WARN
            )
            saw_block = saw_block or status is GateDecision.BLOCK
            saw_warn = saw_warn or status is GateDecision.WARN
        else:
            status = GateDecision.PASS

        metric_results.append(
            MetricEvaluation(
                name=metric.name,
                status=status,
                severity=metric.severity,
                direction=metric.direction,
                baseline=base,
                candidate=cand,
                regression=regression,
                max_regression=metric.max_regression,
                reasons=tuple(reasons) if reasons else ("within_policy",),
            )
        )

    reasons = []
    if saw_block:
        decision = GateDecision.BLOCK
        reasons.append("one_or_more_blocking_metrics_failed")
    elif saw_unknown and policy.unknown is MetricSeverity.BLOCK:
        decision = GateDecision.UNKNOWN
        reasons.append("required_metric_evidence_missing")
    elif saw_warn or saw_unknown:
        decision = GateDecision.WARN
        if saw_warn:
            reasons.append("one_or_more_warning_metrics_failed")
        if saw_unknown:
            reasons.append("metric_evidence_missing_but_policy_warns")
    else:
        decision = GateDecision.PASS
        reasons.append("all_metrics_within_policy")

    return CiGateResult(
        decision=decision,
        policy_id=policy.policy_id,
        policy_digest=policy.digest,
        baseline_digest=baseline.digest,
        candidate_digest=candidate.digest,
        metrics=tuple(metric_results),
        reasons=tuple(reasons),
    )


def render_markdown(result: CiGateResult) -> str:
    lines = [
        f"## DriftGuard: {result.decision.value}",
        "",
        f"Policy: `{result.policy_id}`",
        "",
        "| Metric | Status | Baseline | Candidate | Regression | Limit |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for metric in result.metrics:
        baseline = "—" if metric.baseline is None else f"{metric.baseline:.6g}"
        candidate = "—" if metric.candidate is None else f"{metric.candidate:.6g}"
        regression = "—" if metric.regression is None else f"{metric.regression:.6g}"
        lines.append(
            f"| {metric.name} | {metric.status.value} | {baseline} | "
            f"{candidate} | {regression} | {metric.max_regression:.6g} |"
        )
    lines.extend(
        [
            "",
            f"Result digest: `{result.digest}`",
            "",
            "This result compares supplied metrics under the exact policy. "
            "It does not prove evaluator correctness or production impact.",
            "",
        ]
    )
    return "\n".join(lines)
