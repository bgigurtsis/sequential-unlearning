import json
import random
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import finalize_probe2_impossible as finalizer  # noqa: E402
from decay_scalar_normalization import (  # noqa: E402
    V2_CORRUPTION_TRACKS,
    V2_LADDER_VERSION,
    V2_POLICY,
    bidirectional_policy_fingerprint,
    load_bidirectional_anchors,
    normalise_components_bidirectional,
)
from run_noise_sweep import (  # noqa: E402
    DEFAULT_ALPHAS,
    DEFAULT_SEEDS,
    fingerprint,
    model_weight_hashes,
    pchip_eval,
    sha256_of_file,
    support_file_hashes,
)


Y05 = 9.6020107277
Y10 = 95.1455064481


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


class CanonicalInterruptedFixture:
    def __init__(self, base):
        self.root = Path(base) / "probe2_noise_v2"
        self.parent = Path(base) / "parent"
        self.parent.mkdir(parents=True)
        (self.parent / "model.safetensors").write_bytes(b"clean-parent-weights")
        (self.parent / "config.json").write_text('{"model":"fixture"}\n')
        self.parent_weights = model_weight_hashes(self.parent)
        self.parent_support = support_file_hashes(self.parent)
        self.root.mkdir()
        self._write_config_and_identity()
        self._write_baseline_anchor_ladder()
        self._write_completed_curve()
        self._write_partial_checkpoint()
        command = (
            "$ python scripts/eval_decay_scalar.py --model "
            f"{self.root / 'sweep' / 'alpha0.2_seed0' / 'checkpoint'} "
            f"--output {self.root / 'sweep' / 'alpha0.2_seed0' / 'scalar.json'}\n"
        )
        (self.root / "commands.log").write_text(
            command
            + "196 prompts in the battery\n"
            + "  generated 8/196\n"
            + "  generated 16/196\n"
            + "  generated 24/196\n"
            + "  generated 32/196\n",
            encoding="utf-8",
        )

    def _write_config_and_identity(self):
        instruments = {
            relative: sha256_of_file(REPO / relative)
            for relative in finalizer.EXPECTED_INSTRUMENT_PATHS
        }
        body = {
            "parent_model": str(self.parent.resolve()),
            "beta": 1.0,
            "alphas": DEFAULT_ALPHAS,
            "seeds": DEFAULT_SEEDS,
            "batch_size": 8,
            "max_new_tokens": 256,
            "cliff_threshold": 20.0,
            "max_bisections": 8,
            "normalisation_version": V2_POLICY,
            "parent_weight_sha256": self.parent_weights,
            "parent_support_sha256": self.parent_support,
            "instrument_file_sha256": instruments,
            "code_commit": "a" * 40,
        }
        self.config = {**body, "fingerprint": fingerprint(body)}
        write_json(self.root / "run_config.json", self.config)
        identity_body = {
            "source_model": str(self.parent.resolve()),
            "weight_file_sha256": self.parent_weights,
            "support_file_sha256": self.parent_support,
        }
        self.identity = {**identity_body, "fingerprint": fingerprint(identity_body)}
        write_json(self.root / "parent_identity.json", self.identity)
        write_json(
            self.root / "state.json",
            {
                "status": "running",
                "run_config_fingerprint": self.config["fingerprint"],
                "alphas": DEFAULT_ALPHAS,
                "seeds": DEFAULT_SEEDS,
                "bisections": [],
                "normalisation_version": V2_POLICY,
            },
        )

    def scalar_payload(self, model, components, weights, support, policy=None, fp=None):
        prompt_hashes = finalizer.expected_prompt_hashes(self.config)
        return {
            "model": str(model),
            "judge_model": str(self.parent.resolve()),
            "tokenizer_model": str(self.parent.resolve()),
            "limit": None,
            "judge_parse_complete": True,
            "components": components,
            "model_weight_sha256": weights,
            "model_support_sha256": support,
            "tokenizer_support_sha256": self.parent_support,
            "judge_support_sha256": self.parent_support,
            "judge_weight_sha256": self.parent_weights,
            "prompt_files": {
                key: {"sha256": value} for key, value in prompt_hashes.items()
            },
            "normalisation_policy": policy,
            "normalisation_policy_fingerprint": fp,
        }

    def _write_baseline_anchor_ladder(self):
        self.baseline_components = {key: 0.1 for key in ("R", "D", "J", "F")}
        baseline = self.scalar_payload(
            self.parent.resolve(),
            self.baseline_components,
            self.parent_weights,
            self.parent_support,
        )
        self.baseline_path = self.root / "baseline" / "scalar.json"
        write_json(self.baseline_path, baseline)

        anchor_sidecar = {
            "alpha": 1.0,
            "beta": 1.0,
            "seed": 0,
            "source_model": str(self.parent.resolve()),
            "tokenizer_source": str(self.parent.resolve()),
            "source_identity_fingerprint": self.identity["fingerprint"],
            "source_identity": self.identity,
            "weight_file_sha256": {"model.safetensors": "c" * 64},
            "support_file_sha256": {"config.json": "d" * 64},
        }
        write_json(self.root / "anchor" / "decay_dose.json", anchor_sidecar)
        self.anchor_components = {"R": 0.0, "D": 0.0, "J": 1.0, "F": 1.0}
        self.anchor_path = self.root / "anchor" / "scalar.json"
        write_json(
            self.anchor_path,
            self.scalar_payload(
                self.root / "anchor" / "checkpoint",
                self.anchor_components,
                anchor_sidecar["weight_file_sha256"],
                anchor_sidecar["support_file_sha256"],
            ),
        )
        ladder = {
            "ladder_version": V2_LADDER_VERSION,
            "corruption_tracks": V2_CORRUPTION_TRACKS,
            "limit": None,
            "baseline_sha256": sha256_of_file(self.baseline_path),
            "judge_model": str(self.parent.resolve()),
            "tokenizer_model": str(self.parent.resolve()),
            "tokenizer_support_sha256": self.parent_support,
            "judge_support_sha256": self.parent_support,
            "judge_weight_sha256": self.parent_weights,
            "judge_parse_complete": True,
            "factual_dropout_order": [f"fact-{index}" for index in range(40)],
            "component_summary": [
                {"fraction": 0.0, **self.baseline_components},
                {"fraction": 1.0, "R": 1.0, "D": 1.0, "J": 1.0, "F": 1.0},
            ],
            "monotonicity": {
                key: {"strictly_nondecreasing": True, "range": 0.9}
                for key in ("R", "D", "J", "F")
            },
        }
        self.ladder_path = self.root / "ladder" / "corruption_ladder.json"
        write_json(self.ladder_path, ladder)
        self.baseline, self.positive, self.negative, self.sources = (
            load_bidirectional_anchors(
                self.baseline_path, self.anchor_path, self.ladder_path
            )
        )
        self.policy_fp = bidirectional_policy_fingerprint(
            self.baseline, self.positive, self.negative, self.sources
        )
        self._write_reanalysis(self.baseline_path)
        self._write_reanalysis(self.anchor_path)

    def _write_reanalysis(self, scalar_path):
        payload = json.loads(Path(scalar_path).read_text())
        normalised, scalar, directions = normalise_components_bidirectional(
            payload["components"], self.baseline, self.positive, self.negative
        )
        write_json(
            Path(scalar_path).with_name("scalar_reanalysis_bidirectional_v2.json"),
            {
                "normalisation_version": V2_POLICY,
                "source_scalar_json": str(scalar_path),
                "source_scalar_sha256": sha256_of_file(scalar_path),
                "policy_fingerprint": self.policy_fp,
                "components": payload["components"],
                "normalised_components": normalised,
                "normalisation_directions": directions,
                "scalar_0_100": scalar,
                "baseline_components": self.baseline,
                "positive_component_anchor": self.positive,
                "negative_component_anchor": self.negative,
                "component_anchor_sources": self.sources,
            },
        )

    def dose_sidecar(self, alpha, seed, weights=None, support=None):
        return {
            "alpha": float(alpha),
            "beta": 1.0,
            "seed": int(seed),
            "source_model": str(self.parent.resolve()),
            "tokenizer_source": str(self.parent.resolve()),
            "source_identity_fingerprint": self.identity["fingerprint"],
            "source_identity": self.identity,
            "weight_file_sha256": weights or {"model.safetensors": f"{seed + 1:x}" * 64},
            "support_file_sha256": support or {"config.json": f"{seed + 4:x}" * 64},
        }

    def _write_completed_curve(self):
        for alpha, value in ((0.05, Y05), (0.1, Y10)):
            fraction = value / 100.0
            components = {
                key: 0.1 + 0.9 * fraction for key in ("R", "D", "J", "F")
            }
            for seed in DEFAULT_SEEDS:
                dose_dir = self.root / "sweep" / f"alpha{alpha:g}_seed{seed}"
                sidecar = self.dose_sidecar(alpha, seed)
                write_json(dose_dir / "decay_dose.json", sidecar)
                scalar_path = dose_dir / "scalar.json"
                payload = self.scalar_payload(
                    dose_dir / "checkpoint",
                    components,
                    sidecar["weight_file_sha256"],
                    sidecar["support_file_sha256"],
                    V2_POLICY,
                    self.policy_fp,
                )
                _, scalar, _ = normalise_components_bidirectional(
                    components, self.baseline, self.positive, self.negative
                )
                payload["scalar_0_100"] = scalar
                write_json(scalar_path, payload)
                self._write_reanalysis(scalar_path)

    def _write_partial_checkpoint(self):
        checkpoint = self.root / "sweep" / "alpha0.2_seed0" / "checkpoint"
        checkpoint.mkdir(parents=True)
        (checkpoint / "model.safetensors").write_bytes(b"partial-checkpoint")
        (checkpoint / "config.json").write_text('{"partial":true}\n')
        sidecar = self.dose_sidecar(
            0.2,
            0,
            model_weight_hashes(checkpoint),
            support_file_hashes(checkpoint),
        )
        write_json(checkpoint / "decay_dose.json", sidecar)


class FinalizeProbe2ImpossibleTests(unittest.TestCase):
    def setUp(self):
        self.source_commit_patch = mock.patch.object(
            finalizer, "resolve_source_commit", return_value="b" * 40
        )
        self.source_blob_patch = mock.patch.object(
            finalizer,
            "read_committed_finalizer_blob",
            side_effect=lambda repo, commit: (
                REPO / "scripts" / "finalize_probe2_impossible.py"
            ).read_bytes(),
        )
        self.source_commit_patch.start()
        self.source_blob_patch.start()
        self.addCleanup(self.source_commit_patch.stop)
        self.addCleanup(self.source_blob_patch.stop)

    def make_fixture(self, temporary):
        return CanonicalInterruptedFixture(temporary)

    def test_exact_pchip_regression_and_monotone_bound_property(self):
        bound = finalizer.pchip_max_prediction_at_point_one(Y05)
        self.assertAlmostEqual(bound["extreme_slopes"]["m_at_0.05"], 268.17234460445263)
        self.assertAlmostEqual(bound["max_possible_prediction"], 38.99791190061747)
        proof = finalizer.prove_loo_impossible(Y05, Y10)
        self.assertAlmostEqual(proof["minimum_possible_absolute_error"], 56.14759454748253)
        rng = random.Random(7)
        xs = bound["rest_xs"]
        for _ in range(1000):
            ys = [0.0, Y05] + sorted(rng.uniform(Y05, 100.0) for _ in range(7))
            self.assertLessEqual(
                pchip_eval(xs, ys, 0.1), bound["max_possible_prediction"] + 1e-12
            )

    def test_finalizes_exact_fail_schema_and_sealed_rerun(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.make_fixture(temporary)
            checkpoint = fixture.root / "sweep" / "alpha0.2_seed0" / "checkpoint"
            original_sidecar = (checkpoint / "decay_dose.json").read_bytes()
            foreign = Path(temporary) / "foreign"
            foreign.mkdir()
            (foreign / "sentinel").write_text("keep")
            first = finalizer.finalize(fixture.root, fixture.parent, REPO)
            second = finalizer.finalize(fixture.root, fixture.parent, REPO)
            self.assertEqual(first["sha256"], second["sha256"])
            self.assertFalse(checkpoint.exists())
            archived = (
                fixture.root
                / "sweep"
                / "alpha0.2_seed0"
                / finalizer.ABORTED_SIDECAR_NAME
            )
            self.assertEqual(archived.read_bytes(), original_sidecar)
            self.assertTrue((foreign / "sentinel").is_file())
            summary = finalizer.read_json(fixture.root / finalizer.SUMMARY_NAME)
            gates = summary["gates"]
            self.assertNotIn("curve", summary)
            self.assertIn("partial_curve", summary)
            self.assertIsNone(gates["loo_interpolation_errors"])
            self.assertIsNone(gates["max_loo_error"])
            self.assertFalse(gates["loo_gate_pass"])
            self.assertEqual(gates["primary_verdict"], "FAIL")
            self.assertEqual(gates["probe2_verdict"], "FAIL")
            self.assertEqual(gates["failure_stage"], "noise_calibration")
            self.assertIsNone(gates["heavy_parent_target_reachable"])
            self.assertIsNone(summary["alpha_at_scalar"])
            state = finalizer.read_json(fixture.root / "state.json")
            self.assertEqual(state["status"], "failed_primary")
            self.assertEqual(state["failure_stage"], "noise_calibration")
            self.assertEqual(
                state["termination_reason"], "alpha0.1_loo_mathematically_impossible"
            )
            certificate = finalizer.read_json(
                fixture.root / finalizer.CERTIFICATE_NAME
            )
            self.assertEqual(
                certificate["commands_log_sha256"],
                sha256_of_file(fixture.root / "commands.log"),
            )
            self.assertTrue(
                (fixture.root / finalizer.FINALIZER_ARCHIVE).is_file()
            )
            (fixture.root / "unmanifested").write_text("tamper")
            with self.assertRaisesRegex(RuntimeError, "exactly cover"):
                finalizer.validate_sealed_failure(fixture.root)

    def test_missing_or_wrong_completed_scalar_never_deletes_partial(self):
        for mutation in ("missing", "wrong", "stale_reanalysis"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                fixture = self.make_fixture(temporary)
                scalar = fixture.root / "sweep" / "alpha0.1_seed1" / "scalar.json"
                if mutation == "missing":
                    scalar.unlink()
                else:
                    if mutation == "wrong":
                        payload = finalizer.read_json(scalar)
                        payload["scalar_0_100"] = 0.0
                        write_json(scalar, payload)
                    else:
                        companion = scalar.with_name(
                            "scalar_reanalysis_bidirectional_v2.json"
                        )
                        payload = finalizer.read_json(companion)
                        payload["normalisation_directions"]["R"] = "forged"
                        write_json(companion, payload)
                with self.assertRaises((RuntimeError, FileNotFoundError)):
                    finalizer.finalize(fixture.root, fixture.parent, REPO)
                self.assertTrue(
                    (fixture.root / "sweep" / "alpha0.2_seed0" / "checkpoint").is_dir()
                )

    def test_partial_sidecar_hash_mismatch_never_deletes_checkpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.make_fixture(temporary)
            checkpoint = fixture.root / "sweep" / "alpha0.2_seed0" / "checkpoint"
            (checkpoint / "model.safetensors").write_bytes(b"tampered")
            with self.assertRaisesRegex(RuntimeError, "weight hashes changed"):
                finalizer.finalize(fixture.root, fixture.parent, REPO)
            self.assertTrue(checkpoint.is_dir())

    def test_injected_preseal_crash_is_verified_and_resumed(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.make_fixture(temporary)
            with self.assertRaisesRegex(RuntimeError, "immediately before manifest"):
                finalizer.finalize(
                    fixture.root,
                    fixture.parent,
                    REPO,
                    fail_before_manifest=True,
                )
            self.assertFalse((fixture.root / "MANIFEST.sha256").exists())
            self.assertTrue((fixture.root / finalizer.SUMMARY_NAME).is_file())
            self.assertTrue((fixture.root / finalizer.CERTIFICATE_NAME).is_file())
            self.assertTrue((fixture.root / "COMPLETE.json").is_file())
            self.assertFalse(
                (fixture.root / "sweep" / "alpha0.2_seed0" / "checkpoint").exists()
            )
            finalizer.finalize(fixture.root, fixture.parent, REPO)
            finalizer.validate_sealed_failure(fixture.root, fixture.parent, REPO)

    def test_crash_after_complete_before_terminal_state_is_resumed(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.make_fixture(temporary)
            with self.assertRaisesRegex(RuntimeError, "before terminal state"):
                finalizer.finalize(
                    fixture.root,
                    fixture.parent,
                    REPO,
                    fail_before_terminal_state=True,
                )
            self.assertFalse((fixture.root / "MANIFEST.sha256").exists())
            self.assertTrue((fixture.root / finalizer.SUMMARY_NAME).is_file())
            self.assertTrue((fixture.root / finalizer.CERTIFICATE_NAME).is_file())
            self.assertTrue((fixture.root / "COMPLETE.json").is_file())
            self.assertEqual(
                finalizer.read_json(fixture.root / "state.json")["status"],
                "running",
            )
            finalizer.finalize(fixture.root, fixture.parent, REPO)
            finalizer.validate_sealed_failure(fixture.root, fixture.parent, REPO)

    def test_atomic_archive_partial_copy_recovery(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.make_fixture(temporary)
            archived_sidecar = (
                fixture.root
                / "sweep"
                / "alpha0.2_seed0"
                / finalizer.ABORTED_SIDECAR_NAME
            )
            archived_source = fixture.root / finalizer.FINALIZER_ARCHIVE
            archived_sidecar.parent.mkdir(parents=True, exist_ok=True)
            archived_source.parent.mkdir(parents=True, exist_ok=True)
            archived_sidecar.with_name(archived_sidecar.name + ".tmp").write_bytes(
                b"partial-sidecar-copy"
            )
            archived_source.with_name(archived_source.name + ".tmp").write_bytes(
                b"partial-source-copy"
            )
            finalizer.finalize(fixture.root, fixture.parent, REPO)
            self.assertFalse(
                archived_sidecar.with_name(archived_sidecar.name + ".tmp").exists()
            )
            self.assertFalse(
                archived_source.with_name(archived_source.name + ".tmp").exists()
            )
            finalizer.validate_sealed_failure(fixture.root, fixture.parent, REPO)

    def test_partial_checkpoint_deletion_resumes_from_tombstone(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.make_fixture(temporary)
            with self.assertRaisesRegex(RuntimeError, "after checkpoint deletion rename"):
                finalizer.finalize(
                    fixture.root,
                    fixture.parent,
                    REPO,
                    fail_after_checkpoint_rename=True,
                )
            dose_dir = fixture.root / "sweep" / "alpha0.2_seed0"
            checkpoint = dose_dir / "checkpoint"
            tombstone = dose_dir / "checkpoint.deleting"
            self.assertFalse(checkpoint.exists())
            self.assertTrue(tombstone.is_dir())
            (tombstone / "model.safetensors").unlink()
            finalizer.finalize(fixture.root, fixture.parent, REPO)
            self.assertFalse(tombstone.exists())
            finalizer.validate_sealed_failure(fixture.root, fixture.parent, REPO)

    def test_dirty_or_uncommitted_finalizer_source_is_rejected_before_delete(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.make_fixture(temporary)
            checkpoint = fixture.root / "sweep" / "alpha0.2_seed0" / "checkpoint"
            with mock.patch.object(
                finalizer,
                "read_committed_finalizer_blob",
                return_value=b"different committed blob",
            ):
                with self.assertRaisesRegex(RuntimeError, "dirty, untracked"):
                    finalizer.finalize(fixture.root, fixture.parent, REPO)
            self.assertTrue(checkpoint.is_dir())

    def test_resealed_semantic_tamper_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.make_fixture(temporary)
            finalizer.finalize(fixture.root, fixture.parent, REPO)
            summary_path = fixture.root / finalizer.SUMMARY_NAME
            summary = finalizer.read_json(summary_path)
            summary["partial_curve"]["0.05"]["per_seed"][0]["scalar"] += 1.0
            write_json(summary_path, summary)
            complete_path = fixture.root / "COMPLETE.json"
            complete = finalizer.read_json(complete_path)
            complete["summary_sha256"] = sha256_of_file(summary_path)
            write_json(complete_path, complete)
            finalizer.write_manifest_atomic(fixture.root)
            with self.assertRaises(RuntimeError):
                finalizer.validate_sealed_failure(
                    fixture.root, fixture.parent, REPO
                )

    def test_resealed_baseline_semantic_tamper_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.make_fixture(temporary)
            finalizer.finalize(fixture.root, fixture.parent, REPO)
            baseline_path = fixture.root / "baseline" / "scalar.json"
            baseline = finalizer.read_json(baseline_path)
            baseline["components"]["R"] = 999.0
            write_json(baseline_path, baseline)
            summary_path = fixture.root / finalizer.SUMMARY_NAME
            summary = finalizer.read_json(summary_path)
            summary["reference_artifact_sha256"]["baseline_scalar"] = (
                sha256_of_file(baseline_path)
            )
            write_json(summary_path, summary)
            complete_path = fixture.root / "COMPLETE.json"
            complete = finalizer.read_json(complete_path)
            complete["summary_sha256"] = sha256_of_file(summary_path)
            write_json(complete_path, complete)
            finalizer.write_manifest_atomic(fixture.root)
            with self.assertRaises(RuntimeError):
                finalizer.validate_sealed_failure(
                    fixture.root, fixture.parent, REPO
                )

    def test_resealed_aborted_sidecar_semantic_tamper_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.make_fixture(temporary)
            finalizer.finalize(fixture.root, fixture.parent, REPO)
            sidecar_path = (
                fixture.root
                / "sweep"
                / "alpha0.2_seed0"
                / finalizer.ABORTED_SIDECAR_NAME
            )
            sidecar = finalizer.read_json(sidecar_path)
            sidecar["seed"] = 99
            write_json(sidecar_path, sidecar)
            aborted_path = fixture.root / finalizer.ABORTED_RECORD_NAME
            aborted = finalizer.read_json(aborted_path)
            aborted["archived_dose_sidecar_sha256"] = sha256_of_file(sidecar_path)
            write_json(aborted_path, aborted)
            certificate_path = fixture.root / finalizer.CERTIFICATE_NAME
            certificate = finalizer.read_json(certificate_path)
            certificate["archived_partial_dose_sidecar_sha256"] = (
                sha256_of_file(sidecar_path)
            )
            certificate["aborted_stage_record_sha256"] = sha256_of_file(aborted_path)
            write_json(certificate_path, certificate)
            summary_path = fixture.root / finalizer.SUMMARY_NAME
            summary = finalizer.read_json(summary_path)
            summary["aborted_stage"] = aborted
            summary["failure_certificate_sha256"] = sha256_of_file(certificate_path)
            write_json(summary_path, summary)
            complete_path = fixture.root / "COMPLETE.json"
            complete = finalizer.read_json(complete_path)
            complete["summary_sha256"] = sha256_of_file(summary_path)
            complete["failure_certificate_sha256"] = sha256_of_file(
                certificate_path
            )
            write_json(complete_path, complete)
            finalizer.write_manifest_atomic(fixture.root)
            with self.assertRaises(RuntimeError):
                finalizer.validate_sealed_failure(
                    fixture.root, fixture.parent, REPO
                )

    def test_explicit_source_commit_survives_later_head_advance(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.make_fixture(temporary)
            finalizer.finalize(fixture.root, fixture.parent, REPO)
            with mock.patch.object(
                finalizer,
                "resolve_source_commit",
                side_effect=lambda repo, selector=None: (
                    "c" * 40 if selector is None else "b" * 40
                ),
            ):
                finalizer.validate_sealed_failure(
                    fixture.root,
                    fixture.parent,
                    REPO,
                    source_commit="b" * 40,
                )

    def test_resume_after_provenance_archive_and_checkpoint_deletion(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.make_fixture(temporary)
            evidence = finalizer.validate_interrupted_eval_log(fixture.root)
            finalizer.validate_and_archive_partial_checkpoint(
                fixture.root, fixture.parent.resolve(), fixture.identity, evidence
            )
            self.assertFalse(
                (fixture.root / "sweep" / "alpha0.2_seed0" / "checkpoint").exists()
            )
            finalizer.finalize(fixture.root, fixture.parent, REPO)
            finalizer.validate_sealed_failure(fixture.root)

    def test_stale_manifest_is_rejected_and_checkpoint_is_untouched(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.make_fixture(temporary)
            (fixture.root / "MANIFEST.sha256").write_text(
                f"{'0' * 64}  state.json\n", encoding="utf-8"
            )
            with self.assertRaises(RuntimeError):
                finalizer.finalize(fixture.root, fixture.parent, REPO)
            self.assertTrue(
                (fixture.root / "sweep" / "alpha0.2_seed0" / "checkpoint").is_dir()
            )


if __name__ == "__main__":
    unittest.main()
