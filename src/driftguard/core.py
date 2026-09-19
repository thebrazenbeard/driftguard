from __future__ import annotations

from typing import Iterable

from .model import (
    Decision,
    DriftEvidence,
    Evaluation,
    SaveState,
    evidence_set_digest,
)


class DriftGuardError(ValueError):
    pass


class StaleGenerationError(DriftGuardError):
    pass


class DriftGuardEngine:
    """Pure deterministic admission and decision engine."""

    def evaluate(
        self,
        *,
        state: SaveState,
        evidence: Iterable[DriftEvidence],
        turn_index: int,
        generation: int,
        last_reload_turn: int | None,
    ) -> Evaluation:
        if type(turn_index) is not int or turn_index < 0:
            raise DriftGuardError("turn_index must be a non-negative integer")
        if type(generation) is not int or generation < 0:
            raise DriftGuardError("generation must be a non-negative integer")
        if last_reload_turn is not None:
            if type(last_reload_turn) is not int or last_reload_turn < 0:
                raise DriftGuardError("last_reload_turn must be None or non-negative int")
            if last_reload_turn > turn_index:
                raise DriftGuardError("last_reload_turn cannot be in the future")

        evidence = tuple(evidence)
        evidence_digest = evidence_set_digest(evidence)
        dimension_by_id = {item.dimension_id: item for item in state.dimensions}
        allowed_sources = set(state.allowed_probe_sources)

        by_dimension: dict[str, DriftEvidence] = {}
        reasons: list[str] = []
        admission_failed = False
        seen_evidence_ids: set[str] = set()
        seen_execution_ids: set[str] = set()

        for item in evidence:
            if type(item) is not DriftEvidence:
                raise DriftGuardError("evidence must contain exact DriftEvidence values")
            if item.evidence_id in seen_evidence_ids:
                reasons.append(f"duplicate_evidence_id:{item.evidence_id}")
                admission_failed = True
                continue
            if item.execution_id in seen_execution_ids:
                reasons.append(f"duplicate_execution_id:{item.execution_id}")
                admission_failed = True
                continue
            seen_evidence_ids.add(item.evidence_id)
            seen_execution_ids.add(item.execution_id)

            dimension = dimension_by_id.get(item.dimension_id)
            if dimension is None:
                reasons.append(f"unknown_dimension:{item.dimension_id}")
                admission_failed = True
                continue
            if item.dimension_id in by_dimension:
                reasons.append(f"multiple_evidence_for_dimension:{item.dimension_id}")
                admission_failed = True
                continue
            if item.independence < dimension.min_independence:
                reasons.append(f"insufficient_independence:{item.dimension_id}")
                admission_failed = True
                continue
            if any(binding not in allowed_sources for binding in item.source_bindings):
                reasons.append(f"ungoverned_source:{item.dimension_id}")
                admission_failed = True
                continue
            by_dimension[item.dimension_id] = item

        missing = [
            item.dimension_id
            for item in state.dimensions
            if item.dimension_id not in by_dimension
        ]
        if missing:
            reasons.extend(f"missing_evidence:{item}" for item in missing)
            admission_failed = True

        if admission_failed:
            return Evaluation(
                decision=Decision.UNKNOWN,
                aggregate_drift=None,
                dimension_scores=tuple(
                    sorted(
                        (key, float(value.drift_score))
                        for key, value in by_dimension.items()
                    )
                ),
                reasons=tuple(reasons),
                state_digest=state.digest,
                evidence_digest=evidence_digest,
                turn_index=turn_index,
                generation=generation,
            )

        scores = tuple(
            (dimension.dimension_id, float(by_dimension[dimension.dimension_id].drift_score))
            for dimension in state.dimensions
        )
        total_weight = sum(float(item.weight) for item in state.dimensions)
        aggregate = sum(
            float(dimension.weight)
            * float(by_dimension[dimension.dimension_id].drift_score)
            for dimension in state.dimensions
        ) / total_weight

        critical_breach = any(
            dimension.critical
            and float(by_dimension[dimension.dimension_id].drift_score)
            >= state.policy.critical_reload_threshold
            for dimension in state.dimensions
        )
        periodic_due = (
            state.policy.max_turns_without_reload > 0
            and last_reload_turn is not None
            and turn_index - last_reload_turn >= state.policy.max_turns_without_reload
        )
        cooldown_active = (
            last_reload_turn is not None
            and turn_index - last_reload_turn < state.policy.reload_cooldown_turns
        )

        reload_reasons: list[str] = []
        if critical_breach:
            reload_reasons.append("critical_dimension_breach")
        if aggregate >= state.policy.reload_threshold:
            reload_reasons.append("aggregate_reload_threshold")
        if periodic_due:
            reload_reasons.append("periodic_reload_due")

        if reload_reasons and (critical_breach or not cooldown_active):
            return Evaluation(
                decision=Decision.RELOAD,
                aggregate_drift=aggregate,
                dimension_scores=scores,
                reasons=tuple(reload_reasons),
                state_digest=state.digest,
                evidence_digest=evidence_digest,
                turn_index=turn_index,
                generation=generation,
                restore_packet=self.restore_packet(state),
            )

        warn_reasons: list[str] = []
        if reload_reasons and cooldown_active:
            warn_reasons.extend(reload_reasons)
            warn_reasons.append("reload_suppressed_by_cooldown")
        elif aggregate >= state.policy.warn_threshold:
            warn_reasons.append("aggregate_warn_threshold")

        if warn_reasons:
            return Evaluation(
                decision=Decision.WARN,
                aggregate_drift=aggregate,
                dimension_scores=scores,
                reasons=tuple(warn_reasons),
                state_digest=state.digest,
                evidence_digest=evidence_digest,
                turn_index=turn_index,
                generation=generation,
            )

        return Evaluation(
            decision=Decision.STABLE,
            aggregate_drift=aggregate,
            dimension_scores=scores,
            reasons=("within_policy",),
            state_digest=state.digest,
            evidence_digest=evidence_digest,
            turn_index=turn_index,
            generation=generation,
        )

    @staticmethod
    def restore_packet(state: SaveState) -> str:
        return (
            "DRIFTGUARD_RESTORE\n"
            f"state_id={state.state_id}\n"
            f"state_version={state.version}\n"
            f"state_digest={state.digest}\n"
            "---\n"
            f"{state.restore_text}"
        )
