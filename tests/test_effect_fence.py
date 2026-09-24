import os
import tempfile
import unittest
from unittest.mock import patch

from driftguard import (
    BehaviorDimension,
    Decision,
    DriftEvidence,
    DriftPolicy,
    EvidenceIndependence,
    ProbeSource,
    SaveState,
    SourceBinding,
    StaleGenerationError,
)
from driftguard.external_boundary import build_reload_directive
from driftguard.ledger import (
    DriftLedger,
    EffectDispatchPermit,
)
from driftguard.model import raw_bytes_digest


SOURCE = SourceBinding("probe://effect-fence", "v1")
OBS = raw_bytes_digest(b"effect fence observation")


def state() -> SaveState:
    return SaveState(
        "effect-fence",
        "1",
        "restore exact behavior",
        (
            BehaviorDimension(
                "d",
                "behavioral dimension",
                min_independence=EvidenceIndependence.EXTERNAL,
            ),
        ),
        (
            ProbeSource(
                SOURCE,
                EvidenceIndependence.EXTERNAL,
                ("d",),
            ),
        ),
        DriftPolicy(max_turns_without_reload=5, reload_cooldown_turns=0),
    )


def evidence(
    s: SaveState,
    turn: int,
    score: float,
) -> tuple[DriftEvidence, ...]:
    return (
        DriftEvidence(
            f"effect-{turn}",
            "d",
            score,
            EvidenceIndependence.EXTERNAL,
            (SOURCE,),
            f"effect-run-{turn}",
            s.digest,
            OBS,
            turn,
        ),
    )


class EffectFenceTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.close()
        self.path = handle.name
        self.ledger = DriftLedger(self.path)
        self.s = state()
        first = self.ledger.evaluate_and_commit(
            session_id="session",
            state=self.s,
            evidence=evidence(self.s, 0, 0.0),
            observation_digest=OBS,
            turn_index=0,
            expected_generation=0,
        )
        self.assertEqual(Decision.STABLE, first.evaluation.decision)
        self.commit = self.ledger.evaluate_and_commit(
            session_id="session",
            state=self.s,
            evidence=evidence(self.s, 5, 1.0),
            observation_digest=OBS,
            turn_index=5,
            expected_generation=1,
        )
        self.assertTrue(self.commit.evaluation.reload_required)
        self.directive = build_reload_directive(
            session_id="session",
            commit=self.commit,
            ledger=self.ledger,
        )

    def tearDown(self):
        os.unlink(self.path)

    def reserve(self, attempt_id="attempt-1"):
        return self.ledger.reserve_effect_attempt(
            attempt_id=attempt_id,
            session_id="session",
            evaluation_digest=self.directive.evaluation_digest,
            state=self.s,
            expected_generation=self.directive.expected_generation,
            directive_digest=self.directive.digest,
        )

    def test_reservation_binds_exact_currentness_and_creates_one_fence(self):
        receipt = self.reserve()
        self.assertEqual("RESERVED", receipt.status)
        self.assertEqual(self.directive.digest, receipt.directive_digest)
        self.assertEqual(
            self.directive.expected_generation,
            receipt.expected_generation,
        )
        fence = self.ledger.active_effect_fence("session")
        self.assertIsNotNone(fence)
        self.assertEqual(receipt.attempt_id, fence["attempt_id"])
        self.assertEqual(receipt.reservation_digest, fence["reservation_digest"])

    def test_reservation_currentness_and_insert_share_one_connection(self):
        original_connect = self.ledger._connect
        calls = 0

        def counted_connect():
            nonlocal calls
            calls += 1
            return original_connect()

        with patch.object(self.ledger, "_connect", side_effect=counted_connect):
            self.reserve()
        self.assertEqual(1, calls)

    def test_second_unresolved_reservation_is_rejected(self):
        self.reserve()
        with self.assertRaisesRegex(
            StaleGenerationError,
            "unresolved effect fence",
        ):
            self.reserve("attempt-2")

    def test_stale_generation_cannot_reserve(self):
        with self.assertRaisesRegex(
            StaleGenerationError,
            "generation is stale",
        ):
            self.ledger.reserve_effect_attempt(
                attempt_id="stale",
                session_id="session",
                evaluation_digest=self.directive.evaluation_digest,
                state=self.s,
                expected_generation=self.directive.expected_generation - 1,
                directive_digest=self.directive.digest,
            )

    def test_pre_dispatch_cancel_releases_fence_and_allows_fresh_reservation(self):
        self.reserve()
        cancelled = self.ledger.cancel_effect_attempt("attempt-1")
        self.assertEqual("CANCELLED_BEFORE_DISPATCH", cancelled.status)
        self.assertIsNone(self.ledger.active_effect_fence("session"))

        successor = self.reserve("attempt-2")
        self.assertEqual("RESERVED", successor.status)
        self.assertEqual("attempt-2", successor.attempt_id)

    def test_dispatch_claim_is_single_use_and_fence_remains_active(self):
        receipt = self.reserve()
        permit = self.ledger.claim_effect_dispatch("attempt-1")
        self.assertEqual("attempt-1", permit.attempt_id)
        self.assertEqual(receipt.reservation_digest, permit.reservation_digest)
        self.assertEqual(
            "MECHANICAL_SINGLE_USE_DISPATCH_PERMIT_ONLY",
            permit.claim,
        )
        self.assertEqual(
            "DISPATCH_UNCERTAIN",
            self.ledger.effect_attempt("attempt-1").status,
        )
        self.assertIsNotNone(self.ledger.active_effect_fence("session"))

        with self.assertRaisesRegex(
            StaleGenerationError,
            "no longer available",
        ):
            self.ledger.claim_effect_dispatch("attempt-1")

    def test_claimed_attempt_cannot_be_cancelled_or_release_fence(self):
        self.reserve()
        self.ledger.claim_effect_dispatch("attempt-1")
        with self.assertRaisesRegex(
            StaleGenerationError,
            "only a RESERVED",
        ):
            self.ledger.cancel_effect_attempt("attempt-1")
        self.assertIsNotNone(self.ledger.active_effect_fence("session"))

    def test_dispatch_permit_cannot_be_constructed_directly(self):
        receipt = self.reserve()
        with self.assertRaisesRegex(ValueError, "may only be issued"):
            EffectDispatchPermit(
                attempt_id=receipt.attempt_id,
                reservation_digest=receipt.reservation_digest,
            )

    def test_generation_move_after_reservation_does_not_release_fence(self):
        self.reserve()
        self.ledger.acknowledge_reload(
            session_id="session",
            state=self.s,
            acknowledgement=__import__(
                "driftguard", fromlist=["ReloadAcknowledgement"]
            ).ReloadAcknowledgement(
                "ack-effect-fence",
                self.commit.evaluation.digest,
                self.s.digest,
                self.commit.evaluation.turn_index,
            ),
            expected_generation=self.commit.successor_generation,
        )
        self.assertIsNotNone(self.ledger.active_effect_fence("session"))
        with self.assertRaisesRegex(
            StaleGenerationError,
            "unresolved effect fence",
        ):
            self.reserve("attempt-after-generation-move")


if __name__ == "__main__":
    unittest.main()
