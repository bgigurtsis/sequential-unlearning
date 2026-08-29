#!/usr/bin/env python3
"""Adversarial tests for the pinned TransformerCompression vendor verifier."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFIER = REPO_ROOT / "scripts" / "verify_transformer_compression_vendor.py"
VENDOR = REPO_ROOT / "vendor" / "TransformerCompression"
SOURCE_PREFIX = Path("vendor/TransformerCompression/source")
EXECUTABLES = (
    "build_and_test.sh",
    "experiments/run_benchmark.py",
    "experiments/run_slicegpt.py",
    "src/slicegpt/data_utils.py",
    "src/slicegpt/hf_utils.py",
    "test.sh",
)


class VendorFixture:
    def __init__(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary.name)
        (self.root / "scripts").mkdir()
        shutil.copy2(VERIFIER, self.root / "scripts" / VERIFIER.name)
        shutil.copy2(REPO_ROOT / ".gitattributes", self.root / ".gitattributes")
        shutil.copytree(VENDOR, self.root / "vendor" / "TransformerCompression")
        self.git("init", "--quiet")
        self.git("config", "user.email", "vendor-test@example.invalid")
        self.git("config", "user.name", "Vendor Test")
        self.git("add", "-f", "--", ".gitattributes")
        self.git("add", "-f", "--", SOURCE_PREFIX.as_posix())
        self.git(
            "add",
            "--chmod=+x",
            "--",
            *(SOURCE_PREFIX.joinpath(path).as_posix() for path in EXECUTABLES),
        )

    def close(self) -> None:
        self._temporary.cleanup()

    def git(self, *args: str, input_bytes: bytes | None = None) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.root), *args],
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=True,
        )
        return result.stdout.decode("utf-8").strip()

    def verify(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(self.root / "scripts" / VERIFIER.name), *args],
            cwd=self.root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

    def source(self, relative: str) -> Path:
        return self.root / SOURCE_PREFIX / relative


class VerifyTransformerCompressionVendorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = VendorFixture()

    def tearDown(self) -> None:
        self.fixture.close()

    def assert_fails(self, expected: str, *args: str) -> None:
        result = self.fixture.verify(*args)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(expected, result.stdout)

    def test_exact_staged_vendor_passes(self) -> None:
        result = self.fixture.verify()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("PASS: Microsoft TransformerCompression vendor verified", result.stdout)

    def test_windows_style_fresh_checkout_preserves_bytes_and_modes(self) -> None:
        self.fixture.git(
            "add",
            "-f",
            "--",
            ".gitattributes",
            "scripts/verify_transformer_compression_vendor.py",
            "vendor/TransformerCompression/SOURCE_SHA256SUMS",
            "vendor/TransformerCompression/UPSTREAM.md",
        )
        self.fixture.git("add", "-f", "--", SOURCE_PREFIX.as_posix())
        staged_modes = self.fixture.git("ls-files", "--stage", "--", SOURCE_PREFIX.as_posix())
        self.assertEqual(sum(line.startswith("100755 ") for line in staged_modes.splitlines()), 6)
        self.fixture.git("commit", "--quiet", "-m", "vendor fixture")

        clone = self.fixture.root / "fresh-checkout"
        subprocess.run(
            [
                "git",
                "-c",
                "core.autocrlf=true",
                "clone",
                "--quiet",
                str(self.fixture.root),
                str(clone),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        result = subprocess.run(
            [sys.executable, str(clone / "scripts" / VERIFIER.name)],
            cwd=clone,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_tampered_source_fails(self) -> None:
        path = self.fixture.source("README.md")
        payload = path.read_bytes()
        path.write_bytes(bytes([payload[0] ^ 1]) + payload[1:])
        self.assert_fails("SHA-256 mismatch: README.md")

    def test_extra_source_file_fails(self) -> None:
        self.fixture.source("LOCAL_GEMMA_PATCH.py").write_text("patched\n", encoding="utf-8")
        self.assert_fails("source/ membership differs from manifest")

    def test_missing_source_file_fails(self) -> None:
        self.fixture.source("README.md").unlink()
        self.assert_fails("source/ membership differs from manifest")

    def test_manifest_tamper_fails_even_before_rehashing_source(self) -> None:
        path = self.fixture.root / "vendor" / "TransformerCompression" / "SOURCE_SHA256SUMS"
        payload = path.read_bytes()
        path.write_bytes(bytes([ord("0") if payload[0] != ord("0") else ord("1")]) + payload[1:])
        self.assert_fails("manifest bytes differ from the pinned official-source manifest")

    def test_missing_byte_preservation_attribute_fails(self) -> None:
        path = self.fixture.root / ".gitattributes"
        path.write_text("# vendor rule removed\n", encoding="utf-8", newline="\n")
        self.fixture.git("add", "-f", "--", ".gitattributes")
        self.assert_fails("vendored byte-preservation attribute mismatch")

    def test_upstream_record_wrong_commit_fails(self) -> None:
        path = self.fixture.root / "vendor" / "TransformerCompression" / "UPSTREAM.md"
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace("6b12cdee", "7b12cdee", 1), encoding="utf-8", newline="\n")
        self.assert_fails("UPSTREAM.md differs from the pinned provenance record")

    def test_incomplete_license_fails(self) -> None:
        path = self.fixture.source("LICENSE")
        path.write_bytes(path.read_bytes()[:-1])
        self.assert_fails("upstream MIT license differs from the pinned complete text")

    def test_wrong_executable_mode_fails(self) -> None:
        relative = SOURCE_PREFIX.joinpath("build_and_test.sh").as_posix()
        self.fixture.git("update-index", "--chmod=-x", "--", relative)
        self.assert_fails("vendored Git index mode mismatch: build_and_test.sh: 100644 != 100755")

    def test_missing_index_entry_fails(self) -> None:
        relative = SOURCE_PREFIX.joinpath("README.md").as_posix()
        self.fixture.git("rm", "--cached", "--quiet", "--", relative)
        self.assert_fails("Git index membership differs from source/")

    def test_stale_index_blob_fails(self) -> None:
        relative = SOURCE_PREFIX.joinpath("README.md").as_posix()
        bogus_blob = self.fixture.git("hash-object", "-w", "--stdin", input_bytes=b"bogus\n")
        self.fixture.git("update-index", "--cacheinfo", f"100644,{bogus_blob},{relative}")
        self.assert_fails("vendored Git index blob is stale: README.md")

    def test_wrong_upstream_checkout_fails(self) -> None:
        self.fixture.git("commit", "--quiet", "-m", "synthetic wrong upstream")
        self.assert_fails(
            "upstream checkout is not pinned",
            "--upstream-repo",
            str(self.fixture.root),
        )


if __name__ == "__main__":
    unittest.main()
