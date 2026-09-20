import os
import tempfile
import unittest

from driftguard import (
    BehaviorDimension,
    DriftEvidence,
    DriftPolicy,
    EvidenceIndependence,
    ProbeSource,
    ReloadAcknowledgement,
    SaveState,
    SourceBinding,
)
from driftguard.discovery_effect import (
    DISCOVERY_EFFECT_SCHEMA_VERSION,
    reload_acknowledgement_envelope,
    reload_decision_envelope,
)
from driftguard.ledger import DriftLedger
from driftguard.model import raw_bytes_digest


SOURCE = SourceBinding("probe://discovery-effect-test", "v1")
OBS = raw_bytes_digest(b"discovery-effect-observation")


def state() -> SaveState:
    return SaveState(
        "discovery-effect-state",
        "1",
        "restore exact governed behavior",
        (
            BehaviorDimension(
                "critical",
                "critical governed behavior",
                critical=True,
                min_independence=EvidenceIndependence.SEPARATE_CONTEXT,
            ),
        ),
        (
            ProbeSource(
                SOURCE,
                EvidenceIndependence.SEPARATE_CONTEXT,
                ("critical",),
            ),
        ),
        DriftPolicy(
            critical_reload_threshold=0.4,
            max_turns_without_reload=100,
            reload_cooldown_turns=0,
        ),
    )


def evidence(s: SaveState) -> tuple[DriftEvidence, ...]:
    return (
        DriftEvidence(
            "discovery-effect-evidence",
            "critical",
            1.0,
            EvidenceIndependence.SEPARATE_CONTEXT,
            (SOURCE,),
            "discovery-effect-run",
            s.digest,
            OBS,
            0,
        ),
    )


class DiscoveryEffectAdapterTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.close()
        self.path = handle.name
        self.ledger = DriftLedger(self.path)
        self.state = state()

    def tearDown(self):
        os.unlink(self.path)

    def reload_commit(self):
        return self.ledger.evaluate_and_commit(
            session_id="session",
            state=self.state,
            evidence=evidence(self.state),
            observation_digest=OBS,
            turn_index=0,
            expected_generation=0,
        )

    def test_reload_decision_maps_to_pre_effect_only(self):
        commit = self.reload_commit()
        envelope = reload_decision_envelope(
            session_id="session",
            commit=commit,
        )
        self.assertEqual(
            envelope["schema_version"],
            DISCOVERY_EFFECT_SCHEMA_VERSION,
        )
        self.assertEqual(envelope["normalized_phase"], "PRE_EFFECT")
        self.assertEqual(envelope["retry_disposition"], "DOMAIN_DECIDES")
        self.assertEqual(
            envelope["source_payload_sha256"],
            commit.evaluation.digest,
        )
        self.assertEqual(
            envelope["receipts"][-1],
            {
                "kind": "claim_ceiling",
                "value": "RELOAD_DECISION_NOT_EFFECT",
            },
        )

    def test_accepted_acknowledgement_stays_post_effect_unverified(self):
        commit = self.reload_commit()
        ack = ReloadAcknowledgement(
            "ack-discovery-effect",
            commit.evaluation.digest,
            self.state.digest,
            0,
        )
        result = self.ledger.acknowledge_reload(
            session_id="session",
            state=self.state,
            acknowledgement=ack,
            expected_generation=commit.successor_generation,
        )
        envelope = reload_acknowledgement_envelope(
            session_id="session",
            acknowledgement=ack,
            result=result,
            expected_generation=commit.successor_generation,
        )
        self.assertEqual(
            envelope["normalized_phase"],
            "POST_EFFECT_UNVERIFIED",
        )
        self.assertNotEqual(
            envelope["normalized_phase"],
            "POST_EFFECT_VERIFIED",
        )
        self.assertIn(
            {
                "kind": "claim_ceiling",
                "value": "CALLER_ACKNOWLEDGED_NOT_BEHAVIORALLY_VERIFIED",
            },
            envelope["receipts"],
        )

    def test_adapter_does_not_mutate_native_ledger(self):
        commit = self.reload_commit()
        before = self.ledger.session_row("session")
        reload_decision_envelope(session_id="session", commit=commit)
        after = self.ledger.session_row("session")
        self.assertEqual(before, after)

    def test_non_reload_decision_cannot_be_exported_as_effect_attempt(self):
        stable = SaveState(
            "stable",
            "1",
            "restore",
            (BehaviorDimension("d", "stable dimension"),),
            (
                ProbeSource(
                    SOURCE,
                    EvidenceIndependence.SEPARATE_CONTEXT,
                    ("d",),
                ),
            ),
            DriftPolicy(max_turns_without_reload=100),
        )
        rows = (
            DriftEvidence(
                "stable-e",
                "d",
                0.0,
                EvidenceIndependence.SEPARATE_CONTEXT,
                (SOURCE,),
                "stable-run",
                stable.digest,
                OBS,
                0,
            ),
        )
        commit = self.ledger.evaluate_and_commit(
            session_id="stable-session",
            state=stable,
            evidence=rows,
            observation_digest=OBS,
            turn_index=0,
            expected_generation=0,
        )
        with self.assertRaisesRegex(ValueError, "reload-required"):
            reload_decision_envelope(
                session_id="stable-session",
                commit=commit,
            )

    def test_ack_adapter_rejects_mismatched_native_receipt(self):
        commit = self.reload_commit()
        ack = ReloadAcknowledgement(
            "ack-discovery-effect",
            commit.evaluation.digest,
            self.state.digest,
            0,
        )
        result = self.ledger.acknowledge_reload(
            session_id="session",
            state=self.state,
            acknowledgement=ack,
            expected_generation=commit.successor_generation,
        )
        wrong = ReloadAcknowledgement(
            "different-ack",
            commit.evaluation.digest,
            self.state.digest,
            0,
        )
        with self.assertRaisesRegex(ValueError, "id mismatch"):
            reload_acknowledgement_envelope(
                session_id="session",
                acknowledgement=wrong,
                result=result,
                expected_generation=commit.successor_generation,
            )

    def test_adapter_has_no_verified_recovery_export_surface(self):
        import driftguard.discovery_effect as adapter

        exported = set(adapter.__all__)
        self.assertNotIn("verified_recovery_envelope", exported)
        self.assertNotIn("POST_EFFECT_VERIFIED", exported)


if __name__ == "__main__":
    unittest.main()
