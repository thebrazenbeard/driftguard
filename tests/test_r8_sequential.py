from dataclasses import replace
import os
import tempfile
import unittest

from driftguard import (
    BehaviorDimension,
    CusumDimensionPolicy,
    Decision,
    DriftEvidence,
    EvidenceIndependence,
    MeasurementMode,
    MonitoredSubject,
    ProbeSource,
    ReloadAcknowledgement,
    SaveState,
    SequentialDetectorSpec,
    SequentialStatus,
    SourceBinding,
    StaleGenerationError,
    SubjectComponent,
)
from driftguard.ledger import DriftLedger
from driftguard.model import raw_bytes_digest


OBS = raw_bytes_digest(b"r8-observation")
SOURCE = SourceBinding("probe://r8", "v1")
SOURCE_CAL = SourceBinding("calibration://r8-probe", "v1")
SOURCE_CAL_DIGEST = raw_bytes_digest(b"r8-probe-calibration")
DETECTOR_CAL = SourceBinding("calibration://r8-cusum", "v1")
DETECTOR_CAL_DIGEST = raw_bytes_digest(b"r8-cusum-calibration")
REQUIRED = (
    "provider",
    "model",
    "instructions",
    "tools",
    "retrieval",
    "memory",
    "inference",
    "harness",
)


def state():
    return SaveState(
        "r8-state",
        "1",
        "restore",
        (
            BehaviorDimension(
                "d",
                "dimension",
                critical=False,
                min_independence=EvidenceIndependence.SEPARATE_CONTEXT,
                min_sources=1,
                min_correlation_groups=1,
                score_scale="r8-scale",
                max_source_spread=0.50,
                warn_threshold=0.80,
                reload_threshold=0.95,
            ),
        ),
        (
            ProbeSource(
                SOURCE,
                EvidenceIndependence.SEPARATE_CONTEXT,
                ("d",),
                calibration=SOURCE_CAL,
                calibration_digest=SOURCE_CAL_DIGEST,
                correlation_group="r8-root",
                score_scale="r8-scale",
            ),
        ),
        measurement_mode=MeasurementMode.CALIBRATED_QUORUM,
    )


def subject(epoch=0):
    return MonitoredSubject(
        "r8-subject",
        epoch,
        tuple(
            SubjectComponent(
                component_id=item,
                binding=SourceBinding(f"subject://{item}", "v1"),
                digest=raw_bytes_digest(f"r8-{item}".encode("utf-8")),
            )
            for item in REQUIRED
        ),
    )


def evidence(s, monitored, turn, score):
    return (
        DriftEvidence(
            f"e-{turn}",
            "d",
            score,
            EvidenceIndependence.SEPARATE_CONTEXT,
            (SOURCE,),
            f"run-{turn}",
            s.digest,
            OBS,
            turn,
            monitored.configuration_digest,
            monitored.epoch,
        ),
    )


def detector_spec(
    s,
    monitored,
    session_id="r8-session",
    *,
    max_consecutive_unknown=1,
    max_turn_gap=2,
):
    return SequentialDetectorSpec(
        detector_id="cusum-r8",
        session_id=session_id,
        state_digest=s.digest,
        measurement_digest=s.measurement_digest,
        subject_digest=monitored.configuration_digest,
        subject_epoch=monitored.epoch,
        calibration=DETECTOR_CAL,
        calibration_digest=DETECTOR_CAL_DIGEST,
        max_consecutive_unknown=max_consecutive_unknown,
        max_turn_gap=max_turn_gap,
        dimensions=(
            CusumDimensionPolicy(
                "d",
                baseline_mean=0.10,
                allowance=0.05,
                alarm_threshold=0.50,
            ),
        ),
    )


class SequentialCusumTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.close()
        self.path = handle.name
        self.ledger = DriftLedger(self.path)
        self.state = state()
        self.subject = subject()
        self.session_id = "r8-session"

    def tearDown(self):
        os.unlink(self.path)

    def commit(self, score, *, turn, generation, session_id=None):
        session_id = session_id or self.session_id
        return self.ledger.evaluate_and_commit(
            session_id=session_id,
            state=self.state,
            evidence=evidence(
                self.state,
                self.subject,
                turn,
                score,
            ),
            observation_digest=OBS,
            turn_index=turn,
            expected_generation=generation,
            subject=self.subject,
        )

    def commit_unknown(self, *, turn, generation):
        return self.ledger.evaluate_and_commit(
            session_id=self.session_id,
            state=self.state,
            evidence=(),
            observation_digest=OBS,
            turn_index=turn,
            expected_generation=generation,
            subject=self.subject,
        )

    def register_after_anchor(self, anchor_score=0.10, **spec_kwargs):
        anchor = self.commit(anchor_score, turn=0, generation=0)
        spec = detector_spec(
            self.state,
            self.subject,
            self.session_id,
            **spec_kwargs,
        )
        registration = self.ledger.register_sequential_detector(
            spec=spec,
            state=self.state,
            subject=self.subject,
        )
        self.assertEqual(anchor.evaluation.digest, registration.anchor_evaluation_digest)
        self.assertEqual(1, registration.session_generation)
        return spec, registration, anchor

    def advance(self, spec, commit, generation):
        return self.ledger.advance_sequential_detector(
            spec=spec,
            state=self.state,
            subject=self.subject,
            evaluation_digest=commit.evaluation.digest,
            expected_generation=generation,
        )

    def test_registration_is_future_only_precommit(self):
        anchor = self.commit(0.10, turn=0, generation=0)
        historical = self.commit(0.70, turn=1, generation=1)
        spec = detector_spec(self.state, self.subject, self.session_id)
        registration = self.ledger.register_sequential_detector(
            spec=spec,
            state=self.state,
            subject=self.subject,
        )
        self.assertEqual(
            historical.evaluation.digest,
            registration.anchor_evaluation_digest,
        )
        self.assertEqual(2, registration.session_generation)
        self.assertNotEqual(
            anchor.evaluation.digest,
            registration.anchor_evaluation_digest,
        )

        future = self.commit(0.10, turn=2, generation=2)
        with self.assertRaisesRegex(
            StaleGenerationError,
            "exact next evaluation",
        ):
            self.advance(spec, historical, 0)
        accepted = self.advance(spec, future, 0)
        self.assertEqual(SequentialStatus.MONITORING, accepted.status)
        self.assertEqual(1, accepted.observation_count)

    def test_registration_receipt_is_idempotent_for_exact_spec(self):
        spec, first, _ = self.register_after_anchor()
        second = self.ledger.register_sequential_detector(
            spec=spec,
            state=self.state,
            subject=self.subject,
        )
        self.assertEqual(first.digest, second.digest)

    def test_precommitted_cusum_accumulates_and_alarms(self):
        spec, _, _ = self.register_after_anchor(0.10)

        first = self.commit(0.10, turn=1, generation=1)
        r0 = self.advance(spec, first, 0)
        self.assertEqual(SequentialStatus.MONITORING, r0.status)
        self.assertEqual((("d", 0.0),), r0.cusum_values)

        second = self.commit(0.20, turn=2, generation=2)
        r1 = self.advance(spec, second, 1)
        self.assertEqual((("d", 0.05),), r1.cusum_values)

        third = self.commit(0.40, turn=3, generation=3)
        r2 = self.advance(spec, third, 2)
        self.assertEqual((("d", 0.30),), r2.cusum_values)

        fourth = self.commit(0.50, turn=4, generation=4)
        r3 = self.advance(spec, fourth, 3)
        self.assertEqual(SequentialStatus.ALARM, r3.status)
        self.assertEqual((("d", 0.65),), r3.cusum_values)
        self.assertEqual(("d",), r3.alarm_dimensions)
        self.assertEqual(4, r3.observation_count)
        self.assertEqual(4, len(self.ledger.sequential_events(spec.detector_id)))

    def test_alarm_is_latched_not_auto_reset(self):
        spec, _, _ = self.register_after_anchor()
        high = self.commit(0.80, turn=1, generation=1)
        alarm = self.advance(spec, high, 0)
        self.assertEqual(SequentialStatus.ALARM, alarm.status)
        low = self.commit(0.0, turn=2, generation=2)
        later = self.advance(spec, low, 1)
        self.assertEqual(SequentialStatus.ALARM, later.status)
        self.assertEqual(("d",), later.alarm_dimensions)

    def test_unknown_after_alarm_does_not_erase_alarm_latch(self):
        spec, _, _ = self.register_after_anchor(max_consecutive_unknown=2)
        high = self.commit(0.80, turn=1, generation=1)
        alarm = self.advance(spec, high, 0)
        unknown = self.commit_unknown(turn=2, generation=2)
        receipt = self.advance(spec, unknown, 1)
        self.assertEqual(SequentialStatus.ALARM, receipt.status)
        self.assertEqual(alarm.alarm_dimensions, receipt.alarm_dimensions)
        self.assertEqual(1, receipt.consecutive_unknown)
        self.assertIn("evaluation_behavior_unknown", receipt.reasons)

    def test_cannot_cherry_pick_later_future_evaluation(self):
        spec, _, _ = self.register_after_anchor()
        second = self.commit(0.10, turn=1, generation=1)
        third = self.commit(0.10, turn=2, generation=2)
        with self.assertRaisesRegex(
            StaleGenerationError,
            "exact next evaluation",
        ):
            self.advance(spec, third, 0)
        accepted = self.advance(spec, second, 0)
        self.assertEqual(SequentialStatus.MONITORING, accepted.status)

    def test_detector_generation_compare_and_swap(self):
        spec, _, _ = self.register_after_anchor()
        next_event = self.commit(0.10, turn=1, generation=1)
        with self.assertRaisesRegex(
            StaleGenerationError,
            "generation mismatch",
        ):
            self.advance(spec, next_event, 1)

    def test_unknown_budget_invalidates_detector_irreversibly(self):
        spec, _, _ = self.register_after_anchor(max_consecutive_unknown=1)

        valid = self.commit(0.20, turn=1, generation=1)
        initial = self.advance(spec, valid, 0)
        self.assertEqual(1, initial.observation_count)

        unknown1 = self.commit_unknown(turn=2, generation=2)
        skipped = self.advance(spec, unknown1, 1)
        self.assertEqual(SequentialStatus.SKIPPED_UNKNOWN, skipped.status)
        self.assertEqual(1, skipped.consecutive_unknown)
        self.assertFalse(skipped.gap_invalid)
        self.assertEqual(initial.cusum_values, skipped.cusum_values)

        unknown2 = self.commit_unknown(turn=3, generation=3)
        invalid = self.advance(spec, unknown2, 2)
        self.assertEqual(SequentialStatus.INVALID_GAP, invalid.status)
        self.assertTrue(invalid.gap_invalid)
        self.assertEqual(2, invalid.consecutive_unknown)
        self.assertEqual(1, invalid.observation_count)

        later_valid = self.commit(0.90, turn=4, generation=4)
        still_invalid = self.advance(spec, later_valid, 3)
        self.assertEqual(SequentialStatus.INVALID_GAP, still_invalid.status)
        self.assertTrue(still_invalid.gap_invalid)
        self.assertEqual(invalid.cusum_values, still_invalid.cusum_values)
        self.assertEqual(1, still_invalid.observation_count)

    def test_zero_unknown_budget_invalidates_first_unknown(self):
        spec, _, _ = self.register_after_anchor(max_consecutive_unknown=0)
        unknown = self.commit_unknown(turn=1, generation=1)
        receipt = self.advance(spec, unknown, 0)
        self.assertEqual(SequentialStatus.INVALID_GAP, receipt.status)
        self.assertTrue(receipt.gap_invalid)

    def test_turn_gap_budget_invalidates_detector(self):
        spec, _, _ = self.register_after_anchor(max_turn_gap=2)
        far = self.commit(0.20, turn=3, generation=1)
        receipt = self.advance(spec, far, 0)
        self.assertEqual(SequentialStatus.INVALID_GAP, receipt.status)
        self.assertTrue(receipt.gap_invalid)
        self.assertEqual(3, receipt.turn_gap)
        self.assertIn("turn_gap_exceeded", receipt.reasons)
        self.assertEqual(0, receipt.observation_count)

    def test_session_generation_mutation_invalidates_detector(self):
        spec, _, _ = self.register_after_anchor(max_turn_gap=3)

        reload_commit = self.commit(0.99, turn=1, generation=1)
        first = self.advance(spec, reload_commit, 0)
        self.assertEqual(SequentialStatus.ALARM, first.status)
        self.assertEqual(1, first.session_generation_before)
        self.assertEqual(2, first.session_generation_after)

        acknowledgement = ReloadAcknowledgement(
            "ack-r8-continuity",
            reload_commit.evaluation.digest,
            self.state.digest,
            1,
        )
        ack = self.ledger.acknowledge_reload(
            session_id=self.session_id,
            state=self.state,
            acknowledgement=acknowledgement,
            expected_generation=2,
            subject=self.subject,
        )
        self.assertEqual(3, ack.successor_generation)

        after_ack = self.commit(0.10, turn=2, generation=3)
        invalid = self.advance(spec, after_ack, 1)
        self.assertEqual(SequentialStatus.INVALID_GAP, invalid.status)
        self.assertTrue(invalid.gap_invalid)
        self.assertEqual(3, invalid.session_generation_before)
        self.assertEqual(4, invalid.session_generation_after)
        self.assertIn(
            "session_generation_discontinuity",
            invalid.reasons,
        )

    def test_detector_id_cannot_be_rebound_to_new_policy(self):
        spec, _, _ = self.register_after_anchor()
        changed = replace(
            spec,
            dimensions=(
                replace(
                    spec.dimensions[0],
                    alarm_threshold=0.75,
                ),
            ),
        )
        with self.assertRaisesRegex(
            StaleGenerationError,
            "already bound to another spec",
        ):
            self.ledger.register_sequential_detector(
                spec=changed,
                state=self.state,
                subject=self.subject,
            )

    def test_detector_spec_must_match_exact_measurement_contract(self):
        self.commit(0.10, turn=0, generation=0)
        spec = detector_spec(self.state, self.subject, self.session_id)
        bad = replace(
            spec,
            measurement_digest=raw_bytes_digest(
                b"different-measurement-contract"
            ),
        )
        with self.assertRaisesRegex(
            ValueError,
            "measurement digest mismatch",
        ):
            self.ledger.register_sequential_detector(
                spec=bad,
                state=self.state,
                subject=self.subject,
            )

    def test_superseded_subject_epoch_invalidates_detector(self):
        spec, _, _ = self.register_after_anchor()
        future = self.commit(0.20, turn=1, generation=1)

        next_subject = subject(epoch=1)
        self.ledger.evaluate_and_commit(
            session_id="new-epoch-session",
            state=self.state,
            evidence=evidence(
                self.state,
                next_subject,
                0,
                0.10,
            ),
            observation_digest=OBS,
            turn_index=0,
            expected_generation=0,
            subject=next_subject,
        )
        with self.assertRaisesRegex(
            StaleGenerationError,
            "epoch has been superseded",
        ):
            self.ledger.advance_sequential_detector(
                spec=spec,
                state=self.state,
                subject=self.subject,
                evaluation_digest=future.evaluation.digest,
                expected_generation=0,
            )

    def test_sequential_alarm_has_no_reload_side_effect(self):
        spec, _, _ = self.register_after_anchor()
        high = self.commit(0.80, turn=1, generation=1)
        receipt = self.advance(spec, high, 0)
        self.assertEqual(SequentialStatus.ALARM, receipt.status)
        session = self.ledger.session_row(self.session_id)
        self.assertIsNone(session["last_reload_decision_turn"])
        self.assertEqual(2, session["generation"])
        self.assertEqual(1, receipt.generation_after)

    def test_reprocessing_same_event_is_rejected(self):
        spec, _, _ = self.register_after_anchor()
        next_event = self.commit(0.10, turn=1, generation=1)
        self.advance(spec, next_event, 0)
        with self.assertRaisesRegex(
            StaleGenerationError,
            "no next evaluation event",
        ):
            self.advance(spec, next_event, 1)

    def test_policy_digest_moves_when_calibrated_threshold_moves(self):
        spec, _, _ = self.register_after_anchor()
        changed = replace(
            spec,
            dimensions=(
                replace(
                    spec.dimensions[0],
                    alarm_threshold=0.51,
                ),
            ),
        )
        self.assertNotEqual(spec.digest, changed.digest)

    def test_policy_digest_moves_when_turn_gap_budget_moves(self):
        spec, _, _ = self.register_after_anchor(max_turn_gap=2)
        changed = replace(spec, max_turn_gap=3)
        self.assertNotEqual(spec.digest, changed.digest)

    def test_policy_digest_moves_when_unknown_budget_moves(self):
        spec, _, _ = self.register_after_anchor(max_consecutive_unknown=1)
        changed = replace(spec, max_consecutive_unknown=2)
        self.assertNotEqual(spec.digest, changed.digest)


if __name__ == "__main__":
    unittest.main()
