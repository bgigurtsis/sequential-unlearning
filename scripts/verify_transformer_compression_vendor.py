#!/usr/bin/env python3
"""Verify the pinned Microsoft TransformerCompression vendor import."""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
from pathlib import Path, PurePosixPath


UPSTREAM_URL = "https://github.com/microsoft/TransformerCompression.git"
UPSTREAM_COMMIT = "6b12cdee6ad51791d7c776b3a046bc408b9e77e9"
UPSTREAM_TREE = "b58f7a03ed03a968d6b763b29b100f2683e6dfd2"
EXPECTED_FILE_COUNT = 40
EXPECTED_BYTE_COUNT = 211_032
EXPECTED_MANIFEST_SHA256 = "ba3ee5f9788e4a5e937eabcac6beaeb3aef31746952b4c3ddca452b22fedc2a4"
EXPECTED_UPSTREAM_RECORD_SHA256 = "50fcbeabfa766a056f0c2594b5e84f8d01b307e8da722538ee483043e8d80893"
EXPECTED_LICENSE_SHA256 = "c2cfccb812fe482101a8f04597dfc5a9991a6b2748266c47ac91b6a5aae15383"
EXPECTED_EXECUTABLES = {
    "build_and_test.sh",
    "experiments/run_benchmark.py",
    "experiments/run_slicegpt.py",
    "src/slicegpt/data_utils.py",
    "src/slicegpt/hf_utils.py",
    "test.sh",
}
MANIFEST_LINE = re.compile(r"([0-9a-f]{64})  (.+)")


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def run_git(repo: Path, *args: str, binary: bool = False) -> bytes | str:
    command = ["git", "-c", f"safe.directory={repo.resolve().as_posix()}", "-C", str(repo), *args]
    try:
        output = subprocess.check_output(command)
    except (OSError, subprocess.CalledProcessError) as exc:
        fail(f"git command failed: {' '.join(command)}: {exc}")
    return output if binary else output.decode("utf-8").strip()


def read_manifest(path: Path) -> dict[str, str]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        fail(f"cannot read manifest {path}: {exc}")
    digest = hashlib.sha256(payload).hexdigest()
    if digest != EXPECTED_MANIFEST_SHA256:
        fail(
            "manifest bytes differ from the pinned official-source manifest: "
            f"{digest} != {EXPECTED_MANIFEST_SHA256}"
        )
    try:
        text = payload.decode("ascii")
    except UnicodeError as exc:
        fail(f"cannot read manifest {path}: {exc}")
    if b"\r" in payload or not payload.endswith(b"\n"):
        fail("manifest must use LF line endings and end with one newline")
    lines = text.splitlines()
    entries: dict[str, str] = {}
    for line_number, line in enumerate(lines, 1):
        match = MANIFEST_LINE.fullmatch(line)
        if not match:
            fail(f"non-canonical manifest line {line_number}")
        digest, relative = match.groups()
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts or "\\" in relative:
            fail(f"unsafe manifest path at line {line_number}: {relative!r}")
        if relative in entries:
            fail(f"duplicate manifest path: {relative}")
        entries[relative] = digest
    if list(entries) != sorted(entries):
        fail("manifest paths are not sorted")
    return entries


def source_files(source_root: Path) -> dict[str, Path]:
    files = {
        path.relative_to(source_root).as_posix(): path
        for path in source_root.rglob("*")
        if path.is_file()
    }
    return dict(sorted(files.items()))


def sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        fail(f"cannot read {path}: {exc}")


def verify_metadata(vendor_root: Path) -> None:
    upstream_record = vendor_root / "UPSTREAM.md"
    record_digest = sha256_file(upstream_record)
    if record_digest != EXPECTED_UPSTREAM_RECORD_SHA256:
        fail(
            "UPSTREAM.md differs from the pinned provenance record: "
            f"{record_digest} != {EXPECTED_UPSTREAM_RECORD_SHA256}"
        )
    license_digest = sha256_file(vendor_root / "source" / "LICENSE")
    if license_digest != EXPECTED_LICENSE_SHA256:
        fail(
            "upstream MIT license differs from the pinned complete text: "
            f"{license_digest} != {EXPECTED_LICENSE_SHA256}"
        )


def verify_index_modes(repo_root: Path, actual: dict[str, Path]) -> None:
    source_prefix = "vendor/TransformerCompression/source/"
    raw = run_git(
        repo_root,
        "ls-files",
        "--stage",
        "-z",
        "--",
        source_prefix,
        binary=True,
    )
    assert isinstance(raw, bytes)
    index: dict[str, tuple[str, str]] = {}
    for record in raw.split(b"\0"):
        if not record:
            continue
        metadata, encoded_path = record.split(b"\t", 1)
        mode, object_id, stage = metadata.decode("ascii").split(" ")
        path = encoded_path.decode("utf-8")
        if stage != "0":
            fail(f"vendor source has an unmerged index entry: {path} stage={stage}")
        if not path.startswith(source_prefix):
            fail(f"unexpected indexed vendor path: {path}")
        relative = path.removeprefix(source_prefix)
        if relative in index:
            fail(f"duplicate indexed vendor path: {relative}")
        index[relative] = (mode, object_id)

    if set(index) != set(actual):
        missing = sorted(set(actual) - set(index))
        extra = sorted(set(index) - set(actual))
        fail(f"Git index membership differs from source/; missing={missing}, extra={extra}")

    for relative, path in actual.items():
        expected_mode = "100755" if relative in EXPECTED_EXECUTABLES else "100644"
        mode, index_blob = index[relative]
        if mode != expected_mode:
            fail(f"vendored Git index mode mismatch: {relative}: {mode} != {expected_mode}")
        working_blob = run_git(repo_root, "hash-object", "--no-filters", str(path.resolve()))
        if index_blob != working_blob:
            fail(f"vendored Git index blob is stale: {relative}: {index_blob} != {working_blob}")


def verify_byte_preservation_attributes(repo_root: Path, actual: dict[str, Path]) -> None:
    source_prefix = "vendor/TransformerCompression/source/"
    paths = [
        *(f"{source_prefix}{relative}" for relative in actual),
        "vendor/TransformerCompression/SOURCE_SHA256SUMS",
        "vendor/TransformerCompression/UPSTREAM.md",
    ]
    for cached in (False, True):
        args = ["check-attr", "-z"]
        if cached:
            args.append("--cached")
        args.extend(["text", "--", *paths])
        raw = run_git(repo_root, *args, binary=True)
        assert isinstance(raw, bytes)
        fields = raw.split(b"\0")
        if fields and not fields[-1]:
            fields.pop()
        if len(fields) % 3:
            fail("git check-attr returned malformed output")
        records = {
            fields[index].decode("utf-8"): (
                fields[index + 1].decode("utf-8"),
                fields[index + 2].decode("utf-8"),
            )
            for index in range(0, len(fields), 3)
        }
        if set(records) != set(paths):
            fail("Git text-attribute membership differs from the vendored files")
        for path, (attribute, value) in records.items():
            if attribute != "text" or value != "unset":
                location = "cached" if cached else "working"
                fail(
                    f"vendored byte-preservation attribute mismatch ({location}): "
                    f"{path}: {attribute}={value}"
                )


def verify_local(vendor_root: Path) -> dict[str, Path]:
    source_root = vendor_root / "source"
    manifest = read_manifest(vendor_root / "SOURCE_SHA256SUMS")
    actual = source_files(source_root)
    if set(actual) != set(manifest):
        missing = sorted(set(manifest) - set(actual))
        extra = sorted(set(actual) - set(manifest))
        fail(f"source/ membership differs from manifest; missing={missing}, extra={extra}")
    if len(actual) != EXPECTED_FILE_COUNT:
        fail(f"expected {EXPECTED_FILE_COUNT} source files, found {len(actual)}")
    byte_count = 0
    for relative, path in actual.items():
        payload = path.read_bytes()
        byte_count += len(payload)
        digest = hashlib.sha256(payload).hexdigest()
        if digest != manifest[relative]:
            fail(f"SHA-256 mismatch: {relative}: {digest} != {manifest[relative]}")
    if byte_count != EXPECTED_BYTE_COUNT:
        fail(f"expected {EXPECTED_BYTE_COUNT} source bytes, found {byte_count}")
    return actual


def upstream_tree(repo: Path) -> dict[str, tuple[str, str]]:
    raw = run_git(repo, "ls-tree", "-r", "-z", "--full-tree", UPSTREAM_COMMIT, binary=True)
    assert isinstance(raw, bytes)
    entries: dict[str, tuple[str, str]] = {}
    for record in raw.split(b"\0"):
        if not record:
            continue
        metadata, encoded_path = record.split(b"\t", 1)
        mode, object_type, object_id = metadata.decode("ascii").split(" ")
        if object_type != "blob":
            fail(f"upstream tree has unsupported {object_type} entry: {encoded_path!r}")
        relative = encoded_path.decode("utf-8")
        entries[relative] = (mode, object_id)
    return entries


def verify_upstream(repo: Path, actual: dict[str, Path]) -> None:
    head = run_git(repo, "rev-parse", "HEAD")
    if head != UPSTREAM_COMMIT:
        fail(f"upstream checkout is not pinned at {UPSTREAM_COMMIT}; HEAD={head}")
    commit = run_git(repo, "rev-parse", UPSTREAM_COMMIT)
    tree = run_git(repo, "rev-parse", f"{UPSTREAM_COMMIT}^{{tree}}")
    remote = run_git(repo, "remote", "get-url", "origin")
    if commit != UPSTREAM_COMMIT:
        fail(f"upstream commit did not resolve to itself: {commit}")
    if tree != UPSTREAM_TREE:
        fail(f"upstream root tree mismatch: {tree} != {UPSTREAM_TREE}")
    normalized_remote = str(remote).removesuffix("/")
    if normalized_remote not in {UPSTREAM_URL, UPSTREAM_URL.removesuffix(".git")}:
        fail(f"unexpected upstream origin: {remote}")
    upstream = upstream_tree(repo)
    if set(upstream) != set(actual):
        missing = sorted(set(upstream) - set(actual))
        extra = sorted(set(actual) - set(upstream))
        fail(f"source/ differs from upstream paths; missing={missing}, extra={extra}")
    for relative, path in actual.items():
        _mode, expected_blob = upstream[relative]
        blob = run_git(repo, "hash-object", "--no-filters", str(path.resolve()))
        if blob != expected_blob:
            fail(f"upstream Git blob mismatch: {relative}: {blob} != {expected_blob}")
    for relative, (mode, _blob) in upstream.items():
        expected_mode = "100755" if relative in EXPECTED_EXECUTABLES else "100644"
        if mode != expected_mode:
            fail(f"upstream mode mismatch: {relative}: {mode} != {expected_mode}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--upstream-repo",
        type=Path,
        help="pinned official clone for commit/tree/path/blob/mode verification",
    )
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    vendor_root = repo_root / "vendor" / "TransformerCompression"
    verify_metadata(vendor_root)
    actual = verify_local(vendor_root)
    verify_byte_preservation_attributes(repo_root, actual)
    verify_index_modes(repo_root, actual)
    if args.upstream_repo is not None:
        verify_upstream(args.upstream_repo.resolve(), actual)
    print(
        "PASS: Microsoft TransformerCompression vendor verified "
        f"({len(actual)} files, {EXPECTED_BYTE_COUNT} bytes, commit {UPSTREAM_COMMIT}, "
        f"tree {UPSTREAM_TREE}, upstream={'yes' if args.upstream_repo else 'not requested'})"
    )


if __name__ == "__main__":
    main()
