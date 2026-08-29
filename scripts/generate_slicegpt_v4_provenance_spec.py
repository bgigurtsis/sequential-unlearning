#!/usr/bin/env python3
"""Derive the canonical Probe-2 v4 runtime provenance specification.

This generator accepts paths, never hashes or fingerprints.  Every identity is
derived from exact local bytes.  It refuses to produce a specification until
its own sources, the runtime lock, and every member of all five calibration
archives are clean committed HEAD blobs.  The resulting JSON must itself be
committed before the runtime qualifier will consume it.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping


GENERATOR_PATH = "scripts/generate_slicegpt_v4_provenance_spec.py"
TEST_PATH = "scripts/test_generate_slicegpt_v4_provenance_spec.py"
QUALIFIER_PATH = "scripts/qualify_slicegpt_runtime_v4.py"
MATERIALIZER_PATH = "scripts/materialize_slicegpt_calibration_v4.py"
PROTOCOL_VERSION = "slicegpt_v4_runtime_provenance_spec_v1"
CALIBRATION_SEEDS = (0, 1, 2, 7, 11)
MATERIALIZER_SOURCE_SHA256 = (
    "4f8a9b62d823677eb0fdec29b94e557279c5657d97077f360904e0680e479fcf"
)
ARCHIVE_FILES = (
    "MANIFEST.sha256",
    "calibration_metadata.json",
    "calibration.safetensors",
    "COMPLETE.json",
)
WEIGHT_SUFFIXES = (".safetensors", ".bin", ".pt", ".pth")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class GenerationError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise GenerationError(message)


def reject_json_aliases(value: Any, label: str = "JSON") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            fail(f"{label}: non-finite number")
        fail(f"{label}: floating-point identities are forbidden")
    if isinstance(value, list):
        for index, item in enumerate(value):
            reject_json_aliases(item, f"{label}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                fail(f"{label}: non-string object key")
            reject_json_aliases(item, f"{label}.{key}")
        return
    fail(f"{label}: unsupported value type {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    reject_json_aliases(value)
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
            separators=(",", ": "),
        )
        + "\n"
    ).encode("utf-8")


def fingerprint(value: Any) -> str:
    reject_json_aliases(value)
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_linklike(path: Path) -> bool:
    try:
        information = path.lstat()
    except FileNotFoundError:
        return False
    attributes = getattr(information, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(information.st_mode) or bool(attributes & reparse)


def lexical_path(path: Path, label: str, *, base: Path | None = None) -> Path:
    expanded = path.expanduser()
    if not expanded.is_absolute():
        expanded = (Path.cwd() if base is None else base) / expanded
    absolute = Path(os.path.abspath(expanded))
    for component in reversed((absolute, *absolute.parents)):
        if is_linklike(component):
            fail(f"{label}: symlink/junction/reparse ancestor forbidden: {component}")
    return absolute


def relative_to_repo(repo: Path, path: Path, label: str) -> str:
    path = lexical_path(path, label, base=repo)
    try:
        relative = path.relative_to(repo).as_posix()
    except ValueError:
        fail(f"{label}: must be inside repository")
    if not relative or relative.startswith("../") or "\\" in relative:
        fail(f"{label}: invalid repository-relative path")
    return relative


def declared_path(repo: Path, path: Path, label: str) -> str:
    """Return the qualifier's canonical relative-or-absolute declaration."""

    path = lexical_path(path, label, base=repo)
    try:
        return relative_to_repo(repo, path, label)
    except GenerationError:
        value = path.as_posix()
        if not path.is_absolute() or "\\" in value or any(
            part in {"", ".", ".."} for part in value.split("/")[1:]
        ):
            fail(f"{label}: cannot encode canonical absolute path")
        return value


def git(repo: Path, arguments: list[str], *, binary: bool = False) -> str | bytes:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=repo,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=not binary,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        fail(f"git {' '.join(arguments)} failed: {error}")
    return result.stdout


def committed_file(repo: Path, path: Path, head: str, label: str) -> tuple[str, str]:
    path = lexical_path(path, label, base=repo)
    if not path.is_file() or is_linklike(path):
        fail(f"{label}: regular file required")
    relative = relative_to_repo(repo, path, label)
    committed = git(repo, ["show", f"{head}:{relative}"], binary=True)
    assert isinstance(committed, bytes)
    live = path.read_bytes()
    if live != committed:
        fail(f"{label}: live bytes differ from committed HEAD blob")
    return relative, hashlib.sha256(live).hexdigest()


def exact_tree(root: Path, label: str) -> dict[str, str]:
    root = lexical_path(root, label)
    if not root.is_dir() or is_linklike(root):
        fail(f"{label}: exact regular directory required")
    files: dict[str, str] = {}
    directories: set[str] = set()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if is_linklike(path):
            fail(f"{label}: linklike member forbidden: {relative}")
        if path.is_file():
            files[relative] = sha256_file(path)
        elif path.is_dir():
            directories.add(relative)
        else:
            fail(f"{label}: unsupported member: {relative}")
    if not files:
        fail(f"{label}: tree is empty")
    expected_directories: set[str] = set()
    for relative in files:
        parts = relative.split("/")[:-1]
        for index in range(1, len(parts) + 1):
            expected_directories.add("/".join(parts[:index]))
    if directories != expected_directories:
        fail(f"{label}: empty or unbound directory membership changed")
    return files


def parse_manifest(path: Path, label: str) -> dict[str, str]:
    raw = path.read_bytes()
    if b"\r" in raw or not raw.endswith(b"\n"):
        fail(f"{label} must be LF canonical and newline-terminated")
    result: dict[str, str] = {}
    previous = ""
    for line in raw.decode("utf-8", errors="strict").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            fail(f"{label}: malformed line: {line!r}")
        digest, relative = match.groups()
        parts = relative.split("/")
        if (
            relative in result
            or (previous and relative <= previous)
            or relative.startswith("/")
            or "\\" in relative
            or re.match(r"^[A-Za-z]:", relative)
            or any(part in {"", ".", ".."} for part in parts)
        ):
            fail(f"{label} paths are duplicate, unsorted, or noncanonical")
        result[relative] = digest
        previous = relative
    if not result:
        fail(f"{label} is empty")
    return result


def load_qualifier(repo: Path, head: str) -> Any:
    path = repo / QUALIFIER_PATH
    _, digest = committed_file(repo, path, head, "runtime qualifier")
    name = f"_probe2_v4_runtime_qualifier_{digest}"
    if name in sys.modules:
        fail("preloaded runtime qualifier module is forbidden")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None or Path(str(spec.origin)).resolve() != path.resolve():
        fail("runtime qualifier source specification was substituted")
    module = importlib.util.module_from_spec(spec)
    source = path.read_bytes()
    exec(compile(source, str(path), "exec"), module.__dict__)
    if sha256_file(path) != digest:
        fail("runtime qualifier source changed during execution")
    required = {
        "PROTOCOL_VERSION", "UPSTREAM_COMMIT", "UPSTREAM_TREE", "VENDOR_MANIFEST_SHA256",
        "CALIBRATION_ARROW_SHA256", "CALIBRATION_METADATA_SHA256", "CALIBRATION_SEEDS",
        "PROTECTED_PROMPT_PATHS", "MANDATORY_COMMITTED_SOURCES", "MATERIALIZER_PATH",
        "validate_runtime_observation", "load_canonical_json", "_load_verified_materializer",
    }
    if any(not hasattr(module, item) for item in required):
        fail("runtime qualifier generator surface changed")
    return module


def bind_executed_generator(repo: Path, head: str) -> None:
    expected = lexical_path(repo / GENERATOR_PATH, "committed generator")
    executed = lexical_path(Path(__file__), "executed generator")
    if executed != expected:
        fail("executed generator path differs from repository canonical source")
    committed_file(repo, expected, head, "executed generator")


def committed_sources(
    repo: Path,
    head: str,
    qualifier: Any,
    runtime_lock: Path,
    archive_roots: Mapping[int, Path],
) -> dict[str, str]:
    required = set(qualifier.MANDATORY_COMMITTED_SOURCES) | set(qualifier.PROTECTED_PROMPT_PATHS)
    required |= {GENERATOR_PATH, TEST_PATH, relative_to_repo(repo, runtime_lock, "runtime lock")}
    for root in archive_roots.values():
        for name in ARCHIVE_FILES:
            required.add(relative_to_repo(repo, root / name, f"calibration archive {name}"))
    result: dict[str, str] = {}
    for relative in sorted(required):
        committed_relative, digest = committed_file(repo, repo / relative, head, f"committed source {relative}")
        result[committed_relative] = digest
    return result


def build_spec(
    *,
    repo: Path,
    runtime_lock: Path,
    archive_roots: Mapping[int, Path],
    source_arrow: Path,
    source_metadata: Path,
    parent_model: Path,
    clean_ruler: Path,
) -> dict[str, Any]:
    repo = lexical_path(repo, "repository")
    if not (repo / ".git").exists():
        fail("repository Git metadata is missing")
    head_value = git(repo, ["rev-parse", "HEAD"])
    assert isinstance(head_value, str)
    head = head_value.strip()
    if re.fullmatch(r"[0-9a-f]{40}", head) is None:
        fail("repository HEAD is not an exact commit")
    bind_executed_generator(repo, head)
    qualifier = load_qualifier(repo, head)
    if qualifier.PROTOCOL_VERSION != PROTOCOL_VERSION:
        fail("runtime qualifier provenance protocol changed")
    if qualifier.MATERIALIZER_PATH != MATERIALIZER_PATH:
        fail("runtime qualifier materializer path changed")
    expected_seeds = tuple(qualifier.CALIBRATION_SEEDS)
    if expected_seeds != CALIBRATION_SEEDS:
        fail("runtime qualifier calibration seed schedule changed")
    if set(archive_roots) != set(expected_seeds):
        fail(f"exact calibration seed set required: {expected_seeds}")
    archives = {
        seed: lexical_path(archive_roots[seed], f"calibration seed {seed}", base=repo)
        for seed in expected_seeds
    }
    if len(set(archives.values())) != len(expected_seeds):
        fail("calibration archive roots must be distinct")
    for seed, root in archives.items():
        relative = relative_to_repo(repo, root, f"calibration seed {seed}")
        if not relative.startswith("derisk/") or not root.is_dir() or is_linklike(root):
            fail(f"calibration seed {seed}: sealed archive must be a real directory under derisk")
        actual = {path.name for path in root.iterdir() if path.is_file() and not is_linklike(path)}
        if actual != set(ARCHIVE_FILES) or any(not path.is_file() or is_linklike(path) for path in root.iterdir()):
            fail(f"calibration seed {seed}: exact four-file archive layout changed")

    runtime_lock = lexical_path(runtime_lock, "runtime lock", base=repo)
    source_arrow = lexical_path(source_arrow, "calibration Arrow", base=repo)
    source_metadata = lexical_path(source_metadata, "calibration metadata", base=repo)
    parent_model = lexical_path(parent_model, "parent model", base=repo)
    clean_ruler = lexical_path(clean_ruler, "clean ruler", base=repo)
    sources = committed_sources(repo, head, qualifier, runtime_lock, archives)
    if sources.get(MATERIALIZER_PATH) != MATERIALIZER_SOURCE_SHA256:
        fail("committed calibration materializer source hash changed")

    lock_payload = qualifier.load_canonical_json(runtime_lock)
    qualifier.validate_runtime_observation(lock_payload)
    runtime_relative = relative_to_repo(repo, runtime_lock, "runtime lock")
    runtime_digest = sha256_file(runtime_lock)
    if sources.get(runtime_relative) != runtime_digest:
        fail("runtime lock is not the exact committed source blob")

    if sha256_file(source_arrow) != qualifier.CALIBRATION_ARROW_SHA256:
        fail("calibration Arrow hash differs from frozen protocol")
    if sha256_file(source_metadata) != qualifier.CALIBRATION_METADATA_SHA256:
        fail("calibration source metadata hash differs from frozen protocol")
    arrow_record = {
        "path": declared_path(repo, source_arrow, "calibration Arrow"),
        "sha256": qualifier.CALIBRATION_ARROW_SHA256,
    }
    metadata_record = {
        "path": declared_path(repo, source_metadata, "calibration metadata"),
        "sha256": qualifier.CALIBRATION_METADATA_SHA256,
    }

    parent_files = exact_tree(parent_model, "parent model")
    parent_weights = {name: digest for name, digest in parent_files.items() if name.endswith(WEIGHT_SUFFIXES)}
    parent_support = {name: digest for name, digest in parent_files.items() if name not in parent_weights}
    if not parent_weights or not parent_support:
        fail("parent model requires nonempty disjoint weight and support file sets")
    parent_payload = {
        "source": str(parent_model),
        "weight_file_sha256": parent_weights,
        "support_file_sha256": parent_support,
    }
    parent = {
        "root": declared_path(repo, parent_model, "parent model"),
        "weights_sha256": parent_weights,
        "support_sha256": parent_support,
        "fingerprint": fingerprint(parent_payload),
    }
    ruler_files = exact_tree(clean_ruler, "clean ruler")
    ruler = {
        "root": declared_path(repo, clean_ruler, "clean ruler"),
        "files_sha256": ruler_files,
        "fingerprint": fingerprint(ruler_files),
    }

    protected = {
        relative: sources[relative]
        for relative in qualifier.PROTECTED_PROMPT_PATHS
    }
    materializer = qualifier._load_verified_materializer(repo, sources)
    prompts, prompt_hashes = materializer.load_disjoint_prompts(repo)
    if not prompts or prompt_hashes != protected:
        fail("protected prompt source hashes/set do not match the materializer")

    archive_records: dict[str, dict[str, Any]] = {}
    identities: set[str] = set()
    tensors: set[str] = set()
    for seed in expected_seeds:
        root = archives[seed]
        declared_manifest = parse_manifest(
            root / "MANIFEST.sha256", f"calibration seed {seed} manifest"
        )
        expected_manifest = {
            name: sha256_file(root / name)
            for name in ARCHIVE_FILES
            if name != "MANIFEST.sha256"
        }
        if declared_manifest != expected_manifest:
            fail(f"calibration seed {seed}: manifest/member identity mismatch")
        metadata = materializer.validate_sealed_archive(
            root, repo=repo, runtime_lock_path=runtime_lock
        )
        if metadata is None or metadata.get("seed") != seed:
            fail(f"calibration seed {seed}: semantic validation/seed failed")
        if metadata["runtime"]["runtime_lock_sha256"] != runtime_digest:
            fail(f"calibration seed {seed}: runtime lock mismatch")
        if metadata["parent"]["weight_file_sha256"] != parent_weights or metadata["parent"]["support_file_sha256"] != parent_support:
            fail(f"calibration seed {seed}: parent tree mismatch")
        if metadata["parent"]["fingerprint"] != parent["fingerprint"]:
            fail(f"calibration seed {seed}: parent fingerprint mismatch")
        if metadata["disjointness"]["source_file_sha256"] != protected or metadata["disjointness"]["protected_prompt_count"] != len(prompts):
            fail(f"calibration seed {seed}: protected prompt identity mismatch")
        if metadata["dataset"]["source_cache_sha256"] != {
            "train_arrow": qualifier.CALIBRATION_ARROW_SHA256,
            "dataset_metadata": qualifier.CALIBRATION_METADATA_SHA256,
        }:
            fail(f"calibration seed {seed}: source cache identity mismatch")
        identities.add(fingerprint(metadata["source_identity"]))
        tensor_digest = metadata["tensors"]["sha256"]
        if not isinstance(tensor_digest, str) or HEX64.fullmatch(tensor_digest) is None:
            fail(f"calibration seed {seed}: invalid tensor digest")
        tensors.add(tensor_digest)
        metadata_fingerprint = metadata["fingerprint"]
        if not isinstance(metadata_fingerprint, str) or HEX64.fullmatch(metadata_fingerprint) is None:
            fail(f"calibration seed {seed}: invalid metadata fingerprint")
        archive_records[str(seed)] = {
            "root": relative_to_repo(repo, root, f"calibration seed {seed}"),
            "manifest_sha256": sha256_file(root / "MANIFEST.sha256"),
            "metadata_sha256": sha256_file(root / "calibration_metadata.json"),
            "tensors_sha256": sha256_file(root / "calibration.safetensors"),
            "complete_sha256": sha256_file(root / "COMPLETE.json"),
            "metadata_fingerprint": metadata_fingerprint,
        }
        if archive_records[str(seed)]["tensors_sha256"] != metadata["tensors"]["sha256"]:
            fail(f"calibration seed {seed}: tensor hash mismatch")
    if len(identities) != 1 or len(tensors) != len(expected_seeds):
        fail("calibration archives do not share one source identity and five distinct tensors")

    vendor_manifest = repo / "vendor/TransformerCompression/SOURCE_SHA256SUMS"
    if sha256_file(vendor_manifest) != qualifier.VENDOR_MANIFEST_SHA256:
        fail("vendor manifest hash differs from frozen qualifier")
    vendor_hashes = parse_manifest(vendor_manifest, "vendor manifest")
    vendor_root = repo / "vendor/TransformerCompression/source"
    if exact_tree(vendor_root, "vendor source") != vendor_hashes:
        fail("vendor source tree differs from frozen manifest")
    vendor = {
        "commit": qualifier.UPSTREAM_COMMIT,
        "tree": qualifier.UPSTREAM_TREE,
        "root": "vendor/TransformerCompression/source",
        "manifest_path": "vendor/TransformerCompression/SOURCE_SHA256SUMS",
        "manifest_sha256": qualifier.VENDOR_MANIFEST_SHA256,
        "source_sha256": vendor_hashes,
    }
    calibration_base = {
        "archives": archive_records,
        "source_arrow": arrow_record,
        "source_metadata": metadata_record,
        "protected_prompt_sha256": protected,
    }
    return {
        "version": qualifier.PROTOCOL_VERSION,
        "committed_sources": sources,
        "runtime_lock": {"path": runtime_relative, "sha256": runtime_digest},
        "vendor": vendor,
        "calibration": {**calibration_base, "fingerprint": fingerprint(calibration_base)},
        "parent_model": parent,
        "clean_ruler": ruler,
    }


def write_spec(output: Path, spec: Mapping[str, Any], repo: Path) -> Path:
    repo = lexical_path(repo, "repository")
    output = lexical_path(output, "provenance output", base=repo)
    derisk = lexical_path(repo / "derisk", "derisk root")
    if derisk not in output.parents or output.suffix != ".json":
        fail("provenance output must be a JSON file below repository derisk")
    data = canonical_json_bytes(dict(spec))
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        if is_linklike(output) or not output.is_file() or output.read_bytes() != data:
            fail("existing provenance output differs; refusing replacement")
        return output
    temporary = output.with_name(output.name + ".tmp")
    if temporary.exists() or is_linklike(temporary):
        fail("partial provenance output already exists")
    with temporary.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.link(temporary, output)
    except FileExistsError:
        fail("provenance output appeared concurrently; refusing replacement")
    temporary.unlink()
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--runtime-lock", required=True)
    parser.add_argument("--calibration", action="append", required=True, metavar="SEED=ROOT")
    parser.add_argument("--source-arrow", required=True)
    parser.add_argument("--source-metadata", required=True)
    parser.add_argument("--parent-model", required=True)
    parser.add_argument("--clean-ruler", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    archives: dict[int, Path] = {}
    for item in args.calibration:
        seed_text, separator, root = item.partition("=")
        if not separator or re.fullmatch(r"(?:0|1|2|7|11)", seed_text) is None or int(seed_text) in archives:
            fail(f"invalid/duplicate --calibration entry: {item!r}")
        archives[int(seed_text)] = Path(root)
    repo = Path(args.repo)
    spec = build_spec(
        repo=repo,
        runtime_lock=Path(args.runtime_lock),
        archive_roots=archives,
        source_arrow=Path(args.source_arrow),
        source_metadata=Path(args.source_metadata),
        parent_model=Path(args.parent_model),
        clean_ruler=Path(args.clean_ruler),
    )
    path = write_spec(Path(args.output), spec, repo)
    print(f"Canonical v4 provenance specification generated: {path}")
    print("Commit this exact JSON before invoking the runtime qualifier.")


if __name__ == "__main__":
    main()
