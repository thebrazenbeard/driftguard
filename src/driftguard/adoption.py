from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Iterable

from .ci_gate import CiPolicy, CiReport, GateDecision, evaluate_ci


class AdoptionError(RuntimeError):
    pass


def _canonical_digest(payload) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def parse_metric_assignments(items: Iterable[str]) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for item in items:
        if "=" not in item:
            raise AdoptionError(
                f"metric assignment must be NAME=VALUE: {item!r}"
            )
        name, raw_value = item.split("=", 1)
        name = name.strip()
        if not name:
            raise AdoptionError("metric name must not be empty")
        if name in metrics:
            raise AdoptionError(f"duplicate metric assignment: {name}")
        try:
            value = float(raw_value)
        except ValueError as exc:
            raise AdoptionError(
                f"metric {name} value must be numeric"
            ) from exc
        if not math.isfinite(value):
            raise AdoptionError(f"metric {name} value must be finite")
        metrics[name] = value
    return metrics


def build_report(
    *,
    run_id: str,
    subject: str | None,
    metrics: dict[str, float],
) -> CiReport:
    return CiReport.from_mapping(
        {
            "schema": "DRIFTGUARD_CI_REPORT_V1",
            "run_id": run_id,
            "subject": subject,
            "metrics": metrics,
        }
    )


@dataclass(frozen=True)
class BaselinePromotionReceipt:
    policy_id: str
    policy_digest: str
    previous_baseline_digest: str
    promoted_candidate_digest: str
    gate_result_digest: str
    candidate_run_id: str
    subject: str | None

    def payload(self) -> dict:
        return {
            "schema": "DRIFTGUARD_BASELINE_PROMOTION_V1",
            "policy_id": self.policy_id,
            "policy_digest": self.policy_digest,
            "previous_baseline_digest": self.previous_baseline_digest,
            "promoted_candidate_digest": self.promoted_candidate_digest,
            "gate_result_digest": self.gate_result_digest,
            "candidate_run_id": self.candidate_run_id,
            "subject": self.subject,
            "claim_ceiling": [
                "Candidate passed the exact supplied policy against the exact previous baseline.",
                "Receipt does not prove evaluator correctness or authorize repository/deployment effects.",
                "Promotion output records the candidate report; repository review remains external.",
            ],
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


def qualify_baseline_promotion(
    *,
    policy: CiPolicy,
    baseline: CiReport,
    candidate: CiReport,
) -> BaselinePromotionReceipt:
    result = evaluate_ci(
        policy=policy,
        baseline=baseline,
        candidate=candidate,
    )
    if result.decision is not GateDecision.PASS:
        raise AdoptionError(
            "baseline promotion requires an exact PASS; "
            f"gate returned {result.decision.value}"
        )
    return BaselinePromotionReceipt(
        policy_id=policy.policy_id,
        policy_digest=policy.digest,
        previous_baseline_digest=baseline.digest,
        promoted_candidate_digest=candidate.digest,
        gate_result_digest=result.digest,
        candidate_run_id=candidate.run_id,
        subject=candidate.subject,
    )


def write_json_atomic(path: str | Path, payload: dict) -> None:
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(
        payload,
        sort_keys=True,
        indent=2,
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"
    fd, temporary = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=str(target.parent),
    )
    tmp_path = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, target)
    except BaseException:
        try:
            tmp_path.unlink(missing_ok=True)
        finally:
            raise


def promote_baseline_file(
    *,
    policy_path: str | Path,
    baseline_path: str | Path,
    candidate_path: str | Path,
    output_path: str | Path,
    receipt_path: str | Path | None = None,
) -> BaselinePromotionReceipt:
    policy = CiPolicy.load(policy_path)
    baseline = CiReport.load(baseline_path)
    candidate = CiReport.load(candidate_path)
    receipt = qualify_baseline_promotion(
        policy=policy,
        baseline=baseline,
        candidate=candidate,
    )

    source_baseline = Path(baseline_path).resolve()
    output = Path(output_path).resolve()

    if output == source_baseline:
        raise AdoptionError(
            "refusing to overwrite the accepted baseline in place; "
            "write a proposed baseline and review it separately"
        )
    if output.exists():
        raise AdoptionError(
            f"proposed baseline output already exists: {output}"
        )
    receipt_target = (
        Path(receipt_path).resolve()
        if receipt_path is not None
        else None
    )
    if receipt_target == output:
        raise AdoptionError(
            "promotion receipt path must differ from proposed baseline output"
        )
    if receipt_target is not None and receipt_target.exists():
        raise AdoptionError(
            f"promotion receipt already exists: {receipt_target}"
        )

    write_json_atomic(output, candidate.payload())
    written = CiReport.load(output)
    if written.digest != candidate.digest:
        raise AdoptionError(
            "proposed baseline readback digest mismatch"
        )

    if receipt_path is not None:
        payload = receipt.payload()
        payload["promotion_digest"] = receipt.digest
        payload["prepared_baseline_digest"] = written.digest
        payload["effect_state"] = "PREPARED_FOR_REVIEW"
        write_json_atomic(receipt_path, payload)
    return receipt
