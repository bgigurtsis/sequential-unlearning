"""CPU-only policy tests for the Probe 2 v3 diagnostic pilot."""

import hashlib
import json
import subprocess
import tempfile
from argparse import Namespace
from pathlib import Path

from run_noise_pilot_v3 import (
    ARM_A_ALPHAS,
    ARM_B_ALPHAS,
    EXPECTED_V2_MEANS,
    HEAVY_PARENT_U,
    MAPPING_SCHEMA_SHA256,
    OUTCOMES,
    PUBLIC_CONTROLLER_U,
    V2_POLICY,
    analyse_arm,
    build_controller_mapping,
    committed_source_identity,
    ensure_stage,
    fingerprint,
    outcome_for_arms,
    raw_adjacent_brackets,
    remove_checkpoint_after_validation,
    recompute_summary_arms,
    should_fail_early,
    validate_config,
    validate_failed_v2_summary,
    validate_pilot_scalar_execution,
    verify_pilot_manifest,
    write_manifest,
)


def linear_points(alphas, beta, include_terminal=False):
    points = [{
        "alpha": 0.0,
        "beta": None,
        "seed": None,
        "scheduled": False,
        "historical_seed_exception": True,
        "scalar": 0.0,
        "reference": "unit_baseline",
        "reference_artifact": "baseline/scalar.json",
        "reference_artifact_sha256": "a" * 64,
    }]
    points.extend(
        {
            "alpha": alpha,
            "beta": beta,
            "seed": 11,
            "scheduled": True,
            "historical_seed_exception": False,
            "scalar": alpha * 100.0,
            "scalar_json": f"dose/{alpha}/scalar.json",
            "scalar_sha256": "b" * 64,
            "dose_sidecar": f"dose/{alpha}/decay_dose.json",
            "dose_sidecar_sha256": "c" * 64,
        }
        for alpha in alphas
    )
    if include_terminal and points[-1]["alpha"] != 1.0:
        points.append({
            "alpha": 1.0,
            "beta": beta,
            "seed": 0,
            "scheduled": False,
            "historical_seed_exception": True,
            "scalar": 100.0,
            "reference": "unit_terminal",
            "reference_artifact": "anchor/scalar.json",
            "reference_artifact_sha256": "d" * 64,
        })
    return points


def main():
    assert OUTCOMES == {
        "PROMOTE_ARM_A", "PROMOTE_ARM_B", "FAIL_WEIGHT_NOISE", "INCOMPLETE"
    }
    assert ARM_A_ALPHAS == (
        0.0025, 0.005, 0.01, 0.02, 0.03, 0.04, 0.05, 0.055, 0.06,
        0.065, 0.07, 0.075, 0.08, 0.085, 0.09, 0.095, 0.1, 0.12,
    )
    assert ARM_B_ALPHAS == (
        0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40,
        0.45, 0.50, 0.55, 0.60, 0.70, 0.85, 1.0,
    )
    validate_config(Namespace(batch_size=8, max_new_tokens=256))
    try:
        validate_config(Namespace(batch_size=16, max_new_tokens=256))
    except ValueError:
        pass
    else:
        raise AssertionError("noncanonical pilot batch size was accepted")

    failed_v2 = {
        "certification_scope": "clean_parent_primary_only",
        "normalisation_version": V2_POLICY,
        "normalisation_policy_fingerprint": "f" * 64,
        "gates": {
            "primary_verdict": "FAIL",
            "loo_gate_pass": False,
            "ladder_gate_pass": True,
        },
        "partial_curve": {
            str(alpha): {"mean": value}
            for alpha, value in EXPECTED_V2_MEANS.items()
        },
    }
    failed_v2["gates"].update({
        "failure_stage": "noise_calibration",
        "sweep_completed": False,
        "probe2_verdict": "FAIL",
        "loo_gate_mathematically_impossible": True,
        "loo_impossibility_error_lower_bound": 56.1475945475,
    })
    certificate = {
        "certificate_version": "probe2_v2_loo_impossibility_v1",
        "conclusion": "PROBE2_PRIMARY_FAIL",
        "never_pass_capable": True,
        "normalisation_version": V2_POLICY,
        "normalisation_policy_fingerprint": "f" * 64,
        "loo_impossibility_proof": {
            "observed_alpha0.05_mean": EXPECTED_V2_MEANS[0.05],
            "observed_alpha0.1_mean": EXPECTED_V2_MEANS[0.1],
            "minimum_possible_absolute_error": 56.1475945475,
            "loo_error_limit": 3.0,
            "gate_mathematically_impossible": True,
        },
    }
    validate_failed_v2_summary(failed_v2, certificate, "f" * 64)
    mutated = json.loads(json.dumps(failed_v2))
    mutated["partial_curve"]["0.1"]["mean"] += 1e-4
    try:
        validate_failed_v2_summary(mutated, certificate, "f" * 64)
    except RuntimeError:
        pass
    else:
        raise AssertionError("pilot accepted a different archived v2 failure")

    scalar_policy = {
        "seed": 0,
        "decoding": {
            "method": "greedy",
            "max_new_tokens": 256,
            "batch_size": 8,
            "padding_side": "left",
        },
        "limit": None,
        "weights": {"R": 0.25, "D": 0.15, "J": 0.35, "F": 0.25},
        "judge_parse_complete": True,
        "judge_unparsed_count": 0,
        "normalisation_policy_requested": V2_POLICY,
        "normalisation_policy": V2_POLICY,
    }
    validate_pilot_scalar_execution(scalar_policy)
    for field, bad_value in (
        ("seed", 7),
        ("decoding", {**scalar_policy["decoding"], "batch_size": 16}),
    ):
        mutated_policy = json.loads(json.dumps(scalar_policy))
        mutated_policy[field] = bad_value
        try:
            validate_pilot_scalar_execution(mutated_policy)
        except RuntimeError:
            pass
        else:
            raise AssertionError(f"pilot accepted noncanonical scalar {field}")

    arm_a = analyse_arm(linear_points(ARM_A_ALPHAS, 1.0, True), "A")
    assert arm_a["promotion_screen_pass"], arm_a
    mapping = arm_a["controller_mapping"]
    assert mapping["schema_sha256"] == MAPPING_SCHEMA_SHA256
    assert [point["u"] for point in mapping["controller"]] == list(PUBLIC_CONTROLLER_U)
    assert mapping["heavy_parent"]["u"] == HEAVY_PARENT_U
    assert mapping["heavy_parent"]["physical_alpha"] == 0.65
    assert mapping["fingerprint"] == fingerprint(
        {key: value for key, value in mapping.items() if key != "fingerprint"}
    )
    assert len(arm_a["spearman_points"]) == len(ARM_A_ALPHAS)
    assert all(0.0 < point["alpha"] < 1.0 for point in arm_a["spearman_points"])
    assert all(
        "reference_artifact" in point or (
            "scalar_artifact" in point and "dose_sidecar" in point
        )
        for point in mapping["raw_points"]
    )
    arm_b = analyse_arm(linear_points(ARM_B_ALPHAS, 0.1), "B")
    assert arm_b["promotion_screen_pass"], arm_b
    assert len(arm_b["spearman_points"]) == len(ARM_B_ALPHAS) - 1
    assert all(point["alpha"] < 1.0 for point in arm_b["spearman_points"])
    assert outcome_for_arms(arm_a) == "PROMOTE_ARM_A"
    failed_arm = {"promotion_screen_pass": False}
    assert outcome_for_arms(failed_arm) is None
    assert outcome_for_arms(failed_arm, arm_b) == "PROMOTE_ARM_B"
    assert outcome_for_arms(failed_arm, failed_arm) == "FAIL_WEIGHT_NOISE"
    try:
        outcome_for_arms(arm_a, arm_b)
    except RuntimeError:
        pass
    else:
        raise AssertionError("Arm B was accepted after Arm A promotion")

    valid_summary = {"arm_a": arm_a, "arm_b": None, "outcome": "PROMOTE_ARM_A"}
    recomputed_a, recomputed_b, recomputed_outcome = recompute_summary_arms(
        valid_summary
    )
    assert recomputed_a == arm_a and recomputed_b is None
    assert recomputed_outcome == "PROMOTE_ARM_A"
    forged = json.loads(json.dumps(valid_summary))
    forged["arm_a"]["spearman"] = 0.0
    try:
        recompute_summary_arms(forged)
    except RuntimeError:
        pass
    else:
        raise AssertionError("forged stored arm analysis was accepted")
    forged = json.loads(json.dumps(valid_summary))
    forged["outcome"] = "FAIL_WEIGHT_NOISE"
    try:
        recompute_summary_arms(forged)
    except RuntimeError:
        pass
    else:
        raise AssertionError("forged stored pilot outcome was accepted")

    assert raw_adjacent_brackets(
        [{"alpha": 0.1, "scalar": 9.0}, {"alpha": 0.2, "scalar": 10.0}],
        10.0,
    )
    assert not raw_adjacent_brackets(
        [{"alpha": 0.1, "scalar": 11.0}, {"alpha": 0.2, "scalar": 9.0}],
        10.0,
    )

    unreachable = linear_points(ARM_A_ALPHAS, 1.0, True)
    for point in unreachable:
        point["scalar"] = 0.0
    mapping, mapping_error = build_controller_mapping(unreachable, "A")
    assert mapping is None
    assert mapping_error == "controller_mapping_target_unreachable"

    cliff = [
        {"alpha": 0.0, "scalar": 0.0, "scheduled": False},
        {"alpha": 0.05, "scalar": 9.0, "scheduled": True},
        {"alpha": 0.055, "scalar": 40.0, "scheduled": True},
        {"alpha": 1.0, "scalar": 100.0, "scheduled": False},
    ]
    assert should_fail_early(cliff, "A") == "unresolved_local_jump_gt_20"
    decline = [
        {"alpha": 0.05, "scalar": 20.0},
        {"alpha": 0.055, "scalar": 16.0},
    ]
    assert should_fail_early(decline, "A") == "adjacent_decrease_gt_3"
    high_first = [
        {"alpha": 0.0, "scalar": 0.0, "scheduled": False},
        {"alpha": ARM_A_ALPHAS[0], "scalar": 5.00001, "scheduled": True},
        {"alpha": 1.0, "scalar": 100.0, "scheduled": False},
    ]
    assert should_fail_early(high_first, "A") == "low_end_not_resolved"
    early_summary = analyse_arm(high_first, "A", ["low_end_not_resolved"])
    recomputed_early_summary = analyse_arm(high_first, "A")
    assert early_summary == recomputed_early_summary

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        checkpoint = root / "dose" / "checkpoint"
        checkpoint.mkdir(parents=True)
        (checkpoint / "sentinel").write_text("preserve", encoding="utf-8")
        try:
            remove_checkpoint_after_validation(checkpoint, root, False)
        except RuntimeError:
            pass
        else:
            raise AssertionError("unvalidated checkpoint cleanup was accepted")
        assert checkpoint.is_dir()
        remove_checkpoint_after_validation(checkpoint, root, True)
        assert not checkpoint.exists()

    incomplete = analyse_arm(
        [{"alpha": 0.0, "scalar": 0.0}, {"alpha": 1.0, "scalar": 100.0}],
        "A",
    )
    assert not incomplete["promotion_screen_pass"]
    assert "incomplete_grid" in incomplete["failure_reasons"]

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        output = root / "output.json"
        calls = []

        def action():
            calls.append(True)
            output.write_text("{}\n", encoding="utf-8")

        config_fp = fingerprint({"pilot": 3})
        ensure_stage(root, "unit", config_fp, {"x": 1}, (output,), action)
        ensure_stage(root, "unit", config_fp, {"x": 1}, (output,), action)
        assert len(calls) == 1
        output.write_text('{"changed": true}\n', encoding="utf-8")
        try:
            ensure_stage(root, "unit", config_fp, {"x": 1}, (output,), action)
        except RuntimeError:
            pass
        else:
            raise AssertionError("mutated resumable pilot stage was accepted")

    with tempfile.TemporaryDirectory() as temporary:
        repo = Path(temporary)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(
            ["git", "config", "user.email", "pilot-test@example.invalid"],
            cwd=repo,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Pilot Test"], cwd=repo, check=True
        )
        source = repo / "source.py"
        source.write_text("value = 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "source.py"], cwd=repo, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "fixture"], cwd=repo, check=True
        )
        identity = committed_source_identity(repo, ("source.py",))
        assert identity["sha256"]["source.py"] == hashlib.sha256(
            subprocess.run(
                ["git", "show", "HEAD:source.py"],
                cwd=repo,
                check=True,
                capture_output=True,
            ).stdout
        ).hexdigest()
        source.write_text("value = 2\n", encoding="utf-8")
        try:
            committed_source_identity(repo, ("source.py",))
        except RuntimeError:
            pass
        else:
            raise AssertionError("uncommitted executed source was accepted")

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / "artifact.json").write_text("{}\n", encoding="utf-8")
        (root / "MANIFEST.sha256.tmp").write_text("stale", encoding="utf-8")
        write_manifest(root)
        assert verify_pilot_manifest(root)
        assert not (root / "MANIFEST.sha256.tmp").exists()
        (root / "artifact.json").write_text("changed\n", encoding="utf-8")
        try:
            verify_pilot_manifest(root)
        except RuntimeError:
            pass
        else:
            raise AssertionError("mutated pilot archive was accepted")

    print("Probe 2 v3 pilot policy tests: PASS")


if __name__ == "__main__":
    main()
