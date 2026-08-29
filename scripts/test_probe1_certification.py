"""Focused CPU-only tests for Probe 1 certification policy helpers."""

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run_probe1


def write_json(path, payload):
    Path(path).write_text(json.dumps(payload) + "\n", encoding="utf-8")


def seal(root):
    root = Path(root)
    lines = []
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(root).as_posix()}")
    (root / "MANIFEST.sha256").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )


class Probe1PolicyTests(unittest.TestCase):
    def test_certification_configuration_is_frozen(self):
        class Args:
            pass

        args = Args()
        for key, value in run_probe1.CANONICAL_CERTIFICATION.items():
            setattr(args, key, value)
        run_probe1.validate_certification_args(args)
        args.forget_steps = 121
        with self.assertRaisesRegex(ValueError, "frozen"):
            run_probe1.validate_certification_args(args)

    def test_certification_inputs_and_concept_are_frozen(self):
        class Args:
            concepts = "data/rehearsal_concepts.json"
            heal_corpus = "data/heal_corpus.json"

        repo = Path.cwd().resolve()
        run_probe1.validate_certification_inputs(
            Args(), repo, {"id": run_probe1.CANONICAL_CONCEPT_ID}
        )
        args = Args()
        args.concepts = str(repo / "data" / "other_concepts.json")
        with self.assertRaisesRegex(ValueError, "canonical paths"):
            run_probe1.validate_certification_inputs(
                args, repo, {"id": run_probe1.CANONICAL_CONCEPT_ID}
            )
        with self.assertRaisesRegex(ValueError, "concept"):
            run_probe1.validate_certification_inputs(
                Args(), repo, {"id": "easier_target"}
            )

    def test_heal_trainer_configuration_is_exact(self):
        payload = {
            "model_id": "forget-model",
            "heal_data": "heal.json",
            "output_dir": "heal-adapter",
            "num_steps": 60,
            "save_every": 30,
            "batch_size": 4,
            "max_length": 384,
            "rank": 16,
            "lora_alpha": 32,
            "learning_rate": 2e-5,
            "seed": 0,
            "objective": "retain-only CE on the filtered healing corpus",
            "master_weight_dtype": "float32",
            "heal_examples": 100,
        }
        run_probe1.validate_heal_trainer_config(
            payload, "forget-model", "heal.json", "heal-adapter"
        )
        payload["learning_rate"] = 1e-5
        with self.assertRaisesRegex(RuntimeError, "configuration mismatch"):
            run_probe1.validate_heal_trainer_config(
                payload, "forget-model", "heal.json", "heal-adapter"
            )

    def test_forget_snapshot_grid_and_terminal_state_are_exact(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for step in run_probe1.EXPECTED_FORGET_SNAPSHOT_STEPS:
                (root / f"step{step:03d}").mkdir()
            state = {
                "external_semantic_selection": True,
                "stopped_at_step": 120,
                "stop_reason": "step_budget_exhausted",
                "final_adapter": str(root.resolve() / "step120"),
            }
            snapshots = run_probe1.validate_forget_snapshot_grid(root, state)
            self.assertEqual([step for step, _ in snapshots], list(range(10, 121, 10)))

            (root / "step050").rmdir()
            with self.assertRaisesRegex(RuntimeError, "grid mismatch"):
                run_probe1.validate_forget_snapshot_grid(root, state)
            (root / "step050").mkdir()

            for key, bad_value in (
                ("stopped_at_step", 110),
                ("stop_reason", "jsd_gate"),
                ("final_adapter", str(root / "step110")),
            ):
                mutated = dict(state)
                mutated[key] = bad_value
                with self.assertRaisesRegex(RuntimeError, "terminal state"):
                    run_probe1.validate_forget_snapshot_grid(root, mutated)

    def test_group_gate_requires_exact_group_set(self):
        expected = ("core", "neighbour")
        complete = {
            "groups": {
                "core": {"verdict": "ABSENT"},
                "neighbour": {"verdict": "ABSENT"},
            }
        }
        missing = {"groups": {"core": {"verdict": "ABSENT"}}}
        extra = {
            "groups": {
                **complete["groups"],
                "unexpected": {"verdict": "ABSENT"},
            }
        }
        self.assertTrue(run_probe1.all_group_verdicts(complete, "ABSENT", expected))
        self.assertFalse(run_probe1.all_group_verdicts(missing, "ABSENT", expected))
        self.assertFalse(run_probe1.all_group_verdicts(extra, "ABSENT", expected))

    def test_judgement_identity_is_exact(self):
        expected = ("core", "neighbour")
        parent = str((Path.cwd() / "parent").resolve())
        payload = {
            "judge_model": parent,
            "concept_id": "nightmares",
            "groups": {
                group: {"verdict": "ABSENT", "responses": 3}
                for group in expected
            },
        }
        verdicts = run_probe1.validate_judgement_payload(
            payload, parent, "nightmares", expected
        )
        self.assertEqual(set(verdicts), set(expected))
        payload["judge_model"] = str((Path.cwd() / "other-parent").resolve())
        with self.assertRaisesRegex(RuntimeError, "judge identity"):
            run_probe1.validate_judgement_payload(
                payload, parent, "nightmares", expected
            )

    def test_semantic_record_recomputes_pass_from_judgement(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            semantic_eval = root / "semantic_eval.json"
            semantic_judgement = root / "semantic_judgement.json"
            write_json(semantic_eval, {"fixture": True})
            judgement = {
                "groups": {
                    "core": {"verdict": "PRESENT"},
                    "neighbour": {"verdict": "ABSENT"},
                }
            }
            write_json(semantic_judgement, judgement)
            record = run_probe1.semantic_record_from_evidence(
                10,
                root / "step010",
                semantic_eval,
                semantic_judgement,
                judgement,
                ("core", "neighbour"),
            )
            self.assertFalse(record["pass"])
            self.assertEqual(record["group_verdicts"]["core"], "PRESENT")

    def test_scalar_artifact_requires_exact_runtime_provenance(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            model = root / "model"
            parent = root / "parent"
            model.mkdir()
            parent.mkdir()
            scalar_path = root / "scalar.json"
            prompt_hashes = {
                "battery": "1" * 64,
                "capability": "2" * 64,
                "survival": "3" * 64,
            }
            baseline = {key: 0.0 for key in ("R", "D", "J", "F")}
            positive = {key: 1.0 for key in baseline}
            negative = {"R": -1.0, "D": -1.0}
            payload = {
                "model": str(model.resolve()),
                "model_weight_sha256": {"model.safetensors": "a" * 64},
                "model_support_sha256": {"config.json": "b" * 64},
                "judge_model": str(parent.resolve()),
                "judge_support_sha256": {"config.json": "c" * 64},
                "judge_weight_sha256": {"model.safetensors": "d" * 64},
                "judge_unparsed_count": 0,
                "judge_parse_complete": True,
                "tokenizer_model": str(parent.resolve()),
                "tokenizer_support_sha256": {"config.json": "c" * 64},
                "seed": 0,
                "decoding": {
                    "method": "greedy",
                    "max_new_tokens": 256,
                    "batch_size": 8,
                    "padding_side": "left",
                },
                "prompt_files": {
                    key: {"sha256": value} for key, value in prompt_hashes.items()
                },
                "limit": None,
                "components": {key: 0.5 for key in baseline},
                "normalisation_policy_requested": run_probe1.V2_POLICY,
                "normalisation_policy": run_probe1.V2_POLICY,
                "normalisation_policy_fingerprint": "f" * 64,
                "scalar_0_100": 50.0,
                "baseline_json": "baseline.json",
                "anchor_json": "anchor.json",
                "ladder_json": "ladder.json",
            }
            write_json(scalar_path, payload)
            scalar = run_probe1.validate_probe1_scalar_artifact(
                scalar_path,
                model_path=model,
                parent_model=parent,
                model_weight_sha256={"model.safetensors": "a" * 64},
                model_support_sha256={"config.json": "b" * 64},
                parent_weight_sha256={"model.safetensors": "d" * 64},
                parent_support_sha256={"config.json": "c" * 64},
                prompt_sha256=prompt_hashes,
                baseline_json="baseline.json",
                anchor_json="anchor.json",
                ladder_json="ladder.json",
                policy_fingerprint="f" * 64,
                batch_size=8,
                max_new_tokens=256,
                baseline=baseline,
                positive_anchor=positive,
                negative_anchor=negative,
            )
            self.assertEqual(scalar, 50.0)
            payload["tokenizer_model"] = str(model.resolve())
            write_json(scalar_path, payload)
            with self.assertRaisesRegex(RuntimeError, "tokenizer provenance"):
                run_probe1.validate_probe1_scalar_artifact(
                    scalar_path,
                    model_path=model,
                    parent_model=parent,
                    model_weight_sha256={"model.safetensors": "a" * 64},
                    model_support_sha256={"config.json": "b" * 64},
                    parent_weight_sha256={"model.safetensors": "d" * 64},
                    parent_support_sha256={"config.json": "c" * 64},
                    prompt_sha256=prompt_hashes,
                    baseline_json="baseline.json",
                    anchor_json="anchor.json",
                    ladder_json="ladder.json",
                    policy_fingerprint="f" * 64,
                    batch_size=8,
                    max_new_tokens=256,
                    baseline=baseline,
                    positive_anchor=positive,
                    negative_anchor=negative,
                )

    def test_skip_scalar_is_never_certified(self):
        gates = {
            "pre_erasure_present_pass": True,
            "forgetting_pass": True,
            "persistence_after_heal_pass": True,
            "drift_reversible_pass": True,
            "leakage_within_budget": True,
        }
        verdict, _ = run_probe1.compute_probe1_verdict(gates, use_scalar=False)
        self.assertEqual(verdict, "INCOMPLETE_SCALAR_SKIPPED")

    def test_leakage_is_telemetry_not_a_pass_gate(self):
        gates = {
            "pre_erasure_present_pass": True,
            "forgetting_pass": True,
            "persistence_after_heal_pass": True,
            "drift_reversible_pass": True,
            "repair_pass": True,
            "leakage_within_budget": False,
        }
        verdict, required = run_probe1.compute_probe1_verdict(gates, use_scalar=True)
        self.assertEqual(verdict, "PASS")
        self.assertNotIn("leakage_within_budget", required)

    def test_manifest_ignores_stale_temporary_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "artifact.json").write_text("{}\n", encoding="utf-8")
            (root / "MANIFEST.sha256.tmp").write_text(
                "interrupted write", encoding="utf-8"
            )
            manifest, count = run_probe1.write_manifest(root)
            self.assertEqual(count, 1)
            self.assertFalse((root / "MANIFEST.sha256.tmp").exists())
            self.assertIn("artifact.json", manifest.read_text(encoding="utf-8"))
            self.assertEqual(run_probe1.verify_archive(root)["entry_count"], 1)
            (root / "artifact.json").write_text("changed\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "hash mismatch"):
                run_probe1.verify_archive(root)

    def test_output_overlap_detection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assertTrue(run_probe1.paths_overlap(root, root / "child"))
            self.assertTrue(run_probe1.paths_overlap(root / "child", root))
            self.assertFalse(
                run_probe1.paths_overlap(root / "left", root / "right")
            )
            scalar_inputs = (
                root / "ruler/baseline/scalar.json",
                root / "ruler/anchor/scalar.json",
                root / "ruler/ladder/corruption_ladder.json",
            )
            payload = {
                "certification_version": "probe2_weight_noise_heavy_certification_v3",
                "primary_archive": {"root": str(root / "primary")},
                "pilot_archive": {"root": str(root / "pilot")},
            }
            protected = run_probe1.probe2_protected_roots(
                root / "parent", root / "heavy/summary.json", scalar_inputs, payload
            )
            self.assertIn((root / "pilot").resolve(), protected)
            self.assertIn((root / "ruler").resolve(), protected)

    def make_aggregate(self, temporary, policy="policy-v2"):
        temporary = Path(temporary)
        parent = temporary / "parent"
        primary = temporary / "primary"
        archive = temporary / "aggregate"
        parent.mkdir()
        primary.mkdir()
        archive.mkdir()
        (parent / "model.safetensors").write_bytes(b"weights")
        (parent / "config.json").write_bytes(b"config")
        identity = {
            "source_model": str(parent.resolve()),
            "weight_file_sha256": {
                "model.safetensors": run_probe1.sha256_of_file(
                    parent / "model.safetensors"
                )
            },
            "support_file_sha256": {
                "config.json": run_probe1.sha256_of_file(parent / "config.json")
            },
        }
        identity["fingerprint"] = run_probe1.fingerprint(identity)
        scalar_paths = (
            primary / "baseline" / "scalar.json",
            primary / "anchor" / "scalar.json",
            primary / "ladder" / "corruption_ladder.json",
        )
        for index, scalar_path in enumerate(scalar_paths):
            scalar_path.parent.mkdir()
            write_json(scalar_path, {"fixture": index})
        primary_summary = {
            "certification_scope": "clean_parent_primary_only",
            "parent_model": str(parent.resolve()),
            "normalisation_version": run_probe1.V2_POLICY,
            "normalisation_policy_fingerprint": policy,
            "gates": {
                "primary_verdict": "PASS",
                "probe2_verdict": "INCOMPLETE_PENDING_HEAVY_PARENT",
            },
        }
        write_json(primary / "sweep_summary_bidirectional_v2.json", primary_summary)
        write_json(
            primary / "run_config.json", {"parent_model": str(parent.resolve())}
        )
        write_json(primary / "parent_identity.json", identity)
        seal(primary)
        primary_seal = run_probe1.verify_archive(primary)
        summary = {
            "certification_scope": "heavy_parent_repeat_and_probe2_aggregate",
            "normalisation_version": run_probe1.V2_POLICY,
            "normalisation_policy_fingerprint": policy,
            "clean_ruler": {
                "policy_fingerprint": policy,
                "baseline": run_probe1.sha256_of_file(scalar_paths[0]),
                "terminal": run_probe1.sha256_of_file(scalar_paths[1]),
                "ladder": run_probe1.sha256_of_file(scalar_paths[2]),
            },
            "primary_archive": {
                "root": str(primary.resolve()),
                "manifest_sha256": primary_seal["manifest_sha256"],
                "summary_sha256": run_probe1.sha256_of_file(
                    primary / "sweep_summary_bidirectional_v2.json"
                ),
                "run_config_sha256": run_probe1.sha256_of_file(
                    primary / "run_config.json"
                ),
                "parent_identity_sha256": run_probe1.sha256_of_file(
                    primary / "parent_identity.json"
                ),
            },
            "gates": {
                "probe2_verdict": "PASS",
                "heavy_verdict": "PASS",
                "heavy_parent_selection_pass": True,
                "primary_manifest_verified": True,
                "primary_verdict_verified": True,
            },
        }
        write_json(archive / "sweep_summary_heavy_parent_v2.json", summary)
        write_json(archive / "run_config.json", {"clean_parent_identity": identity})
        seal(archive)
        return (
            parent,
            archive / "sweep_summary_heavy_parent_v2.json",
            scalar_paths,
        )

    def make_v3_aggregate(self, temporary, policy="policy-v2", arm="A"):
        temporary = Path(temporary)
        beta = {"A": 1.0, "B": 0.1}[arm]
        outcome = f"PROMOTE_ARM_{arm}"
        parent = temporary / "parent"
        ruler = temporary / "sealed_v2_ruler"
        pilot = temporary / "sealed_v3_pilot"
        primary = temporary / "sealed_v3_primary"
        aggregate = temporary / "sealed_v3_heavy"
        for root in (parent, ruler, pilot, primary, aggregate):
            root.mkdir()
        (parent / "model.safetensors").write_bytes(b"weights")
        (parent / "config.json").write_bytes(b"config")
        identity = {
            "source_model": str(parent.resolve()),
            "weight_file_sha256": {
                "model.safetensors": run_probe1.sha256_of_file(
                    parent / "model.safetensors"
                )
            },
            "support_file_sha256": {
                "config.json": run_probe1.sha256_of_file(parent / "config.json")
            },
        }
        identity["fingerprint"] = run_probe1.fingerprint(identity)
        scalar_paths = (
            ruler / "baseline" / "scalar.json",
            ruler / "anchor" / "scalar.json",
            ruler / "ladder" / "corruption_ladder.json",
        )
        for index, scalar_path in enumerate(scalar_paths):
            scalar_path.parent.mkdir()
            write_json(scalar_path, {"fixture": index})
        seal(ruler)
        clean_ruler = {
            "policy_fingerprint": policy,
            "baseline": run_probe1.sha256_of_file(scalar_paths[0]),
            "terminal": run_probe1.sha256_of_file(scalar_paths[1]),
            "normalisation_anchor": run_probe1.sha256_of_file(scalar_paths[1]),
            "ladder": run_probe1.sha256_of_file(scalar_paths[2]),
        }
        schema = run_probe1.V3_MAPPING_SCHEMA
        pilot_alphas = run_probe1.V3_PILOT_ALPHA[arm]

        def pilot_raw_point(alpha):
            scheduled = not (alpha == 0.0 or (arm == "A" and alpha == 1.0))
            record = {
                "physical_alpha": alpha,
                "raw_scalar": 100.0 * alpha,
                "seed": 11 if scheduled else (0 if alpha == 1.0 else None),
                "scheduled": scheduled,
                "historical_seed_exception": not scheduled,
            }
            if scheduled:
                record.update(
                    {
                        "scalar_artifact": {
                            "path": f"arm_{arm}/alpha{alpha:g}/scalar.json",
                            "sha256": "a" * 64,
                        },
                        "dose_sidecar": {
                            "path": f"arm_{arm}/alpha{alpha:g}/decay_dose.json",
                            "sha256": "b" * 64,
                        },
                    }
                )
            else:
                record.update(
                    {
                        "reference_artifact": {
                            "path": f"references/alpha{alpha:g}.json",
                            "sha256": "c" * 64,
                        },
                        "reference": "sealed fixture support",
                    }
                )
            return record

        mapping = {
            "schema": schema,
            "schema_sha256": run_probe1.fingerprint(schema),
            "source_arm": arm,
            "beta": beta,
            "seed_used_to_fit": 11,
            "raw_points": [pilot_raw_point(alpha) for alpha in pilot_alphas],
            "fit_points": [
                {"physical_alpha": alpha, "isotonic_scalar": 100.0 * alpha}
                for alpha in pilot_alphas
            ],
            "controller": [
                {"u": u, "target_scalar": 100.0 * u, "physical_alpha": u}
                for u in run_probe1.V3_CONTROLLER_U
            ],
            "heavy_parent": {
                "u": 0.65,
                "target_scalar": 65.0,
                "physical_alpha": 0.65,
            },
        }
        mapping["fingerprint"] = run_probe1.fingerprint(mapping)
        mapping_path = pilot / "controller_mapping.json"
        write_json(mapping_path, mapping)
        pilot_summary = {
            "outcome": outcome,
            "explicitly_not_a_pass_verdict": True,
            "controller_mapping": str(mapping_path.resolve()),
            "controller_mapping_sha256": run_probe1.sha256_of_file(mapping_path),
            "controller_mapping_fingerprint": mapping["fingerprint"],
            "controller_mapping_schema_sha256": mapping["schema_sha256"],
        }
        pilot_summary_path = pilot / "pilot_summary.json"
        write_json(pilot_summary_path, pilot_summary)
        seal(pilot)
        pilot_archive = {
            "root": str(pilot.resolve()),
            "summary": str(pilot_summary_path.resolve()),
            "summary_sha256": run_probe1.sha256_of_file(pilot_summary_path),
            "manifest_sha256": run_probe1.sha256_of_file(
                pilot / "MANIFEST.sha256"
            ),
            "outcome": outcome,
        }
        mapping_record = {
            "path": str(mapping_path.resolve()),
            "sha256": run_probe1.sha256_of_file(mapping_path),
            "fingerprint": mapping["fingerprint"],
            "schema_sha256": mapping["schema_sha256"],
        }
        alpha_by_u = {str(u): u for u in run_probe1.V3_CONTROLLER_U}

        def curve(means):
            return {
                str(u): {
                    "u": u,
                    "physical_alpha": u,
                    "per_seed": [
                        {"seed": seed, "scalar": mean + seed - 1.0}
                        for seed in (0, 1, 2)
                    ],
                    "mean": mean,
                    "raw_range": 2.0,
                }
                for u, mean in zip(run_probe1.V3_INTERIOR_U, means)
            }

        def policy_gates():
            return {
                "curve_raw_means_nondecreasing": True,
                "raw_mean_nondecrease_gate_pass": True,
                "per_dose_raw_ranges": {
                    str(u): 2.0 for u in run_probe1.V3_INTERIOR_U
                },
                "per_dose_range_gate_pass": True,
                "no_refit_bisection_or_extra_points": True,
                "ladder_component_pass": {
                    "R": True, "D": True, "J": True, "F": True
                },
                "ladder_gate_pass": True,
            }

        primary_summary = {
            "certification_version": run_probe1.V3_PRIMARY_VERSION,
            "certification_scope": "clean_parent_primary_only",
            "parent_model": str(parent.resolve()),
            "beta": beta,
            "normalisation_version": run_probe1.V2_POLICY,
            "normalisation_policy_fingerprint": policy,
            "clean_ruler": clean_ruler,
            "primary_archive": {
                "root": str(primary.resolve()),
                "run_config": str((primary / "run_config.json").resolve()),
                "summary": str((primary / "primary_summary_v3.json").resolve()),
                "manifest": str((primary / "MANIFEST.sha256").resolve()),
            },
            "pilot_archive": pilot_archive,
            "controller_mapping": mapping_record,
            "controller_coordinate": "u",
            "controller_u": list(run_probe1.V3_CONTROLLER_U),
            "physical_alpha_by_u": alpha_by_u,
            "baseline_scalar": 0.0,
            "terminal_weight_noise_scalar": 100.0,
            "curve": curve((10, 20, 30, 40, 50, 60, 75, 90)),
            "endpoints": {
                "u0": {"u": 0.0, "support": True, "mean": 0.0},
                "u1": {"u": 1.0, "support": True, "mean": 100.0},
            },
            "gates": {
                **policy_gates(),
                "primary_verdict": "PASS",
                "probe2_verdict": "INCOMPLETE_PENDING_HEAVY_PARENT",
            },
        }
        write_json(primary / "primary_summary_v3.json", primary_summary)
        write_json(
            primary / "run_config.json",
            {"parent_model": str(parent.resolve()), "clean_parent_identity": identity},
        )
        write_json(primary / "parent_identity.json", identity)
        seal(primary)
        primary_archive = {
            "root": str(primary.resolve()),
            "manifest_sha256": run_probe1.sha256_of_file(primary / "MANIFEST.sha256"),
            "summary_sha256": run_probe1.sha256_of_file(
                primary / "primary_summary_v3.json"
            ),
            "run_config_sha256": run_probe1.sha256_of_file(primary / "run_config.json"),
            "parent_identity_sha256": run_probe1.sha256_of_file(
                primary / "parent_identity.json"
            ),
        }
        heavy_identity = {
            "source_model": str((aggregate / "checkpoint").resolve()),
            "weight_file_sha256": {"model.safetensors": "a" * 64},
            "support_file_sha256": {"config.json": "b" * 64},
            "dose_seed": 7,
            "controller_u": 0.65,
            "beta": beta,
            "mapping_fingerprint": mapping["fingerprint"],
            "construction": "one_shot_no_search",
            "administered_alpha": 0.65,
            "measured_global_scalar": 65.0,
        }
        heavy_identity["fingerprint"] = run_probe1.fingerprint(heavy_identity)
        heavy_gates = {
            **policy_gates(),
            "primary_manifest_verified": True,
            "primary_verdict_verified": True,
            "heavy_parent_selection_pass": True,
            "no_refit_bisection_or_extra_points": True,
            "heavy_verdict": "PASS",
            "probe2_verdict": "PASS",
        }
        heavy_summary = {
            "certification_version": "probe2_weight_noise_heavy_certification_v3",
            "certification_scope": "heavy_parent_repeat_and_probe2_aggregate",
            "normalisation_version": run_probe1.V2_POLICY,
            "normalisation_policy_fingerprint": policy,
            "primary_archive": primary_archive,
            "pilot_archive": pilot_archive,
            "clean_ruler": clean_ruler,
            "beta": beta,
            "controller_mapping": mapping_record,
            "controller_coordinate": "u",
            "controller_u": list(run_probe1.V3_CONTROLLER_U),
            "physical_alpha_by_u": alpha_by_u,
            "heavy_parent": {
                "identity": heavy_identity,
                "measurement": {"seed": 7, "controller_u": 0.65, "scalar": 65.0},
            },
            "incremental_alpha1_endpoint": {
                "seed": 0, "controller_u": 1.0, "scalar": 100.0
            },
            "curve": curve((66, 70, 74, 78, 82, 86, 90, 94)),
            "gates": heavy_gates,
        }
        aggregate_path = aggregate / "sweep_summary_heavy_parent_v3.json"
        write_json(aggregate_path, heavy_summary)
        seal(aggregate)
        return parent, aggregate_path, scalar_paths

    def authoritative_v3_bundle(self, aggregate, scalar_paths):
        return {
            "root": aggregate.parent.resolve(),
            "summary": json.loads(aggregate.read_text(encoding="utf-8")),
            "config": {
                "clean_ruler_paths": {
                    "baseline": str(Path(scalar_paths[0]).resolve()),
                    "normalisation_anchor": str(Path(scalar_paths[1]).resolve()),
                    "ladder": str(Path(scalar_paths[2]).resolve()),
                }
            },
        }

    def test_probe2_prerequisite_binds_seal_policy_and_parent(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent, aggregate, scalar_paths = self.make_aggregate(temporary)
            payload = run_probe1.validate_probe2_aggregate(
                aggregate, "policy-v2", parent, scalar_paths
            )
            self.assertEqual(
                payload["_verified_archive"]["entry_count"], 2
            )

            with self.assertRaisesRegex(RuntimeError, "policy"):
                run_probe1.validate_probe2_aggregate(
                    aggregate, "different-policy", parent, scalar_paths
                )

            (parent / "model.safetensors").write_bytes(b"changed")
            with self.assertRaisesRegex(RuntimeError, "parent bytes"):
                run_probe1.validate_probe2_aggregate(
                    aggregate, "policy-v2", parent, scalar_paths
                )

    def test_probe2_prerequisite_rejects_unsealed_or_tampered_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent, aggregate, scalar_paths = self.make_aggregate(temporary)
            manifest = aggregate.parent / "MANIFEST.sha256"
            manifest.unlink()
            with self.assertRaisesRegex(RuntimeError, "not sealed"):
                run_probe1.validate_probe2_aggregate(
                    aggregate, "policy-v2", parent, scalar_paths
                )

        with tempfile.TemporaryDirectory() as temporary:
            parent, aggregate, scalar_paths = self.make_aggregate(temporary)
            payload = json.loads(aggregate.read_text(encoding="utf-8"))
            payload["gates"].pop("heavy_parent_selection_pass")
            write_json(aggregate, payload)
            (aggregate.parent / "MANIFEST.sha256").unlink()
            seal(aggregate.parent)
            with self.assertRaisesRegex(RuntimeError, "selection"):
                run_probe1.validate_probe2_aggregate(
                    aggregate, "policy-v2", parent, scalar_paths
                )

        with tempfile.TemporaryDirectory() as temporary:
            parent, aggregate, scalar_paths = self.make_aggregate(temporary)
            payload = json.loads(aggregate.read_text(encoding="utf-8"))
            payload["gates"]["probe2_verdict"] = "FAIL"
            write_json(aggregate, payload)
            with self.assertRaisesRegex(RuntimeError, "hash mismatch"):
                run_probe1.validate_probe2_aggregate(
                    aggregate, "policy-v2", parent, scalar_paths
                )

    def test_v3_prerequisite_decouples_ruler_and_validates_controller_chain(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent, aggregate, scalar_paths = self.make_v3_aggregate(temporary)
            with patch.object(
                run_probe1,
                "_validate_v3_producer_archive",
                return_value=self.authoritative_v3_bundle(aggregate, scalar_paths),
            ):
                payload = run_probe1.validate_probe2_aggregate(
                    aggregate, "policy-v2", parent, scalar_paths
                )
            self.assertEqual(payload["_verified_controller_mapping"]["beta"], 1.0)
            self.assertNotEqual(
                Path(payload["primary_archive"]["root"]),
                scalar_paths[0].parent.parent,
            )

    def test_v2_path_does_not_invoke_the_v3_producer_validator(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent, aggregate, scalar_paths = self.make_aggregate(temporary)
            with patch.object(
                run_probe1,
                "_validate_v3_producer_archive",
                side_effect=AssertionError("v2 must not enter v3 validation"),
            ) as v3_authority:
                payload = run_probe1.validate_probe2_aggregate(
                    aggregate, "policy-v2", parent, scalar_paths
                )
            self.assertEqual(
                payload["certification_scope"],
                "heavy_parent_repeat_and_probe2_aggregate",
            )
            v3_authority.assert_not_called()

    def test_v3_requires_the_exact_producer_archive_validator(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent, aggregate, scalar_paths = self.make_v3_aggregate(temporary)
            with self.assertRaisesRegex(RuntimeError, "producer's sealed-archive"):
                run_probe1.validate_probe2_aggregate(
                    aggregate, "policy-v2", parent, scalar_paths
                )

    def test_v3_consumer_delegates_to_the_producer_validator(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, aggregate, scalar_paths = self.make_v3_aggregate(temporary)
            bundle = self.authoritative_v3_bundle(aggregate, scalar_paths)
            with patch(
                "run_noise_heavy_v3.validate_sealed_heavy",
                return_value=bundle,
            ) as authority:
                self.assertEqual(
                    run_probe1._validate_v3_producer_archive(aggregate), bundle
                )
            authority.assert_called_once_with(aggregate.parent.resolve())

    @unittest.skipUnless(
        all(
            os.environ.get(name)
            for name in (
                "PROBE2_V3_HEAVY_SUMMARY",
                "PROBE2_V3_CLEAN_PARENT",
                "PROBE2_V3_RULER_BASELINE",
                "PROBE2_V3_RULER_ANCHOR",
                "PROBE2_V3_RULER_LADDER",
            )
        ),
        "requires a real sealed Probe 2 v3 GPU archive",
    )
    def test_real_sealed_v3_archive_smoke(self):
        scalar_paths = tuple(
            Path(os.environ[name])
            for name in (
                "PROBE2_V3_RULER_BASELINE",
                "PROBE2_V3_RULER_ANCHOR",
                "PROBE2_V3_RULER_LADDER",
            )
        )
        baseline, positive, negative, sources = (
            run_probe1.load_bidirectional_anchors(*scalar_paths)
        )
        policy = run_probe1.bidirectional_policy_fingerprint(
            baseline, positive, negative, sources
        )
        payload = run_probe1.validate_probe2_aggregate(
            os.environ["PROBE2_V3_HEAVY_SUMMARY"],
            policy,
            os.environ["PROBE2_V3_CLEAN_PARENT"],
            scalar_paths,
        )
        self.assertEqual(payload["gates"]["probe2_verdict"], "PASS")

    def test_v3_arm_b_beta_flows_through_the_consumer_chain(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent, aggregate, scalar_paths = self.make_v3_aggregate(
                temporary, arm="B"
            )
            with patch.object(
                run_probe1,
                "_validate_v3_producer_archive",
                return_value=self.authoritative_v3_bundle(aggregate, scalar_paths),
            ):
                payload = run_probe1.validate_probe2_aggregate(
                    aggregate, "policy-v2", parent, scalar_paths
                )
            self.assertEqual(payload["beta"], 0.1)
            self.assertEqual(payload["heavy_parent"]["identity"]["beta"], 0.1)

    def test_consumer_json_and_fingerprints_reject_nonfinite_numbers(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "nonfinite.json"
            path.write_text('{"value": NaN}\n', encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "non-finite JSON"):
                run_probe1.read_json(path)
        with self.assertRaisesRegex(RuntimeError, "non-finite"):
            run_probe1.fingerprint({"value": float("inf")})

    def test_v3_consumer_rejects_overlapping_archive_roots(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent, aggregate, scalar_paths = self.make_v3_aggregate(temporary)
            payload = json.loads(aggregate.read_text(encoding="utf-8"))
            payload["primary_archive"]["root"] = str(
                scalar_paths[0].parent.parent.resolve()
            )
            write_json(aggregate, payload)
            (aggregate.parent / "MANIFEST.sha256").unlink()
            seal(aggregate.parent)
            with patch.object(
                run_probe1,
                "_validate_v3_producer_archive",
                return_value=self.authoritative_v3_bundle(aggregate, scalar_paths),
            ):
                with self.assertRaisesRegex(RuntimeError, "archives overlap"):
                    run_probe1.validate_probe2_aggregate(
                        aggregate, "policy-v2", parent, scalar_paths
                    )

    def test_v3_mapping_defence_rejects_extra_alias_and_nonmonotone_alpha(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, aggregate, _ = self.make_v3_aggregate(temporary)
            summary = json.loads(aggregate.read_text(encoding="utf-8"))
            mapping_path = Path(summary["controller_mapping"]["path"])
            original = json.loads(mapping_path.read_text(encoding="utf-8"))
            pilot_summary = json.loads(
                Path(summary["pilot_archive"]["summary"]).read_text(
                    encoding="utf-8"
                )
            )
            for label in (
                "extra", "alias", "descending", "unrounded_g",
                "raw_extra", "fit_extra", "raw_pointer_alias",
            ):
                mapping = json.loads(json.dumps(original))
                if label == "extra":
                    mapping["controller"][1]["alpha"] = 0.1
                elif label == "alias":
                    mapping["controller"][1]["u"] = "0.1"
                elif label == "descending":
                    mapping["controller"][1]["physical_alpha"] = 0.9
                    mapping["controller"][2]["physical_alpha"] = 0.8
                elif label == "unrounded_g":
                    mapping["heavy_parent"]["physical_alpha"] = 0.650000001
                elif label == "raw_extra":
                    mapping["raw_points"][1]["alpha"] = 0.1
                elif label == "fit_extra":
                    mapping["fit_points"][1]["raw_scalar"] = 10.0
                else:
                    mapping["raw_points"][1]["scalar_artifact"]["digest"] = (
                        mapping["raw_points"][1]["scalar_artifact"]["sha256"]
                    )
                mapping["fingerprint"] = run_probe1.fingerprint(
                    {
                        key: value
                        for key, value in mapping.items()
                        if key != "fingerprint"
                    }
                )
                descriptor = dict(summary["controller_mapping"])
                descriptor["fingerprint"] = mapping["fingerprint"]
                linked_pilot = dict(pilot_summary)
                linked_pilot["controller_mapping_fingerprint"] = mapping[
                    "fingerprint"
                ]
                with self.subTest(label=label):
                    with self.assertRaisesRegex(
                        RuntimeError, r"grid|g\(.65\)|pilot fit"
                    ):
                        run_probe1._validate_v3_mapping(
                            mapping, descriptor, linked_pilot
                        )

    def test_v3_prerequisite_rejects_range_and_mapping_tampering(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent, aggregate, scalar_paths = self.make_v3_aggregate(temporary)
            payload = json.loads(aggregate.read_text(encoding="utf-8"))
            payload["gates"]["per_dose_range_gate_pass"] = False
            write_json(aggregate, payload)
            (aggregate.parent / "MANIFEST.sha256").unlink()
            seal(aggregate.parent)
            with patch.object(
                run_probe1,
                "_validate_v3_producer_archive",
                return_value=self.authoritative_v3_bundle(aggregate, scalar_paths),
            ):
                with self.assertRaisesRegex(RuntimeError, "range"):
                    run_probe1.validate_probe2_aggregate(
                        aggregate, "policy-v2", parent, scalar_paths
                    )

        with tempfile.TemporaryDirectory() as temporary:
            parent, aggregate, scalar_paths = self.make_v3_aggregate(temporary)
            payload = json.loads(aggregate.read_text(encoding="utf-8"))
            payload["beta"] = 0.1
            write_json(aggregate, payload)
            (aggregate.parent / "MANIFEST.sha256").unlink()
            seal(aggregate.parent)
            with patch.object(
                run_probe1,
                "_validate_v3_producer_archive",
                return_value=self.authoritative_v3_bundle(aggregate, scalar_paths),
            ):
                with self.assertRaisesRegex(RuntimeError, "controller"):
                    run_probe1.validate_probe2_aggregate(
                        aggregate, "policy-v2", parent, scalar_paths
                    )


if __name__ == "__main__":
    unittest.main()
