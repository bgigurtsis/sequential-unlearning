#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import package_immutable_archive as package


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fixture(root: Path, name: str = "sealed") -> Path:
    source = root / name
    (source / "nested").mkdir(parents=True)
    files = {
        "a.bin": bytes(range(251)) * 5,
        "nested/b.json": b'{"finite":true}\n',
    }
    for relative, data in files.items():
        path = source / relative
        path.write_bytes(data)
    lines = "".join(f"{sha(data)}  {relative}\n" for relative, data in sorted(files.items()))
    (source / package.MANIFEST_NAME).write_text(lines, encoding="ascii", newline="")
    return source


def rebind_package(output: Path) -> dict:
    metadata_path = output / package.PACKAGE_JSON
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    whole = hashlib.sha256()
    for item in metadata["parts"]:
        path = output / item["name"]
        raw = path.read_bytes()
        item["size"] = len(raw)
        item["sha256"] = sha(raw)
        whole.update(raw)
    metadata["tar_size"] = sum(item["size"] for item in metadata["parts"])
    metadata["tar_sha256"] = whole.hexdigest()
    metadata_path.write_bytes(package.canonical_json_bytes(metadata))
    lines = [f"{item['sha256']}  {item['name']}\n" for item in metadata["parts"]]
    lines.append(f"{package.sha256_file(metadata_path)}  {package.PACKAGE_JSON}\n")
    (output / package.PACKAGE_MANIFEST).write_text("".join(lines), encoding="ascii", newline="")
    return metadata


def rewrite_metadata(output: Path, metadata: dict) -> None:
    metadata_path = output / package.PACKAGE_JSON
    metadata_path.write_bytes(package.canonical_json_bytes(metadata))
    lines = [f"{item['sha256']}  {item['name']}\n" for item in metadata["parts"]]
    lines.append(f"{package.sha256_file(metadata_path)}  {package.PACKAGE_JSON}\n")
    (output / package.PACKAGE_MANIFEST).write_text("".join(lines), encoding="ascii", newline="")


class PackageTests(unittest.TestCase):
    def test_rejects_invalid_release_chunk_sizes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for size in (0, package.MAX_RELEASE_CHUNK_SIZE + 1):
                with self.subTest(size=size), self.assertRaisesRegex(ValueError, "chunk size"):
                    package.create_package(fixture(root, f"sealed_{size}"), root / f"out_{size}", size)

    def test_create_verify_and_immutable_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = fixture(root)
            output = root / "release"
            first = package.create_package(source, output, 257)
            before = {path.name: package.sha256_file(path) for path in output.iterdir()}
            second = package.create_package(source, output, 257)
            after = {path.name: package.sha256_file(path) for path in output.iterdir()}
            self.assertEqual(first, second)
            self.assertEqual(before, after)
            self.assertGreater(len(first["parts"]), 1)
            self.assertEqual(package.verify_package(output, source), first)
            with self.assertRaisesRegex(ValueError, "different chunk size"):
                package.create_package(source, output, 258)

    def test_deterministic_across_fresh_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = fixture(root)
            one = root / "one"
            two = root / "two"
            package.create_package(source, one, 333)
            package.create_package(source, two, 333)
            self.assertEqual(
                {p.name: p.read_bytes() for p in one.iterdir()},
                {p.name: p.read_bytes() for p in two.iterdir()},
            )

    def test_rejects_source_hash_drift_and_extra_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = fixture(root)
            (source / "a.bin").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                package.inspect_source(source)
            source = fixture(root, "sealed_extra")
            (source / "extra").write_text("x", encoding="ascii")
            with self.assertRaisesRegex(ValueError, "membership mismatch"):
                package.inspect_source(source)

    def test_rejects_manifest_traversal_duplicate_and_noncanonical_hash(self) -> None:
        digest = "0" * 64
        cases = [
            f"{digest}  ../escape\n".encode(),
            f"{digest}  a\n{digest}  a\n".encode(),
            f"{'A' * 64}  a\n".encode(),
            f"{digest}  a".encode(),
            f"{digest}  ./a\n".encode(),
            f"{digest}  a//b\n".encode(),
            f"{digest}  a\r\n".encode(),
            f"{digest}  z\n{digest}  a\n".encode(),
        ]
        for raw in cases:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                package.parse_manifest_bytes(raw)

    def test_rejects_part_and_metadata_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = fixture(root)
            output = root / "release"
            metadata = package.create_package(source, output, 300)
            first_part = output / metadata["parts"][0]["name"]
            original = first_part.read_bytes()
            first_part.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
            with self.assertRaisesRegex(ValueError, "part hash mismatch"):
                package.verify_package(output, source)

    def test_rejects_extra_package_member(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = fixture(root)
            output = root / "release"
            package.create_package(source, output, 300)
            (output / "extra").write_text("x", encoding="ascii")
            with self.assertRaisesRegex(ValueError, "membership mismatch"):
                package.verify_package(output, source)

    def test_rejects_live_source_substitution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = fixture(root)
            output = root / "release"
            package.create_package(source, output, 300)
            substitute = root / "other"
            substitute.mkdir()
            for path in source.rglob("*"):
                if path.is_file():
                    target = substitute / path.relative_to(source)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(path.read_bytes())
            with self.assertRaisesRegex(ValueError, "source name"):
                package.verify_package(output, substitute)

    def test_rejects_noncanonical_package_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = fixture(root)
            output = root / "release"
            package.create_package(source, output, 300)
            path = output / package.PACKAGE_JSON
            value = json.loads(path.read_text(encoding="utf-8"))
            path.write_text(json.dumps(value, indent=2), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not canonical"):
                package.verify_package(output, source)

    def test_rejects_coherently_rebound_trailing_bytes_and_padding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = fixture(root)
            trailing = root / "trailing"
            metadata = package.create_package(source, trailing, 1_000_000)
            part = trailing / metadata["parts"][0]["name"]
            part.write_bytes(part.read_bytes() + b"arbitrary trailing bytes")
            rebind_package(trailing)
            with self.assertRaisesRegex(ValueError, "trailing bytes|non-canonical length"):
                package.verify_package(trailing, source)

            padding = root / "padding"
            metadata = package.create_package(source, padding, 1_000_000)
            part = padding / metadata["parts"][0]["name"]
            raw = bytearray(part.read_bytes())
            manifest_size = (source / package.MANIFEST_NAME).stat().st_size
            padding_offset = package.tarfile.BLOCKSIZE + manifest_size
            self.assertNotEqual(manifest_size % package.tarfile.BLOCKSIZE, 0)
            raw[padding_offset] = 1
            part.write_bytes(raw)
            rebind_package(padding)
            with self.assertRaisesRegex(ValueError, "nonzero tar data padding"):
                package.verify_package(padding, source)

    def test_source_less_verify_requires_external_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = fixture(root)
            output = root / "release"
            metadata = package.create_package(source, output, 300)
            with self.assertRaisesRegex(ValueError, "source-less verification requires"):
                package.verify_package(output)
            self.assertEqual(
                package.verify_package(
                    output,
                    expected_tar_sha256=metadata["tar_sha256"],
                    expected_package_manifest_sha256=package.sha256_file(output / package.PACKAGE_MANIFEST),
                ),
                metadata,
            )

    def test_verifier_rejects_oversized_declared_part_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = fixture(root)
            output = root / "release"
            metadata = package.create_package(source, output, 300)
            metadata["part_size_limit"] = package.MAX_RELEASE_CHUNK_SIZE + 1
            rewrite_metadata(output, metadata)
            with self.assertRaisesRegex(ValueError, "exceeds release maximum"):
                package.verify_package(output, source)

    def test_pending_directory_is_preserved_and_blocks_create(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = fixture(root)
            output = root / "release"
            pending = root / "release.pending"
            pending.mkdir()
            marker = pending / "evidence"
            marker.write_text("partial", encoding="ascii")
            with self.assertRaisesRegex(ValueError, "preserving interrupted"):
                package.create_package(source, output, 300)
            self.assertEqual(marker.read_text(encoding="ascii"), "partial")

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks unavailable")
    def test_rejects_source_symlink_when_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = fixture(root)
            link = source / "link"
            try:
                link.symlink_to(source / "a.bin")
            except OSError:
                self.skipTest("symlink creation not permitted")
            with self.assertRaisesRegex(ValueError, "symlink"):
                package.inspect_source(source)


if __name__ == "__main__":
    unittest.main()
