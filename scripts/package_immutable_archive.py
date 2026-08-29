#!/usr/bin/env python3
"""Create and verify deterministic split-tar packages for sealed archives.

The source archive is read-only.  A package is written through a sibling
``.pending`` directory, fully verified, and only then atomically renamed.
Existing packages are verification-only and are never rewritten.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tarfile
from typing import BinaryIO


BUFFER_SIZE = 8 * 1024 * 1024
DEFAULT_CHUNK_SIZE = 1_000_000_000
MAX_RELEASE_CHUNK_SIZE = 2_000_000_000
MANIFEST_NAME = "MANIFEST.sha256"
PACKAGE_JSON = "PACKAGE.json"
PACKAGE_MANIFEST = "PACKAGE.sha256"
PART_PREFIX = "archive.tar.part"
SHA256_RE = re.compile(r"[0-9a-f]{64}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(BUFFER_SIZE):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def absolute_without_resolving(path: Path) -> Path:
    return Path(os.path.abspath(path))


def reject_symlink_ancestors(path: Path, *, include_leaf: bool = True) -> None:
    current = absolute_without_resolving(path if include_leaf else path.parent)
    while True:
        if is_linklike(current):
            raise ValueError(f"symlink/reparse ancestor is forbidden: {current}")
        parent = current.parent
        if parent == current:
            break
        current = parent


def is_linklike(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except (FileNotFoundError, OSError):
        return False
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
        return True
    attributes = getattr(metadata, "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def safe_relative_path(raw: str) -> Path:
    if not raw or "\\" in raw or "\x00" in raw:
        raise ValueError(f"unsafe manifest path: {raw!r}")
    posix = PurePosixPath(raw)
    if posix.is_absolute() or any(part in ("", ".", "..") for part in posix.parts):
        raise ValueError(f"unsafe manifest path: {raw!r}")
    canonical = posix.as_posix()
    if raw != canonical:
        raise ValueError(f"non-canonical manifest path: {raw!r}")
    if len(raw.encode("utf-8")) > 100:
        raise ValueError(f"path exceeds deterministic GNU-tar name field: {raw!r}")
    return Path(*posix.parts)


def parse_manifest_bytes(data: bytes) -> dict[str, str]:
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("source manifest must be ASCII") from exc
    if "\r" in text or not text.endswith("\n"):
        raise ValueError("source manifest must end with a newline")
    entries: dict[str, str] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        if len(line) < 67 or line[64:66] != "  ":
            raise ValueError(f"malformed manifest line {line_number}")
        digest, raw_path = line[:64], line[66:]
        if not SHA256_RE.fullmatch(digest):
            raise ValueError(f"invalid SHA-256 on manifest line {line_number}")
        relative = safe_relative_path(raw_path).as_posix()
        if relative == MANIFEST_NAME or relative in entries:
            raise ValueError(f"duplicate/reserved manifest path: {relative}")
        entries[relative] = digest
    if not entries:
        raise ValueError("source manifest is empty")
    canonical = "".join(f"{entries[path]}  {path}\n" for path in sorted(entries))
    if text != canonical:
        raise ValueError("source manifest is not in canonical sorted form")
    return entries


def inspect_source(root: Path) -> tuple[dict[str, str], bytes]:
    reject_symlink_ancestors(root)
    if is_linklike(root) or not root.is_dir():
        raise ValueError("source must be a real directory, not a symlink")
    manifest_path = root / MANIFEST_NAME
    if is_linklike(manifest_path) or not manifest_path.is_file():
        raise ValueError(f"missing regular {MANIFEST_NAME}")
    manifest_bytes = manifest_path.read_bytes()
    entries = parse_manifest_bytes(manifest_bytes)

    actual: set[str] = set()
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if is_linklike(path):
            raise ValueError(f"source contains symlink/reparse member: {relative}")
        if path.is_file():
            actual.add(relative)
        elif not path.is_dir():
            raise ValueError(f"source contains unsupported member: {relative}")
    expected = set(entries) | {MANIFEST_NAME}
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(f"source membership mismatch; missing={missing}, extra={extra}")
    for relative, expected_hash in entries.items():
        path = root / safe_relative_path(relative)
        if sha256_file(path) != expected_hash:
            raise ValueError(f"source hash mismatch: {relative}")
    return entries, manifest_bytes


class SplitWriter(io.RawIOBase):
    def __init__(self, directory: Path, chunk_size: int) -> None:
        if chunk_size <= 0 or chunk_size > MAX_RELEASE_CHUNK_SIZE:
            raise ValueError(f"chunk size must be in [1,{MAX_RELEASE_CHUNK_SIZE}]")
        self.directory = directory
        self.chunk_size = chunk_size
        self.position = 0
        self.part_index = -1
        self.part_handle: BinaryIO | None = None
        self.part_size = 0
        self.part_digest = hashlib.sha256()
        self.whole_digest = hashlib.sha256()
        self.parts: list[dict[str, object]] = []

    def writable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.position

    def _open_part(self) -> None:
        self.part_index += 1
        name = f"{PART_PREFIX}{self.part_index:05d}"
        self.part_handle = (self.directory / name).open("xb")
        self.part_size = 0
        self.part_digest = hashlib.sha256()

    def _close_part(self) -> None:
        if self.part_handle is None:
            return
        self.part_handle.flush()
        os.fsync(self.part_handle.fileno())
        self.part_handle.close()
        self.parts.append(
            {
                "name": f"{PART_PREFIX}{self.part_index:05d}",
                "sha256": self.part_digest.hexdigest(),
                "size": self.part_size,
            }
        )
        self.part_handle = None

    def write(self, data: bytes | bytearray) -> int:
        view = memoryview(data)
        total = len(view)
        offset = 0
        while offset < total:
            if self.part_handle is None:
                self._open_part()
            capacity = self.chunk_size - self.part_size
            piece = view[offset : offset + capacity]
            assert self.part_handle is not None
            written = self.part_handle.write(piece)
            if written != len(piece):
                raise OSError("short write while creating package")
            raw_piece = piece.tobytes()
            self.part_digest.update(raw_piece)
            self.whole_digest.update(raw_piece)
            self.part_size += written
            self.position += written
            offset += written
            if self.part_size == self.chunk_size:
                self._close_part()
        return total

    def finish(self) -> None:
        self._close_part()
        if not self.parts:
            raise ValueError("tar stream produced no parts")


class JoinedReader(io.RawIOBase):
    def __init__(self, paths: list[Path]) -> None:
        self.paths = paths
        self.index = 0
        self.handle: BinaryIO | None = None

    def readable(self) -> bool:
        return True

    def _advance(self) -> bool:
        if self.handle is not None:
            self.handle.close()
        if self.index >= len(self.paths):
            self.handle = None
            return False
        self.handle = self.paths[self.index].open("rb")
        self.index += 1
        return True

    def readinto(self, buffer: bytearray) -> int:
        view = memoryview(buffer)
        total = 0
        while total < len(view):
            if self.handle is None and not self._advance():
                break
            assert self.handle is not None
            count = self.handle.readinto(view[total:])
            if count:
                total += count
            elif not self._advance():
                break
        return total

    def close(self) -> None:
        if self.handle is not None:
            self.handle.close()
        super().close()


def write_tar(root: Path, relative_paths: list[str], writer: SplitWriter) -> None:
    with tarfile.open(fileobj=writer, mode="w|", format=tarfile.GNU_FORMAT) as archive:
        for relative in sorted(relative_paths):
            path = root / safe_relative_path(relative)
            stat = path.stat()
            info = tarfile.TarInfo(relative)
            info.size = stat.st_size
            info.mtime = 0
            info.mode = 0o644
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            with path.open("rb") as handle:
                archive.addfile(info, handle)
    writer.finish()


def parse_package_json(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("invalid package JSON") from exc
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        raise ValueError("package JSON is not canonical")
    exact_keys = {
        "format",
        "part_size_limit",
        "parts",
        "source_manifest_sha256",
        "source_member_count",
        "source_name",
        "tar_sha256",
        "tar_size",
    }
    if set(value) != exact_keys or value.get("format") != "deterministic-gnu-tar-split-v1":
        raise ValueError("unsupported package schema")
    if not isinstance(value.get("parts"), list) or not value["parts"]:
        raise ValueError("package parts must be a non-empty list")
    for key in ("source_manifest_sha256", "tar_sha256"):
        if not isinstance(value.get(key), str) or not SHA256_RE.fullmatch(value[key]):
            raise ValueError(f"invalid {key}")
    for key in ("part_size_limit", "source_member_count", "tar_size"):
        if type(value.get(key)) is not int or value[key] <= 0:
            raise ValueError(f"invalid {key}")
    if value["part_size_limit"] > MAX_RELEASE_CHUNK_SIZE:
        raise ValueError("package part-size limit exceeds release maximum")
    if (
        not isinstance(value.get("source_name"), str)
        or value["source_name"] in ("", ".", "..")
        or Path(value["source_name"]).name != value["source_name"]
    ):
        raise ValueError("invalid source_name")
    return value


def _read_exact(handle: BinaryIO, size: int, label: str) -> bytes:
    data = bytearray()
    while len(data) < size:
        block = handle.read(size - len(data))
        if not block:
            raise ValueError(f"truncated tar while reading {label}")
        data.extend(block)
    return bytes(data)


def inspect_exact_tar(part_paths: list[Path], tar_size: int) -> tuple[dict[str, str], bytes]:
    reader = io.BufferedReader(JoinedReader(part_paths), buffer_size=BUFFER_SIZE)
    hashes: dict[str, str] = {}
    manifest_bytes: bytes | None = None
    member_order: list[str] = []
    position = 0
    try:
        while True:
            header = _read_exact(reader, tarfile.BLOCKSIZE, "member header")
            position += tarfile.BLOCKSIZE
            if header == bytes(tarfile.BLOCKSIZE):
                second = _read_exact(reader, tarfile.BLOCKSIZE, "second end record")
                position += tarfile.BLOCKSIZE
                if second != bytes(tarfile.BLOCKSIZE):
                    raise ValueError("tar has only one canonical end record")
                expected_size = ((position + tarfile.RECORDSIZE - 1) // tarfile.RECORDSIZE) * tarfile.RECORDSIZE
                trailing = _read_exact(reader, expected_size - position, "end padding")
                position = expected_size
                if any(trailing):
                    raise ValueError("tar end padding is nonzero")
                if reader.read(1) or position != tar_size:
                    raise ValueError("tar has unread trailing bytes or non-canonical length")
                break
            try:
                parsed = tarfile.TarInfo.frombuf(header, "utf-8", "strict")
            except (tarfile.HeaderError, UnicodeError) as exc:
                raise ValueError("invalid GNU-tar header") from exc
            relative = safe_relative_path(parsed.name).as_posix()
            if not parsed.isfile() or parsed.issym() or parsed.islnk() or relative in hashes:
                raise ValueError(f"unsupported/duplicate tar member: {relative}")
            canonical = tarfile.TarInfo(relative)
            canonical.size = parsed.size
            canonical.mtime = 0
            canonical.mode = 0o644
            canonical.uid = 0
            canonical.gid = 0
            canonical.uname = ""
            canonical.gname = ""
            if canonical.tobuf(tarfile.GNU_FORMAT, "utf-8", "strict") != header:
                raise ValueError(f"non-canonical GNU-tar header: {relative}")
            digest = hashlib.sha256()
            captured = bytearray() if relative == MANIFEST_NAME else None
            remaining = parsed.size
            while remaining:
                block = _read_exact(reader, min(BUFFER_SIZE, remaining), relative)
                position += len(block)
                remaining -= len(block)
                digest.update(block)
                if captured is not None:
                    captured.extend(block)
            padding_size = (-parsed.size) % tarfile.BLOCKSIZE
            padding = _read_exact(reader, padding_size, f"{relative} padding") if padding_size else b""
            position += padding_size
            if any(padding):
                raise ValueError(f"nonzero tar data padding: {relative}")
            hashes[relative] = digest.hexdigest()
            member_order.append(relative)
            if captured is not None:
                manifest_bytes = bytes(captured)
    finally:
        reader.close()
    if manifest_bytes is None:
        raise ValueError(f"tar is missing {MANIFEST_NAME}")
    source_entries = parse_manifest_bytes(manifest_bytes)
    expected = set(source_entries) | {MANIFEST_NAME}
    if set(hashes) != expected or member_order != sorted(expected):
        raise ValueError("tar membership/order does not match embedded source manifest")
    for relative, digest in source_entries.items():
        if hashes[relative] != digest:
            raise ValueError(f"tar member hash mismatch: {relative}")
    return source_entries, manifest_bytes


def verify_package(
    package: Path,
    source: Path | None = None,
    *,
    expected_tar_sha256: str | None = None,
    expected_package_manifest_sha256: str | None = None,
) -> dict[str, object]:
    reject_symlink_ancestors(package)
    if is_linklike(package) or not package.is_dir():
        raise ValueError("package must be a real directory")
    metadata_path = package / PACKAGE_JSON
    package_manifest_path = package / PACKAGE_MANIFEST
    if any(is_linklike(path) for path in (metadata_path, package_manifest_path)):
        raise ValueError("package metadata cannot be symlinks")
    metadata = parse_package_json(metadata_path)
    if source is None:
        for label, value in (
            ("expected tar SHA-256", expected_tar_sha256),
            ("expected package-manifest SHA-256", expected_package_manifest_sha256),
        ):
            if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
                raise ValueError(f"source-less verification requires {label}")
    parts = metadata["parts"]
    assert isinstance(parts, list)
    expected_files = {PACKAGE_JSON, PACKAGE_MANIFEST}
    part_paths: list[Path] = []
    total_size = 0
    whole_digest = hashlib.sha256()
    package_lines: list[str] = []
    for index, item in enumerate(parts):
        if not isinstance(item, dict) or set(item) != {"name", "sha256", "size"}:
            raise ValueError("invalid part record")
        expected_name = f"{PART_PREFIX}{index:05d}"
        if (
            item.get("name") != expected_name
            or not isinstance(item.get("sha256"), str)
            or not SHA256_RE.fullmatch(item["sha256"])
        ):
            raise ValueError("invalid part name/hash")
        if type(item.get("size")) is not int or item["size"] <= 0 or item["size"] > metadata["part_size_limit"]:
            raise ValueError("invalid part size")
        if index < len(parts) - 1 and item["size"] != metadata["part_size_limit"]:
            raise ValueError("non-final part is not full")
        part_path = package / expected_name
        if is_linklike(part_path) or not part_path.is_file() or part_path.stat().st_size != item["size"]:
            raise ValueError(f"missing or wrong-size part: {expected_name}")
        digest = hashlib.sha256()
        with part_path.open("rb") as handle:
            while block := handle.read(BUFFER_SIZE):
                digest.update(block)
                whole_digest.update(block)
        if digest.hexdigest() != item["sha256"]:
            raise ValueError(f"part hash mismatch: {expected_name}")
        total_size += item["size"]
        expected_files.add(expected_name)
        part_paths.append(part_path)
        package_lines.append(f"{item['sha256']}  {expected_name}\n")
    package_json_hash = sha256_file(metadata_path)
    package_lines.append(f"{package_json_hash}  {PACKAGE_JSON}\n")
    if package_manifest_path.read_text(encoding="ascii") != "".join(package_lines):
        raise ValueError("package manifest mismatch")
    actual_files: set[str] = set()
    for path in package.iterdir():
        if is_linklike(path) or not path.is_file():
            raise ValueError(f"unexpected package member: {path.name}")
        actual_files.add(path.name)
    if actual_files != expected_files:
        raise ValueError(f"package membership mismatch: {sorted(actual_files ^ expected_files)}")
    if total_size != metadata["tar_size"] or whole_digest.hexdigest() != metadata["tar_sha256"]:
        raise ValueError("whole tar stream mismatch")
    if expected_tar_sha256 is not None and metadata["tar_sha256"] != expected_tar_sha256:
        raise ValueError("tar SHA-256 differs from external expectation")
    package_manifest_hash = sha256_file(package_manifest_path)
    if (
        expected_package_manifest_sha256 is not None
        and package_manifest_hash != expected_package_manifest_sha256
    ):
        raise ValueError("package-manifest SHA-256 differs from external expectation")
    source_entries, manifest_bytes = inspect_exact_tar(part_paths, total_size)
    if hashlib.sha256(manifest_bytes).hexdigest() != metadata["source_manifest_sha256"]:
        raise ValueError("embedded source manifest hash mismatch")
    if len(source_entries) + 1 != metadata["source_member_count"]:
        raise ValueError("source member count mismatch")

    if source is not None:
        source_entries_live, source_manifest_live = inspect_source(source)
        if source_entries_live != source_entries or source_manifest_live != manifest_bytes:
            raise ValueError("live source differs from packaged source")
        if source.name != metadata["source_name"]:
            raise ValueError("live source name differs from package provenance")
    return metadata


def create_package(source: Path, output: Path, chunk_size: int) -> dict[str, object]:
    source = absolute_without_resolving(source)
    output = absolute_without_resolving(output)
    entries, manifest_bytes = inspect_source(source)
    reject_symlink_ancestors(output, include_leaf=False)
    if output.exists() or output.is_symlink():
        metadata = verify_package(output, source)
        if metadata["part_size_limit"] != chunk_size:
            raise ValueError("existing immutable package used a different chunk size")
        print(f"Immutable package already verified: {output}")
        return metadata
    pending = output.with_name(output.name + ".pending")
    if pending.exists() or pending.is_symlink():
        raise ValueError(f"preserving interrupted pending package: {pending}")
    pending.mkdir(parents=False)
    try:
        writer = SplitWriter(pending, chunk_size)
        write_tar(source, list(entries) + [MANIFEST_NAME], writer)
        metadata: dict[str, object] = {
            "format": "deterministic-gnu-tar-split-v1",
            "part_size_limit": chunk_size,
            "parts": writer.parts,
            "source_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "source_member_count": len(entries) + 1,
            "source_name": source.name,
            "tar_sha256": writer.whole_digest.hexdigest(),
            "tar_size": writer.position,
        }
        (pending / PACKAGE_JSON).write_bytes(canonical_json_bytes(metadata))
        package_lines = [f"{item['sha256']}  {item['name']}\n" for item in writer.parts]
        package_lines.append(f"{sha256_file(pending / PACKAGE_JSON)}  {PACKAGE_JSON}\n")
        (pending / PACKAGE_MANIFEST).write_text("".join(package_lines), encoding="ascii", newline="")
        verify_package(pending, source)
        os.replace(pending, output)
        return verify_package(output, source)
    except Exception:
        # Preserve partial output as evidence; never silently delete it.
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--source", type=Path, required=True)
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--package", type=Path, required=True)
    verify.add_argument("--source", type=Path)
    verify.add_argument("--expected-tar-sha256")
    verify.add_argument("--expected-package-manifest-sha256")
    args = parser.parse_args()
    if args.command == "create":
        result = create_package(args.source, args.output, args.chunk_size)
    else:
        result = verify_package(
            absolute_without_resolving(args.package),
            absolute_without_resolving(args.source) if args.source else None,
            expected_tar_sha256=args.expected_tar_sha256,
            expected_package_manifest_sha256=args.expected_package_manifest_sha256,
        )
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
