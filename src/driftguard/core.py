from __future__ import annotations

from statistics import median
from typing import Iterable

from .model import (
    Decision,
    DriftEvidence,
    Evaluation,
    MeasurementMode,
    MonitoredSubject,
    SaveState,
    evidence_set_digest,
    require_sha256_digest,
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
        observation_digest: str,
        turn_index: int,
        generation: int,
        restore_anchor_turn: int,
        last_reload_decision_turn: int | None,
        subject: MonitoredSubject | None = None,
    ) -> Evaluation:
        require_sha256_digest(observation_digest, "observation digest")
        if type(turn_index) is not int or turn_index < 0:
            raise DriftGuardError("turn_index must be a non-negative integer")
        if type(generation) is not int or generation < 0:
            raise DriftGuardError("generation must be a non-negative integer")
        if type(restore_anchor_turn) is not int or restore_anchor_turn < 0:
            raise DriftGuardError("restore_anchor_turn must be a non-negative integer")
        if restore_anchor_turn > turn_index:
            raise DriftGuardError("restore_anchor_turn cannot be in the future")
        if last_reload_decision_turn is not None:
            if type(last_reload_decision_turn) is not int or last_reload_decision_turn < 0:
                raise DriftGuardError(
                    "last_reload_decision_turn must be None or non-negative int"
                )
            if last_reload_decision_turn > turn_index:
                raise DriftGuardError("last_reload_decision_turn cannot be in the future")

        if subject is not None and type(subject) is not MonitoredSubject:
            raise DriftGuardError("subject must be exact MonitoredSubject or None")
        subject_digest = (
            subject.configuration_digest if subject is not None else None
        )
        subject_epoch = subject.epoch if subject is not None else None

        strict = state.measurement_mode is MeasurementMode.CALIBRATED_QUORUM
        periodic_due = (
            state.policy.max_turns_without_reload > 0
            and turn_index - restore_anchor_turn >= state.policy.max_turns_without_reload
        )
        cooldown_active = (
            last_reload_decision_turn is not None
            and turn_index - last_reload_decision_turn
            < state.policy.reload_cooldown_turns
        )

        evidence = tuple(evidence)
        evidence_digest = evidence_set_digest(evidence)
        dimension_by_id = {item.dimension_id: item for item in state.dimensions}
        probe_by_binding = {source.binding: source for source in state.probe_sources}

        by_dimension: dict[str, list[tuple[DriftEvidence, object]]] = {}
        reasons: list[str] = []
        admission_failed = False
        seen_evidence_ids: set[str] = set()
        seen_execution_ids: set[str] = set()
        seen_dimension_sources: set[tuple[str, object]] = set()

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
            if not strict and item.dimension_id in by_dimension:
                reasons.append(f"multiple_evidence_for_dimension:{item.dimension_id}")
                admission_failed = True
                continue
            if item.state_digest != state.digest:
                reasons.append(f"state_binding_mismatch:{item.dimension_id}")
                admission_failed = True
                continue
            if item.observation_digest != observation_digest:
                reasons.append(f"observation_binding_mismatch:{item.dimension_id}")
                admission_failed = True
                continue
            if item.turn_index != turn_index:
                reasons.append(f"turn_binding_mismatch:{item.dimension_id}")
                admission_failed = True
                continue
            if subject is None:
                if item.subject_digest is not None or item.subject_epoch is not None:
                    reasons.append(f"unexpected_subject_binding:{item.dimension_id}")
                    admission_failed = True
                    continue
            else:
                if item.subject_digest != subject_digest:
                    reasons.append(f"subject_binding_mismatch:{item.dimension_id}")
                    admission_failed = True
                    continue
                if item.subject_epoch != subject_epoch:
                    reasons.append(f"subject_epoch_mismatch:{item.dimension_id}")
                    admission_failed = True
                    continue
            if len(item.source_bindings) != 1:
                reasons.append(f"ambiguous_source_set:{item.dimension_id}")
                admission_failed = True
                continue
            source = probe_by_binding.get(item.source_bindings[0])
            if source is None:
                reasons.append(f"ungoverned_source:{item.dimension_id}")
                admission_failed = True
                continue
            if item.dimension_id not in source.dimensions:
                reasons.append(f"source_scope_violation:{item.dimension_id}")
                admission_failed = True
                continue
            if item.independence > source.max_independence:
                reasons.append(f"independence_overclaim:{item.dimension_id}")
                admission_failed = True
                continue
            if item.independence < dimension.min_independence:
                reasons.append(f"insufficient_independence:{item.dimension_id}")
                admission_failed = True
                continue
            if strict:
                source_key = (item.dimension_id, source.binding)
                if source_key in seen_dimension_sources:
                    reasons.append(
                        f"duplicate_source_for_dimension:{item.dimension_id}"
                    )
                    admission_failed = True
                    continue
                seen_dimension_sources.add(source_key)
                if source.calibration is None:
                    reasons.append(f"uncalibrated_source:{item.dimension_id}")
                    admission_failed = True
                    continue
                if source.calibration_digest is None:
                    reasons.append(
                        f"missing_calibration_digest:{item.dimension_id}"
                    )
                    admission_failed = True
                    continue
                if source.correlation_group is None:
                    reasons.append(
                        f"missing_correlation_group:{item.dimension_id}"
                    )
                    admission_failed = True
                    continue
                if source.score_scale != dimension.score_scale:
                    reasons.append(f"score_scale_mismatch:{item.dimension_id}")
                    admission_failed = True
                    continue
            by_dimension.setdefault(item.dimension_id, []).append((item, source))

        dimension_scores: dict[str, float] = {}
        quorum_satisfied: dict[str, bool] = {}
        for dimension in state.dimensions:
            rows = by_dimension.get(dimension.dimension_id, [])
            if not rows:
                reasons.append(f"missing_evidence:{dimension.dimension_id}")
                admission_failed = True
                quorum_satisfied[dimension.dimension_id] = False
                continue
            if strict:
                source_quorum = len(rows) >= dimension.min_sources
                if not source_quorum:
                    reasons.append(
                        f"insufficient_source_quorum:{dimension.dimension_id}"
                    )
                    admission_failed = True
                groups = {
                    source.correlation_group
                    for _, source in rows
                    if source.correlation_group is not None
                }
                correlation_quorum = (
                    len(groups) >= dimension.min_correlation_groups
                )
                if not correlation_quorum:
                    reasons.append(
                        f"insufficient_correlation_quorum:{dimension.dimension_id}"
                    )
                    admission_failed = True
                quorum_satisfied[dimension.dimension_id] = (
                    source_quorum and correlation_quorum
                )
                source_scores = [
                    float(item.drift_score) for item, _ in rows
                ]
                source_spread = max(source_scores) - min(source_scores)
                if source_spread > float(dimension.max_source_spread):
                    reasons.append(
                        f"evaluator_disagreement:{dimension.dimension_id}"
                    )
                    admission_failed = True
                dimension_scores[dimension.dimension_id] = float(
                    median(source_scores)
                )
            else:
                quorum_satisfied[dimension.dimension_id] = True
                dimension_scores[dimension.dimension_id] = float(
                    rows[0][0].drift_score
                )

        strict_evidence_trace = (
            tuple(
                sorted(
                    (
                        item.evidence_id,
                        item.dimension_id,
                        source.binding.ref,
                        source.binding.version,
                        float(item.drift_score),
                        item.independence.name,
                        item.execution_id,
                    )
                    for rows in by_dimension.values()
                    for item, source in rows
                )
            )
            if strict
            else ()
        )

        valid_critical_breach = any(
            dimension.critical
            and quorum_satisfied.get(dimension.dimension_id, False)
            and any(
                float(item.drift_score)
                >= (
                    float(dimension.critical_reload_threshold)
                    if strict
                    else state.policy.critical_reload_threshold
                )
                for item, _ in by_dimension.get(dimension.dimension_id, [])
            )
            for dimension in state.dimensions
        )

        if admission_failed:
            reload_required = valid_critical_breach or (
                periodic_due and not cooldown_active
            )
            if valid_critical_breach:
                reasons.append("critical_dimension_breach")
            if periodic_due:
                reasons.append("periodic_reload_due")
                if cooldown_active and not valid_critical_breach:
                    reasons.append("reload_suppressed_by_cooldown")
            return Evaluation(
                decision=Decision.UNKNOWN,
                reload_required=reload_required,
                aggregate_drift=None,
                dimension_scores=tuple(sorted(dimension_scores.items())),
                reasons=tuple(reasons),
                state_digest=state.digest,
                observation_digest=observation_digest,
                evidence_digest=evidence_digest,
                turn_index=turn_index,
                generation=generation,
                subject_digest=subject_digest,
                subject_epoch=subject_epoch,
                restore_packet=(
                    self.restore_packet(state) if reload_required else None
                ),
                behavioral_decision=(
                    Decision.UNKNOWN if strict else None
                ),
                evidence_trace=strict_evidence_trace,
            )

        scores = tuple(
            (dimension.dimension_id, dimension_scores[dimension.dimension_id])
            for dimension in state.dimensions
        )

        if strict:
            aggregate = None
            reload_dimensions = [
                dimension.dimension_id
                for dimension in state.dimensions
                if dimension_scores[dimension.dimension_id]
                >= float(dimension.reload_threshold)
            ]
            warn_dimensions = [
                dimension.dimension_id
                for dimension in state.dimensions
                if dimension_scores[dimension.dimension_id]
                >= float(dimension.warn_threshold)
            ]
            if valid_critical_breach or reload_dimensions:
                behavioral_decision = Decision.RELOAD
            elif warn_dimensions:
                behavioral_decision = Decision.WARN
            else:
                behavioral_decision = Decision.STABLE

            reload_reasons: list[str] = []
            if valid_critical_breach:
                reload_reasons.append("critical_dimension_breach")
            reload_reasons.extend(
                f"dimension_reload_threshold:{dimension_id}"
                for dimension_id in reload_dimensions
            )
            if periodic_due:
                reload_reasons.append("periodic_reload_due")

            reload_required = bool(reload_reasons) and (
                valid_critical_breach or not cooldown_active
            )
            if reload_required:
                return Evaluation(
                    decision=Decision.RELOAD,
                    reload_required=True,
                    aggregate_drift=aggregate,
                    dimension_scores=scores,
                    reasons=tuple(reload_reasons),
                    state_digest=state.digest,
                    observation_digest=observation_digest,
                    evidence_digest=evidence_digest,
                    turn_index=turn_index,
                    generation=generation,
                    subject_digest=subject_digest,
                    subject_epoch=subject_epoch,
                    restore_packet=self.restore_packet(state),
                    behavioral_decision=behavioral_decision,
                    evidence_trace=strict_evidence_trace,
                )

            warn_reasons: list[str] = []
            if reload_reasons and cooldown_active:
                warn_reasons.extend(reload_reasons)
                warn_reasons.append("reload_suppressed_by_cooldown")
            elif behavioral_decision is Decision.WARN:
                warn_reasons.extend(
                    f"dimension_warn_threshold:{dimension_id}"
                    for dimension_id in warn_dimensions
                )

            if warn_reasons:
                return Evaluation(
                    decision=Decision.WARN,
                    reload_required=False,
                    aggregate_drift=aggregate,
                    dimension_scores=scores,
                    reasons=tuple(warn_reasons),
                    state_digest=state.digest,
                    observation_digest=observation_digest,
                    evidence_digest=evidence_digest,
                    turn_index=turn_index,
                    generation=generation,
                    subject_digest=subject_digest,
                    subject_epoch=subject_epoch,
                    behavioral_decision=behavioral_decision,
                    evidence_trace=strict_evidence_trace,
                )

            return Evaluation(
                decision=Decision.STABLE,
                reload_required=False,
                aggregate_drift=aggregate,
                dimension_scores=scores,
                reasons=("within_policy",),
                state_digest=state.digest,
                observation_digest=observation_digest,
                evidence_digest=evidence_digest,
                turn_index=turn_index,
                generation=generation,
                subject_digest=subject_digest,
                subject_epoch=subject_epoch,
                behavioral_decision=behavioral_decision,
                evidence_trace=strict_evidence_trace,
            )

        total_weight = sum(float(item.weight) for item in state.dimensions)
        aggregate = sum(
            float(dimension.weight)
            * dimension_scores[dimension.dimension_id]
            for dimension in state.dimensions
        ) / total_weight

        critical_breach = valid_critical_breach
        reload_reasons: list[str] = []
        if critical_breach:
            reload_reasons.append("critical_dimension_breach")
        if aggregate >= state.policy.reload_threshold:
            reload_reasons.append("aggregate_reload_threshold")
        if periodic_due:
            reload_reasons.append("periodic_reload_due")

        reload_required = bool(reload_reasons) and (
            critical_breach or not cooldown_active
        )
        if reload_required:
            return Evaluation(
                decision=Decision.RELOAD,
                reload_required=True,
                aggregate_drift=aggregate,
                dimension_scores=scores,
                reasons=tuple(reload_reasons),
                state_digest=state.digest,
                observation_digest=observation_digest,
                evidence_digest=evidence_digest,
                turn_index=turn_index,
                generation=generation,
                subject_digest=subject_digest,
                subject_epoch=subject_epoch,
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
                reload_required=False,
                aggregate_drift=aggregate,
                dimension_scores=scores,
                reasons=tuple(warn_reasons),
                state_digest=state.digest,
                observation_digest=observation_digest,
                evidence_digest=evidence_digest,
                turn_index=turn_index,
                generation=generation,
                subject_digest=subject_digest,
                subject_epoch=subject_epoch,
            )

        return Evaluation(
            decision=Decision.STABLE,
            reload_required=False,
            aggregate_drift=aggregate,
            dimension_scores=scores,
            reasons=("within_policy",),
            state_digest=state.digest,
            observation_digest=observation_digest,
            evidence_digest=evidence_digest,
            turn_index=turn_index,
            generation=generation,
            subject_digest=subject_digest,
            subject_epoch=subject_epoch,
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
