"""Fail-closed launch boundary for the predeclared Probe 2 SliceGPT v4 pilot.

The v4 scientific protocol is frozen, but its mandatory Gemma-3 adapter,
calibration materialization, serialization/PEFT compatibility and environment
qualification gates are not yet sealed.  This module deliberately has no
model-mutation path.  It records that adapter-readiness gap in a small
immutable archive and can never emit a Probe 2 verdict.

Once every mandatory qualification gate is sealed, replace this blocked path
with the independently audited Gemma-3 SliceGPT implementation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
from pathlib import Path


VERSION = "probe2_slicegpt_dial_pilot_v4_adapter_boundary_v2"
PILOT_SEED = 11
FRACTIONS = (
    0.05,
    0.10,
    0.15,
    0.20,
    0.25,
    0.30,
    0.35,
    0.40,
    0.50,
    0.60,
    0.70,
    0.80,
)
RETAINED_DIMENSIONS = (2432, 2304, 2176, 2048, 1920, 1792, 1664, 1536, 1280, 1024, 768, 512)
VENDOR_UPSTREAM = {
    "url": "https://github.com/microsoft/TransformerCompression.git",
    "commit": "6b12cdee6ad51791d7c776b3a046bc408b9e77e9",
    "root_tree": "b58f7a03ed03a968d6b763b29b100f2683e6dfd2",
    "file_count": 40,
    "byte_count": 211032,
    "manifest_sha256": "ba3ee5f9788e4a5e937eabcac6beaeb3aef31746952b4c3ddca452b22fedc2a4",
    "upstream_record_sha256": "50fcbeabfa766a056f0c2594b5e84f8d01b307e8da722538ee483043e8d80893",
    "license_sha256": "c2cfccb812fe482101a8f04597dfc5a9991a6b2748266c47ac91b6a5aae15383",
}
SEED_POLICY = {
    "diagnostic_calibration": 11,
    "fresh_primary_calibration": [0, 1, 2],
    "heavy_parent_calibration": 7,
    "heavy_child_calibration": [0, 1, 2],
    "scalar_decoding_and_clean_judge": 0,
}
SOURCE_PATHS = (
    "scripts/run_slicegpt_pilot_v4.py",
    "scripts/check_slicegpt_gemma3_zero_slice.py",
    "scripts/slicegpt_gemma3_math_v4.py",
    "scripts/test_slicegpt_pilot_v4.py",
    "scripts/verify_transformer_compression_vendor.py",
)
EVIDENCE_PATHS = (
    ".gitattributes",
    "EXPERIMENTS.md",
    "requirements.txt",
    "docs/litreview/SYNTHESIS.md",
    "docs/litreview/notes/ashkboos-2024-slicegpt.md",
    "docs/V4_SLICEGPT_PROTOCOL.md",
    "vendor/TransformerCompression/UPSTREAM.md",
    "vendor/TransformerCompression/SOURCE_SHA256SUMS",
)
COMMITTED_PATHS = SOURCE_PATHS + EVIDENCE_PATHS
ARCHIVE_MEMBERS = {
    "run_config.json",
    "adapter_blocked.json",
    "COMPLETE.json",
}
MANIFEST_NAME = "MANIFEST.sha256"
PROTOCOL_SPEC_DEFAULT = "docs/V4_SLICEGPT_PROTOCOL.md"


BLOCKERS = (
    {
        "code": "UNQUALIFIED_GEMMA3_ADAPTER",
        "missing": (
            "audited Gemma-3 sandwich-norm compressed layer and arbitrary-rotation implementation"
        ),
        "why_required": (
            "upstream SliceGPT does not list Gemma or Gemma-3 as a supported model"
        ),
    },
    {
        "code": "UNSEALED_ADAPTER_EQUIVALENCE",
        "missing": (
            "all six frozen adapter-qualification gates, including FP64 algebra, full "
            "196-prompt extraction, BF16 logits/scalar, cache paths and protected q/k norms"
        ),
        "why_required": (
            "any miss is adapter INCOMPLETE and no fraction above zero may run"
        ),
    },
    {
        "code": "UNMATERIALIZED_CALIBRATION_TENSORS",
        "missing": (
            "committed exact ordered WikiText-2 input_ids/attention masks and disjointness manifest"
        ),
        "why_required": "the protocol requires this immutable pre-data artifact before slicing",
    },
    {
        "code": "UNQUALIFIED_NATIVE_SERIALIZATION",
        "missing": (
            "bit-identical native Safetensors save/load roundtrip with custom slicing metadata"
        ),
        "why_required": "upstream state_dict plus JSON is forbidden by the frozen protocol",
    },
    {
        "code": "UNQUALIFIED_PEFT_AND_PROJECT_LOADER",
        "missing": (
            "shared evaluator/trainer/merger loader and one-step seven-module LoRA smoke"
        ),
        "why_required": (
            "Probe 1/3 and the lineage must train, merge, hash and reload sliced parents"
        ),
    },
    {
        "code": "UNSEALED_RUNTIME_LOCK",
        "missing": (
            "hashed v4 environment lock and proof of deterministic CUDA settings on the launch host"
        ),
        "why_required": "determinism failure is operational INCOMPLETE",
    },
)


def reject_symlink_components(path: Path, label: str, base: Path | None = None) -> Path:
    """Return an absolute lexical path after rejecting every symlink component.

    ``Path.resolve()`` follows links and therefore cannot be used before this
    check.  The returned path is absolute and normalized but deliberately not
    resolved through the filesystem.
    """
    path = Path(path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path if base is None else Path(base) / path
    lexical = Path(os.path.abspath(path))
    for component in reversed((lexical, *lexical.parents)):
        if component.is_symlink():
            raise RuntimeError(f"{label} contains a symlink component: {component}")
    return lexical


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="derisk/probe2_slicegpt_v4_adapter_block")
    parser.add_argument("--protocol-spec", default=PROTOCOL_SPEC_DEFAULT)
    return parser.parse_args()


def sha256_of_file(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while block := handle.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def _reject_nonfinite(value: object, label: str = "JSON") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise RuntimeError(f"{label} contains a non-finite number")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise RuntimeError(f"{label} contains a non-string object key")
            _reject_nonfinite(child, label)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _reject_nonfinite(child, label)


def canonical_bytes(payload: object) -> bytes:
    _reject_nonfinite(payload)
    return (
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def fingerprint(payload: object) -> str:
    _reject_nonfinite(payload)
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def read_json(path: Path) -> object:
    def reject_constant(value: str) -> object:
        raise RuntimeError(f"non-finite JSON constant: {value}")

    payload = json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=reject_constant)
    _reject_nonfinite(payload, str(path))
    return payload


def atomic_write_json(path: Path, payload: object) -> None:
    path = reject_symlink_components(path, "v4 JSON output")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if path.is_symlink() or temporary.is_symlink():
        raise RuntimeError("v4 JSON output must not be a symlink")
    temporary.write_bytes(canonical_bytes(payload))
    temporary.replace(path)


def recover_or_write_json(path: Path, payload: object) -> None:
    """Recover only the exact atomic-write crash image; never overwrite drift."""
    path = reject_symlink_components(path, "partial v4 JSON member")
    expected = canonical_bytes(payload)
    temporary = path.with_name(path.name + ".tmp")
    if path.is_symlink() or temporary.is_symlink():
        raise RuntimeError("partial v4 JSON member must not be a symlink")
    if path.exists():
        if path.read_bytes() != expected:
            raise RuntimeError(f"partial v4 archive member changed: {path.name}")
        if temporary.exists():
            if temporary.read_bytes() != expected:
                raise RuntimeError(f"partial v4 temporary member changed: {temporary.name}")
            temporary.unlink()
        return
    if temporary.exists():
        if temporary.read_bytes() != expected:
            raise RuntimeError(f"partial v4 temporary member changed: {temporary.name}")
        temporary.replace(path)
        return
    atomic_write_json(path, payload)


def committed_source_identity(
    repo: Path,
    relative_paths: tuple[str, ...] = COMMITTED_PATHS,
    expected_commit: str | None = None,
) -> dict:
    repo = Path(repo).resolve()
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise RuntimeError("v4 boundary cannot bind to a valid Git HEAD")
    if expected_commit is not None and commit != expected_commit:
        raise RuntimeError("v4 boundary Git HEAD changed")
    hashes = {}
    for relative in relative_paths:
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise RuntimeError(f"invalid committed v4 path: {relative}")
        current_path = reject_symlink_components(
            repo / relative_path, f"committed v4 path {relative}"
        )
        if not current_path.is_file():
            raise RuntimeError(f"v4 source is not a regular file: {relative}")
        try:
            committed = subprocess.run(
                ["git", "show", f"{commit}:{relative}"],
                cwd=repo,
                check=True,
                capture_output=True,
            ).stdout
        except subprocess.CalledProcessError as error:
            raise RuntimeError(f"v4 source is not committed at HEAD: {relative}") from error
        committed_oid = subprocess.check_output(
            ["git", "rev-parse", f"{commit}:{relative}"], cwd=repo, text=True
        ).strip()
        current_oid = subprocess.check_output(
            ["git", "hash-object", "--path", relative, relative], cwd=repo, text=True
        ).strip()
        if committed_oid != current_oid:
            raise RuntimeError(f"v4 source differs from its HEAD blob: {relative}")
        hashes[relative] = hashlib.sha256(committed).hexdigest()
    return {"commit": commit, "sha256": hashes}


def validate_recorded_source_identity(
    repo: Path, identity: object, relative_paths: tuple[str, ...] = COMMITTED_PATHS
) -> None:
    if not isinstance(identity, dict):
        raise RuntimeError("malformed v4 source identity")
    commit, hashes = identity.get("commit"), identity.get("sha256")
    if (
        re.fullmatch(r"[0-9a-f]{40}", str(commit)) is None
        or not isinstance(hashes, dict)
        or set(hashes) != set(relative_paths)
    ):
        raise RuntimeError("malformed v4 source identity")
    for relative in relative_paths:
        if re.fullmatch(r"[0-9a-f]{64}", str(hashes.get(relative))) is None:
            raise RuntimeError("malformed v4 source identity")
        try:
            blob = subprocess.run(
                ["git", "show", f"{commit}:{relative}"],
                cwd=Path(repo).resolve(),
                check=True,
                capture_output=True,
            ).stdout
        except subprocess.CalledProcessError as error:
            raise RuntimeError(f"recorded v4 source commit lacks {relative}") from error
        if hashlib.sha256(blob).hexdigest() != hashes[relative]:
            raise RuntimeError(f"recorded v4 source hash changed: {relative}")


def validate_frozen_boundary(repo: Path) -> dict[str, str]:
    repo = Path(repo).resolve()
    experiment_text = (repo / "EXPERIMENTS.md").read_text(encoding="utf-8")
    expected_grid = "[.05,.10,.15,.20,.25,.30,.35,.40,.50,.60,.70,.80]"
    if expected_grid not in experiment_text:
        raise RuntimeError("the frozen SliceGPT v4 fraction grid changed")
    if "Layer targeting or blended mechanisms are not added post hoc." not in experiment_text:
        raise RuntimeError("the frozen separate-dial/no-blending boundary changed")
    protocol_text = (repo / PROTOCOL_SPEC_DEFAULT).read_text(encoding="utf-8")
    required_protocol_declarations = (
        "diagnostic calibration seed **11**",
        "fresh primary seeds **0/1/2**",
        "one-shot heavy-parent seed **7**",
        "constant residual-width scheduler",
        "round_interval=8",
        "No fraction above zero may run until all of the following are sealed",
    )
    if any(text not in protocol_text for text in required_protocol_declarations):
        raise RuntimeError("the committed v4 protocol declarations changed")
    for fraction, dimension in zip(FRACTIONS, RETAINED_DIMENSIONS):
        row = f"| {fraction:.2f} | {dimension} |".replace("| 0.", "| .")
        if row not in protocol_text:
            raise RuntimeError(f"the frozen v4 fraction/dimension row changed: {row}")
    for relative in EVIDENCE_PATHS:
        path = reject_symlink_components(
            repo / relative, f"v4 protocol evidence {relative}"
        )
        if not path.is_file():
            raise RuntimeError(f"missing v4 protocol evidence: {relative}")
    return {relative: sha256_of_file(repo / relative) for relative in EVIDENCE_PATHS}


def validate_vendored_upstream(repo: Path) -> dict:
    """Run the committed local vendor verifier and return its frozen identity."""
    try:
        import verify_transformer_compression_vendor as verifier

        if (
            verifier.UPSTREAM_URL != VENDOR_UPSTREAM["url"]
            or verifier.UPSTREAM_COMMIT != VENDOR_UPSTREAM["commit"]
            or verifier.UPSTREAM_TREE != VENDOR_UPSTREAM["root_tree"]
            or verifier.EXPECTED_FILE_COUNT != VENDOR_UPSTREAM["file_count"]
            or verifier.EXPECTED_BYTE_COUNT != VENDOR_UPSTREAM["byte_count"]
            or verifier.EXPECTED_MANIFEST_SHA256 != VENDOR_UPSTREAM["manifest_sha256"]
            or verifier.EXPECTED_UPSTREAM_RECORD_SHA256
            != VENDOR_UPSTREAM["upstream_record_sha256"]
            or verifier.EXPECTED_LICENSE_SHA256 != VENDOR_UPSTREAM["license_sha256"]
        ):
            raise RuntimeError("v4 boundary and vendor verifier identities differ")
        vendor_root = Path(repo) / "vendor" / "TransformerCompression"
        verifier.verify_metadata(vendor_root)
        actual = verifier.verify_local(vendor_root)
        verifier.verify_byte_preservation_attributes(Path(repo), actual)
        verifier.verify_index_modes(Path(repo), actual)
    except SystemExit as error:
        raise RuntimeError(f"vendored TransformerCompression verification failed: {error}") from error
    return dict(VENDOR_UPSTREAM)


def build_config(repo: Path, source_identity: dict, protocol_spec: Path) -> dict:
    repo = Path(repo).resolve()
    protocol_spec = Path(protocol_spec)
    if not protocol_spec.is_absolute():
        protocol_spec = repo / protocol_spec
    protocol_spec = reject_symlink_components(protocol_spec, "v4 protocol spec")
    canonical_protocol_spec = (repo / PROTOCOL_SPEC_DEFAULT).resolve()
    if protocol_spec.resolve() != canonical_protocol_spec:
        raise RuntimeError("v4 protocol spec path must be the canonical repository path")
    if not protocol_spec.is_file() or protocol_spec.is_symlink():
        raise RuntimeError("the committed canonical v4 protocol freeze is missing")
    body = {
        "version": VERSION,
        "certification_scope": "adapter_qualification_only_not_a_pilot_or_probe2_verdict",
        "fixed_fraction_grid": list(FRACTIONS),
        "fixed_retained_dimensions": list(RETAINED_DIMENSIONS),
        "seed_policy": SEED_POLICY,
        "mechanism": "SliceGPT_structural_slicing_separate_dial",
        "post_result_layer_targeting": False,
        "post_result_mechanism_blending": False,
        "scalar_instrument": "unchanged_sealed_v2_ruler_and_unlimited_scalar_battery",
        "protocol_spec_expected_path": PROTOCOL_SPEC_DEFAULT,
        "protocol_spec_present": True,
        "vendor_upstream": validate_vendored_upstream(repo),
        "evidence_sha256": {},
        "source_identity": source_identity,
    }
    validate_frozen_boundary(repo)
    body["evidence_sha256"] = {
        relative: source_identity["sha256"][relative] for relative in EVIDENCE_PATHS
    }
    body["fingerprint"] = fingerprint(body)
    return body


def _expected_report(config: dict) -> dict:
    return {
        "version": VERSION,
        "status": "BLOCKED_ADAPTER_QUALIFICATION",
        "config_fingerprint": config["fingerprint"],
        "blockers": list(BLOCKERS),
        "gpu_work_launched": False,
        "model_mutated": False,
        "probe2_verdict": None,
        "pilot_outcome": None,
        "explicitly_not_a_pass_verdict": True,
        "next_step": (
            "seal every mandatory adapter qualification gate and calibration artifact, "
            "then use a fresh v4 diagnostic-pilot root"
        ),
    }


def _manifest_entries(root: Path) -> dict[str, str]:
    excluded = {root / MANIFEST_NAME}
    return {
        path.relative_to(root).as_posix(): sha256_of_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path not in excluded
    }


def _manifest_bytes(entries: dict[str, str]) -> bytes:
    return (
        "\n".join(f"{digest}  {relative}" for relative, digest in entries.items())
        + "\n"
    ).encode("ascii")


def write_manifest(root: Path) -> None:
    root = reject_symlink_components(root, "v4 blocker archive root").resolve()
    temporary = root / (MANIFEST_NAME + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise RuntimeError("v4 blocker manifest temporary already exists")
    if any(path.is_symlink() or path.is_dir() for path in root.rglob("*")):
        raise RuntimeError("v4 blocker archive contains a symlink or directory")
    actual = _manifest_entries(root)
    if set(actual) != ARCHIVE_MEMBERS:
        raise RuntimeError("v4 blocker archive has an unexpected pre-manifest layout")
    temporary.write_bytes(_manifest_bytes(actual))
    temporary.replace(root / MANIFEST_NAME)


def verify_manifest(root: Path) -> bool:
    supplied_root = reject_symlink_components(root, "sealed v4 archive root")
    root = supplied_root.resolve()
    manifest = root / MANIFEST_NAME
    if not manifest.is_file():
        return False
    expected: dict[str, str] = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, separator, relative = line.partition("  ")
        relative_path = Path(relative)
        if (
            not separator
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or relative_path.is_absolute()
            or ".." in relative_path.parts
            or relative_path.as_posix() in expected
        ):
            raise RuntimeError(f"malformed v4 manifest line: {line!r}")
        expected[relative_path.as_posix()] = digest
    forbidden_layout = [
        path
        for path in root.rglob("*")
        if path.is_symlink() or path.is_dir()
    ]
    if forbidden_layout:
        raise RuntimeError("sealed v4 protocol-block archive changed")
    actual = _manifest_entries(root)
    if (
        set(actual) != ARCHIVE_MEMBERS
        or expected != actual
        or manifest.read_bytes() != _manifest_bytes(actual)
    ):
        raise RuntimeError("sealed v4 protocol-block archive changed")
    return True


def validate_sealed_archive(root: Path, repo: Path | None = None) -> dict | None:
    supplied_root = reject_symlink_components(root, "sealed v4 archive root")
    if not verify_manifest(supplied_root):
        return None
    root = supplied_root.resolve()
    config = read_json(root / "run_config.json")
    report = read_json(root / "adapter_blocked.json")
    complete = read_json(root / "COMPLETE.json")
    if not all(isinstance(item, dict) for item in (config, report, complete)):
        raise RuntimeError("sealed v4 blocker archive contains non-object JSON")
    config_body = {key: value for key, value in config.items() if key != "fingerprint"}
    expected_config_keys = {
        "version",
        "certification_scope",
        "fixed_fraction_grid",
        "fixed_retained_dimensions",
        "seed_policy",
        "mechanism",
        "post_result_layer_targeting",
        "post_result_mechanism_blending",
        "scalar_instrument",
        "protocol_spec_expected_path",
        "protocol_spec_present",
        "vendor_upstream",
        "evidence_sha256",
        "source_identity",
        "fingerprint",
    }
    expected_complete = {
        "status": "complete",
        "outcome": "BLOCKED_ADAPTER_QUALIFICATION",
        "config_fingerprint": config.get("fingerprint"),
        "report_sha256": sha256_of_file(root / "adapter_blocked.json"),
    }
    if (
        set(config) != expected_config_keys
        or config.get("version") != VERSION
        or config.get("certification_scope")
        != "adapter_qualification_only_not_a_pilot_or_probe2_verdict"
        or config.get("fixed_fraction_grid") != list(FRACTIONS)
        or config.get("fixed_retained_dimensions") != list(RETAINED_DIMENSIONS)
        or config.get("seed_policy") != SEED_POLICY
        or config.get("mechanism") != "SliceGPT_structural_slicing_separate_dial"
        or config.get("post_result_layer_targeting") is not False
        or config.get("post_result_mechanism_blending") is not False
        or config.get("scalar_instrument")
        != "unchanged_sealed_v2_ruler_and_unlimited_scalar_battery"
        or config.get("protocol_spec_expected_path") != PROTOCOL_SPEC_DEFAULT
        or config.get("protocol_spec_present") is not True
        or config.get("vendor_upstream") != VENDOR_UPSTREAM
        or not isinstance(config.get("evidence_sha256"), dict)
        or set(config.get("evidence_sha256", {})) != set(EVIDENCE_PATHS)
        or any(
            re.fullmatch(r"[0-9a-f]{64}", str(value)) is None
            for value in config.get("evidence_sha256", {}).values()
        )
        or config.get("fingerprint") != fingerprint(config_body)
        or report != _expected_report(config)
        or complete != expected_complete
    ):
        raise RuntimeError("sealed v4 protocol-block semantics changed")
    identity = config.get("source_identity")
    if (
        not isinstance(identity, dict)
        or set(identity) != {"commit", "sha256"}
        or re.fullmatch(r"[0-9a-f]{40}", str(identity.get("commit"))) is None
        or not isinstance(identity.get("sha256"), dict)
        or set(identity.get("sha256", {})) != set(COMMITTED_PATHS)
        or any(
            re.fullmatch(r"[0-9a-f]{64}", str(value)) is None
            for value in identity.get("sha256", {}).values()
        )
    ):
        raise RuntimeError("sealed v4 protocol-block source identity is malformed")
    if any(
        config["evidence_sha256"][relative]
        != identity["sha256"][relative]
        for relative in EVIDENCE_PATHS
    ):
        raise RuntimeError("sealed v4 evidence is not bound to its committed blobs")
    if repo is not None:
        validate_recorded_source_identity(repo, config.get("source_identity"))
        if validate_vendored_upstream(repo) != config.get("vendor_upstream"):
            raise RuntimeError("sealed v4 vendor identity changed")
    return report


def seal_blocked_archive(root: Path, config: dict) -> dict:
    supplied_root = reject_symlink_components(root, "v4 blocker root")
    root = supplied_root.resolve()
    sealed = validate_sealed_archive(root)
    if sealed is not None:
        return sealed
    root.mkdir(parents=True, exist_ok=True)
    manifest = root / MANIFEST_NAME
    temporary_manifest = root / (MANIFEST_NAME + ".tmp")
    if manifest.exists():
        raise RuntimeError("invalid v4 manifest was not replaced")
    if temporary_manifest.exists() or temporary_manifest.is_symlink():
        raise RuntimeError("v4 blocker manifest temporary was preserved fail-closed")
    allowed_partial = ARCHIVE_MEMBERS
    allowed_partial_with_temporaries = allowed_partial | {
        member + ".tmp" for member in allowed_partial
    }
    unexpected = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path != temporary_manifest
    } - allowed_partial_with_temporaries
    if unexpected:
        raise RuntimeError(f"v4 blocker root contains unexpected files: {sorted(unexpected)}")
    if any(path.is_symlink() or path.is_dir() for path in root.rglob("*")):
        raise RuntimeError("v4 blocker root contains a symlink or directory")

    config_path = root / "run_config.json"
    recover_or_write_json(config_path, config)

    report = _expected_report(config)
    report_path = root / "adapter_blocked.json"
    recover_or_write_json(report_path, report)

    complete = {
        "status": "complete",
        "outcome": "BLOCKED_ADAPTER_QUALIFICATION",
        "config_fingerprint": config["fingerprint"],
        "report_sha256": sha256_of_file(report_path),
    }
    complete_path = root / "COMPLETE.json"
    recover_or_write_json(complete_path, complete)
    write_manifest(root)
    return validate_sealed_archive(root)


def main() -> None:
    args = parse_args()
    repo = Path.cwd().resolve()
    supplied_root = reject_symlink_components(args.root, "v4 blocker root", base=repo)
    root = supplied_root.resolve()
    derisk = (repo / "derisk").resolve()
    if root == derisk or derisk not in root.parents:
        raise RuntimeError("v4 blocker root must be a child of the repository derisk directory")
    sealed = validate_sealed_archive(root, repo=repo)
    if sealed is not None:
        print("Immutable v4 readiness outcome: BLOCKED_ADAPTER_QUALIFICATION")
        return
    source_identity = committed_source_identity(repo)
    config = build_config(repo, source_identity, Path(args.protocol_spec))
    seal_blocked_archive(root, config)
    print("V4 READYNESS: BLOCKED_ADAPTER_QUALIFICATION")
    print("No GPU work was launched and no Probe 2 verdict was emitted.")


if __name__ == "__main__":
    main()
