"""CPU-only policy and archive-contract tests for Probe 2 v3 heavy certification."""

import hashlib
import itertools
import json
import subprocess
import tempfile
from pathlib import Path

from run_noise_pilot_v3 import MAPPING_SCHEMA_SHA256, PUBLIC_CONTROLLER_U
from run_noise_certification_v3 import CERTIFICATION_VERSION
from run_noise_heavy_v3 import (
    CHILD_SEEDS,
    CONFIG_KEYS,
    EXECUTED_SOURCE_PATHS,
    HEAVY_PARENT_BAND,
    HEAVY_IDENTITY_KEYS,
    HEAVY_PARENT_KEYS,
    HEAVY_PARENT_SEED,
    HEAVY_PARENT_U,
    INTERIOR_U,
    SUMMARY_KEYS,
    aggregate_seed_entries,
    analyse_heavy_curve,
    artifact_inside,
    checkpoint_snapshot,
    cleanup_checkpoint,
    committed_source_identity,
    delete_validated_child_checkpoint,
    dose_resume_requires_apply,
    ensure_stage,
    fingerprint,
    mapping_for_heavy,
    model_weight_hashes,
    parent_failure_gates,
    primary_archive_identity,
    read_json,
    recover_archived_sidecar,
    recompute_summary_semantics,
    require_finite_tree,
    require_exact_keys,
    sha256_of_file,
    support_file_hashes,
    validate_dose_sidecar_schema,
    validate_checkpoint_resume_provenance,
    validate_primary_for_heavy,
    validate_exact_archive_layout,
    validate_recorded_source_identity,
    validate_stage_marker,
    verify_manifest,
    write_json,
    write_manifest,
)


LADDER = {
    "ladder_monotonicity": {"R": True, "D": True, "J": True, "F": True},
    "ladder_component_pass": {"R": True, "D": True, "J": True, "F": True},
    "ladder_gate_pass": True,
}


def record(seed, scalar, u, alpha=None):
    alpha = u if alpha is None else alpha
    return {
        "controller_u": u,
        "physical_alpha": alpha,
        "seed": seed,
        "scalar": scalar,
        "raw_components": {key: scalar for key in ("R", "D", "J", "F")},
        "normalised_components": {
            key: scalar / 100.0 for key in ("R", "D", "J", "F")
        },
        "normalisation_directions": {
            key: "positive" for key in ("R", "D", "J", "F")
        },
        "scalar_json": f"u{u}/seed{seed}/scalar.json",
        "scalar_sha256": "a" * 64,
        "reanalysis_json": f"u{u}/seed{seed}/reanalysis.json",
        "reanalysis_sha256": "b" * 64,
        "decay_dose_json": f"u{u}/seed{seed}/dose.json",
        "decay_dose_sha256": "c" * 64,
    }


def linear_curve(spread=2.0):
    curve = {}
    half = spread / 2.0
    for u in INTERIOR_U:
        mean = 65.0 + 35.0 * u
        curve[u] = aggregate_seed_entries(
            [record(0, mean - half, u), record(1, mean, u), record(2, mean + half, u)]
        )
    return curve


def promoted_mapping(root):
    controller = [
        {"u": u, "target_scalar": 100.0 * u, "physical_alpha": u}
        for u in PUBLIC_CONTROLLER_U
    ]
    mapping = {
        "schema_sha256": MAPPING_SCHEMA_SHA256,
        "source_arm": "A",
        "beta": 1.0,
        "seed_used_to_fit": 11,
        "controller": controller,
        "heavy_parent": {
            "u": HEAVY_PARENT_U,
            "target_scalar": 65.0,
            "physical_alpha": 0.65,
        },
    }
    mapping["fingerprint"] = fingerprint(mapping)
    path = root / "controller_mapping.json"
    path.write_text(json.dumps(mapping, allow_nan=False) + "\n", encoding="utf-8")
    summary = {
        "outcome": "PROMOTE_ARM_A",
        "controller_mapping": str(path.resolve()),
        "controller_mapping_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "controller_mapping_fingerprint": mapping["fingerprint"],
    }
    return path, mapping, summary


def make_complete_checkpoint(checkpoint):
    checkpoint.mkdir(parents=True)
    (checkpoint / "model.safetensors").write_bytes(b"weights")
    (checkpoint / "config.json").write_text("{}\n", encoding="utf-8")
    source_identity = {
        "source_model": str((checkpoint.parent / "source-model").resolve()),
        "weight_file_sha256": {"source.bin": "c" * 64},
        "support_file_sha256": {"source.json": "d" * 64}, "fingerprint": "f" * 64,
    }
    sidecar = {
        "source_model": source_identity["source_model"],
        "tokenizer_source": source_identity["source_model"],
        "source_identity": source_identity,
        "source_identity_fingerprint": "f" * 64,
        "alpha": 0.1, "beta": 1.0, "seed": 0,
        "per_tensor_seed_rule": "(seed * 1000003 + crc32(name)) % 2**63",
        "transform": "W' = (1-alpha)*W + alpha*beta*max_abs_per_output_channel(W)*N(0,1)",
        "dtype": "bfloat16 weights, fp32 transform arithmetic",
        "modified_tensors": 0, "modified": [], "skipped": [],
        "weight_file_sha256": model_weight_hashes(checkpoint),
        "support_file_sha256": support_file_hashes(checkpoint),
    }
    (checkpoint / "decay_dose.json").write_text(
        json.dumps(sidecar, allow_nan=False) + "\n", encoding="utf-8"
    )
    return sidecar


def expect_error(action, label):
    try:
        action()
    except (RuntimeError, ValueError, KeyError):
        return
    raise AssertionError(f"{label} was accepted")


def main():
    assert HEAVY_PARENT_U == 0.65
    assert HEAVY_PARENT_SEED == 7
    assert HEAVY_PARENT_BAND == (60.0, 70.0)
    assert INTERIOR_U == (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.75, 0.9)
    assert CHILD_SEEDS == (0, 1, 2)

    curve = linear_curve()
    gates = analyse_heavy_curve(curve, 65.0, 100.0, LADDER)
    assert gates["primary_manifest_verified"] is True
    assert gates["primary_verdict_verified"] is True
    assert gates["heavy_verdict"] == "PASS", gates
    assert gates["probe2_verdict"] == "PASS"
    assert gates["spearman_seed_means"] == 1.0
    assert gates["max_loo_error"] < 1e-8
    assert gates["raw_mean_nondecrease_gate_pass"]
    assert gates["per_dose_range_gate_pass"]
    assert gates["no_refit_bisection_or_extra_points"] is True
    assert set(gates["per_dose_raw_ranges"]) == {str(u) for u in INTERIOR_U}

    inclusive = linear_curve(spread=6.0)
    assert analyse_heavy_curve(inclusive, 65.0, 100.0, LADDER)[
        "per_dose_range_gate_pass"
    ]
    too_wide = linear_curve(spread=6.000001)
    assert not analyse_heavy_curve(too_wide, 65.0, 100.0, LADDER)[
        "per_dose_range_gate_pass"
    ]
    assert analyse_heavy_curve(too_wide, 65.0, 100.0, LADDER)["heavy_verdict"] == "FAIL"

    falling = linear_curve()
    falling[0.4] = aggregate_seed_entries(
        [record(0, 70.0, 0.4), record(1, 71.0, 0.4), record(2, 72.0, 0.4)]
    )
    falling_gates = analyse_heavy_curve(falling, 65.0, 100.0, LADDER)
    assert not falling_gates["raw_mean_nondecrease_gate_pass"]
    assert falling_gates["heavy_verdict"] == "FAIL"
    assert analyse_heavy_curve(linear_curve(), 65.0, 90.0, LADDER)[
        "raw_mean_nondecrease_gate_pass"
    ] is False
    expect_error(
        lambda: analyse_heavy_curve(
            {u: row for u, row in linear_curve().items() if u != 0.5}, 65, 100, LADDER
        ),
        "missing controller dose",
    )
    wrong_seed = linear_curve()
    wrong_seed[0.1]["per_seed"][2]["seed"] = 7
    expect_error(
        lambda: analyse_heavy_curve(wrong_seed, 65, 100, LADDER),
        "noncanonical child seed",
    )

    failed = parent_failure_gates(70.000001, LADDER)
    assert failed["heavy_parent_selection_pass"] is False
    assert failed["heavy_verdict"] == failed["probe2_verdict"] == "FAIL"
    assert failed["spearman_seed_means"] is None
    assert failed["no_refit_bisection_or_extra_points"] is True
    for boundary in (60.0, 70.0):
        assert parent_failure_gates(boundary, LADDER)[
            "heavy_parent_selection_pass"
        ] is True
    assert parent_failure_gates(59.999999, LADDER)[
        "heavy_parent_selection_pass"
    ] is False

    valid_summary = {
        "heavy_parent": {"identity": {"measured_global_scalar": 65.0}},
        "curve": {str(u): row for u, row in linear_curve().items()},
        "incremental_alpha1_endpoint": record(0, 100.0, 1.0),
        "gates": gates,
    }
    assert recompute_summary_semantics(valid_summary) == gates
    forged = json.loads(json.dumps(valid_summary, allow_nan=False))
    forged["gates"]["max_loo_error"] = 0.5
    expect_error(lambda: recompute_summary_semantics(forged), "forged LOO seal")
    aliased = json.loads(json.dumps(valid_summary, allow_nan=False))
    aliased["curve"]["0.10"] = aliased["curve"].pop("0.1")
    expect_error(
        lambda: recompute_summary_semantics(aliased), "aliased controller JSON key"
    )
    extra_gate = json.loads(json.dumps(valid_summary, allow_nan=False))
    extra_gate["gates"]["surprise"] = True
    expect_error(lambda: recompute_summary_semantics(extra_gate), "extra gate field")
    extra_row = linear_curve()
    extra_row[0.2]["surprise"] = True
    expect_error(
        lambda: analyse_heavy_curve(extra_row, 65.0, 100.0, LADDER),
        "extra aggregate field",
    )
    extra_record = linear_curve()
    extra_record[0.3]["per_seed"][0]["surprise"] = True
    expect_error(
        lambda: analyse_heavy_curve(extra_record, 65.0, 100.0, LADDER),
        "extra per-seed field",
    )
    bad_component_aggregate = linear_curve()
    bad_component_aggregate[0.5]["raw_component_means"]["R"] += 0.01
    expect_error(
        lambda: analyse_heavy_curve(bad_component_aggregate, 65.0, 100.0, LADDER),
        "tampered aggregate component mean",
    )
    bad_direction_counts = linear_curve()
    bad_direction_counts[0.6]["normalisation_direction_counts"]["R"]["positive"] = 2
    expect_error(
        lambda: analyse_heavy_curve(bad_direction_counts, 65.0, 100.0, LADDER),
        "tampered aggregate direction count",
    )
    boolean_component = linear_curve()
    boolean_component[0.2]["per_seed"][0]["raw_components"]["R"] = True
    expect_error(
        lambda: analyse_heavy_curve(boolean_component, 65.0, 100.0, LADDER),
        "boolean raw component",
    )
    wrong_alpha = linear_curve()
    wrong_alpha[0.4]["physical_alpha"] = 0.40001
    for child_record in wrong_alpha[0.4]["per_seed"]:
        child_record["physical_alpha"] = 0.40001
    expect_error(
        lambda: analyse_heavy_curve(
            wrong_alpha, 65.0, 100.0, LADDER,
            {str(u): u for u in PUBLIC_CONTROLLER_U},
        ),
        "aggregate physical-alpha remap",
    )
    fail_summary = {
        "heavy_parent": {"identity": {"measured_global_scalar": 75.0}},
        "curve": {},
        "incremental_alpha1_endpoint": None,
        "gates": parent_failure_gates(75.0, LADDER),
    }
    recompute_summary_semantics(fail_summary)
    fail_summary["curve"] = {"0.1": linear_curve()[0.1]}
    expect_error(
        lambda: recompute_summary_semantics(fail_summary),
        "child work after terminal parent failure",
    )

    for value in (float("nan"), float("inf"), float("-inf")):
        expect_error(lambda value=value: require_finite_tree({"x": [value]}), "nonfinite tree")
        expect_error(lambda value=value: fingerprint({"x": value}), "nonfinite fingerprint")
    require_exact_keys({key: None for key in CONFIG_KEYS}, CONFIG_KEYS, "config")
    require_exact_keys({key: None for key in SUMMARY_KEYS}, SUMMARY_KEYS, "summary")
    require_exact_keys({key: None for key in HEAVY_PARENT_KEYS}, HEAVY_PARENT_KEYS, "parent")
    expect_error(
        lambda: require_exact_keys(
            {**{key: None for key in HEAVY_IDENTITY_KEYS}, "alias": 0},
            HEAVY_IDENTITY_KEYS, "heavy identity",
        ),
        "extra nested heavy identity field",
    )
    expect_error(
        lambda: require_exact_keys(
            {**{key: None for key in CONFIG_KEYS}, "extra": True}, CONFIG_KEYS,
            "config",
        ),
        "extra top-level config field",
    )
    expect_error(
        lambda: require_exact_keys(
            {key: None for key in SUMMARY_KEYS if key != "curve"}, SUMMARY_KEYS,
            "summary",
        ),
        "missing top-level summary field",
    )
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        invalid = root / "invalid.json"
        invalid.write_text('{"value": NaN}\n', encoding="utf-8")
        expect_error(lambda: read_json(invalid), "JSON NaN")
        expect_error(lambda: write_json(root / "out.json", {"value": float("inf")}), "JSON infinity write")
        inside = root / "inside.json"
        inside.write_text("{}\n", encoding="utf-8")
        assert artifact_inside(root, inside, "unit") == inside.resolve()
        outside = root.parent / "outside-heavy-test.json"
        outside.write_text("{}\n", encoding="utf-8")
        try:
            expect_error(lambda: artifact_inside(root, outside, "unit"), "outside archive path")
        finally:
            outside.unlink()

    valid_sidecar = {
        "source_model": "model", "tokenizer_source": "model",
        "source_identity": {"fingerprint": "f" * 64},
        "source_identity_fingerprint": "f" * 64,
        "alpha": 0.1, "beta": 1.0, "seed": 0,
        "per_tensor_seed_rule": "(seed * 1000003 + crc32(name)) % 2**63",
        "transform": "W' = (1-alpha)*W + alpha*beta*max_abs_per_output_channel(W)*N(0,1)",
        "dtype": "bfloat16 weights, fp32 transform arithmetic",
        "modified_tensors": 1,
        "modified": [{
            "name": "layer.weight", "shape": [2, 2],
            "channel_scale_mean": 1.0, "channel_scale_max": 2.0,
        }],
        "skipped": [{"name": "layer.bias", "reason": "rank<2"}],
        "weight_file_sha256": {"model.safetensors": "a" * 64},
        "support_file_sha256": {"config.json": "b" * 64},
    }
    validate_dose_sidecar_schema(valid_sidecar)
    extra_sidecar = json.loads(json.dumps(valid_sidecar, allow_nan=False))
    extra_sidecar["unexpected"] = True
    expect_error(
        lambda: validate_dose_sidecar_schema(extra_sidecar),
        "extra dose-sidecar field",
    )

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        path, mapping, summary = promoted_mapping(root)
        actual_path, actual = mapping_for_heavy(root, summary)
        assert actual_path == path.resolve() and actual == mapping
        mutated = json.loads(json.dumps(mapping, allow_nan=False))
        mutated["controller"][3]["physical_alpha"] = mutated["controller"][2][
            "physical_alpha"
        ]
        path.write_text(json.dumps(mutated, allow_nan=False) + "\n", encoding="utf-8")
        summary["controller_mapping_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        summary["controller_mapping_fingerprint"] = mutated["fingerprint"]
        expect_error(lambda: mapping_for_heavy(root, summary), "non-distinct mapping")

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        mapping_path, mapping, pilot_summary = promoted_mapping(root)
        for name in ("run_config.json", "primary_summary_v3.json", "parent_identity.json"):
            (root / name).write_text("{}\n", encoding="utf-8")
        bundle = {
            "root": root,
            "seal": {"sha256": "d" * 64},
            "config_path": root / "run_config.json",
            "summary_path": root / "primary_summary_v3.json",
            "identity_path": root / "parent_identity.json",
        }
        archive = primary_archive_identity(bundle)
        descriptor = {
            "path": str(mapping_path.resolve()),
            "sha256": hashlib.sha256(mapping_path.read_bytes()).hexdigest(),
            "fingerprint": mapping["fingerprint"],
            "schema_sha256": MAPPING_SCHEMA_SHA256,
        }
        alphas = {str(row["u"]): row["physical_alpha"] for row in mapping["controller"]}
        config = {
            "version": CERTIFICATION_VERSION,
            "pilot_archive": {"root": str(root.resolve()), "outcome": "PROMOTE_ARM_A"},
            "controller_mapping": descriptor,
            "beta": 1.0,
            "controller_coordinate": "u",
            "controller_u": list(PUBLIC_CONTROLLER_U),
            "physical_alpha_by_u": alphas,
        }
        primary_summary = {
            "certification_version": CERTIFICATION_VERSION,
            "certification_scope": "clean_parent_primary_only",
            "controller_mapping": descriptor,
            "beta": 1.0,
            "controller_coordinate": "u",
            "controller_u": list(PUBLIC_CONTROLLER_U),
            "physical_alpha_by_u": alphas,
            "gates": {
                "primary_verdict": "PASS",
                "probe2_verdict": "INCOMPLETE_PENDING_HEAVY_PARENT",
                "no_refit_bisection_or_extra_points": True,
                "raw_mean_nondecrease_gate_pass": True,
                "per_dose_range_gate_pass": True,
            },
        }
        bundle.update({"config": config, "summary": primary_summary})
        _, _, actual_archive = validate_primary_for_heavy(
            bundle, root, pilot_summary, mapping_path.resolve(), mapping
        )
        assert actual_archive == archive
        primary_summary["gates"]["raw_mean_nondecrease_gate_pass"] = False
        expect_error(
            lambda: validate_primary_for_heavy(
                bundle, root, pilot_summary, mapping_path.resolve(), mapping
            ),
            "primary PASS with failed raw gate",
        )

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        output = root / "output.json"
        calls = []

        def action():
            calls.append(True)
            output.write_text("{}\n", encoding="utf-8")

        ensure_stage(root, "unit", "f" * 64, {"seed": 7}, (output,), action)
        ensure_stage(root, "unit", "f" * 64, {"seed": 7}, (output,), action)
        assert len(calls) == 1
        output.write_text('{"tampered":true}\n', encoding="utf-8")
        expect_error(
            lambda: ensure_stage(root, "unit", "f" * 64, {"seed": 7}, (output,), action),
            "mutated resume output",
        )

    with tempfile.TemporaryDirectory() as temporary:
        dose_dir = Path(temporary) / "dose"
        dose_dir.mkdir()
        checkpoint = dose_dir / "checkpoint"
        scalar_path, sidecar_path = dose_dir / "scalar.json", dose_dir / "decay_dose.json"
        assert dose_resume_requires_apply(checkpoint, scalar_path, sidecar_path) is True

    with tempfile.TemporaryDirectory() as temporary:
        dose_dir = Path(temporary) / "dose"
        checkpoint = dose_dir / "checkpoint"
        checkpoint.mkdir(parents=True)
        sentinel = checkpoint / "partial-weight.tmp"
        sentinel.write_bytes(b"interrupted apply evidence")
        scalar_path, sidecar_path = dose_dir / "scalar.json", dose_dir / "decay_dose.json"
        expect_error(
            lambda: dose_resume_requires_apply(checkpoint, scalar_path, sidecar_path),
            "interrupted apply checkpoint redraw",
        )
        assert checkpoint.is_dir() and sentinel.read_bytes() == b"interrupted apply evidence"

    with tempfile.TemporaryDirectory() as temporary:
        dose_dir = Path(temporary) / "dose"
        dose_dir.mkdir()
        checkpoint = dose_dir / "checkpoint"
        checkpoint.write_bytes(b"unknown checkpoint evidence")
        scalar_path, sidecar_path = dose_dir / "scalar.json", dose_dir / "decay_dose.json"
        expect_error(
            lambda: dose_resume_requires_apply(checkpoint, scalar_path, sidecar_path),
            "unknown non-directory checkpoint",
        )
        assert checkpoint.read_bytes() == b"unknown checkpoint evidence"

    orphan_outputs = (
        "scalar.json", "decay_dose.json",
        "scalar_reanalysis_bidirectional_v2.json", "checkpoint_deletion.json",
    )
    orphan_combinations = [
        names
        for size in range(1, len(orphan_outputs) + 1)
        for names in itertools.combinations(orphan_outputs, size)
    ]
    for orphan_names in orphan_combinations:
        with tempfile.TemporaryDirectory() as temporary:
            dose_dir = Path(temporary) / "dose"
            dose_dir.mkdir()
            checkpoint = dose_dir / "checkpoint"
            scalar_path, sidecar_path = dose_dir / "scalar.json", dose_dir / "decay_dose.json"
            for name in orphan_names:
                (dose_dir / name).write_text("{}\n", encoding="utf-8")
            expect_error(
                lambda: dose_resume_requires_apply(checkpoint, scalar_path, sidecar_path),
                f"absent checkpoint with orphan outputs {orphan_names}",
            )
            assert all((dose_dir / name).is_file() for name in orphan_names)

    with tempfile.TemporaryDirectory() as temporary:
        dose_dir = Path(temporary) / "dose"
        dose_dir.mkdir()
        checkpoint = dose_dir / "checkpoint"
        scalar_path, sidecar_path = dose_dir / "scalar.json", dose_dir / "decay_dose.json"
        unknown = dose_dir / "unknown-resume-artifact.bin"
        unknown.write_bytes(b"preserve")
        expect_error(
            lambda: dose_resume_requires_apply(checkpoint, scalar_path, sidecar_path),
            "absent checkpoint with unknown orphan output",
        )
        assert unknown.read_bytes() == b"preserve"

    with tempfile.TemporaryDirectory() as temporary:
        dose_dir = Path(temporary) / "dose"
        checkpoint = dose_dir / "checkpoint"
        make_complete_checkpoint(checkpoint)
        scalar_path, sidecar_path = dose_dir / "scalar.json", dose_dir / "decay_dose.json"
        assert dose_resume_requires_apply(checkpoint, scalar_path, sidecar_path) is False
        scalar_path.write_text("{}\n", encoding="utf-8")
        assert dose_resume_requires_apply(checkpoint, scalar_path, sidecar_path) is False
        sidecar_path.write_text("{}\n", encoding="utf-8")
        assert dose_resume_requires_apply(checkpoint, scalar_path, sidecar_path) is False

    with tempfile.TemporaryDirectory() as temporary:
        dose_dir = Path(temporary) / "dose"
        checkpoint = dose_dir / "checkpoint"
        make_complete_checkpoint(checkpoint)
        scalar_path, sidecar_path = dose_dir / "scalar.json", dose_dir / "decay_dose.json"
        sidecar_path.write_text("{}\n", encoding="utf-8")
        expect_error(
            lambda: dose_resume_requires_apply(checkpoint, scalar_path, sidecar_path),
            "archived sidecar without scalar despite complete checkpoint",
        )

    with tempfile.TemporaryDirectory() as temporary:
        dose_dir = Path(temporary) / "dose"
        checkpoint = dose_dir / "checkpoint"
        make_complete_checkpoint(checkpoint)
        internal = checkpoint / "decay_dose.json"
        scalar_path, sidecar_path = dose_dir / "scalar.json", dose_dir / "decay_dose.json"
        scalar_path.write_text("{}\n", encoding="utf-8")
        assert dose_resume_requires_apply(checkpoint, scalar_path, sidecar_path) is False
        assert recover_archived_sidecar(checkpoint, scalar_path, sidecar_path) is True
        assert sidecar_path.read_bytes() == internal.read_bytes()
        sidecar = read_json(internal)
        validate_checkpoint_resume_provenance(
            checkpoint, sidecar["source_identity"], 0.1, 1.0, 0
        )
        wrong_source = dict(sidecar["source_identity"])
        wrong_source["fingerprint"] = "0" * 64
        expect_error(
            lambda: validate_checkpoint_resume_provenance(
                checkpoint, wrong_source, 0.1, 1.0, 0
            ),
            "complete checkpoint with wrong source identity",
        )

    with tempfile.TemporaryDirectory() as temporary:
        dose_dir = Path(temporary) / "dose"
        checkpoint = dose_dir / "checkpoint"
        make_complete_checkpoint(checkpoint)
        internal = checkpoint / "decay_dose.json"
        scalar_path, sidecar_path = dose_dir / "scalar.json", dose_dir / "decay_dose.json"
        scalar_path.write_text("{}\n", encoding="utf-8")
        sidecar_path.write_bytes(b'{"archived":"different"}\n')
        before = sidecar_path.read_bytes()
        assert dose_resume_requires_apply(checkpoint, scalar_path, sidecar_path) is False
        assert recover_archived_sidecar(checkpoint, scalar_path, sidecar_path) is False
        assert sidecar_path.read_bytes() == before
        expect_error(
            lambda: checkpoint_snapshot(checkpoint, sidecar_path),
            "complete checkpoint/archive sidecar mismatch",
        )

    with tempfile.TemporaryDirectory() as temporary:
        dose_dir = Path(temporary) / "dose"
        checkpoint = dose_dir / "checkpoint"
        make_complete_checkpoint(checkpoint)
        unknown = checkpoint / "unknown-nested"
        unknown.mkdir()
        (unknown / "evidence.bin").write_bytes(b"preserve")
        scalar_path, sidecar_path = dose_dir / "scalar.json", dose_dir / "decay_dose.json"
        expect_error(
            lambda: dose_resume_requires_apply(checkpoint, scalar_path, sidecar_path),
            "sidecar-bearing checkpoint with unknown nested evidence",
        )
        assert (unknown / "evidence.bin").read_bytes() == b"preserve"

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        scalar_path, sidecar_path = root / "scalar.json", root / "decay_dose.json"
        scalar_path.write_text("{}\n", encoding="utf-8")
        sidecar_path.write_text("{}\n", encoding="utf-8")
        inputs = {
            "source_identity_fingerprint": "a" * 64,
            "controller_u": 0.1,
            "physical_alpha": 0.02,
            "beta": 1.0,
            "seed": 0,
        }
        ensure_stage(
            root, "child_u0.1_seed0", "f" * 64, inputs,
            (scalar_path, sidecar_path), lambda: None,
        )
        validate_stage_marker(
            root, "child_u0.1_seed0", "f" * 64, "a" * 64, 0.1, 0.02,
            1.0, 0, scalar_path, sidecar_path,
        )
        marker = root / "stages" / "child_u0.1_seed0.json"
        payload = read_json(marker)
        payload["inputs"]["seed"] = 1
        write_json(marker, payload)
        expect_error(
            lambda: validate_stage_marker(
                root, "child_u0.1_seed0", "f" * 64, "a" * 64, 0.1,
                0.02, 1.0, 0, scalar_path, sidecar_path,
            ),
            "semantically forged stage marker",
        )

    def deletion_fixture(root, with_checkpoint=True):
        dose_dir = root / "sweep" / "u0.1_seed0"
        checkpoint = dose_dir / "checkpoint"
        dose_dir.mkdir(parents=True)
        if with_checkpoint:
            sidecar = make_complete_checkpoint(checkpoint)
        else:
            sidecar = {
                "weight_file_sha256": {"model.safetensors": "0" * 64},
                "support_file_sha256": {"config.json": "0" * 64},
            }
        archived = dose_dir / "decay_dose.json"
        archived.write_text(json.dumps(sidecar, allow_nan=False) + "\n", encoding="utf-8")
        if with_checkpoint:
            (checkpoint / "decay_dose.json").write_bytes(archived.read_bytes())
        child_record = record(0, 70.0, 0.1, 0.02)
        child_record["decay_dose_json"] = str(archived.resolve())
        child_record["decay_dose_sha256"] = sha256_of_file(archived)
        return dose_dir, checkpoint, child_record

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        dose_dir, checkpoint, child_record = deletion_fixture(root)
        evidence = delete_validated_child_checkpoint(
            checkpoint, dose_dir, root, "f" * 64, 0.1, 0.02, 1.0, 0,
            child_record,
        )
        assert evidence.is_file() and not checkpoint.exists()
        delete_validated_child_checkpoint(
            checkpoint, dose_dir, root, "f" * 64, 0.1, 0.02, 1.0, 0,
            child_record,
        )
        valid_evidence = read_json(evidence)
        tampered_snapshot = json.loads(json.dumps(valid_evidence, allow_nan=False))
        tampered_snapshot["checkpoint_weight_sha256"]["model.safetensors"] = "0" * 64
        write_json(evidence, tampered_snapshot)
        expect_error(
            lambda: delete_validated_child_checkpoint(
                checkpoint, dose_dir, root, "f" * 64, 0.1, 0.02, 1.0, 0,
                child_record,
            ),
            "self-consistent but false resumed deletion snapshot",
        )
        write_json(evidence, valid_evidence)
        tampered = read_json(evidence)
        tampered["seed"] = 2
        write_json(evidence, tampered)
        expect_error(
            lambda: delete_validated_child_checkpoint(
                checkpoint, dose_dir, root, "f" * 64, 0.1, 0.02, 1.0, 0,
                child_record,
            ),
            "tampered deletion evidence",
        )

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        dose_dir, checkpoint, child_record = deletion_fixture(root, False)
        expect_error(
            lambda: delete_validated_child_checkpoint(
                checkpoint, dose_dir, root, "f" * 64, 0.1, 0.02, 1.0, 0,
                child_record,
            ),
            "prematurely absent checkpoint",
        )

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        dose_dir, checkpoint, child_record = deletion_fixture(root)
        (checkpoint / "decay_dose.json").write_text('{"tampered":true}\n', encoding="utf-8")
        expect_error(
            lambda: delete_validated_child_checkpoint(
                checkpoint, dose_dir, root, "f" * 64, 0.1, 0.02, 1.0, 0,
                child_record,
            ),
            "tampered checkpoint internal sidecar",
        )

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        checkpoint = root / "child" / "checkpoint"
        checkpoint.mkdir(parents=True)
        (checkpoint / "sentinel").write_text("x", encoding="utf-8")
        expect_error(
            lambda: cleanup_checkpoint(checkpoint, root, False),
            "unvalidated checkpoint cleanup",
        )
        assert checkpoint.is_dir()
        cleanup_checkpoint(checkpoint, root, True)
        assert not checkpoint.exists()

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary).resolve()
        checkpoint = root / "heavy_parent" / "checkpoint"
        checkpoint.mkdir(parents=True)
        (checkpoint / "model.safetensors").write_bytes(b"w")
        (checkpoint / "config.json").write_text("{}\n", encoding="utf-8")
        (checkpoint / "decay_dose.json").write_text("{}\n", encoding="utf-8")
        for path in (
            root / "run_config.json", root / "sweep_summary_heavy_parent_v3.json",
            root / "COMPLETE.json", root / "commands.log",
            root / "heavy_parent_identity.json", root / "heavy_parent" / "scalar.json",
            root / "heavy_parent" / "decay_dose.json",
            root / "heavy_parent" / "scalar_reanalysis_bidirectional_v2.json",
            root / "stages" / "heavy_parent_u0.65_seed7.json",
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n", encoding="utf-8")
        layout_summary = {
            "heavy_parent": {"identity": {
                "weight_file_sha256": {"model.safetensors": "a" * 64},
                "support_file_sha256": {"config.json": "b" * 64},
            }},
            "gates": {"heavy_parent_selection_pass": False},
        }
        validate_exact_archive_layout(root, layout_summary, checkpoint)
        nested_manifest = root / "heavy_parent" / "MANIFEST.sha256"
        nested_manifest.write_text("alias\n", encoding="utf-8")
        expect_error(
            lambda: validate_exact_archive_layout(root, layout_summary, checkpoint),
            "nested manifest-name alias",
        )
        nested_manifest.unlink()
        (root / "unexpected_empty_alias").mkdir()
        expect_error(
            lambda: validate_exact_archive_layout(root, layout_summary, checkpoint),
            "extra empty archive directory",
        )

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary).resolve()
        checkpoint = root / "heavy_parent" / "checkpoint"
        checkpoint.mkdir(parents=True)
        (checkpoint / "model.safetensors").write_bytes(b"w")
        (checkpoint / "config.json").write_text("{}\n", encoding="utf-8")
        (checkpoint / "decay_dose.json").write_text("{}\n", encoding="utf-8")
        fixed_files = (
            root / "run_config.json", root / "sweep_summary_heavy_parent_v3.json",
            root / "COMPLETE.json", root / "commands.log",
            root / "heavy_parent_identity.json", root / "heavy_parent" / "scalar.json",
            root / "heavy_parent" / "decay_dose.json",
            root / "heavy_parent" / "scalar_reanalysis_bidirectional_v2.json",
            root / "stages" / "heavy_parent_u0.65_seed7.json",
        )
        for path in fixed_files:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n", encoding="utf-8")
        for u in INTERIOR_U:
            for seed in CHILD_SEEDS:
                tag = f"u{u:g}_seed{seed}"
                (root / "stages" / f"child_{tag}.json").write_text(
                    "{}\n", encoding="utf-8"
                )
                dose_dir = root / "sweep" / tag
                dose_dir.mkdir(parents=True)
                for name in (
                    "scalar.json", "decay_dose.json",
                    "scalar_reanalysis_bidirectional_v2.json",
                    "checkpoint_deletion.json",
                ):
                    (dose_dir / name).write_text("{}\n", encoding="utf-8")
        (root / "stages" / "child_u1_seed0.json").write_text(
            "{}\n", encoding="utf-8"
        )
        endpoint_dir = root / "sweep" / "u1_seed0"
        endpoint_dir.mkdir(parents=True)
        for name in (
            "scalar.json", "decay_dose.json",
            "scalar_reanalysis_bidirectional_v2.json",
            "checkpoint_deletion.json",
        ):
            (endpoint_dir / name).write_text("{}\n", encoding="utf-8")
        layout_summary = {
            "heavy_parent": {"identity": {
                "weight_file_sha256": {"model.safetensors": "a" * 64},
                "support_file_sha256": {"config.json": "b" * 64},
            }},
            "gates": {"heavy_parent_selection_pass": True},
        }
        validate_exact_archive_layout(root, layout_summary, checkpoint)
        (endpoint_dir / "checkpoint_deletion.json").unlink()
        expect_error(
            lambda: validate_exact_archive_layout(root, layout_summary, checkpoint),
            "passing archive missing endpoint deletion evidence",
        )

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        artifact = root / "artifact.json"
        artifact.write_text("{}\n", encoding="utf-8")
        (root / "MANIFEST.sha256.tmp").write_text("stale", encoding="utf-8")
        seal = write_manifest(root)
        assert seal["entry_count"] == 1 and verify_manifest(root)
        assert not (root / "MANIFEST.sha256.tmp").exists()
        artifact.write_text("changed\n", encoding="utf-8")
        expect_error(lambda: verify_manifest(root), "mutated exact manifest")
        (root / "extra").write_text("extra\n", encoding="utf-8")
        expect_error(lambda: verify_manifest(root), "unmanifested extra member")

    with tempfile.TemporaryDirectory() as temporary:
        repo = Path(temporary)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "heavy@example.invalid"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Heavy Test"], cwd=repo, check=True)
        for relative in EXECUTED_SOURCE_PATHS:
            path = repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# {relative}\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "sources"], cwd=repo, check=True)
        source = committed_source_identity(repo)
        validate_recorded_source_identity(repo, source["commit"], source["sha256"])
        (repo / "unrelated.txt").write_text("later\n", encoding="utf-8")
        subprocess.run(["git", "add", "unrelated.txt"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "later"], cwd=repo, check=True)
        validate_recorded_source_identity(repo, source["commit"], source["sha256"])
        bad = dict(source["sha256"])
        bad[EXECUTED_SOURCE_PATHS[0]] = "0" * 64
        expect_error(
            lambda: validate_recorded_source_identity(repo, source["commit"], bad),
            "forged committed source hash",
        )
        live = repo / EXECUTED_SOURCE_PATHS[0]
        live.write_text("# dirty\n", encoding="utf-8")
        expect_error(lambda: committed_source_identity(repo), "dirty executed source")

    print("Probe 2 v3 heavy-parent policy tests: PASS")


if __name__ == "__main__":
    main()
