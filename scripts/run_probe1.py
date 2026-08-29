"""Probe 1 driver: forget -> heal -> recheck on one concept, with gates.

Stage order (each stage skipped when its output exists, so the run resumes):
  1. compile the concept day (diversified training prompts + conjugate probes)
  2. build the filtered healing corpus
  3. pre-eval the parent: rehearsal eval, decay scalar, drift
  4. on-policy forget answers from the parent
  5. bounded-objective erasure with early stopping
  6. merge the erasure adapter
  7. post-forget: rehearsal eval + judge + conjugate probes + scalar + drift
  8. heal (retain-only LoRA r=16)
  9. merge the healing adapter
 10. post-heal: the same battery again
 11. gate verdicts, written as JSON and printed

Gates (SYNTHESIS section 7, probe 1):
  - forgetting: judge ABSENT on core and all required-neighbour groups
  - persistence: still ABSENT after healing, on both the original and the
    conjugate probes
  - repair: (post_forget - post_heal) / (post_forget - pre) >= 0.5 on the
    decay scalar
  - leakage: post_heal - pre scalar, recorded; > 1 point puts H4 in trouble
  - regime: PCA drift stays in the reversible band
"""

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from decay_scalar_normalization import (
    V2_POLICY,
    bidirectional_policy_fingerprint,
    load_bidirectional_anchors,
    normalise_components_bidirectional,
)
from run_noise_sweep import (
    validate_scalar_artifact,
)


CANONICAL_CERTIFICATION = {
    "concept_index": 21,
    "heal_steps": 60,
    "forget_steps": 120,
    "batch_size": 8,
    "max_new_tokens": 256,
    "seed": 0,
}
EXPECTED_FORGET_SNAPSHOT_STEPS = tuple(range(10, 121, 10))
CANONICAL_REPO_INPUTS = {
    "concepts": "data/rehearsal_concepts.json",
    "heal_corpus": "data/heal_corpus.json",
}
CANONICAL_CONCEPT_ID = "nightmares"
V3_PRIMARY_VERSION = "probe2_weight_noise_primary_certification_v3"
V3_CONTROLLER_U = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.75, 0.9, 1.0)
V3_INTERIOR_U = V3_CONTROLLER_U[1:-1]
V3_PILOT_ALPHA = {
    "A": (
        0.0, 0.0025, 0.005, 0.01, 0.02, 0.03, 0.04, 0.05, 0.055, 0.06,
        0.065, 0.07, 0.075, 0.08, 0.085, 0.09, 0.095, 0.1, 0.12, 1.0,
    ),
    "B": (
        0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5,
        0.55, 0.6, 0.7, 0.85, 1.0,
    ),
}
V3_MAPPING_SCHEMA = {
    "version": "probe2_v3_controller_mapping_v1",
    "coordinate": "u",
    "target_scalar": "100*u",
    "fit_ordinates": "raw_seed11_scalars_after_running_max",
    "interpolator": "run_noise_sweep.monotone_fritsch_carlson_pchip",
    "inverse": "leftmost_generalized_inverse_80_bisections",
    "physical_alpha_decimal_places": 8,
    "raw_point_provenance": (
        "reference artifact path+sha256, or seed11 scalar and dose-sidecar path+sha256"
    ),
    "fixed_endpoints": {"g(0)": 0.0, "g(1)": 1.0},
    "certification_u": list(V3_CONTROLLER_U),
    "heavy_parent_u": 0.65,
}


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-model", default="google/gemma-3-4b-it")
    parser.add_argument("--root", default="derisk/probe1_forget_heal")
    parser.add_argument("--concepts", default="data/rehearsal_concepts.json")
    parser.add_argument(
        "--concept-index",
        type=int,
        default=21,
        help="one-based index into the concept file (21 = nightmares)",
    )
    parser.add_argument(
        "--probe2-aggregate",
        default=(
            "derisk/probe2_noise_v2_heavy_parent/"
            "sweep_summary_heavy_parent_v2.json"
        ),
        help="final sealed Probe 2 aggregate; overall probe2_verdict must be PASS",
    )
    parser.add_argument(
        "--scalar-baseline",
        default="derisk/probe2_noise_v2/baseline/scalar.json",
        help="sealed Probe 2 v2 clean baseline",
    )
    parser.add_argument(
        "--scalar-anchor",
        default="derisk/probe2_noise_v2/anchor/scalar.json",
        help="sealed Probe 2 v2 alpha=1 token-salad endpoint",
    )
    parser.add_argument(
        "--scalar-ladder",
        default="derisk/probe2_noise_v2/ladder/corruption_ladder.json",
        help="sealed Probe 2 v2 dual-track ladder",
    )
    parser.add_argument("--heal-corpus", default="data/heal_corpus.json")
    parser.add_argument("--heal-steps", type=int, default=60)
    parser.add_argument("--forget-steps", type=int, default=120)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--skip-scalar",
        action="store_true",
        help="smoke only: skip scalar stages and force an INCOMPLETE verdict",
    )
    return parser.parse_args()


def read_json(path):
    return _require_finite_json(
        json.loads(
            Path(path).read_text(encoding="utf-8"),
            parse_constant=_reject_nonfinite_json_constant,
        ),
        str(Path(path)),
    )


def _reject_nonfinite_json_constant(value):
    raise RuntimeError(f"non-finite JSON constant is forbidden: {value}")


def _require_finite_json(value, label="JSON payload"):
    if isinstance(value, float) and not math.isfinite(value):
        raise RuntimeError(f"{label} contains a non-finite number")
    if isinstance(value, dict):
        for key, child in value.items():
            _require_finite_json(child, f"{label}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _require_finite_json(child, f"{label}[{index}]")
    return value


def write_json(path, payload):
    _require_finite_json(payload)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def sha256_of_file(path, chunk=1 << 20):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while block := handle.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def fingerprint(payload):
    _require_finite_json(payload)
    return hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


def paths_overlap(left, right):
    left = Path(left).resolve()
    right = Path(right).resolve()
    return left == right or left in right.parents or right in left.parents


def probe2_protected_roots(parent_model, aggregate_path, scalar_inputs, payload=None):
    roots = [Path(parent_model).resolve(), Path(aggregate_path).resolve().parent]
    roots.extend(path.resolve().parent.parent for path in scalar_inputs)
    if payload is not None:
        roots.append(Path(payload["primary_archive"]["root"]).resolve())
        if payload.get("certification_version") == (
            "probe2_weight_noise_heavy_certification_v3"
        ):
            roots.append(Path(payload["pilot_archive"]["root"]).resolve())
    return tuple(dict.fromkeys(roots))


def validate_certification_args(args):
    actual = {
        key: getattr(args, key) for key in CANONICAL_CERTIFICATION
    }
    if actual != CANONICAL_CERTIFICATION:
        raise ValueError(
            "Probe 1 certification configuration is frozen: "
            f"expected={CANONICAL_CERTIFICATION} actual={actual}"
        )


def validate_certification_inputs(args, repo, concept):
    repo = Path(repo).resolve()
    actual = {
        key: Path(getattr(args, key)).resolve()
        for key in CANONICAL_REPO_INPUTS
    }
    expected = {
        key: (repo / relative).resolve()
        for key, relative in CANONICAL_REPO_INPUTS.items()
    }
    if actual != expected:
        raise ValueError(
            "Probe 1 certification inputs are frozen to repository canonical "
            f"paths: expected={expected} actual={actual}"
        )
    if concept.get("id") != CANONICAL_CONCEPT_ID:
        raise ValueError(
            "Probe 1 certification concept must be "
            f"{CANONICAL_CONCEPT_ID!r}, found {concept.get('id')!r}"
        )


def validate_heal_trainer_config(payload, model_id, heal_data, output_dir):
    expected = {
        "model_id": str(model_id),
        "tokenizer_model": None,
        "heal_data": str(heal_data),
        "output_dir": str(output_dir),
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
    }
    projection = {key: payload.get(key) for key in expected}
    if projection != expected:
        raise RuntimeError("healing trainer configuration mismatch")
    return expected


def validate_forget_snapshot_grid(adapter_root, stop_state):
    adapter_root = Path(adapter_root).resolve()
    actual = []
    for path in adapter_root.glob("step*"):
        match = re.fullmatch(r"step(\d+)", path.name)
        if match and path.is_dir():
            actual.append(int(match.group(1)))
    actual.sort()
    if tuple(actual) != EXPECTED_FORGET_SNAPSHOT_STEPS:
        raise RuntimeError(
            "forget snapshot grid mismatch: "
            f"expected={EXPECTED_FORGET_SNAPSHOT_STEPS} actual={tuple(actual)}"
        )
    expected_final = adapter_root / "step120"
    if (
        stop_state.get("external_semantic_selection") is not True
        or stop_state.get("stopped_at_step") != 120
        or stop_state.get("stop_reason") != "step_budget_exhausted"
        or Path(stop_state.get("final_adapter", "")).resolve() != expected_final
    ):
        raise RuntimeError("forget trainer terminal state is not the frozen full grid")
    return [(step, adapter_root / f"step{step:03d}") for step in actual]


def model_file_hashes(model_dir):
    model_dir = Path(model_dir)
    files = sorted(
        path
        for path in model_dir.iterdir()
        if path.is_file() and path.name != "decay_dose.json"
    )
    if not files:
        raise RuntimeError(f"model directory has no files: {model_dir}")
    return {path.name: sha256_of_file(path) for path in files}


def split_model_file_hashes(files):
    weights = {
        name: digest
        for name, digest in files.items()
        if Path(name).suffix in {".safetensors", ".bin"}
    }
    if not weights:
        raise RuntimeError("model identity contains no weight files")
    support = {
        name: digest
        for name, digest in files.items()
        if Path(name).suffix not in {".safetensors", ".bin"}
    }
    return weights, support


def tree_file_hashes(root, exclude_names=()):
    root = Path(root)
    excluded = set(exclude_names)
    return {
        path.relative_to(root).as_posix(): sha256_of_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name not in excluded
    }


def hash_paths(paths):
    return {str(Path(path)): sha256_of_file(path) for path in paths}


def overall_probe2_verdict(payload):
    direct = payload.get("probe2_verdict")
    nested = payload.get("gates", {}).get("probe2_verdict")
    if direct is not None and nested is not None and direct != nested:
        raise RuntimeError("Probe 2 aggregate contains conflicting verdict fields")
    return direct if direct is not None else nested


def verify_archive(root):
    """Verify exact coverage and hashes for a manifest-sealed archive."""
    root = Path(root).resolve()
    manifest = root / "MANIFEST.sha256"
    if not manifest.is_file():
        raise RuntimeError(f"Probe 2 archive is not sealed: {root}")
    entries = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, separator, relative = line.partition("  ")
        relative_path = Path(relative)
        if (
            not separator
            or len(digest) != 64
            or relative_path.is_absolute()
            or ".." in relative_path.parts
        ):
            raise RuntimeError(f"malformed Probe 2 manifest line: {line!r}")
        try:
            int(digest, 16)
        except ValueError as error:
            raise RuntimeError(
                f"malformed Probe 2 manifest digest: {digest!r}"
            ) from error
        key = relative_path.as_posix()
        if key in entries:
            raise RuntimeError(f"duplicate Probe 2 manifest entry: {key}")
        entries[key] = digest.lower()
    actual_files = {
        candidate.relative_to(root).as_posix(): candidate
        for candidate in root.rglob("*")
        if candidate.is_file() and candidate != manifest
    }
    if set(entries) != set(actual_files):
        raise RuntimeError("Probe 2 manifest does not exactly cover its archive")
    for relative, expected in entries.items():
        if sha256_of_file(actual_files[relative]) != expected:
            raise RuntimeError(f"Probe 2 manifest hash mismatch: {relative}")
    return {
        "manifest_path": str(manifest),
        "manifest_sha256": sha256_of_file(manifest),
        "entry_count": len(entries),
        "entries": entries,
    }


def verify_sealed_member(path):
    """Require *path* to be covered by an exact, valid archive manifest."""
    path = Path(path).resolve()
    seal = verify_archive(path.parent)
    relative = path.relative_to(path.parent).as_posix()
    if relative not in seal["entries"]:
        raise RuntimeError("Probe 2 aggregate is not covered by its manifest")
    return {key: value for key, value in seal.items() if key != "entries"}


def _validate_probe2_v2_aggregate(
    path, expected_policy, parent_model, scalar_inputs
):
    seal = verify_sealed_member(path)
    payload = read_json(path)
    if overall_probe2_verdict(payload) != "PASS":
        raise RuntimeError("Probe 1 requires final overall Probe 2 PASS")
    if payload.get("certification_scope") != (
        "heavy_parent_repeat_and_probe2_aggregate"
    ):
        raise RuntimeError("only the final two-parent Probe 2 aggregate is valid")
    gates = payload.get("gates", {})
    for gate in (
        "primary_manifest_verified",
        "primary_verdict_verified",
    ):
        if gates.get(gate) is not True:
            raise RuntimeError(f"Probe 2 aggregate did not establish {gate}")
    if gates.get("heavy_verdict") != "PASS":
        raise RuntimeError("Probe 2 aggregate heavy-parent verdict is not PASS")
    if gates.get("heavy_parent_selection_pass") is not True:
        raise RuntimeError("Probe 2 aggregate heavy-parent selection did not pass")
    if payload.get("normalisation_version") != V2_POLICY:
        raise RuntimeError("Probe 2 aggregate is not bidirectional v2")
    if payload.get("normalisation_policy_fingerprint") != expected_policy:
        raise RuntimeError("Probe 2 aggregate/pinned scalar policy mismatch")
    clean_ruler = payload.get("clean_ruler", {})
    if clean_ruler.get("policy_fingerprint") != expected_policy:
        raise RuntimeError("Probe 2 clean-ruler policy fingerprint mismatch")
    identity = payload.get("primary_archive", {})
    scalar_paths = tuple(Path(value).resolve() for value in scalar_inputs)
    primary_roots = {value.parent.parent for value in scalar_paths}
    if len(primary_roots) != 1:
        raise RuntimeError("Probe 2 scalar ruler files are not in one primary archive")
    primary_root = primary_roots.pop()
    primary_seal = verify_archive(primary_root)
    if Path(identity.get("root", "")).resolve() != primary_root:
        raise RuntimeError("Probe 2 aggregate references a different primary root")
    if identity.get("manifest_sha256") != primary_seal["manifest_sha256"]:
        raise RuntimeError("Probe 2 aggregate references a different primary seal")
    for label, scalar_path in zip(
        ("baseline", "terminal", "ladder"), scalar_paths
    ):
        relative = scalar_path.relative_to(primary_root).as_posix()
        if (
            relative not in primary_seal["entries"]
            or clean_ruler.get(label) != sha256_of_file(scalar_path)
        ):
            raise RuntimeError(f"Probe 2 {label} ruler provenance mismatch")
    for label, filename in (
        ("summary_sha256", "sweep_summary_bidirectional_v2.json"),
        ("run_config_sha256", "run_config.json"),
        ("parent_identity_sha256", "parent_identity.json"),
    ):
        primary_path = primary_root / filename
        if not primary_path.is_file() or identity.get(label) != sha256_of_file(
            primary_path
        ):
            raise RuntimeError(f"Probe 2 primary {filename} provenance mismatch")
    primary_summary = read_json(primary_root / "sweep_summary_bidirectional_v2.json")
    primary_config = read_json(primary_root / "run_config.json")
    primary_identity = read_json(primary_root / "parent_identity.json")
    if (
        primary_summary.get("certification_scope") != "clean_parent_primary_only"
        or primary_summary.get("gates", {}).get("primary_verdict") != "PASS"
        or primary_summary.get("gates", {}).get("probe2_verdict")
        != "INCOMPLETE_PENDING_HEAVY_PARENT"
        or primary_summary.get("normalisation_version") != V2_POLICY
        or primary_summary.get("normalisation_policy_fingerprint")
        != expected_policy
    ):
        raise RuntimeError("sealed Probe 2 primary record is not the certified PASS")
    clean_identity = payload.get("clean_parent_identity")
    # The aggregate summary currently carries the clean identity through its
    # run configuration rather than duplicating it at the top level.  The
    # primary summary reference is not sufficient: Probe 1 must bind to the
    # exact clean bytes that established the ruler.
    if clean_identity is None:
        run_config_path = Path(path).resolve().parent / "run_config.json"
        run_config = read_json(run_config_path)
        clean_identity = run_config.get("clean_parent_identity")
    if not isinstance(clean_identity, dict):
        raise RuntimeError("Probe 2 aggregate lacks the clean-parent identity")
    recorded_fingerprint = clean_identity.get("fingerprint")
    identity_body = {
        key: value for key, value in clean_identity.items() if key != "fingerprint"
    }
    if recorded_fingerprint != fingerprint(identity_body):
        raise RuntimeError("Probe 2 clean-parent identity fingerprint is invalid")
    parent_model = Path(parent_model).resolve()
    if Path(clean_identity.get("source_model", "")).resolve() != parent_model:
        raise RuntimeError("Probe 1 parent path differs from Probe 2 clean parent")
    if (
        primary_identity != clean_identity
        or Path(primary_summary.get("parent_model", "")).resolve() != parent_model
        or Path(primary_config.get("parent_model", "")).resolve() != parent_model
    ):
        raise RuntimeError("Probe 2 primary clean-parent provenance conflicts")
    recorded_files = {
        **clean_identity.get("weight_file_sha256", {}),
        **clean_identity.get("support_file_sha256", {}),
    }
    if recorded_files != model_file_hashes(parent_model):
        raise RuntimeError("Probe 1 parent bytes differ from Probe 2 clean parent")
    primary_identity_fingerprint = identity.get("parent_identity_sha256")
    if not primary_identity_fingerprint:
        raise RuntimeError("Probe 2 aggregate lacks primary-identity provenance")
    payload["_verified_archive"] = seal
    payload["_verified_primary_archive"] = {
        key: value for key, value in primary_seal.items() if key != "entries"
    }
    payload["_verified_parent_model_files"] = recorded_files
    return payload


def _required_archive_member(root, value, digest, label):
    root = Path(root).resolve()
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"Probe 2 lacks {label} path provenance")
    member = Path(value).resolve()
    try:
        member.relative_to(root)
    except ValueError as error:
        raise RuntimeError(f"Probe 2 {label} is outside its sealed archive") from error
    if not member.is_file() or sha256_of_file(member) != digest:
        raise RuntimeError(f"Probe 2 {label} hash provenance mismatch")
    return member


def _curve_records(curve):
    if isinstance(curve, list):
        records = curve
    elif isinstance(curve, dict):
        records = []
        for key, value in curve.items():
            if not isinstance(value, dict):
                raise RuntimeError("Probe 2 v3 primary curve contains a malformed dose")
            record = dict(value)
            record.setdefault("u", float(key))
            records.append(record)
    else:
        raise RuntimeError("Probe 2 v3 primary curve is malformed")
    if any(not isinstance(record, dict) for record in records):
        raise RuntimeError("Probe 2 v3 primary curve contains a malformed dose")
    return sorted(records, key=lambda record: float(record.get("u", -1.0)))


def _validate_v3_mapping(mapping, mapping_record, pilot_summary):
    _require_finite_json(mapping, "Probe 2 v3 controller mapping")
    _require_finite_json(mapping_record, "Probe 2 v3 mapping descriptor")
    _require_finite_json(pilot_summary, "Probe 2 v3 pilot summary")
    mapping_body = {key: value for key, value in mapping.items() if key != "fingerprint"}
    schema = mapping.get("schema", {})
    if (
        set(mapping)
        != {
            "schema", "schema_sha256", "source_arm", "beta", "seed_used_to_fit",
            "raw_points", "fit_points", "controller", "heavy_parent", "fingerprint",
        }
        or mapping.get("fingerprint") != fingerprint(mapping_body)
        or mapping.get("schema_sha256") != fingerprint(schema)
        or schema != V3_MAPPING_SCHEMA
        or mapping_record.get("fingerprint") != mapping.get("fingerprint")
        or mapping_record.get("schema_sha256") != mapping.get("schema_sha256")
        or pilot_summary.get("controller_mapping_fingerprint")
        != mapping.get("fingerprint")
        or pilot_summary.get("controller_mapping_schema_sha256")
        != mapping.get("schema_sha256")
    ):
        raise RuntimeError("Probe 2 v3 controller mapping linkage is invalid")
    if mapping.get("seed_used_to_fit") != 11 or mapping.get("source_arm") not in {
        "A", "B"
    }:
        raise RuntimeError("Probe 2 v3 controller mapping lacks the frozen pilot identity")
    beta = mapping.get("beta")
    expected_outcome = f"PROMOTE_ARM_{mapping['source_arm']}"
    if (
        beta != ({"A": 1.0, "B": 0.1}[mapping["source_arm"]])
        or pilot_summary.get("outcome") != expected_outcome
        or pilot_summary.get("explicitly_not_a_pass_verdict") is not True
    ):
        raise RuntimeError("Probe 2 v3 pilot promotion/beta linkage is invalid")
    raw_points = mapping.get("raw_points")
    fit_points = mapping.get("fit_points")
    expected_pilot_alpha = V3_PILOT_ALPHA[mapping["source_arm"]]
    raw_scalars = (
        [float(record.get("raw_scalar")) for record in raw_points]
        if isinstance(raw_points, list)
        else []
    )
    fitted_scalars = (
        [float(record.get("isotonic_scalar")) for record in fit_points]
        if isinstance(fit_points, list)
        else []
    )
    running_max = []
    for value in raw_scalars:
        running_max.append(max(value, running_max[-1]) if running_max else value)
    raw_schema_valid = isinstance(raw_points, list)
    if raw_schema_valid:
        for record, alpha in zip(raw_points, expected_pilot_alpha):
            if not isinstance(record, dict):
                raw_schema_valid = False
                break
            scheduled = not (
                alpha == 0.0 or (mapping["source_arm"] == "A" and alpha == 1.0)
            )
            base_keys = {
                "physical_alpha", "raw_scalar", "seed", "scheduled",
                "historical_seed_exception",
            }
            expected_keys = base_keys | (
                {"scalar_artifact", "dose_sidecar"}
                if scheduled
                else {"reference_artifact", "reference"}
            )
            pointers = (
                (record.get("scalar_artifact"), record.get("dose_sidecar"))
                if scheduled
                else (record.get("reference_artifact"),)
            )
            pointer_valid = all(
                isinstance(pointer, dict)
                and set(pointer) == {"path", "sha256"}
                and isinstance(pointer.get("path"), str)
                and bool(pointer["path"])
                and isinstance(pointer.get("sha256"), str)
                and len(pointer["sha256"]) == 64
                and all(character in "0123456789abcdef" for character in pointer["sha256"])
                for pointer in pointers
            )
            expected_seed = 11 if scheduled else (0 if alpha == 1.0 else None)
            if (
                set(record) != expected_keys
                or record.get("scheduled") is not scheduled
                or record.get("historical_seed_exception") is scheduled
                or record.get("seed") != expected_seed
                or not pointer_valid
                or (not scheduled and not isinstance(record.get("reference"), str))
            ):
                raw_schema_valid = False
                break
    fit_schema_valid = (
        isinstance(fit_points, list)
        and all(
            isinstance(record, dict)
            and set(record) == {"physical_alpha", "isotonic_scalar"}
            for record in fit_points
        )
    )
    if (
        not isinstance(raw_points, list)
        or not isinstance(fit_points, list)
        or not raw_schema_valid
        or not fit_schema_valid
        or tuple(float(record.get("physical_alpha")) for record in raw_points)
        != expected_pilot_alpha
        or tuple(float(record.get("physical_alpha")) for record in fit_points)
        != expected_pilot_alpha
        or not all(math.isfinite(value) for value in raw_scalars)
        or not all(math.isfinite(value) for value in fitted_scalars)
        or any(
            abs(expected - actual) > 1e-12
            for expected, actual in zip(running_max, fitted_scalars)
        )
        or any(
            right + 1e-12 < left
            for left, right in zip(
                fitted_scalars,
                fitted_scalars[1:],
            )
        )
    ):
        raise RuntimeError("Probe 2 v3 mapping does not preserve the frozen pilot fit")
    controller = mapping.get("controller")
    controller_alphas = (
        [record.get("physical_alpha") for record in controller]
        if isinstance(controller, list)
        else []
    )
    if (
        not isinstance(controller, list)
        or any(not isinstance(record, dict) for record in controller)
        or any(
            set(record) != {"u", "target_scalar", "physical_alpha"}
            for record in controller
        )
        or [record.get("u") for record in controller] != list(V3_CONTROLLER_U)
        or any(
            isinstance(value, bool) or not isinstance(value, (int, float))
            for record in controller
            for value in (
                record.get("u"),
                record.get("target_scalar"),
                record.get("physical_alpha"),
            )
        )
        or any(
            record.get("target_scalar") != 100.0 * record["u"]
            for record in controller
        )
        or controller[0].get("physical_alpha") != 0.0
        or controller[-1].get("physical_alpha") != 1.0
        or any(
            not 0.0 < record.get("physical_alpha") < 1.0
            for record in controller[1:-1]
        )
        or any(round(float(value), 8) != value for value in controller_alphas)
        or any(
            right <= left
            for left, right in zip(controller_alphas, controller_alphas[1:])
        )
        or len({record["physical_alpha"] for record in controller[1:-1]})
        != len(V3_INTERIOR_U)
    ):
        raise RuntimeError("Probe 2 v3 controller u grid is invalid")
    heavy = mapping.get("heavy_parent", {})
    heavy_alpha = heavy.get("physical_alpha")
    if (
        not isinstance(heavy, dict)
        or set(heavy) != {"u", "target_scalar", "physical_alpha"}
        or heavy.get("u") != 0.65
        or heavy.get("target_scalar") != 65.0
        or any(
            isinstance(value, bool) or not isinstance(value, (int, float))
            for value in (heavy.get("u"), heavy.get("target_scalar"), heavy_alpha)
        )
        or not 0.0 < heavy_alpha < 1.0
        or round(float(heavy_alpha), 8) != heavy_alpha
        or not controller_alphas[6] < heavy_alpha < controller_alphas[7]
    ):
        raise RuntimeError("Probe 2 v3 mapping lacks g(.65)")
    return float(beta)


def _validate_v3_curve(summary, expected_alpha, label):
    _require_finite_json(summary, f"Probe 2 v3 {label} summary")
    gates = summary.get("gates", {})
    curve = _curve_records(summary.get("curve"))
    if tuple(float(record.get("u")) for record in curve) != V3_INTERIOR_U:
        raise RuntimeError(f"Probe 2 v3 {label} curve does not use the frozen u grid")
    ranges = {}
    for record in curve:
        u = float(record["u"])
        seeds = record.get("per_seed")
        scalars = [float(item.get("scalar")) for item in seeds or ()]
        if (
            not isinstance(seeds, list)
            or [item.get("seed") for item in seeds] != [0, 1, 2]
            or len(scalars) != 3
            or not all(math.isfinite(value) for value in scalars)
            or max(scalars) - min(scalars) > 6.0 + 1e-12
            or abs(float(record.get("raw_range")) - (max(scalars) - min(scalars)))
            > 1e-9
            or abs(float(record.get("mean")) - sum(scalars) / 3.0) > 1e-9
            or abs(float(record.get("physical_alpha")) - expected_alpha[u]) > 1e-12
        ):
            raise RuntimeError(f"Probe 2 v3 {label} range/provenance failed at u={u}")
        ranges[str(u)] = float(record["raw_range"])
    recorded_ranges = {
        str(float(key)): float(value)
        for key, value in gates.get("per_dose_raw_ranges", {}).items()
    }
    if recorded_ranges != ranges:
        raise RuntimeError(f"Probe 2 v3 {label} per-dose range gate is inconsistent")
    endpoints = summary.get("endpoints", {})
    endpoint_records = list(endpoints.values()) if isinstance(endpoints, dict) else []
    if label == "heavy" and not endpoint_records:
        measurement = summary.get("heavy_parent", {}).get("measurement", {})
        terminal = summary.get("incremental_alpha1_endpoint", {})
        if (
            measurement.get("seed") != 7
            or float(measurement.get("controller_u", -1.0)) != 0.65
            or terminal.get("seed") != 0
            or float(terminal.get("controller_u", -1.0)) != 1.0
        ):
            raise RuntimeError("Probe 2 v3 heavy endpoint supports are malformed")
        endpoint_means = [float(measurement["scalar"]), float(terminal["scalar"])]
    else:
        endpoint_records.sort(key=lambda record: float(record.get("u", -1.0)))
        if (
            len(endpoint_records) != 2
            or [float(record.get("u")) for record in endpoint_records] != [0.0, 1.0]
            or any(record.get("support") is not True for record in endpoint_records)
        ):
            raise RuntimeError(f"Probe 2 v3 {label} endpoint supports are malformed")
        endpoint_means = [
            float(endpoint_records[0]["mean"]),
            float(endpoint_records[1]["mean"]),
        ]
    if not all(math.isfinite(value) for value in endpoint_means):
        raise RuntimeError(f"Probe 2 v3 {label} endpoint scalars are non-finite")
    means = [endpoint_means[0]]
    means.extend(float(record["mean"]) for record in curve)
    means.append(endpoint_means[1])
    if (
        any(right + 1e-12 < left for left, right in zip(means, means[1:]))
        or gates.get("curve_raw_means_nondecreasing") is not True
        or gates.get("raw_mean_nondecrease_gate_pass") is not True
        or gates.get("per_dose_range_gate_pass") is not True
        or gates.get("ladder_gate_pass") is not True
        or not isinstance(gates.get("ladder_component_pass"), dict)
        or set(gates["ladder_component_pass"]) != {"R", "D", "J", "F"}
        or not all(gates["ladder_component_pass"].values())
    ):
        raise RuntimeError(f"Probe 2 v3 {label} raw-monotone/range/ladder gates failed")


def _validate_v3_primary(primary_summary, expected_policy, mapping, beta):
    _require_finite_json(primary_summary, "Probe 2 v3 primary summary")
    gates = primary_summary.get("gates", {})
    if (
        primary_summary.get("certification_version") != V3_PRIMARY_VERSION
        or primary_summary.get("certification_scope") != "clean_parent_primary_only"
        or primary_summary.get("normalisation_version") != V2_POLICY
        or primary_summary.get("normalisation_policy_fingerprint") != expected_policy
        or float(primary_summary.get("beta", -1.0)) != beta
        or primary_summary.get("controller_coordinate") != "u"
        or tuple(float(value) for value in primary_summary.get("controller_u", ()))
        != V3_CONTROLLER_U
        or primary_summary.get("controller_mapping", {}).get("fingerprint")
        != mapping.get("fingerprint")
        or gates.get("primary_verdict") != "PASS"
        or gates.get("probe2_verdict") != "INCOMPLETE_PENDING_HEAVY_PARENT"
        or gates.get("per_dose_range_gate_pass") is not True
        or gates.get("raw_mean_nondecrease_gate_pass") is not True
        or gates.get("ladder_gate_pass") is not True
        or gates.get("no_refit_bisection_or_extra_points") is not True
    ):
        raise RuntimeError("sealed Probe 2 v3 primary record is not the certified PASS")
    controller = mapping["controller"]
    expected_alpha = {
        float(record["u"]): float(record["physical_alpha"]) for record in controller
    }
    recorded_alpha = {
        float(key): float(value)
        for key, value in primary_summary.get("physical_alpha_by_u", {}).items()
    }
    if recorded_alpha != expected_alpha:
        raise RuntimeError("Probe 2 v3 primary changed the frozen controller mapping")
    _validate_v3_curve(primary_summary, expected_alpha, "primary")


def _validate_v3_producer_archive(path):
    """Make the current Probe 2 v3 producer the archive-contract authority."""
    from run_noise_heavy_v3 import SUMMARY_NAME, validate_sealed_heavy

    path = Path(path).resolve()
    expected = path.parent / SUMMARY_NAME
    if path != expected:
        raise RuntimeError(
            f"Probe 2 v3 aggregate is not the canonical producer summary: {path}"
        )
    try:
        bundle = validate_sealed_heavy(path.parent)
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        raise RuntimeError(
            "Probe 2 v3 aggregate failed the producer's sealed-archive validator"
        ) from error
    if bundle is None:
        raise RuntimeError("Probe 2 v3 aggregate is not a sealed producer archive")
    if bundle.get("summary") != read_json(path):
        raise RuntimeError("Probe 2 v3 producer summary changed after validation")
    return bundle


def _validate_probe2_v3_aggregate(path, expected_policy, parent_model, scalar_inputs):
    producer = _validate_v3_producer_archive(path)
    seal = verify_sealed_member(path)
    payload = read_json(path)
    gates = payload.get("gates", {})
    if (
        set(payload)
        != {
            "certification_version", "certification_scope", "primary_archive",
            "pilot_archive", "clean_ruler", "normalisation_version",
            "normalisation_policy_fingerprint", "beta", "controller_mapping",
            "controller_coordinate", "controller_u", "physical_alpha_by_u",
            "heavy_parent", "incremental_alpha1_endpoint", "curve", "gates",
        }
        or overall_probe2_verdict(payload) != "PASS"
        or payload.get("certification_version")
        != "probe2_weight_noise_heavy_certification_v3"
        or payload.get("certification_scope")
        != "heavy_parent_repeat_and_probe2_aggregate"
        or payload.get("normalisation_version") != V2_POLICY
        or payload.get("normalisation_policy_fingerprint") != expected_policy
        or gates.get("primary_manifest_verified") is not True
        or gates.get("primary_verdict_verified") is not True
        or gates.get("heavy_parent_selection_pass") is not True
        or gates.get("heavy_verdict") != "PASS"
    ):
        raise RuntimeError("Probe 1 requires a final certified Probe 2 v3 PASS")

    scalar_paths = tuple(Path(value).resolve() for value in scalar_inputs)
    recorded_ruler_paths = producer.get("config", {}).get("clean_ruler_paths", {})
    expected_scalar_paths = tuple(
        Path(recorded_ruler_paths.get(key, "")).resolve()
        for key in ("baseline", "normalisation_anchor", "ladder")
    )
    if scalar_paths != expected_scalar_paths:
        raise RuntimeError(
            "Probe 2 v3 consumer ruler paths differ from the producer-sealed ruler"
        )
    ruler_roots = {value.parent.parent for value in scalar_paths}
    if len(ruler_roots) != 1:
        raise RuntimeError("Probe 2 scalar ruler files are not in one v2 archive")
    ruler_root = ruler_roots.pop()
    ruler_seal = verify_archive(ruler_root)
    clean_ruler = payload.get("clean_ruler", {})
    if clean_ruler.get("policy_fingerprint") != expected_policy:
        raise RuntimeError("Probe 2 clean-ruler policy fingerprint mismatch")
    for label, scalar_path in zip(
        ("baseline", "normalisation_anchor", "ladder"), scalar_paths
    ):
        if (
            scalar_path.relative_to(ruler_root).as_posix() not in ruler_seal["entries"]
            or clean_ruler.get(label) != sha256_of_file(scalar_path)
        ):
            raise RuntimeError(f"Probe 2 {label} ruler provenance mismatch")

    primary_record = payload.get("primary_archive", {})
    primary_root = Path(primary_record.get("root", "")).resolve()
    pilot_root = Path(payload.get("pilot_archive", {}).get("root", "")).resolve()
    aggregate_root = Path(path).resolve().parent
    archive_roots = {
        "aggregate": aggregate_root,
        "primary": primary_root,
        "pilot": pilot_root,
        "clean v2 ruler": ruler_root,
        "clean parent": Path(parent_model).resolve(),
    }
    for left_label, left in archive_roots.items():
        for right_label, right in archive_roots.items():
            if left_label < right_label and paths_overlap(left, right):
                raise RuntimeError(
                    f"Probe 2 v3 {left_label} and {right_label} archives overlap"
                )
    primary_seal = verify_archive(primary_root)
    if primary_record.get("manifest_sha256") != primary_seal["manifest_sha256"]:
        raise RuntimeError("Probe 2 v3 aggregate references a different primary seal")
    primary_summary_path = primary_root / "primary_summary_v3.json"
    primary_config_path = primary_root / "run_config.json"
    primary_identity_path = primary_root / "parent_identity.json"
    for label, member in (
        ("summary_sha256", primary_summary_path),
        ("run_config_sha256", primary_config_path),
        ("parent_identity_sha256", primary_identity_path),
    ):
        if not member.is_file() or primary_record.get(label) != sha256_of_file(member):
            raise RuntimeError(f"Probe 2 v3 primary {member.name} provenance mismatch")
    primary_summary = read_json(primary_summary_path)
    primary_self = primary_summary.get("primary_archive", {})
    if (
        Path(primary_self.get("root", "")).resolve() != primary_root
        or Path(primary_self.get("run_config", "")).resolve() != primary_config_path
        or Path(primary_self.get("summary", "")).resolve() != primary_summary_path
        or Path(primary_self.get("manifest", "")).resolve()
        != (primary_root / "MANIFEST.sha256")
    ):
        raise RuntimeError("Probe 2 v3 primary self-linkage changed")

    pilot_record = primary_summary.get("pilot_archive", {})
    pilot_root = Path(pilot_record.get("root", "")).resolve()
    pilot_seal = verify_archive(pilot_root)
    if pilot_record.get("manifest_sha256") != pilot_seal["manifest_sha256"]:
        raise RuntimeError("Probe 2 v3 primary references a different pilot seal")
    pilot_summary_path = _required_archive_member(
        pilot_root,
        pilot_record.get("summary"),
        pilot_record.get("summary_sha256"),
        "pilot summary",
    )
    pilot_summary = read_json(pilot_summary_path)
    mapping_record = primary_summary.get("controller_mapping", {})
    mapping_path = _required_archive_member(
        pilot_root,
        mapping_record.get("path"),
        mapping_record.get("sha256"),
        "controller mapping",
    )
    mapping = read_json(mapping_path)
    if (
        pilot_summary.get("controller_mapping") != str(mapping_path)
        or pilot_summary.get("controller_mapping_sha256") != sha256_of_file(mapping_path)
        or pilot_record.get("outcome") != pilot_summary.get("outcome")
    ):
        raise RuntimeError("Probe 2 v3 pilot/mapping pointer linkage is invalid")
    beta = _validate_v3_mapping(mapping, mapping_record, pilot_summary)
    _validate_v3_primary(primary_summary, expected_policy, mapping, beta)
    if primary_summary.get("clean_ruler") != clean_ruler:
        raise RuntimeError("Probe 2 v3 primary/aggregate clean-ruler linkage changed")
    expected_alpha = {
        float(record["u"]): float(record["physical_alpha"])
        for record in mapping["controller"]
    }
    aggregate_alpha = {
        float(key): float(value)
        for key, value in payload.get("physical_alpha_by_u", {}).items()
    }
    if (
        float(payload.get("beta", -1.0)) != beta
        or payload.get("controller_coordinate") != "u"
        or tuple(float(value) for value in payload.get("controller_u", ()))
        != V3_CONTROLLER_U
        or aggregate_alpha != expected_alpha
        or payload.get("controller_mapping") != mapping_record
        or payload.get("pilot_archive") != pilot_record
        or gates.get("no_refit_bisection_or_extra_points") is not True
    ):
        raise RuntimeError("Probe 2 v3 aggregate controller/pilot linkage changed")
    _validate_v3_curve(payload, expected_alpha, "heavy")
    heavy_identity = payload.get("heavy_parent", {}).get("identity", {})
    identity_body = {
        key: value for key, value in heavy_identity.items() if key != "fingerprint"
    }
    mapping_heavy = mapping["heavy_parent"]
    heavy_measurement = payload.get("heavy_parent", {}).get("measurement", {})
    if (
        heavy_identity.get("fingerprint") != fingerprint(identity_body)
        or heavy_identity.get("dose_seed") != 7
        or float(heavy_identity.get("controller_u", -1.0)) != 0.65
        or float(heavy_identity.get("beta", -1.0)) != beta
        or heavy_identity.get("mapping_fingerprint") != mapping.get("fingerprint")
        or heavy_identity.get("construction") != "one_shot_no_search"
        or abs(
            float(heavy_identity.get("administered_alpha", -1.0))
            - float(mapping_heavy["physical_alpha"])
        )
        > 1e-12
        or not 60.0 <= float(heavy_identity.get("measured_global_scalar", -1.0)) <= 70.0
        or abs(
            float(heavy_identity.get("measured_global_scalar", -1.0))
            - float(heavy_measurement.get("scalar", -2.0))
        )
        > 1e-9
    ):
        raise RuntimeError("Probe 2 v3 heavy parent controller identity is invalid")

    primary_identity = read_json(primary_identity_path)
    primary_config = read_json(primary_config_path)
    clean_identity = payload.get("clean_parent_identity", primary_identity)
    identity_body = {
        key: value for key, value in clean_identity.items() if key != "fingerprint"
    }
    parent_model = Path(parent_model).resolve()
    if (
        clean_identity.get("fingerprint") != fingerprint(identity_body)
        or primary_identity != clean_identity
        or Path(clean_identity.get("source_model", "")).resolve() != parent_model
        or Path(primary_summary.get("parent_model", "")).resolve() != parent_model
        or primary_config.get("clean_parent_identity") != clean_identity
    ):
        raise RuntimeError("Probe 2 v3 clean-parent identity linkage conflicts")
    recorded_files = {
        **clean_identity.get("weight_file_sha256", {}),
        **clean_identity.get("support_file_sha256", {}),
    }
    if recorded_files != model_file_hashes(parent_model):
        raise RuntimeError("Probe 1 parent bytes differ from Probe 2 clean parent")
    payload["_verified_archive"] = seal
    payload["_verified_primary_archive"] = {
        key: value for key, value in primary_seal.items() if key != "entries"
    }
    payload["_verified_ruler_archive"] = {
        key: value for key, value in ruler_seal.items() if key != "entries"
    }
    payload["_verified_controller_mapping"] = mapping
    payload["_verified_parent_model_files"] = recorded_files
    return payload


def validate_probe2_aggregate(path, expected_policy, parent_model, scalar_inputs):
    """Accept the legacy v2 aggregate or the controller-based v3 aggregate."""
    payload = read_json(path)
    if payload.get("certification_version") == (
        "probe2_weight_noise_heavy_certification_v3"
    ):
        return _validate_probe2_v3_aggregate(
            path, expected_policy, parent_model, scalar_inputs
        )
    return _validate_probe2_v2_aggregate(
        path, expected_policy, parent_model, scalar_inputs
    )


def all_group_verdicts(judgement, expected, expected_group_ids):
    groups = judgement.get("groups", {})
    return set(groups) == set(expected_group_ids) and all(
        result.get("verdict") == expected for result in groups.values()
    )


def validate_judgement_payload(
    judgement, expected_judge_model, expected_concept_id, expected_group_ids
):
    judge_model = judgement.get("judge_model")
    if not judge_model or Path(judge_model).resolve() != Path(
        expected_judge_model
    ).resolve():
        raise RuntimeError("semantic judgement judge identity mismatch")
    if judgement.get("concept_id") != expected_concept_id:
        raise RuntimeError("semantic judgement concept identity mismatch")
    groups = judgement.get("groups", {})
    if set(groups) != set(expected_group_ids):
        raise RuntimeError("semantic judgement group coverage mismatch")
    for group_id, result in groups.items():
        if result.get("verdict") not in {"PRESENT", "ABSENT", "UNCLEAR"}:
            raise RuntimeError(
                f"invalid semantic verdict for group {group_id}: "
                f"{result.get('verdict')!r}"
            )
        if result.get("responses", 0) <= 0:
            raise RuntimeError(f"semantic group {group_id} has no judged responses")
    return {
        group_id: result["verdict"] for group_id, result in groups.items()
    }


def semantic_record_from_evidence(
    step, adapter, semantic_eval, semantic_judgement, judgement, expected_group_ids
):
    group_verdicts = {
        group_id: result["verdict"]
        for group_id, result in judgement.get("groups", {}).items()
    }
    return {
        "step": step,
        "adapter": str(adapter),
        "semantic_eval": str(semantic_eval),
        "semantic_eval_sha256": sha256_of_file(semantic_eval),
        "semantic_judgement": str(semantic_judgement),
        "semantic_judgement_sha256": sha256_of_file(semantic_judgement),
        "group_verdicts": group_verdicts,
        "pass": all_group_verdicts(
            judgement, "ABSENT", expected_group_ids
        ),
    }


def compute_probe1_verdict(gates, use_scalar):
    required = [
        "pre_erasure_present_pass",
        "forgetting_pass",
        "persistence_after_heal_pass",
        "drift_reversible_pass",
    ]
    if use_scalar:
        required.append("repair_pass")
    if not use_scalar:
        return "INCOMPLETE_SCALAR_SKIPPED", required
    return ("PASS" if all(gates.get(key) for key in required) else "FAIL"), required


def write_manifest(root):
    root = Path(root)
    output = root / "MANIFEST.sha256"
    temporary = output.with_name(output.name + ".tmp")
    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path not in {output, temporary}
    )
    temporary.write_text(
        "\n".join(
            f"{sha256_of_file(path)}  {path.relative_to(root).as_posix()}"
            for path in files
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(output)
    return output, len(files)


def run_command(command, log_path, cwd):
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = " ".join(str(value) for value in command)
    print(f"\n$ {rendered}", flush=True)
    started = time.time()
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n$ {rendered}\n")
        log.flush()
        process = subprocess.Popen(
            [str(value) for value in command],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        for line in process.stdout:
            print(line, end="", flush=True)
            log.write(line)
            log.flush()
        code = process.wait()
        log.write(f"\nexit={code} duration_seconds={time.time() - started:.1f}\n")
    if code:
        raise subprocess.CalledProcessError(code, command)


def scalar_of(path, baseline, positive_anchor, negative_anchor):
    components = read_json(path)["components"]
    _, scalar, _ = normalise_components_bidirectional(
        components, baseline, positive_anchor, negative_anchor
    )
    return scalar


def validate_probe1_scalar_artifact(
    path,
    *,
    model_path,
    parent_model,
    model_weight_sha256,
    model_support_sha256,
    parent_weight_sha256,
    parent_support_sha256,
    prompt_sha256,
    baseline_json,
    anchor_json,
    ladder_json,
    policy_fingerprint,
    batch_size,
    max_new_tokens,
    baseline,
    positive_anchor,
    negative_anchor,
):
    model_path = str(Path(model_path).resolve())
    parent_model = str(Path(parent_model).resolve())
    payload = validate_scalar_artifact(
        path,
        expected_model=model_path,
        expected_judge=parent_model,
        expected_tokenizer=parent_model,
        expected_prompt_sha256=prompt_sha256,
        expected_weight_sha256=model_weight_sha256,
        expected_model_support_sha256=model_support_sha256,
        expected_tokenizer_support_sha256=parent_support_sha256,
        expected_judge_support_sha256=parent_support_sha256,
        expected_judge_weight_sha256=parent_weight_sha256,
        expected_policy=V2_POLICY,
        expected_policy_fingerprint=policy_fingerprint,
    )
    expected_decoding = {
        "method": "greedy",
        "max_new_tokens": max_new_tokens,
        "batch_size": batch_size,
        "padding_side": "left",
    }
    expected_anchor_paths = {
        "baseline_json": str(baseline_json),
        "anchor_json": str(anchor_json),
        "ladder_json": str(ladder_json),
    }
    if payload.get("seed") != 0 or payload.get("decoding") != expected_decoding:
        raise RuntimeError(f"scalar decoding configuration mismatch in {path}")
    if payload.get("judge_unparsed_count") != 0:
        raise RuntimeError(f"scalar judge parse count mismatch in {path}")
    if payload.get("normalisation_policy_requested") != V2_POLICY:
        raise RuntimeError(f"scalar requested policy mismatch in {path}")
    if any(payload.get(key) != value for key, value in expected_anchor_paths.items()):
        raise RuntimeError(f"scalar anchor path provenance mismatch in {path}")
    _, scalar, _ = normalise_components_bidirectional(
        payload["components"], baseline, positive_anchor, negative_anchor
    )
    reported = payload.get("scalar_0_100")
    if reported is None or abs(float(reported) - scalar) > 1e-9:
        raise RuntimeError(f"scalar value/components mismatch in {path}")
    return scalar


def main():
    args = parse_args()
    repo = Path.cwd().resolve()
    parent = Path(args.parent_model).expanduser()
    if not parent.is_dir():
        raise ValueError(
            "certified Probe 1 requires --parent-model to be the exact local "
            "clean-parent snapshot used by Probe 2"
        )
    args.parent_model = str(parent.resolve())
    root = Path(args.root).resolve()
    if (root / "MANIFEST.sha256").exists():
        verify_archive(root)
        raise RuntimeError(f"sealed Probe 1 archive is immutable: {root}")
    python = Path(sys.executable).absolute()
    log = root / "commands.log"
    day_dir = root / "day"
    concepts = read_json(args.concepts)
    if not 1 <= args.concept_index <= len(concepts):
        raise ValueError("concept-index is outside the one-based concept list")
    concept = concepts[args.concept_index - 1]
    print(f"Probe 1 concept: {concept['id']} ({concept['concept']})")

    use_scalar = not args.skip_scalar
    if use_scalar:
        validate_certification_args(args)
        validate_certification_inputs(args, repo, concept)
    scalar_inputs = (
        Path(args.scalar_baseline),
        Path(args.scalar_anchor),
        Path(args.scalar_ladder),
    )
    if use_scalar and not all(path.is_file() for path in scalar_inputs):
        raise FileNotFoundError(
            "sealed Probe 2 v2 baseline, endpoint, and ladder are required"
        )

    scalar_policy = None
    probe2_payload = None
    if use_scalar:
        baseline, positive_anchor, negative_anchor, anchor_sources = (
            load_bidirectional_anchors(*scalar_inputs)
        )
        scalar_policy = bidirectional_policy_fingerprint(
            baseline, positive_anchor, negative_anchor, anchor_sources
        )
        if not Path(args.probe2_aggregate).is_file():
            raise FileNotFoundError(
                "final overall Probe 2 aggregate is required before Probe 1"
            )
        probe2_payload = validate_probe2_aggregate(
            args.probe2_aggregate,
            scalar_policy,
            args.parent_model,
            scalar_inputs,
        )
    else:
        baseline = positive_anchor = negative_anchor = anchor_sources = None
    protected_roots = probe2_protected_roots(
        args.parent_model, args.probe2_aggregate, scalar_inputs, probe2_payload
    )
    if any(paths_overlap(root, protected) for protected in protected_roots):
        raise ValueError(
            "Probe 1 output root must not overlap the clean parent or sealed "
            "Probe 2 archives"
        )
    root.mkdir(parents=True, exist_ok=True)
    parent_model_hashes = (
        probe2_payload["_verified_parent_model_files"]
        if probe2_payload
        else model_file_hashes(args.parent_model)
    )
    parent_weight_hashes, parent_support_hashes = split_model_file_hashes(
        parent_model_hashes
    )

    # Healing data is a frozen input to certification. Building it remains a
    # convenience for smoke runs, but its exact bytes and config are pinned.
    if not Path(args.heal_corpus).is_file():
        if use_scalar:
            raise FileNotFoundError(
                "certification requires the prebuilt frozen healing corpus"
            )
        run_command(
            [
                python,
                "scripts/build_heal_corpus.py",
                args.heal_corpus,
                "--concepts",
                args.concepts,
                "--seed",
                str(args.seed),
            ],
            log,
            repo,
        )

    input_paths = {
        "concepts": Path(args.concepts),
        "heal_corpus": Path(args.heal_corpus),
        "retain_corpus": repo / "data/retain.json",
        "chat_retain_corpus": repo / "data/retain_chat.json",
        "frozen_sea_probes": repo / "data/probes.json",
        "frozen_perplexity_text": repo / "data/ppl_text.txt",
        "decay_scalar_prompts": repo / "data/decay_scalar_prompts.json",
        "rehearsal_capability_prompts": (
            repo / "data/rehearsal_capability_prompts.json"
        ),
        "conversational_survival_generations": (
            repo / "data/conversational_survival_generations.json"
        ),
    }
    heal_corpus_path = Path(args.heal_corpus)
    heal_config = heal_corpus_path.with_name(heal_corpus_path.stem + "_config.json")
    if not heal_config.is_file():
        raise FileNotFoundError(
            "healing corpus provenance sidecar is required: " + str(heal_config)
        )
    heal_config_payload = read_json(heal_config)
    if heal_config_payload.get("corpus_sha256") != sha256_of_file(heal_corpus_path):
        raise RuntimeError("healing corpus bytes do not match its provenance sidecar")
    input_paths["heal_config"] = heal_config
    if use_scalar:
        input_paths.update(
            {
                "probe2_aggregate": Path(args.probe2_aggregate),
                "scalar_baseline": Path(args.scalar_baseline),
                "scalar_anchor": Path(args.scalar_anchor),
                "scalar_ladder": Path(args.scalar_ladder),
            }
        )
    missing_inputs = [str(path) for path in input_paths.values() if not path.is_file()]
    if missing_inputs:
        raise FileNotFoundError(
            "Probe 1 certification inputs are missing: " + ", ".join(missing_inputs)
        )
    instrument_paths = [
        repo / "scripts/run_probe1.py",
        repo / "scripts/train_bounded_forget.py",
        repo / "scripts/train_heal.py",
        repo / "scripts/build_probe1_day.py",
        repo / "scripts/build_rehearsal_day.py",
        repo / "scripts/build_onpolicy_forget.py",
        repo / "scripts/build_heal_corpus.py",
        repo / "scripts/decay_scalar_normalization.py",
        repo / "scripts/eval_rehearsal_checkpoint.py",
        repo / "scripts/eval_decay_scalar.py",
        repo / "scripts/eval_drift.py",
        repo / "scripts/judge_rehearsal_generations.py",
        repo / "scripts/merge.py",
    ]
    run_config = {
        "args": vars(args),
        "concept_id": concept["id"],
        "normalisation_version": V2_POLICY if use_scalar else None,
        "normalisation_policy_fingerprint": scalar_policy,
        "probe2_verdict": (
            overall_probe2_verdict(probe2_payload) if probe2_payload else None
        ),
        "probe2_archive_seal": (
            probe2_payload.get("_verified_archive") if probe2_payload else None
        ),
        "probe2_primary_archive_seal": (
            probe2_payload.get("_verified_primary_archive")
            if probe2_payload
            else None
        ),
        "parent_model_files_sha256": parent_model_hashes,
        "input_sha256": {
            name: sha256_of_file(path) for name, path in input_paths.items()
        },
        "instrument_sha256": {
            path.relative_to(repo).as_posix(): sha256_of_file(path)
            for path in instrument_paths
        },
        "code_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo, text=True
        ).strip(),
        "gate_policy": {
            "pre_erasure": "PRESENT on core and every required neighbour, original and conjugate",
            "semantic_selection": "earliest saved held-out original-probe ABSENT",
            "repair_fraction_min": 0.5,
            "leakage_scalar_points_max": 1.0,
            "pca_drift_percent_max": 20.0,
            "drift_checkpoints": ["post_forget", "post_heal"],
            "skip_scalar_verdict": "INCOMPLETE_SCALAR_SKIPPED",
        },
    }
    run_config["fingerprint"] = fingerprint(run_config)
    config_path = root / "run_config.json"
    if config_path.exists():
        if read_json(config_path) != run_config:
            raise RuntimeError(
                f"Probe 1 configuration mismatch in {root}; use a new root"
            )
    else:
        write_json(config_path, run_config)
    state_path = root / "state.json"
    state = read_json(state_path) if state_path.exists() else {
        "status": "running",
        "run_config_fingerprint": run_config["fingerprint"],
    }
    if state.get("run_config_fingerprint") != run_config["fingerprint"]:
        raise RuntimeError("Probe 1 state/config fingerprint mismatch")
    write_json(state_path, state)
    expected_group_ids = tuple(group["id"] for group in concept["groups"])
    if not expected_group_ids or len(expected_group_ids) != len(set(expected_group_ids)):
        raise RuntimeError("concept has no groups or duplicate group ids")

    # 1. Compile the immutable day and write a completion marker.
    day_marker = day_dir / "stage_complete.json"
    if not day_marker.exists():
        if day_dir.exists() and any(day_dir.iterdir()):
            raise RuntimeError(f"partial day compilation needs inspection: {day_dir}")
        run_command(
            [
                python,
                "scripts/build_probe1_day.py",
                str(args.concept_index),
                day_dir,
                "--concepts",
                args.concepts,
                "--seed",
                str(args.seed),
            ],
            log,
            repo,
        )
        day_files = sorted(path for path in day_dir.iterdir() if path.is_file())
        write_json(
            day_marker,
            {
                "run_config_fingerprint": run_config["fingerprint"],
                "files_sha256": hash_paths(day_files),
            },
        )
    day_record = read_json(day_marker)
    if day_record.get("run_config_fingerprint") != run_config["fingerprint"]:
        raise RuntimeError("compiled day belongs to a different Probe 1 run")
    expected_day_hashes = day_record.get("files_sha256", {})
    for path_text, expected_hash in expected_day_hashes.items():
        if not Path(path_text).is_file() or sha256_of_file(path_text) != expected_hash:
            raise RuntimeError("compiled day artifact hash mismatch")

    def artifact_marker(path):
        path = Path(path)
        return path.with_name(path.name + ".complete.json")

    def mark_artifact(path, provenance):
        path = Path(path)
        write_json(
            artifact_marker(path),
            {
                "run_config_fingerprint": run_config["fingerprint"],
                "artifact_sha256": sha256_of_file(path),
                "provenance": provenance,
            },
        )

    def artifact_is_complete(path, provenance):
        path = Path(path)
        marker = artifact_marker(path)
        if not path.exists() and not marker.exists():
            return False
        if not path.is_file() or not marker.is_file():
            raise RuntimeError(f"partial artifact needs inspection: {path}")
        payload = read_json(marker)
        expected = {
            "run_config_fingerprint": run_config["fingerprint"],
            "artifact_sha256": sha256_of_file(path),
            "provenance": provenance,
        }
        if payload != expected:
            raise RuntimeError(f"artifact provenance mismatch: {path}")
        return True

    def eval_stage(name, model_path):
        """Rehearsal eval + conjugate probes + scalar + drift for one checkpoint."""
        stage = root / name
        stage.mkdir(parents=True, exist_ok=True)
        model_path = str(Path(model_path).resolve())
        model_files = model_file_hashes(model_path)
        model_weights, model_support = split_model_file_hashes(model_files)
        model_identity = fingerprint(
            {"path": model_path, "files_sha256": model_files}
        )
        rehearsal = stage / "rehearsal_eval.json"
        rehearsal_provenance = {
            "kind": "rehearsal_eval",
            "model_identity": model_identity,
            "day_marker_sha256": sha256_of_file(day_marker),
            "max_new_tokens": 64,
        }
        if not artifact_is_complete(rehearsal, rehearsal_provenance):
            run_command(
                [
                    python,
                    "scripts/eval_rehearsal_checkpoint.py",
                    model_path,
                    rehearsal,
                    "--day-dir",
                    day_dir,
                    "--tokenizer-model",
                    args.parent_model,
                    "--max-new-tokens",
                    "64",
                    "--skip-cumulative",
                ],
                log,
                repo,
            )
            mark_artifact(rehearsal, rehearsal_provenance)
        conjugate = stage / "conjugate_eval.json"
        conjugate_day = root / "day_conjugate"
        conjugate_marker = conjugate_day / "stage_complete.json"
        if not conjugate_marker.exists():
            # Same evaluator, pointed at a day dir whose probes.json is the
            # conjugate set, so the judge downstream sees the identical shape.
            if conjugate_day.exists() and any(conjugate_day.iterdir()):
                raise RuntimeError(
                    f"partial conjugate day needs inspection: {conjugate_day}"
                )
            if not conjugate_day.exists():
                conjugate_day.mkdir(parents=True, exist_ok=True)
            for filename in ("concept.json", "clozes.json"):
                shutil.copy2(day_dir / filename, conjugate_day / filename)
            shutil.copy2(
                day_dir / "probes_conjugate.json", conjugate_day / "probes.json"
            )
            write_json(
                conjugate_marker,
                {
                    "run_config_fingerprint": run_config["fingerprint"],
                    "source_day_marker_sha256": sha256_of_file(day_marker),
                    "files_sha256": hash_paths(
                        sorted(
                            path
                            for path in conjugate_day.iterdir()
                            if path.is_file()
                        )
                    ),
                },
            )
        conjugate_day_record = read_json(conjugate_marker)
        if (
            conjugate_day_record.get("run_config_fingerprint")
            != run_config["fingerprint"]
            or conjugate_day_record.get("source_day_marker_sha256")
            != sha256_of_file(day_marker)
        ):
            raise RuntimeError("conjugate day provenance mismatch")
        for path_text, expected_hash in conjugate_day_record.get(
            "files_sha256", {}
        ).items():
            if not Path(path_text).is_file() or sha256_of_file(path_text) != expected_hash:
                raise RuntimeError("conjugate day artifact hash mismatch")
        conjugate_provenance = {
            "kind": "conjugate_eval",
            "model_identity": model_identity,
            "conjugate_day_marker_sha256": sha256_of_file(conjugate_marker),
            "max_new_tokens": 64,
        }
        if not artifact_is_complete(conjugate, conjugate_provenance):
            run_command(
                [
                    python,
                    "scripts/eval_rehearsal_checkpoint.py",
                    model_path,
                    conjugate,
                    "--day-dir",
                    conjugate_day,
                    "--tokenizer-model",
                    args.parent_model,
                    "--max-new-tokens",
                    "64",
                    "--skip-capability",
                    "--skip-cumulative",
                    "--skip-perplexity",
                ],
                log,
                repo,
            )
            mark_artifact(conjugate, conjugate_provenance)
        drift = stage / "drift.json"
        drift_provenance = {
            "kind": "pca_cka_drift",
            "model_identity": model_identity,
            "batch_size": args.batch_size,
        }
        if not artifact_is_complete(drift, drift_provenance):
            run_command(
                [
                    python,
                    "scripts/eval_drift.py",
                    model_path,
                    drift,
                    "--reference-model",
                    args.parent_model,
                    "--tokenizer-model",
                    args.parent_model,
                    "--batch-size",
                    str(args.batch_size),
                ],
                log,
                repo,
            )
            mark_artifact(drift, drift_provenance)
        scalar = stage / "scalar.json"
        scalar_provenance = {
            "kind": "decay_scalar",
            "model_identity": model_identity,
            "policy_fingerprint": scalar_policy,
            "batch_size": args.batch_size,
            "max_new_tokens": args.max_new_tokens,
        }
        if use_scalar and not artifact_is_complete(scalar, scalar_provenance):
            run_command(
                [
                    python,
                    "scripts/eval_decay_scalar.py",
                    model_path,
                    scalar,
                    "--batch-size",
                    str(args.batch_size),
                    "--max-new-tokens",
                    str(args.max_new_tokens),
                    "--seed",
                    "0",
                    "--judge-model",
                    args.parent_model,
                    "--tokenizer-model",
                    args.parent_model,
                    "--baseline-json",
                    args.scalar_baseline,
                    "--anchor-json",
                    args.scalar_anchor,
                    "--ladder-json",
                    args.scalar_ladder,
                    "--normalisation-policy",
                    V2_POLICY,
                ],
                log,
                repo,
            )
            mark_artifact(scalar, scalar_provenance)
        if use_scalar:
            validate_probe1_scalar_artifact(
                scalar,
                model_path=model_path,
                parent_model=args.parent_model,
                model_weight_sha256=model_weights,
                model_support_sha256=model_support,
                parent_weight_sha256=parent_weight_hashes,
                parent_support_sha256=parent_support_hashes,
                prompt_sha256={
                    "battery": run_config["input_sha256"]["decay_scalar_prompts"],
                    "capability": run_config["input_sha256"][
                        "rehearsal_capability_prompts"
                    ],
                    "survival": run_config["input_sha256"][
                        "conversational_survival_generations"
                    ],
                },
                baseline_json=args.scalar_baseline,
                anchor_json=args.scalar_anchor,
                ladder_json=args.scalar_ladder,
                policy_fingerprint=scalar_policy,
                batch_size=args.batch_size,
                max_new_tokens=args.max_new_tokens,
                baseline=baseline,
                positive_anchor=positive_anchor,
                negative_anchor=negative_anchor,
            )
        return stage

    def judgement_provenance(source):
        return {
            "kind": "semantic_judgement",
            "source_sha256": sha256_of_file(source),
            "judge_model_identity": fingerprint(parent_model_hashes),
        }

    def judge_eval(source, target, scratch):
        source = Path(source)
        target = Path(target)
        provenance = judgement_provenance(source)
        if artifact_is_complete(target, provenance):
            validate_judgement_payload(
                read_json(target),
                args.parent_model,
                concept["id"],
                expected_group_ids,
            )
            return target
        step_dir = Path(scratch) / "step01_probe"
        step_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, step_dir / "post_eval.json")
        run_command(
            [
                python,
                "scripts/judge_rehearsal_generations.py",
                "--root",
                scratch,
                "--judge-model",
                args.parent_model,
                "--force",
            ],
            log,
            repo,
        )
        shutil.copy2(step_dir / "semantic_judgement.json", target)
        mark_artifact(target, provenance)
        validate_judgement_payload(
            read_json(target),
            args.parent_model,
            concept["id"],
            expected_group_ids,
        )
        return target

    def judge_stage(stage):
        """Run the pinned clean semantic judge over original and conjugate evals."""
        for source, output in (
            ("rehearsal_eval.json", "judgement.json"),
            ("conjugate_eval.json", "judgement_conjugate.json"),
        ):
            judge_eval(
                stage / source,
                stage / output,
                stage / f"judge_{Path(source).stem}",
            )

    def seal_terminal(summary, status):
        summary["run_config_fingerprint"] = run_config["fingerprint"]
        summary["archive_provenance"] = {
            "run_config": str(config_path),
            "run_config_sha256": sha256_of_file(config_path),
            "parent_model_files_sha256": parent_model_hashes,
            "input_sha256": run_config["input_sha256"],
            "instrument_sha256": run_config["instrument_sha256"],
            "probe2_archive_seal": run_config["probe2_archive_seal"],
            "probe2_primary_archive_seal": run_config[
                "probe2_primary_archive_seal"
            ],
        }
        write_json(root / "probe1_summary.json", summary)
        state["status"] = status
        write_json(state_path, state)
        manifest, manifest_count = write_manifest(root)
        seal = verify_archive(root)
        if seal["entry_count"] != manifest_count:
            raise RuntimeError("Probe 1 manifest verification count mismatch")
        print(f"Sealed {manifest} ({manifest_count} files)")

    # 3. Pre-evaluate and prove that the semantic target is initially present.
    pre = eval_stage("pre", args.parent_model)
    judge_stage(pre)
    pre_original = read_json(pre / "judgement.json")
    pre_conjugate = read_json(pre / "judgement_conjugate.json")
    pre_present_pass = all_group_verdicts(
        pre_original, "PRESENT", expected_group_ids
    ) and all_group_verdicts(
        pre_conjugate, "PRESENT", expected_group_ids
    )
    if not pre_present_pass:
        summary = {
            "certification_scope": "probe1_forget_heal",
            "concept": {"index": args.concept_index, **concept},
            "parent_model": args.parent_model,
            "normalisation_policy_fingerprint": scalar_policy,
            "gates": {
                "pre_erasure_present_pass": False,
                "pre_original_group_verdicts": {
                    key: value["verdict"]
                    for key, value in pre_original["groups"].items()
                },
                "pre_conjugate_group_verdicts": {
                    key: value["verdict"]
                    for key, value in pre_conjugate["groups"].items()
                },
                "probe1_verdict": (
                    "FAIL" if use_scalar else "INCOMPLETE_SCALAR_SKIPPED"
                ),
                "failure_stage": "pre_erasure_presence",
            },
        }
        seal_terminal(
            summary,
            (
                "failed_pre_erasure_presence"
                if use_scalar
                else "incomplete_scalar_skipped"
            ),
        )
        pre_verdict = "FAIL" if use_scalar else "INCOMPLETE_SCALAR_SKIPPED"
        print(f"PROBE 1 VERDICT: {pre_verdict} (target not PRESENT before erasure)")
        return

    # 4. On-policy forget answers, with an exact completion marker.
    onpolicy = day_dir / "forget_onpolicy.json"
    onpolicy_provenance = {
        "kind": "onpolicy_forget",
        "parent_identity": fingerprint(parent_model_hashes),
        "prompt_sha256": sha256_of_file(
            day_dir / "forget_prompts_diversified.json"
        ),
        "batch_size": 4,
        "max_new_tokens": 64,
    }
    if not artifact_is_complete(onpolicy, onpolicy_provenance):
        run_command(
            [
                python,
                "scripts/build_onpolicy_forget.py",
                "--model-id",
                args.parent_model,
                "--input",
                day_dir / "forget_prompts_diversified.json",
                "--output",
                onpolicy,
                "--batch-size",
                "4",
                "--max-new-tokens",
                "64",
            ],
            log,
            repo,
        )
        mark_artifact(onpolicy, onpolicy_provenance)

    # 5. Train the complete snapshot grid. Proxy loss gates are telemetry;
    # certification selects the earliest held-out semantic PASS below.
    adapter_root = root / "forget_adapter"
    stop_state = adapter_root / "stop_state.json"
    adapter_marker = root / "forget_adapter_complete.json"
    if not adapter_marker.exists():
        if adapter_root.exists():
            raise RuntimeError(
                f"partial erasure directory needs inspection: {adapter_root}"
            )
        run_command(
            [
                python,
                "scripts/train_bounded_forget.py",
                "--model-id",
                args.parent_model,
                "--forget-data",
                onpolicy,
                "--output-dir",
                adapter_root,
                "--num-steps",
                str(args.forget_steps),
                "--seed",
                str(args.seed),
                "--external-semantic-selection",
            ],
            log,
            repo,
        )
        if not stop_state.is_file() or not (adapter_root / "run_config.json").is_file():
            raise RuntimeError("forget trainer completed without terminal records")
        write_json(
            adapter_marker,
            {
                "run_config_fingerprint": run_config["fingerprint"],
                "trainer_run_config_sha256": sha256_of_file(
                    adapter_root / "run_config.json"
                ),
                "trainer_stop_state_sha256": sha256_of_file(stop_state),
                "adapter_tree_sha256": tree_file_hashes(adapter_root),
                "forget_data_sha256": sha256_of_file(onpolicy),
                "retain_data_sha256": sha256_of_file(repo / "data/retain.json"),
                "chat_retain_data_sha256": sha256_of_file(
                    repo / "data/retain_chat.json"
                ),
            },
        )
    if not stop_state.is_file() or not (adapter_root / "run_config.json").is_file():
        raise RuntimeError("forget adapter marker exists without terminal records")
    expected_adapter_marker = {
        "run_config_fingerprint": run_config["fingerprint"],
        "trainer_run_config_sha256": sha256_of_file(adapter_root / "run_config.json"),
        "trainer_stop_state_sha256": sha256_of_file(stop_state),
        "adapter_tree_sha256": tree_file_hashes(adapter_root),
        "forget_data_sha256": sha256_of_file(onpolicy),
        "retain_data_sha256": sha256_of_file(repo / "data/retain.json"),
        "chat_retain_data_sha256": sha256_of_file(repo / "data/retain_chat.json"),
    }
    if read_json(adapter_marker) != expected_adapter_marker:
        raise RuntimeError("forget adapter completion/provenance marker mismatch")
    trainer_state = read_json(stop_state)
    snapshots = validate_forget_snapshot_grid(adapter_root, trainer_state)
    trainer_config = read_json(adapter_root / "run_config.json")
    expected_trainer_config = {
        "model_id": args.parent_model,
        "forget_data": str(onpolicy),
        "retain_data": "data/retain.json",
        "chat_retain_data": "data/retain_chat.json",
        "output_dir": str(adapter_root),
        "num_steps": args.forget_steps,
        "save_every": 10,
        "save_steps": "",
        "eval_every": 10,
        "batch_forget": 4,
        "batch_retain": 2,
        "batch_chat_retain": 2,
        "max_length": 256,
        "parameterization": "lora",
        "forget_objective": "jensun-jsd",
        "disable_snapshots": False,
        "rank": 4,
        "lora_alpha": 8,
        "train_layer_lo": 4,
        "train_layer_hi": 11,
        "learning_rate": 5e-5,
        "forget_weight": 1.0,
        "retain_weight": 1.0,
        "chat_retain_weight": 1.0,
        "stop_jsd": 0.02,
        "stop_target_prob": 0.9,
        "audit_size": 24,
        "refusal_text": "No idea",
        "seed": args.seed,
        "fp32_base": False,
        "external_semantic_selection": True,
    }
    trainer_projection = {
        key: trainer_config.get(key) for key in expected_trainer_config
    }
    if trainer_projection != expected_trainer_config:
        raise RuntimeError("forget trainer configuration mismatch")

    # 6. Merge/evaluate snapshots in step order and select the first held-out
    # original-probe judgement that is ABSENT for every required group.
    semantic_root = root / "forget_semantic_selection"
    semantic_root.mkdir(parents=True, exist_ok=True)
    semantic_stop_state = semantic_root / "semantic_stop_state.json"
    forget_model = root / "forget_model"
    def snapshot_semantic_provenance(step, adapter):
        return {
            "kind": "snapshot_semantic_eval",
            "step": step,
            "adapter_sha256": fingerprint(tree_file_hashes(adapter)),
            "day_marker_sha256": sha256_of_file(day_marker),
            "evaluation_scope": "held-out current-concept semantics only",
        }

    if semantic_stop_state.exists():
        semantic_selection = read_json(semantic_stop_state)
        if (
            semantic_selection.get("run_config_fingerprint")
            != run_config["fingerprint"]
            or semantic_selection.get("selection_policy")
            != "earliest saved held-out semantic PASS"
            or semantic_selection.get("step_budget") != args.forget_steps
        ):
            raise RuntimeError("semantic selection/config marker mismatch")
        evaluated_steps = []
        snapshot_by_step = dict(snapshots)
        for record in semantic_selection.get("evaluated", []):
            step = record.get("step")
            evaluated_steps.append(step)
            adapter = snapshot_by_step.get(step)
            candidate = semantic_root / f"step{step:03d}" if adapter else None
            semantic_eval_path = candidate / "semantic_eval.json" if candidate else None
            semantic_judgement_path = (
                candidate / "semantic_judgement.json" if candidate else None
            )
            if adapter is None:
                raise RuntimeError("semantic selection names a non-grid snapshot")
            semantic_provenance = snapshot_semantic_provenance(step, adapter)
            if not artifact_is_complete(semantic_eval_path, semantic_provenance):
                raise RuntimeError("semantic selection eval lacks completion evidence")
            judgement_marker_provenance = judgement_provenance(semantic_eval_path)
            if not artifact_is_complete(
                semantic_judgement_path, judgement_marker_provenance
            ):
                raise RuntimeError(
                    "semantic selection judgement lacks completion evidence"
                )
            judgement_payload = read_json(semantic_judgement_path)
            validate_judgement_payload(
                judgement_payload,
                args.parent_model,
                concept["id"],
                expected_group_ids,
            )
            expected_record = semantic_record_from_evidence(
                step,
                adapter,
                semantic_eval_path,
                semantic_judgement_path,
                judgement_payload,
                expected_group_ids,
            )
            if record != expected_record:
                raise RuntimeError("semantic selection evidence/provenance mismatch")
        if evaluated_steps != sorted(evaluated_steps) or len(evaluated_steps) != len(
            set(evaluated_steps)
        ):
            raise RuntimeError("semantic selection steps are not strictly ordered")
        selected_value = semantic_selection.get("selected_adapter")
        selected_adapter = Path(selected_value) if selected_value else None
        if (selected_adapter is None) != (
            semantic_selection.get("selected_step") is None
        ) or semantic_selection.get("semantic_pass") != (selected_adapter is not None):
            raise RuntimeError("semantic selection terminal fields conflict")
        if selected_adapter is not None:
            selected_step = semantic_selection["selected_step"]
            if (
                selected_adapter.resolve().parent != adapter_root.resolve()
                or selected_adapter.name != f"step{selected_step:03d}"
                or not selected_adapter.is_dir()
                or not evaluated_steps
                or evaluated_steps[-1] != selected_step
                or not semantic_selection["evaluated"][-1].get("pass")
            ):
                raise RuntimeError("selected semantic adapter provenance mismatch")
            selected_index = [step for step, _ in snapshots].index(selected_step)
            if evaluated_steps != [
                step for step, _ in snapshots[: selected_index + 1]
            ] or any(
                record.get("pass")
                for record in semantic_selection["evaluated"][:-1]
            ):
                raise RuntimeError("semantic selection did not preserve earliest PASS")
        elif evaluated_steps != [step for step, _ in snapshots] or any(
            record.get("pass") for record in semantic_selection.get("evaluated", [])
        ):
            raise RuntimeError("failed semantic selection did not exhaust the grid")
        if selected_adapter is not None and not forget_model.is_dir():
            raise RuntimeError("semantic stop state exists without selected model")
    else:
        semantic_records = []
        selected_adapter = None
        for step, adapter in snapshots:
            candidate = semantic_root / f"step{step:03d}"
            candidate.mkdir(parents=True, exist_ok=True)
            candidate_model = candidate / "merged_model"
            merge_marker = candidate / "merge_complete.json"
            semantic_eval = candidate / "semantic_eval.json"
            if not merge_marker.exists():
                if candidate_model.exists():
                    raise RuntimeError(
                        f"partial candidate merge needs inspection: {candidate_model}"
                    )
                run_command(
                    [
                        python,
                        "scripts/merge.py",
                        adapter,
                        candidate_model,
                        args.parent_model,
                    ],
                    log,
                    repo,
                )
                write_json(
                    merge_marker,
                    {
                        "run_config_fingerprint": run_config["fingerprint"],
                        "adapter": str(adapter),
                        "adapter_sha256": tree_file_hashes(adapter),
                        "model_sha256": model_file_hashes(candidate_model),
                    },
                )
            elif not candidate_model.is_dir() and not artifact_marker(
                semantic_eval
            ).is_file():
                run_command(
                    [
                        python,
                        "scripts/merge.py",
                        adapter,
                        candidate_model,
                        args.parent_model,
                    ],
                    log,
                    repo,
                )
            merge_record = read_json(merge_marker)
            if (
                merge_record.get("run_config_fingerprint")
                != run_config["fingerprint"]
                or merge_record.get("adapter_sha256") != tree_file_hashes(adapter)
            ):
                raise RuntimeError("candidate merge provenance mismatch")
            if candidate_model.is_dir() and (
                merge_record.get("model_sha256") != model_file_hashes(candidate_model)
            ):
                raise RuntimeError("candidate merged-model hash mismatch")
            semantic_provenance = snapshot_semantic_provenance(step, adapter)
            if not artifact_is_complete(semantic_eval, semantic_provenance):
                run_command(
                    [
                        python,
                        "scripts/eval_rehearsal_checkpoint.py",
                        candidate_model,
                        semantic_eval,
                        "--day-dir",
                        day_dir,
                        "--tokenizer-model",
                        args.parent_model,
                        "--max-new-tokens",
                        "64",
                        "--skip-capability",
                        "--skip-cumulative",
                        "--skip-perplexity",
                        "--skip-sea",
                    ],
                    log,
                    repo,
                )
                mark_artifact(semantic_eval, semantic_provenance)
            semantic_judgement = candidate / "semantic_judgement.json"
            judge_eval(
                semantic_eval,
                semantic_judgement,
                candidate / "judge_scratch",
            )
            judgement_payload = read_json(semantic_judgement)
            passed = all_group_verdicts(
                judgement_payload, "ABSENT", expected_group_ids
            )
            semantic_records.append(
                semantic_record_from_evidence(
                    step,
                    adapter,
                    semantic_eval,
                    semantic_judgement,
                    judgement_payload,
                    expected_group_ids,
                )
            )
            if passed:
                selected_adapter = adapter
                if not forget_model.exists():
                    if not candidate_model.is_dir():
                        raise RuntimeError("passing candidate model is unavailable")
                    candidate_model.replace(forget_model)
                if model_file_hashes(forget_model) != merge_record.get("model_sha256"):
                    raise RuntimeError("selected merged-model hash mismatch")
                write_json(
                    root / "forget_model_complete.json",
                    {
                        "run_config_fingerprint": run_config["fingerprint"],
                        "selected_step": step,
                        "selected_adapter": str(adapter),
                        "model_sha256": model_file_hashes(forget_model),
                    },
                )
                break
            # The full model is redrawn exactly from the archived adapter and
            # clean parent; generations and judgement remain immutable.
            if candidate_model.is_dir():
                shutil.rmtree(candidate_model)
        semantic_selection = {
            "run_config_fingerprint": run_config["fingerprint"],
            "selection_policy": "earliest saved held-out semantic PASS",
            "step_budget": args.forget_steps,
            "evaluated": semantic_records,
            "selected_adapter": (
                str(selected_adapter) if selected_adapter is not None else None
            ),
            "selected_step": (
                int(re.search(r"(\d+)$", selected_adapter.name).group(1))
                if selected_adapter is not None
                else None
            ),
            "semantic_pass": selected_adapter is not None,
        }
        write_json(semantic_stop_state, semantic_selection)

    if selected_adapter is None:
        summary = {
            "certification_scope": "probe1_forget_heal",
            "concept": {"index": args.concept_index, **concept},
            "parent_model": args.parent_model,
            "normalisation_policy_fingerprint": scalar_policy,
            "forget_semantic_selection": semantic_selection,
            "gates": {
                "pre_erasure_present_pass": True,
                "forgetting_pass": False,
                "probe1_verdict": (
                    "FAIL" if use_scalar else "INCOMPLETE_SCALAR_SKIPPED"
                ),
                "failure_stage": "semantic_step_budget",
            },
        }
        seal_terminal(
            summary,
            (
                "failed_semantic_step_budget"
                if use_scalar
                else "incomplete_scalar_skipped"
            ),
        )
        budget_verdict = "FAIL" if use_scalar else "INCOMPLETE_SCALAR_SKIPPED"
        print(
            f"PROBE 1 VERDICT: {budget_verdict} "
            "(semantic bar not reached in budget)"
        )
        return

    forget_model_marker = root / "forget_model_complete.json"
    if not forget_model_marker.is_file():
        raise RuntimeError("selected forget model lacks a completion marker")
    forget_model_record = read_json(forget_model_marker)
    if (
        forget_model_record.get("run_config_fingerprint")
        != run_config["fingerprint"]
        or forget_model_record.get("selected_adapter") != str(selected_adapter)
        or forget_model_record.get("model_sha256")
        != model_file_hashes(forget_model)
    ):
        raise RuntimeError("selected forget model provenance mismatch")

    # 7. post-forget battery.
    post_forget = eval_stage("post_forget", forget_model)
    judge_stage(post_forget)

    # 8-9. heal, then merge.
    heal_root = root / "heal_adapter"
    heal_final = heal_root / f"step{args.heal_steps:03d}"
    heal_marker = root / "heal_adapter_complete.json"
    if not heal_marker.exists():
        if heal_root.exists():
            raise RuntimeError(f"partial healing directory needs inspection: {heal_root}")
        run_command(
            [
                python,
                "scripts/train_heal.py",
                "--model-id",
                forget_model,
                "--heal-data",
                args.heal_corpus,
                "--output-dir",
                heal_root,
                "--num-steps",
                str(args.heal_steps),
                "--seed",
                str(args.seed),
            ],
            log,
            repo,
        )
        if not heal_final.is_dir():
            raise RuntimeError("healing finished without its final adapter")
        write_json(
            heal_marker,
            {
                "run_config_fingerprint": run_config["fingerprint"],
                "final_adapter": str(heal_final),
                "adapter_tree_sha256": tree_file_hashes(heal_root),
                "source_forget_model_sha256": model_file_hashes(forget_model),
                "heal_corpus_sha256": sha256_of_file(args.heal_corpus),
            },
        )
    heal_record = read_json(heal_marker)
    if (
        heal_record.get("run_config_fingerprint") != run_config["fingerprint"]
        or heal_record.get("final_adapter") != str(heal_final)
        or heal_record.get("adapter_tree_sha256") != tree_file_hashes(heal_root)
        or heal_record.get("source_forget_model_sha256")
        != model_file_hashes(forget_model)
        or heal_record.get("heal_corpus_sha256")
        != sha256_of_file(args.heal_corpus)
    ):
        raise RuntimeError("healing adapter provenance mismatch")
    heal_trainer_config_path = heal_root / "run_config.json"
    if not heal_trainer_config_path.is_file():
        raise RuntimeError("healing adapter lacks its trainer configuration")
    heal_trainer_config = read_json(heal_trainer_config_path)
    validate_heal_trainer_config(
        heal_trainer_config,
        forget_model,
        args.heal_corpus,
        heal_root,
    )
    heal_model = root / "heal_model"
    heal_model_marker = root / "heal_model_complete.json"
    if not heal_model_marker.exists():
        if heal_model.exists():
            raise RuntimeError(f"partial healing merge needs inspection: {heal_model}")
        run_command(
            [python, "scripts/merge.py", heal_final, heal_model, forget_model],
            log,
            repo,
        )
        write_json(
            heal_model_marker,
            {
                "run_config_fingerprint": run_config["fingerprint"],
                "heal_adapter_tree_sha256": tree_file_hashes(heal_final),
                "base_forget_model_sha256": model_file_hashes(forget_model),
                "model_sha256": model_file_hashes(heal_model),
            },
        )
    heal_model_record = read_json(heal_model_marker)
    if (
        heal_model_record.get("run_config_fingerprint")
        != run_config["fingerprint"]
        or heal_model_record.get("heal_adapter_tree_sha256")
        != tree_file_hashes(heal_final)
        or heal_model_record.get("base_forget_model_sha256")
        != model_file_hashes(forget_model)
        or heal_model_record.get("model_sha256") != model_file_hashes(heal_model)
    ):
        raise RuntimeError("healed model provenance mismatch")

    # 10. post-heal battery.
    post_heal = eval_stage("post_heal", heal_model)
    judge_stage(post_heal)

    # 11. gates.
    def judged(stage, filename):
        payload = read_json(stage / filename)
        group_verdicts = {
            group_id: result["verdict"]
            for group_id, result in payload.get("groups", {}).items()
        }
        if set(group_verdicts) != set(expected_group_ids):
            raise RuntimeError(
                f"semantic judgement group coverage mismatch: {stage / filename}"
            )
        return {
            "core_unlearned": group_verdicts["core"] == "ABSENT",
            "required_neighbours_unlearned": all(
                group_verdicts[group_id] == "ABSENT"
                for group_id in expected_group_ids
                if group_id != "core"
            ),
            "groups": group_verdicts,
        }

    forget_judgement = judged(post_forget, "judgement.json")
    forget_conjugate = judged(post_forget, "judgement_conjugate.json")
    heal_judgement = judged(post_heal, "judgement.json")
    heal_conjugate = judged(post_heal, "judgement_conjugate.json")

    gates = {
        "pre_erasure_present_pass": pre_present_pass,
        "pre_original_group_verdicts": {
            key: value["verdict"] for key, value in pre_original["groups"].items()
        },
        "pre_conjugate_group_verdicts": {
            key: value["verdict"] for key, value in pre_conjugate["groups"].items()
        },
        "forgetting_pass": (
            semantic_selection["semantic_pass"]
            and semantic_selection["selected_step"] <= args.forget_steps
            and
            forget_judgement["core_unlearned"]
            and forget_judgement["required_neighbours_unlearned"]
        ),
        "persistence_after_heal_pass": (
            heal_judgement["core_unlearned"]
            and heal_judgement["required_neighbours_unlearned"]
            and heal_conjugate["core_unlearned"]
            and heal_conjugate["required_neighbours_unlearned"]
        ),
        "post_forget_judgement": forget_judgement,
        "post_forget_conjugate_judgement": forget_conjugate,
        "post_heal_judgement": heal_judgement,
        "post_heal_conjugate_judgement": heal_conjugate,
        "semantic_selection_step": semantic_selection["selected_step"],
        "semantic_step_budget": args.forget_steps,
    }

    drift_values = {
        name: read_json(root / name / "drift.json")[
            "pca_drift_percent_of_reference_spread"
        ]
        for name in ("pre", "post_forget", "post_heal")
    }
    gates["pca_drift"] = drift_values
    gates["drift_reversible_pass"] = (
        drift_values["post_forget"] <= 20.0
        and drift_values["post_heal"] <= 20.0
    )
    gates["drift_policy"] = {
        "maximum_percent": 20.0,
        "required_checkpoints": ["post_forget", "post_heal"],
    }

    if use_scalar:
        scalars = {
            name: scalar_of(
                root / name / "scalar.json",
                baseline,
                positive_anchor,
                negative_anchor,
            )
            for name in ("pre", "post_forget", "post_heal")
        }
        collateral = scalars["post_forget"] - scalars["pre"]
        recovered = scalars["post_forget"] - scalars["post_heal"]
        fraction = recovered / collateral if collateral > 1e-9 else None
        leakage = scalars["post_heal"] - scalars["pre"]
        gates.update(
            {
                "scalars": scalars,
                "collateral_from_forgetting": collateral,
                "recovered_by_healing": recovered,
                "repair_fraction": fraction,
                "repair_pass": (
                    fraction is not None and recovered >= 0.0 and fraction >= 0.5
                ),
                "leakage_scalar_points": leakage,
                "leakage_within_budget": leakage <= 1.0,
                "leakage_policy_max_scalar_points": 1.0,
                "normalisation_version": V2_POLICY,
                "normalisation_policy_fingerprint": scalar_policy,
                "probe2_archive_seal": (
                    probe2_payload.get("_verified_archive")
                    if probe2_payload
                    else None
                ),
                "positive_component_anchor": positive_anchor,
                "negative_component_anchor": negative_anchor,
                "component_anchor_sources": anchor_sources,
            }
        )
    else:
        gates.update(
            {
                "repair_fraction": None,
                "repair_pass": None,
                "leakage_scalar_points": None,
                "leakage_within_budget": None,
                "leakage_policy_max_scalar_points": 1.0,
            }
        )

    gates["probe1_verdict"], required = compute_probe1_verdict(gates, use_scalar)
    gates["required_gates"] = required

    summary = {
        "certification_scope": "probe1_forget_heal",
        "concept": {"index": args.concept_index, **concept},
        "parent_model": args.parent_model,
        "run_config_fingerprint": run_config["fingerprint"],
        "probe2_aggregate": (
            {
                "path": str(Path(args.probe2_aggregate).resolve()),
                "sha256": sha256_of_file(args.probe2_aggregate),
                "probe2_verdict": overall_probe2_verdict(probe2_payload),
                "normalisation_policy_fingerprint": scalar_policy,
                "archive_seal": probe2_payload.get("_verified_archive"),
                "primary_archive_seal": probe2_payload.get(
                    "_verified_primary_archive"
                ),
            }
            if use_scalar
            else None
        ),
        "forget_training_stop_state": read_json(stop_state),
        "forget_semantic_selection": semantic_selection,
        "models": {
            "forget_model": str(forget_model),
            "heal_model": str(heal_model),
            "forget_model_sha256": model_file_hashes(forget_model),
            "heal_model_sha256": model_file_hashes(heal_model),
        },
        "gates": gates,
    }
    terminal_status = {
        "PASS": "passed",
        "FAIL": "failed",
        "INCOMPLETE_SCALAR_SKIPPED": "incomplete_scalar_skipped",
    }[gates["probe1_verdict"]]
    seal_terminal(summary, terminal_status)
    print("\n" + "=" * 72)
    print("gates=" + json.dumps(gates, indent=2, default=str))
    print(f"PROBE 1 VERDICT: {gates['probe1_verdict']}")
    print(f"Wrote {root / 'probe1_summary.json'}")


if __name__ == "__main__":
    main()
