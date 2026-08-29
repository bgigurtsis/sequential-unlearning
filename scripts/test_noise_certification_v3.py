"""CPU-only policy tests for Probe 2 v3 fresh primary certification."""

import argparse
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_noise_certification_v3 as certification
from run_noise_pilot_v3 import build_controller_mapping


def support(u, mean):
    return {
        "u": u,
        "physical_alpha": u,
        "support": True,
        "per_seed": None,
        "mean": mean,
    }


def dose(u, mean=None, values=None):
    mean = 100.0 * u if mean is None else float(mean)
    values = [mean - 1.0, mean, mean + 1.0] if values is None else list(values)
    return {
        "u": u,
        "physical_alpha": u,
        "support": False,
        "per_seed": [
            {"seed": seed, "scalar": value}
            for seed, value in zip(certification.CERTIFICATION_SEEDS, values)
        ],
        "mean": sum(values) / 3.0,
        "raw_range": max(values) - min(values),
    }


def passing_points():
    return [
        support(0.0, 0.0),
        *(dose(u) for u in certification.INTERIOR_U),
        support(1.0, 100.0),
    ]


def passing_ladder():
    monotonicity = {
        key: {"strictly_nondecreasing": True, "range": 1.0}
        for key in certification.WEIGHTS
    }
    return monotonicity, {key: True for key in certification.WEIGHTS}, True


def populate_canonical_archive(root):
    root = Path(root)
    for relative in certification.expected_primary_archive_members():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")


def checkpoint_deletion_fixture(root):
    root = Path(root)
    checkpoint = root / "dose" / "checkpoint"
    checkpoint.mkdir(parents=True)
    (checkpoint / "model.bin").write_bytes(b"model weights")
    (checkpoint / "config.json").write_text('{"model": "fixture"}\n', encoding="utf-8")
    sidecar_payload = {
        "weight_file_sha256": certification.model_weight_hashes(checkpoint),
        "support_file_sha256": certification.support_file_hashes(checkpoint),
    }
    internal_sidecar = checkpoint / "decay_dose.json"
    certification.write_json(internal_sidecar, sidecar_payload)
    archived_sidecar = root / "dose" / "decay_dose.json"
    archived_sidecar.write_bytes(internal_sidecar.read_bytes())
    scalar = root / "dose" / "scalar.json"
    scalar.write_text('{"scalar_0_100": 10}\n', encoding="utf-8")
    marker = root / "stage.json"
    marker.write_text('{"status": "complete"}\n', encoding="utf-8")
    receipt = root / "dose" / "deletion_receipt.json"
    config = {
        "physical_alpha_by_u": {"0.1": 0.01234567},
        "beta": 1.0,
        "fingerprint": "f" * 64,
    }
    return {
        "checkpoint": checkpoint,
        "scalar": scalar,
        "sidecar": archived_sidecar,
        "marker": marker,
        "receipt": receipt,
        "config": config,
    }


class CertificationPolicyTests(unittest.TestCase):
    def test_configuration_is_frozen(self):
        args = argparse.Namespace(batch_size=8, max_new_tokens=256)
        certification.validate_config_args(args)
        args.batch_size = 4
        with self.assertRaisesRegex(ValueError, "configuration is frozen"):
            certification.validate_config_args(args)

    def test_strict_seed_zero_scalar_execution(self):
        payload = {
            "seed": 0,
            "decoding": {
                "method": "greedy",
                "max_new_tokens": 256,
                "batch_size": 8,
                "padding_side": "left",
            },
            "limit": None,
            "weights": certification.WEIGHTS,
            "judge_parse_complete": True,
            "judge_unparsed_count": 0,
            "normalisation_policy_requested": certification.V2_POLICY,
            "normalisation_policy": certification.V2_POLICY,
        }
        self.assertIs(
            certification.validate_certification_scalar_execution(payload), payload
        )
        for key, bad in (
            ("seed", 1),
            ("limit", 1),
            ("judge_parse_complete", False),
            ("judge_unparsed_count", 1),
            ("normalisation_policy", "wrong"),
        ):
            changed = dict(payload)
            changed[key] = bad
            with self.assertRaisesRegex(RuntimeError, "strict seed-0"):
                certification.validate_certification_scalar_execution(changed)
        changed = dict(payload)
        changed["decoding"] = dict(payload["decoding"], max_new_tokens=32)
        with self.assertRaisesRegex(RuntimeError, "strict seed-0"):
            certification.validate_certification_scalar_execution(changed)

    def test_scalar_payload_rejects_nan_scalar_and_raw_component(self):
        payload = {
            "components": {key: 1.0 for key in certification.WEIGHTS},
            "normalised_components": {key: 1.0 for key in certification.WEIGHTS},
            "scalar_0_100": 10.0,
        }
        certification.validate_finite_scalar_payload(payload)
        for invalid in (math.nan, math.inf, -math.inf):
            changed = json.loads(json.dumps(payload))
            changed["scalar_0_100"] = invalid
            with self.assertRaisesRegex(RuntimeError, "finite|nonfinite"):
                certification.validate_finite_scalar_payload(changed)
            changed = json.loads(json.dumps(payload))
            changed["components"][next(iter(certification.WEIGHTS))] = invalid
            with self.assertRaisesRegex(RuntimeError, "nonfinite"):
                certification.validate_finite_scalar_payload(changed)

    def test_json_writer_and_finite_safe_equality_reject_nonfinite(self):
        self.assertTrue(certification.finite_safe_equal({"x": 1.0}, {"x": 1.0}))
        self.assertFalse(
            certification.finite_safe_equal({"x": math.nan}, {"x": math.nan})
        )
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "bad.json"
            with self.assertRaisesRegex(RuntimeError, "nonfinite"):
                certification.write_json(output, {"x": math.inf})
            self.assertFalse(output.exists())

    def test_exact_mapping_grid_beta_and_distinct_alphas(self):
        digest = "a" * 64
        points = []
        for index in range(11):
            alpha = index / 10.0
            base = {
                "alpha": alpha,
                "scalar": 100.0 * alpha,
                "scheduled": 0 < index < 10,
                "seed": 11 if 0 < index < 10 else None,
                "historical_seed_exception": index in {0, 10},
            }
            if base["scheduled"]:
                base.update(
                    scalar_json=f"scalar-{index}.json",
                    scalar_sha256=digest,
                    dose_sidecar=f"dose-{index}.json",
                    dose_sidecar_sha256=digest,
                )
            else:
                base.update(
                    reference_artifact=f"reference-{index}.json",
                    reference_artifact_sha256=digest,
                    reference="endpoint",
                )
            points.append(base)
        mapping, error = build_controller_mapping(points, "A")
        self.assertIsNone(error)
        physical = certification.validate_controller_mapping(mapping)
        self.assertEqual(list(physical), [str(float(u)) for u in certification.CONTROLLER_U])
        self.assertEqual(physical["0.0"], 0.0)
        self.assertEqual(physical["1.0"], 1.0)
        changed = json.loads(json.dumps(mapping))
        changed["controller"][2]["u"] = 0.21
        changed["fingerprint"] = certification.fingerprint(
            {key: value for key, value in changed.items() if key != "fingerprint"}
        )
        with self.assertRaisesRegex(RuntimeError, "exact v3 u grid"):
            certification.validate_controller_mapping(changed)
        changed = json.loads(json.dumps(mapping))
        changed["beta"] = 0.1
        changed["fingerprint"] = certification.fingerprint(
            {key: value for key, value in changed.items() if key != "fingerprint"}
        )
        with self.assertRaisesRegex(RuntimeError, "beta/arm"):
            certification.validate_controller_mapping(changed)

    def test_all_frozen_numeric_gates_pass_on_linear_curve(self):
        gates = certification.analyse_certification(passing_points(), passing_ladder())
        self.assertEqual(gates["spearman_seed_means"], 1.0)
        self.assertTrue(gates["spearman_gate_pass"])
        self.assertLessEqual(gates["max_loo_error"], 1e-9)
        self.assertTrue(gates["loo_gate_pass"])
        self.assertTrue(gates["curve_raw_means_nondecreasing"])
        self.assertTrue(gates["raw_mean_nondecrease_gate_pass"])
        self.assertTrue(gates["per_dose_range_gate_pass"])
        self.assertTrue(gates["ladder_gate_pass"])
        self.assertEqual(gates["primary_verdict"], "PASS")
        self.assertEqual(
            gates["probe2_verdict"], "INCOMPLETE_PENDING_HEAVY_PARENT"
        )

    def test_range_gate_is_inclusive_and_interior_only(self):
        points = passing_points()
        points[1] = dose(0.1, values=[7.0, 10.0, 13.0])
        gates = certification.analyse_certification(points, passing_ladder())
        self.assertTrue(gates["per_dose_range_gate_pass"])
        points[1] = dose(0.1, values=[6.999, 10.0, 13.001])
        gates = certification.analyse_certification(points, passing_ladder())
        self.assertFalse(gates["per_dose_range_gate_pass"])
        self.assertEqual(gates["primary_verdict"], "FAIL")
        self.assertNotIn("0.0", gates["per_dose_raw_ranges"])
        self.assertNotIn("1.0", gates["per_dose_raw_ranges"])

    def test_raw_mean_nondecrease_includes_both_supports(self):
        points = passing_points()
        points[0] = support(0.0, 11.0)
        gates = certification.analyse_certification(points, passing_ladder())
        self.assertFalse(gates["raw_mean_nondecrease_gate_pass"])
        points = passing_points()
        points[-1] = support(1.0, 89.0)
        gates = certification.analyse_certification(points, passing_ladder())
        self.assertFalse(gates["curve_raw_means_nondecreasing"])

    def test_exact_pchip_loo_uses_raw_held_mean_and_running_max_rest(self):
        points = passing_points()
        points[4] = dose(0.4, mean=55.0)
        gates = certification.analyse_certification(points, passing_ladder())
        self.assertGreater(gates["loo_interpolation_errors"]["0.4"], 3.0)
        self.assertFalse(gates["loo_gate_pass"])
        self.assertEqual(gates["primary_verdict"], "FAIL")

    def test_spearman_is_computed_in_u_space_on_interior_means(self):
        points = passing_points()
        means = list(reversed([100.0 * u for u in certification.INTERIOR_U]))
        points[1:-1] = [dose(u, mean) for u, mean in zip(certification.INTERIOR_U, means)]
        gates = certification.analyse_certification(points, passing_ladder())
        self.assertEqual(gates["spearman_seed_means"], -1.0)
        self.assertFalse(gates["spearman_gate_pass"])

    def test_ladder_gate_is_additive_and_required(self):
        monotonicity, components, _ = passing_ladder()
        components = dict(components)
        components[next(iter(components))] = False
        gates = certification.analyse_certification(
            passing_points(), (monotonicity, components, False)
        )
        self.assertFalse(gates["ladder_gate_pass"])
        self.assertEqual(gates["primary_verdict"], "FAIL")

    def test_wrong_grid_seed_or_nonfinite_scalar_fails_closed(self):
        points = passing_points()
        points[1]["u"] = 0.11
        with self.assertRaisesRegex(RuntimeError, "exact ordered u grid"):
            certification.analyse_certification(points, passing_ladder())
        points = passing_points()
        points[1]["per_seed"][2]["seed"] = 7
        with self.assertRaisesRegex(RuntimeError, "exact seeds"):
            certification.analyse_certification(points, passing_ladder())
        points = passing_points()
        points[1]["per_seed"][0]["scalar"] = math.nan
        with self.assertRaisesRegex(RuntimeError, "finite"):
            certification.analyse_certification(points, passing_ladder())

    def test_stored_mean_and_range_reject_nan_and_inf(self):
        for key, invalid in (
            ("mean", math.nan),
            ("mean", math.inf),
            ("raw_range", math.nan),
            ("raw_range", math.inf),
        ):
            points = passing_points()
            points[1][key] = invalid
            with self.assertRaisesRegex(RuntimeError, "nonfinite|finite"):
                certification.analyse_certification(points, passing_ladder())

    def test_stage_resume_and_stale_output_detection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first, second = root / "a.json", root / "b.json"
            calls = []

            def action():
                calls.append(True)
                first.write_text("a", encoding="utf-8")
                second.write_text("b", encoding="utf-8")

            certification.ensure_stage(root, 0.1, 0, "config", (first, second), action)
            certification.ensure_stage(root, 0.1, 0, "config", (first, second), action)
            self.assertEqual(len(calls), 1)
            first.write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "stage provenance mismatch"):
                certification.ensure_stage(
                    root, 0.1, 0, "config", (first, second), action
                )

    def test_stage_recovers_only_complete_unmarked_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first, second = root / "a.json", root / "b.json"
            first.write_text("a", encoding="utf-8")
            second.write_text("b", encoding="utf-8")
            certification.ensure_stage(
                root,
                0.2,
                1,
                "config",
                (first, second),
                lambda: self.fail("must recover without rerun"),
            )
            self.assertTrue(certification.stage_marker(root, 0.2, 1).is_file())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first, second = root / "a.json", root / "b.json"
            first.write_text("partial", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "unmarked outputs"):
                certification.ensure_stage(
                    root, 0.2, 1, "config", (first, second), lambda: None
                )

    def test_checkpoint_deletion_requires_validation_and_safe_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            checkpoint = root / "dose" / "checkpoint"
            checkpoint.mkdir(parents=True)
            with self.assertRaisesRegex(RuntimeError, "before semantic validation"):
                certification.remove_checkpoint_after_validation(
                    checkpoint, root, False, root / "missing-receipt.json"
                )
            self.assertTrue(checkpoint.exists())
            with self.assertRaisesRegex(RuntimeError, "before semantic validation"):
                certification.remove_checkpoint_after_validation(
                    checkpoint, root, True, root / "forged-receipt.json"
                )
            self.assertTrue(checkpoint.exists())
            unsafe = root / "dose"
            with self.assertRaisesRegex(RuntimeError, "unsafe checkpoint"):
                certification.safe_remove_checkpoint(unsafe, root)

    def test_interrupted_apply_and_eval_preserve_checkpoint_and_resume(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            checkpoint = root / "checkpoint"
            scalar = root / "scalar.json"
            sidecar = root / "decay_dose.json"

            def interrupted_apply():
                checkpoint.mkdir()
                (checkpoint / "partial.bin").write_bytes(b"partial")
                raise RuntimeError("apply interrupted")

            with self.assertRaisesRegex(RuntimeError, "apply interrupted"):
                certification.run_resumable_dose_action(
                    checkpoint, scalar, sidecar, interrupted_apply, lambda: None
                )
            self.assertTrue((checkpoint / "partial.bin").is_file())
            with self.assertRaisesRegex(RuntimeError, "preserved"):
                certification.run_resumable_dose_action(
                    checkpoint,
                    scalar,
                    sidecar,
                    lambda: self.fail("must not redraw"),
                    lambda: None,
                )
            self.assertTrue((checkpoint / "partial.bin").is_file())

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            checkpoint = root / "checkpoint"
            checkpoint.mkdir()
            dose_sidecar = checkpoint / "decay_dose.json"
            dose_sidecar.write_text('{"seed": 0}\n', encoding="utf-8")
            scalar = root / "scalar.json"
            sidecar = root / "decay_dose.json"

            def interrupted_eval():
                (checkpoint / "eval-progress.txt").write_text("partial", encoding="utf-8")
                scalar.write_text('{"scalar_0_100":', encoding="utf-8")
                raise RuntimeError("eval interrupted")

            with self.assertRaisesRegex(RuntimeError, "eval interrupted"):
                certification.run_resumable_dose_action(
                    checkpoint,
                    scalar,
                    sidecar,
                    lambda: self.fail("completed apply must be reused"),
                    interrupted_eval,
                )
            self.assertTrue(checkpoint.is_dir())
            self.assertTrue(scalar.is_file())
            self.assertFalse(sidecar.exists())

            def completed_eval():
                scalar.write_text('{"scalar_0_100": 1}\n', encoding="utf-8")

            certification.run_resumable_dose_action(
                checkpoint,
                scalar,
                sidecar,
                lambda: self.fail("resume must not redraw"),
                completed_eval,
            )
            self.assertTrue(checkpoint.is_dir())
            self.assertEqual(sidecar.read_bytes(), dose_sidecar.read_bytes())

    def test_predelete_verifies_live_model_and_support_hashes(self):
        for changed_name, changed_bytes, message in (
            ("model.bin", b"tampered weights", "actual checkpoint weight"),
            ("config.json", b"tampered support", "actual checkpoint support"),
        ):
            with tempfile.TemporaryDirectory() as temporary:
                fixture = checkpoint_deletion_fixture(temporary)
                (fixture["checkpoint"] / changed_name).write_bytes(changed_bytes)
                with self.assertRaisesRegex(RuntimeError, message):
                    certification.delete_checkpoint_with_evidence(
                        fixture["checkpoint"],
                        Path(temporary),
                        fixture["receipt"],
                        fixture["scalar"],
                        fixture["sidecar"],
                        fixture["marker"],
                        fixture["config"],
                        0.1,
                        0,
                    )
                self.assertTrue(fixture["checkpoint"].is_dir())
                self.assertFalse(fixture["receipt"].exists())

    def test_predelete_requires_internal_sidecar_byte_equality(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = checkpoint_deletion_fixture(temporary)
            internal = fixture["checkpoint"] / "decay_dose.json"
            internal.write_bytes(internal.read_bytes() + b" ")
            with self.assertRaisesRegex(RuntimeError, "differ by bytes"):
                certification.delete_checkpoint_with_evidence(
                    fixture["checkpoint"],
                    Path(temporary),
                    fixture["receipt"],
                    fixture["scalar"],
                    fixture["sidecar"],
                    fixture["marker"],
                    fixture["config"],
                    0.1,
                    0,
                )
            self.assertTrue(fixture["checkpoint"].is_dir())

    def test_deletion_receipt_is_durable_and_preexisting_marker_cannot_bypass(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = checkpoint_deletion_fixture(temporary)
            certification.write_json(
                fixture["receipt"],
                {
                    "status": "validated_checkpoint_deleted",
                    "checkpoint_deleted": True,
                    "evidence": {},
                    "evidence_fingerprint": "0" * 64,
                },
            )
            (fixture["checkpoint"] / "model.bin").write_bytes(b"tampered")
            with self.assertRaisesRegex(RuntimeError, "actual checkpoint weight"):
                certification.delete_checkpoint_with_evidence(
                    fixture["checkpoint"], Path(temporary), fixture["receipt"],
                    fixture["scalar"], fixture["sidecar"], fixture["marker"],
                    fixture["config"], 0.1, 0,
                )
            self.assertTrue(fixture["checkpoint"].is_dir())

        with tempfile.TemporaryDirectory() as temporary:
            fixture = checkpoint_deletion_fixture(temporary)
            receipt = certification.delete_checkpoint_with_evidence(
                fixture["checkpoint"], Path(temporary), fixture["receipt"],
                fixture["scalar"], fixture["sidecar"], fixture["marker"],
                fixture["config"], 0.1, 0,
            )
            self.assertFalse(fixture["checkpoint"].exists())
            self.assertEqual(receipt["status"], "validated_checkpoint_deleted")
            self.assertTrue(receipt["checkpoint_deleted"])
            self.assertTrue(all(receipt["evidence"]["verified_before_deletion"].values()))
            certification.validate_deletion_receipt(
                fixture["receipt"], fixture["checkpoint"], fixture["scalar"],
                fixture["sidecar"], fixture["marker"], fixture["config"], 0.1, 0,
            )
            # Recover the narrow crash window after deletion but before the
            # final receipt-status rewrite, using the exact pending evidence.
            receipt["status"] = "validated_pending_delete"
            receipt["checkpoint_deleted"] = False
            certification.write_json(fixture["receipt"], receipt)
            recovered = certification.delete_checkpoint_with_evidence(
                fixture["checkpoint"], Path(temporary), fixture["receipt"],
                fixture["scalar"], fixture["sidecar"], fixture["marker"],
                fixture["config"], 0.1, 0,
            )
            self.assertEqual(recovered["status"], "validated_checkpoint_deleted")

    def test_absent_checkpoint_without_receipt_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = checkpoint_deletion_fixture(temporary)
            for child in fixture["checkpoint"].iterdir():
                child.unlink()
            fixture["checkpoint"].rmdir()
            with self.assertRaisesRegex(RuntimeError, "no receipt"):
                certification.delete_checkpoint_with_evidence(
                    fixture["checkpoint"], Path(temporary), fixture["receipt"],
                    fixture["scalar"], fixture["sidecar"], fixture["marker"],
                    fixture["config"], 0.1, 0,
                )

    def test_manifest_is_atomic_exact_and_tamper_evident(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            populate_canonical_archive(root)
            member = root / certification.SUMMARY_NAME
            seal = certification.write_primary_manifest(root)
            self.assertEqual(seal["path"], str(root / certification.MANIFEST_NAME))
            member.write_text('{"changed": true}\n', encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "archive changed"):
                certification.verify_primary_manifest(root)

    def test_manifest_rejects_duplicate_and_parent_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / certification.MANIFEST_NAME
            digest = "0" * 64
            manifest.write_text(
                f"{digest}  a\n{digest}  a\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(RuntimeError, "duplicate"):
                certification.verify_primary_manifest(root)
            manifest.write_text(f"{digest}  ../a\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "malformed"):
                certification.verify_primary_manifest(root)

    def test_extra_file_cannot_be_sealed_or_accepted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            populate_canonical_archive(root)
            extra = root / "arbitrary-extra.txt"
            extra.write_text("not canonical", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "non-canonical"):
                certification.write_primary_manifest(root)
            self.assertFalse((root / certification.MANIFEST_NAME).exists())
            extra.unlink()
            certification.write_primary_manifest(root)
            extra.write_text("tamper", encoding="utf-8")
            manifest = root / certification.MANIFEST_NAME
            digest = certification.sha256_of_file(extra)
            with manifest.open("a", encoding="utf-8") as handle:
                handle.write(f"{digest}  arbitrary-extra.txt\n")
            with self.assertRaisesRegex(RuntimeError, "non-canonical"):
                certification.verify_primary_manifest(root)

    def test_exact_archive_members_include_one_receipt_per_dose(self):
        members = certification.expected_primary_archive_members()
        self.assertEqual(len(members), 101)
        receipts = [name for name in members if name.endswith("deletion_receipt.json")]
        self.assertEqual(len(receipts), 24)

    def test_rules_explicitly_ban_refit_bisection_and_extra_points(self):
        rules = certification.expected_certification_rules()
        self.assertEqual(
            rules["dose_policy"],
            "exact_grid_only_no_bisection_refit_or_new_points",
        )
        self.assertEqual(rules["interior_u"], list(certification.INTERIOR_U))
        self.assertEqual(rules["seeds"], [0, 1, 2])


if __name__ == "__main__":
    unittest.main()
