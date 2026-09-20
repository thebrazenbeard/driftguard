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


def detector_spec(s, monitored, session_id="r8-session"):
    return SequentialDetectorSpec(
        detector_id="cusum-r8",
        session_id=session_id,
        state_digest=s.digest,
        measurement_digest=s.measurement_digest,
        subject_digest=monitored.configuration_digest,
        subject_epoch=monitored.epoch,
        calibration=DETECTOR_CAL,
        calibration_digest=DETECTOR_CAL_DIGEST,
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

    def register_after_first(self, score=0.10):
        first = self.commit(score, turn=0, generation=0)
        spec = detector_spec(
            self.state,
            self.subject,
            self.session_id,
        )
        row = self.ledger.register_sequential_detector(
            spec=spec,
            state=self.state,
            subject=self.subject,
        )
        self.assertEqual(0, row["generation"])
        return spec, first

    def advance(self, spec, commit, generation):
        return self.ledger.advance_sequential_detector(
            spec=spec,
            state=self.state,
            subject=self.subject,
            evaluation_digest=commit.evaluation.digest,
            expected_generation=generation,
        )

    def test_precommitted_cusum_accumulates_and_alarms(self):
        spec, first = self.register_after_first(0.10)
        r0 = self.advance(spec, first, 0)
        self.assertEqual(SequentialStatus.MONITORING, r0.status)
        self.assertEqual((("d", 0.0),), r0.cusum_values)

        second = self.commit(0.20, turn=1, generation=1)
        r1 = self.advance(spec, second, 1)
        self.assertEqual((("d", 0.05),), r1.cusum_values)

        third = self.commit(0.40, turn=2, generation=2)
        r2 = self.advance(spec, third, 2)
        self.assertEqual((("d", 0.30),), r2.cusum_values)

        fourth = self.commit(0.50, turn=3, generation=3)
        r3 = self.advance(spec, fourth, 3)
        self.assertEqual(SequentialStatus.ALARM, r3.status)
        self.assertEqual((("d", 0.65),), r3.cusum_values)
        self.assertEqual(("d",), r3.alarm_dimensions)
        self.assertEqual(4, r3.observation_count)
        self.assertEqual(4, len(self.ledger.sequential_events(spec.detector_id)))

    def test_alarm_is_latched_not_auto_reset(self):
        spec, first = self.register_after_first(0.80)
        alarm = self.advance(spec, first, 0)
        self.assertEqual(SequentialStatus.ALARM, alarm.status)
        low = self.commit(0.0, turn=1, generation=1)
        later = self.advance(spec, low, 1)
        self.assertEqual(SequentialStatus.ALARM, later.status)
        self.assertEqual(("d",), later.alarm_dimensions)

    def test_cannot_cherry_pick_later_evaluation(self):
        first = self.commit(0.10, turn=0, generation=0)
        second = self.commit(0.10, turn=1, generation=1)
        spec = detector_spec(self.state, self.subject, self.session_id)
        self.ledger.register_sequential_detector(
            spec=spec,
            state=self.state,
            subject=self.subject,
        )
        with self.assertRaisesRegex(
            StaleGenerationError,
            "exact next evaluation",
        ):
            self.advance(spec, second, 0)
        accepted = self.advance(spec, first, 0)
        self.assertEqual(SequentialStatus.MONITORING, accepted.status)

    def test_detector_generation_compare_and_swap(self):
        spec, first = self.register_after_first()
        with self.assertRaisesRegex(
            StaleGenerationError,
            "generation mismatch",
        ):
            self.advance(spec, first, 1)

    def test_unknown_evaluation_is_consumed_but_not_accumulated(self):
        spec, first = self.register_after_first(0.20)
        initial = self.advance(spec, first, 0)
        self.assertEqual(1, initial.observation_count)

        unknown = self.ledger.evaluate_and_commit(
            session_id=self.session_id,
            state=self.state,
            evidence=(),
            observation_digest=OBS,
            turn_index=1,
            expected_generation=1,
            subject=self.subject,
        )
        skipped = self.advance(spec, unknown, 1)
        self.assertEqual(
            SequentialStatus.SKIPPED_UNKNOWN,
            skipped.status,
        )
        self.assertEqual(1, skipped.observation_count)
        self.assertEqual(initial.cusum_values, skipped.cusum_values)

        valid = self.commit(0.20, turn=2, generation=2)
        resumed = self.advance(spec, valid, 2)
        self.assertEqual(2, resumed.observation_count)

    def test_detector_id_cannot_be_rebound_to_new_policy(self):
        spec, _ = self.register_after_first()
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
        first = self.commit(0.10, turn=0, generation=0)
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
        self.assertEqual(Decision.STABLE, first.evaluation.decision)

    def test_superseded_subject_epoch_invalidates_detector(self):
        spec, first = self.register_after_first()
        self.advance(spec, first, 0)

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
        second = self.ledger.events(self.session_id)
        self.assertEqual(1, len(second))
        with self.assertRaisesRegex(
            StaleGenerationError,
            "epoch has been superseded",
        ):
            self.ledger.advance_sequential_detector(
                spec=spec,
                state=self.state,
                subject=self.subject,
                evaluation_digest=first.evaluation.digest,
                expected_generation=1,
            )

    def test_sequential_alarm_has_no_reload_side_effect(self):
        spec, first = self.register_after_first(0.80)
        receipt = self.advance(spec, first, 0)
        self.assertEqual(SequentialStatus.ALARM, receipt.status)
        session = self.ledger.session_row(self.session_id)
        self.assertIsNone(session["last_reload_decision_turn"])
        self.assertEqual(1, session["generation"])
        self.assertEqual(1, receipt.generation_after)

    def test_reprocessing_same_event_is_rejected(self):
        spec, first = self.register_after_first()
        self.advance(spec, first, 0)
        with self.assertRaisesRegex(
            StaleGenerationError,
            "no next evaluation event",
        ):
            self.advance(spec, first, 1)

    def test_policy_digest_moves_when_calibrated_threshold_moves(self):
        spec, _ = self.register_after_first()
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


if __name__ == "__main__":
    unittest.main()
