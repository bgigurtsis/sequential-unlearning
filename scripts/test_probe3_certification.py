"""CPU-only contract tests for the hardened Probe 3 driver."""

import json
import tempfile
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import run_probe3
from run_probe3 import (
    EXPECTED_PROBE2_SCOPE,
    PROBE3_VERSION,
    SEMANTIC_ONLY_EVAL_FLAGS,
    V3_CONTROLLER_U,
    V3_HEAVY_VERSION,
    V2_POLICY,
    classify_probe3,
    ensure_stage,
    fingerprint,
    model_identity,
    paths_overlap,
    probe2_protected_roots,
    required_runtime_mode,
    scalar_from_components,
    semantic_result,
    select_earliest_semantic_snapshot,
    validate_canonical_config,
    validate_canonical_concept,
    validate_output_root,
    validate_probe2_aggregate,
    validate_probe2_inputs,
    validate_trainer_grid,
    verify_manifest,
    write_manifest,
)


def expect_rejected(payload, policy="policy", policy_fp="f" * 64):
    try:
        validate_probe2_aggregate(payload, policy, policy_fp)
    except ValueError:
        return
    raise AssertionError("invalid Probe 2 aggregate was accepted")


def valid_probe2():
    identity = {
        "source_model": "heavy/checkpoint",
        "weight_file_sha256": {"model.safetensors": "a" * 64},
        "support_file_sha256": {"config.json": "b" * 64},
        "clean_parent_identity_fingerprint": "c" * 64,
        "dose_sidecar_sha256": "d" * 64,
        "scalar_json_sha256": "e" * 64,
        "reanalysis_sha256": "f" * 64,
        "administered_alpha": 0.65,
        "dose_seed": 7,
        "measured_global_scalar": 65.0,
    }
    identity["fingerprint"] = fingerprint(identity)
    return {
        "certification_scope": EXPECTED_PROBE2_SCOPE,
        "normalisation_version": "policy",
        "normalisation_policy_fingerprint": "f" * 64,
        "gates": {
            "probe2_verdict": "PASS",
            "primary_manifest_verified": True,
            "primary_verdict_verified": True,
            "heavy_parent_selection_pass": True,
            "heavy_verdict": "PASS",
        },
        "primary_archive": {
            "root": "primary",
            "manifest_sha256": "1" * 64,
            "summary_sha256": "2" * 64,
            "run_config_sha256": "3" * 64,
            "parent_identity_sha256": "4" * 64,
        },
        "clean_ruler": {
            "baseline": "5" * 64,
            "terminal": "6" * 64,
            "ladder": "7" * 64,
            "policy_fingerprint": "f" * 64,
        },
        "heavy_parent": {
            "identity": identity,
        },
    }


def valid_probe2_v3():
    payload = valid_probe2()
    payload["certification_version"] = V3_HEAVY_VERSION
    payload["beta"] = 0.1
    payload["controller_coordinate"] = "u"
    payload["controller_u"] = list(V3_CONTROLLER_U)
    payload["physical_alpha_by_u"] = {str(u): u for u in V3_CONTROLLER_U}
    payload["controller_mapping"] = {
        "path": "pilot/controller_mapping.json",
        "sha256": "8" * 64,
        "fingerprint": "9" * 64,
        "schema_sha256": "a" * 64,
    }
    payload["gates"].update(
        {
            "per_dose_range_gate_pass": True,
            "raw_mean_nondecrease_gate_pass": True,
            "no_refit_bisection_or_extra_points": True,
        }
    )
    identity = payload["heavy_parent"]["identity"]
    identity.update(
        {
            "controller_u": 0.65,
            "beta": 0.1,
            "mapping_fingerprint": "9" * 64,
            "construction": "one_shot_no_search",
        }
    )
    identity["fingerprint"] = fingerprint(
        {key: value for key, value in identity.items() if key != "fingerprint"}
    )
    return payload


def main():
    assert SEMANTIC_ONLY_EVAL_FLAGS == (
        "--skip-capability",
        "--skip-cumulative",
        "--skip-perplexity",
        "--skip-sea",
    )
    with tempfile.TemporaryDirectory() as temporary:
        nonfinite = Path(temporary) / "nonfinite.json"
        nonfinite.write_text('{"value": Infinity}\n', encoding="utf-8")
        try:
            run_probe3.read_json(nonfinite)
        except RuntimeError as error:
            assert "non-finite JSON" in str(error)
        else:
            raise AssertionError("Probe 3 accepted non-finite JSON")
    valid = valid_probe2()
    assert validate_probe2_aggregate(valid, "policy", "f" * 64) == 0.65
    for mutation in (
        "scope",
        "verdict",
        "policy",
        "fingerprint",
        "sealed",
        "alpha",
        "scalar_band",
        "dose_seed",
        "heavy_gate",
        "identity_fingerprint",
    ):
        payload = json.loads(json.dumps(valid))
        if mutation == "scope":
            payload["certification_scope"] = "clean_parent_primary_only"
        elif mutation == "verdict":
            payload["gates"]["probe2_verdict"] = "INCOMPLETE_PENDING_HEAVY_PARENT"
        elif mutation == "policy":
            payload["normalisation_version"] = "hybrid_synthetic_v1"
        elif mutation == "fingerprint":
            payload["normalisation_policy_fingerprint"] = "0" * 64
        elif mutation == "sealed":
            payload["primary_archive"].pop("manifest_sha256")
        elif mutation == "alpha":
            payload["heavy_parent"]["identity"]["administered_alpha"] = None
        elif mutation == "scalar_band":
            payload["heavy_parent"]["identity"]["measured_global_scalar"] = 70.01
        elif mutation == "dose_seed":
            payload["heavy_parent"]["identity"]["dose_seed"] = 6
        elif mutation == "heavy_gate":
            payload["gates"]["primary_manifest_verified"] = False
        else:
            payload["heavy_parent"]["identity"]["fingerprint"] = "0" * 64
        expect_rejected(payload)

    valid_v3 = valid_probe2_v3()
    assert validate_probe2_aggregate(valid_v3, "policy", "f" * 64) == 0.65
    for mutation in ("u", "beta", "mapping", "construction", "no_refit"):
        payload = json.loads(json.dumps(valid_v3))
        if mutation == "u":
            payload["heavy_parent"]["identity"]["controller_u"] = 0.6
        elif mutation == "beta":
            payload["heavy_parent"]["identity"]["beta"] = 1.0
        elif mutation == "mapping":
            payload["heavy_parent"]["identity"]["mapping_fingerprint"] = "0" * 64
        elif mutation == "construction":
            payload["heavy_parent"]["identity"]["construction"] = "searched"
        else:
            payload["gates"]["no_refit_bisection_or_extra_points"] = False
        expect_rejected(payload)

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        parent = root / "parent"
        heavy_root = root / "heavy"
        checkpoint = heavy_root / "heavy_parent" / "checkpoint"
        parent.mkdir()
        checkpoint.mkdir(parents=True)
        (parent / "model.safetensors").write_bytes(b"clean")
        (parent / "config.json").write_text("{}\n", encoding="utf-8")
        (checkpoint / "model.safetensors").write_bytes(b"heavy")
        (checkpoint / "config.json").write_text("{}\n", encoding="utf-8")
        clean_identity = model_identity(parent)
        checkpoint_identity = model_identity(checkpoint)
        heavy_identity = {
            "source_model": str(checkpoint.resolve()),
            "weight_file_sha256": checkpoint_identity["weight_file_sha256"],
            "support_file_sha256": checkpoint_identity["support_file_sha256"],
            "clean_parent_identity_fingerprint": clean_identity["fingerprint"],
            "administered_alpha": 0.65,
            "dose_seed": 7,
            "measured_global_scalar": 65.0,
            "controller_u": 0.65,
            "beta": 0.1,
            "mapping_fingerprint": "9" * 64,
            "construction": "one_shot_no_search",
        }
        heavy_identity["fingerprint"] = fingerprint(heavy_identity)
        identity_path = heavy_root / "heavy_parent_identity.json"
        identity_path.write_text(json.dumps(heavy_identity) + "\n", encoding="utf-8")
        summary_path = heavy_root / "sweep_summary_heavy_parent_v3.json"
        summary_path.write_text("{}\n", encoding="utf-8")
        authoritative = {
            "certification_version": V3_HEAVY_VERSION,
            "heavy_parent": {
                "identity": heavy_identity,
                "identity_json": str(identity_path.resolve()),
                "checkpoint": str(checkpoint.resolve()),
            },
            "_verified_controller_mapping": {
                "fingerprint": "9" * 64,
                "heavy_parent": {"u": 0.65, "physical_alpha": 0.65},
            },
        }
        with patch.object(
            run_probe3, "validate_probe2_archive_chain", return_value=authoritative
        ), patch.object(
            run_probe3, "validate_probe2_aggregate", return_value=0.65
        ):
            validate_probe2_inputs(summary_path, "f" * 64, parent, ())
            heavy_identity["clean_parent_identity_fingerprint"] = "0" * 64
            identity_path.write_text(
                json.dumps(heavy_identity) + "\n", encoding="utf-8"
            )
            try:
                validate_probe2_inputs(summary_path, "f" * 64, parent, ())
            except ValueError as error:
                assert "linked to the clean parent" in str(error)
            else:
                raise AssertionError("forged clean-parent linkage was accepted")
            heavy_identity["clean_parent_identity_fingerprint"] = clean_identity[
                "fingerprint"
            ]
            identity_path.write_text(
                json.dumps(heavy_identity) + "\n", encoding="utf-8"
            )
            (checkpoint / "model.safetensors").write_bytes(b"tampered")
            try:
                validate_probe2_inputs(summary_path, "f" * 64, parent, ())
            except ValueError as error:
                assert "checkpoint bytes" in str(error)
            else:
                raise AssertionError("tampered retained heavy checkpoint was accepted")

    records = [
        {"step": 30, "semantic_absent": True},
        {"step": 10, "semantic_absent": False},
        {"step": 20, "semantic_absent": True},
    ]
    assert select_earliest_semantic_snapshot(records)["step"] == 20
    assert select_earliest_semantic_snapshot(
        [{"step": 10, "semantic_absent": False}]
    ) is None

    passed = {"arm_pass": True}
    failed = {"arm_pass": False}
    assert classify_probe3(passed, None, skipped=False, smoke=False) == "PASS"
    assert classify_probe3(failed, passed, skipped=False, smoke=False) == "PASS"
    assert classify_probe3(failed, failed, skipped=False, smoke=False) == "FAIL"
    assert classify_probe3(failed, None, skipped=False, smoke=False) == "INCOMPLETE"
    assert classify_probe3(passed, None, skipped=True, smoke=False) == "PASS"
    assert classify_probe3(failed, None, skipped=True, smoke=False) == "INCOMPLETE"
    assert classify_probe3(passed, None, skipped=False, smoke=True) == "INCOMPLETE"
    assert required_runtime_mode(passed, None) == "bf16_base"
    assert required_runtime_mode(failed, passed) == "fp32_base"
    assert required_runtime_mode(failed, failed) is None
    assert paths_overlap("a", "a/b")
    assert not paths_overlap("a/b", "a/c")
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        validate_output_root(base / "probe3", (base / "primary", base / "heavy"))
        try:
            validate_output_root(
                base / "primary" / "probe3", (base / "primary", base / "heavy")
            )
        except ValueError:
            pass
        else:
            raise AssertionError("Probe 3 root inside the primary archive was accepted")
        scalar_inputs = (
            base / "ruler/baseline/scalar.json",
            base / "ruler/anchor/scalar.json",
            base / "ruler/ladder/corruption_ladder.json",
        )
        protected = probe2_protected_roots(
            base / "heavy/sweep_summary_heavy_parent_v3.json",
            {
                "certification_version": V3_HEAVY_VERSION,
                "primary_archive": {"root": str(base / "primary")},
                "pilot_archive": {"root": str(base / "pilot")},
                "heavy_parent": {
                    "identity": {"source_model": str(base / "heavy/checkpoint")}
                },
            },
            scalar_inputs,
            base / "parent",
        )
        assert (base / "pilot").resolve() in protected
        assert (base / "ruler").resolve() in protected

    canonical = Namespace(
        concept_index=23,
        forget_steps=120,
        snapshot_every=10,
        batch_size=8,
        max_new_tokens=256,
        seed=0,
        smoke=False,
    )
    validate_canonical_config(canonical)
    canonical.forget_steps = 240
    try:
        validate_canonical_config(canonical)
    except ValueError:
        pass
    else:
        raise AssertionError("noncanonical Probe 3 budget was accepted")

    with tempfile.TemporaryDirectory() as temporary:
        repo = Path(temporary)
        concepts_path = repo / "data" / "rehearsal_concepts.json"
        concepts_path.parent.mkdir()
        concepts_path.write_text("[]\n", encoding="utf-8")
        concept_args = Namespace(smoke=False, concepts=str(concepts_path))
        validate_canonical_concept(
            concept_args, repo, {"id": "horror_films"}
        )
        for mutated_args, concept in (
            (
                Namespace(smoke=False, concepts=str(repo / "other.json")),
                {"id": "horror_films"},
            ),
            (concept_args, {"id": "different"}),
        ):
            try:
                validate_canonical_concept(mutated_args, repo, concept)
            except ValueError:
                pass
            else:
                raise AssertionError("noncanonical Probe 3 concept was accepted")

    groups = {
        "core": {"verdict": "PRESENT"},
        "neighbour": {"verdict": "PRESENT"},
    }
    semantic = semantic_result(
        {"judge_model": "clean", "concept_id": "target", "groups": groups},
        ("core", "neighbour"),
        "clean",
        "target",
    )
    assert semantic["semantic_present"] and not semantic["semantic_absent"]
    for invalid in (
        {"judge_model": "clean", "concept_id": "target",
         "groups": {"core": {"verdict": "PRESENT"}}},
        {"judge_model": "wrong", "concept_id": "target", "groups": groups},
    ):
        try:
            semantic_result(
                invalid, ("core", "neighbour"), "clean", "target"
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError("invalid semantic judgement was accepted")

    # The driver independently recomputes the scalar and fails closed on a
    # stale policy or a scalar inconsistent with the recorded components.
    baseline = {"R": 1.0, "D": 1.0, "J": 1.0, "F": 1.0}
    positive = {"R": 0.0, "D": 0.0, "J": 0.0, "F": 0.0}
    negative = {"R": 2.0, "D": 2.0, "J": 2.0, "F": 2.0}
    prompt_hashes = {"battery": "1", "capability": "2", "survival": "3"}
    scalar_kwargs = {
        "expected_model": "model",
        "expected_judge": "clean",
        "expected_tokenizer": "clean",
        "expected_prompt_sha256": prompt_hashes,
        "expected_weight_sha256": {"weights": "a"},
        "expected_model_support_sha256": {"config": "b"},
        "expected_clean_weight_sha256": {"weights": "c"},
        "expected_clean_support_sha256": {"config": "d"},
    }
    with tempfile.TemporaryDirectory() as temporary:
        scalar_path = Path(temporary) / "scalar.json"
        scalar_path.write_text(
            json.dumps(
                {
                    "model": "model",
                    "judge_model": "clean",
                    "tokenizer_model": "clean",
                    "limit": None,
                    "judge_parse_complete": True,
                    "components": baseline,
                    "model_weight_sha256": {"weights": "a"},
                    "model_support_sha256": {"config": "b"},
                    "tokenizer_support_sha256": {"config": "d"},
                    "judge_support_sha256": {"config": "d"},
                    "judge_weight_sha256": {"weights": "c"},
                    "prompt_files": {
                        key: {"sha256": value}
                        for key, value in prompt_hashes.items()
                    },
                    "normalisation_policy": V2_POLICY,
                    "normalisation_policy_fingerprint": "a" * 64,
                    "scalar_0_100": 0.0,
                }
            ),
            encoding="utf-8",
        )
        scalar, _, _ = scalar_from_components(
            scalar_path,
            baseline,
            positive,
            negative,
            "a" * 64,
            **scalar_kwargs,
        )
        assert scalar == 0.0
        payload = json.loads(scalar_path.read_text(encoding="utf-8"))
        payload["scalar_0_100"] = 1.0
        scalar_path.write_text(json.dumps(payload), encoding="utf-8")
        try:
            scalar_from_components(
                scalar_path,
                baseline,
                positive,
                negative,
                "a" * 64,
                **scalar_kwargs,
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError("inconsistent scalar artifact was accepted")
        payload["scalar_0_100"] = 0.0
        payload["judge_weight_sha256"] = {"weights": "wrong"}
        scalar_path.write_text(json.dumps(payload), encoding="utf-8")
        try:
            scalar_from_components(
                scalar_path,
                baseline,
                positive,
                negative,
                "a" * 64,
                **scalar_kwargs,
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError("wrong scalar judge identity was accepted")

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        output = root / "artifact.json"
        calls = []

        def action():
            calls.append(True)
            output.write_text('{"ok": true}\n', encoding="utf-8")

        config_fp = fingerprint({"version": PROBE3_VERSION})
        ensure_stage(root, "unit", config_fp, {"x": 1}, [output], action)
        ensure_stage(root, "unit", config_fp, {"x": 1}, [output], action)
        assert len(calls) == 1
        output.write_text('{"ok": false}\n', encoding="utf-8")
        try:
            ensure_stage(root, "unit", config_fp, {"x": 1}, [output], action)
        except RuntimeError:
            pass
        else:
            raise AssertionError("mutated completed stage was accepted")

    with tempfile.TemporaryDirectory() as temporary:
        adapter_root = (Path(temporary) / "adapters").resolve()
        adapter_root.mkdir()
        for step in (10, 20, 30):
            (adapter_root / f"step{step:03d}").mkdir()
        trainer_config = {
            "model_id": "heavy",
            "forget_data": "forget.json",
            "retain_data": "data/retain.json",
            "chat_retain_data": "data/retain_chat.json",
            "output_dir": str(adapter_root),
            "num_steps": 30,
            "save_every": 10,
            "eval_every": 10,
            "batch_forget": 4,
            "batch_retain": 2,
            "batch_chat_retain": 2,
            "max_length": 256,
            "rank": 4,
            "lora_alpha": 8,
            "train_layer_lo": 4,
            "train_layer_hi": 11,
            "learning_rate": 5e-5,
            "forget_weight": 1.0,
            "retain_weight": 1.0,
            "chat_retain_weight": 1.0,
            "stop_jsd": 0.02,
            "stop_answer_prob": 0.05,
            "audit_size": 24,
            "seed": 0,
            "external_semantic_selection": True,
            "fp32_base": False,
        }
        (adapter_root / "run_config.json").write_text(
            json.dumps(trainer_config), encoding="utf-8"
        )
        stop_state = {
            "external_semantic_selection": True,
            "stop_reason": "step_budget_exhausted",
            "stopped_at_step": 30,
            "final_adapter": str(adapter_root / "step030"),
        }
        (adapter_root / "stop_state.json").write_text(
            json.dumps(stop_state), encoding="utf-8"
        )
        _, snapshots = validate_trainer_grid(
            adapter_root,
            model_id="heavy",
            forget_data="forget.json",
            num_steps=30,
            snapshot_every=10,
            seed=0,
            fp32_base=False,
        )
        assert [path.name for path in snapshots] == ["step010", "step020", "step030"]
        (adapter_root / "step020").rmdir()
        try:
            validate_trainer_grid(
                adapter_root,
                model_id="heavy",
                forget_data="forget.json",
                num_steps=30,
                snapshot_every=10,
                seed=0,
                fp32_base=False,
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError("incomplete trainer snapshot grid was accepted")
        (adapter_root / "step020").mkdir()
        trainer_config["learning_rate"] = 1e-4
        (adapter_root / "run_config.json").write_text(
            json.dumps(trainer_config), encoding="utf-8"
        )
        try:
            validate_trainer_grid(
                adapter_root,
                model_id="heavy",
                forget_data="forget.json",
                num_steps=30,
                snapshot_every=10,
                seed=0,
                fp32_base=False,
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError("noncanonical trainer recipe was accepted")

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / "summary.json").write_text("{}\n", encoding="utf-8")
        (root / "MANIFEST.sha256.tmp").write_text("stale", encoding="utf-8")
        write_manifest(root)
        assert verify_manifest(root)
        assert not (root / "MANIFEST.sha256.tmp").exists()
        (root / "summary.json").write_text('{"changed": true}\n', encoding="utf-8")
        try:
            verify_manifest(root)
        except RuntimeError:
            pass
        else:
            raise AssertionError("mutated sealed archive was accepted")

    print("Probe 3 certification tests: PASS")


if __name__ == "__main__":
    main()
