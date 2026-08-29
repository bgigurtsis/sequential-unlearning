import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPT = SCRIPT_DIR / "generate_slicegpt_v4_provenance_spec.py"
SPEC = importlib.util.spec_from_file_location("generate_slicegpt_v4_provenance_spec", SCRIPT)
GEN = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GEN
SPEC.loader.exec_module(GEN)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class FakeMaterializer:
    def __init__(self, fixture):
        self.fixture = fixture

    def load_disjoint_prompts(self, repo):
        return {"protected prompt"}, dict(self.fixture.protected_hashes)

    def validate_sealed_archive(self, root, **kwargs):
        if Path(repo := kwargs["repo"]) != self.fixture.repo:
            raise RuntimeError(f"wrong repository: {repo}")
        if Path(kwargs["runtime_lock_path"]) != self.fixture.runtime_lock:
            raise RuntimeError("wrong runtime lock")
        if "parent_model" in kwargs:
            raise RuntimeError("generator must not rehash the multi-GB parent for every seed")
        return self.fixture.archive_metadata[Path(root)]


class FakeQualifier:
    def __init__(self, fixture):
        self.fixture = fixture
        self.PROTOCOL_VERSION = GEN.PROTOCOL_VERSION
        self.UPSTREAM_COMMIT = "1" * 40
        self.UPSTREAM_TREE = "2" * 40
        self.VENDOR_MANIFEST_SHA256 = fixture.vendor_manifest_sha256
        self.CALIBRATION_ARROW_SHA256 = digest(fixture.source_arrow.read_bytes())
        self.CALIBRATION_METADATA_SHA256 = digest(fixture.source_metadata.read_bytes())
        self.CALIBRATION_SEEDS = GEN.CALIBRATION_SEEDS
        self.PROTECTED_PROMPT_PATHS = tuple(fixture.protected_hashes)
        self.MANDATORY_COMMITTED_SOURCES = frozenset(
            {GEN.QUALIFIER_PATH, GEN.MATERIALIZER_PATH}
        )
        self.MATERIALIZER_PATH = GEN.MATERIALIZER_PATH

    @staticmethod
    def load_canonical_json(path):
        return json.loads(Path(path).read_text(encoding="utf-8"))

    def validate_runtime_observation(self, value):
        if value != self.fixture.runtime_payload:
            raise RuntimeError("runtime payload changed")
        return value

    def _load_verified_materializer(self, repo, sources):
        if Path(repo) != self.fixture.repo:
            raise RuntimeError("wrong repository")
        if sources.get(GEN.MATERIALIZER_PATH) != self.fixture.materializer_sha256:
            raise RuntimeError("materializer was not source-bound")
        return FakeMaterializer(self.fixture)


class Fixture:
    def __init__(self, owner):
        self.owner = owner
        self.repo_temp = tempfile.TemporaryDirectory()
        self.external_temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.repo_temp.name).resolve()
        self.external = Path(self.external_temp.name).resolve()
        self.archive_metadata = {}
        self._run("init")
        self._run("config", "user.email", "test@example.invalid")
        self._run("config", "user.name", "Provenance Test")

        self._write(GEN.GENERATOR_PATH, SCRIPT.read_bytes())
        self._write(GEN.TEST_PATH, Path(__file__).read_bytes())
        self._write(GEN.QUALIFIER_PATH, b"# fixture runtime qualifier\n")
        materializer_bytes = b"# fixture materializer\n"
        self._write(GEN.MATERIALIZER_PATH, materializer_bytes)
        self.materializer_sha256 = digest(materializer_bytes)

        self.runtime_payload = {"fixture": "runtime"}
        self.runtime_lock = self.repo / "derisk/runtime_lock/runtime_lock.json"
        self._write(
            self.runtime_lock.relative_to(self.repo).as_posix(),
            GEN.canonical_json_bytes(self.runtime_payload),
        )
        prompt = self._write("data/protected.json", b"[\"protected prompt\"]\n")
        self.protected_hashes = {"data/protected.json": GEN.sha256_file(prompt)}

        vendor_member = self._write(
            "vendor/TransformerCompression/source/src/slicegpt/data_utils.py",
            b"# exact vendor source\n",
        )
        vendor_relative = "src/slicegpt/data_utils.py"
        manifest_bytes = f"{GEN.sha256_file(vendor_member)}  {vendor_relative}\n".encode()
        vendor_manifest = self._write(
            "vendor/TransformerCompression/SOURCE_SHA256SUMS", manifest_bytes
        )
        self.vendor_manifest_sha256 = GEN.sha256_file(vendor_manifest)

        self.source_arrow = self._external("cache/wikitext-train.arrow", b"arrow\n")
        self.source_metadata = self._external("cache/dataset_info.json", b"metadata\n")
        self.parent = self.external / "parent"
        self._external("parent/model.safetensors", b"weights\n")
        self._external("parent/config.json", b"config\n")
        self.ruler = self.external / "ruler"
        self._external("ruler/baseline.json", b"baseline\n")
        self._external("ruler/terminal.json", b"terminal\n")
        self._external("ruler/ladder.json", b"ladder\n")

        parent_weights = {"model.safetensors": GEN.sha256_file(self.parent / "model.safetensors")}
        parent_support = {"config.json": GEN.sha256_file(self.parent / "config.json")}
        parent_fingerprint = GEN.fingerprint(
            {
                "source": str(self.parent),
                "weight_file_sha256": parent_weights,
                "support_file_sha256": parent_support,
            }
        )
        lock_digest = GEN.sha256_file(self.runtime_lock)
        for seed in GEN.CALIBRATION_SEEDS:
            root = self.repo / f"derisk/calibration_seed{seed}"
            tensor = self._write(
                f"derisk/calibration_seed{seed}/calibration.safetensors",
                f"tensor-{seed}\n".encode(),
            )
            metadata_file = self._write(
                f"derisk/calibration_seed{seed}/calibration_metadata.json",
                GEN.canonical_json_bytes({"seed": seed}),
            )
            complete = self._write(
                f"derisk/calibration_seed{seed}/COMPLETE.json",
                GEN.canonical_json_bytes({"seed": seed, "status": "complete"}),
            )
            manifest = {
                "COMPLETE.json": GEN.sha256_file(complete),
                "calibration.safetensors": GEN.sha256_file(tensor),
                "calibration_metadata.json": GEN.sha256_file(metadata_file),
            }
            self._write(
                f"derisk/calibration_seed{seed}/MANIFEST.sha256",
                "".join(f"{manifest[name]}  {name}\n" for name in sorted(manifest)).encode(),
            )
            self.archive_metadata[root] = {
                "seed": seed,
                "runtime": {"runtime_lock_sha256": lock_digest},
                "parent": {
                    "weight_file_sha256": parent_weights,
                    "support_file_sha256": parent_support,
                    "fingerprint": parent_fingerprint,
                },
                "disjointness": {
                    "source_file_sha256": dict(self.protected_hashes),
                    "protected_prompt_count": 1,
                },
                "dataset": {
                    "source_cache_sha256": {
                        "train_arrow": digest(self.source_arrow.read_bytes()),
                        "dataset_metadata": digest(self.source_metadata.read_bytes()),
                    }
                },
                "source_identity": {"fixture": "one-identity"},
                "tensors": {"sha256": GEN.sha256_file(tensor)},
                "fingerprint": digest(f"metadata-{seed}".encode()),
            }
        self._run("add", ".")
        self._run("commit", "-m", "fixture")
        self.qualifier = FakeQualifier(self)

    def close(self):
        self.repo_temp.cleanup()
        self.external_temp.cleanup()

    def _run(self, *args):
        return subprocess.run(
            ["git", *args], cwd=self.repo, check=True, capture_output=True, text=True
        ).stdout

    def _write(self, relative, data):
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def _external(self, relative, data):
        path = self.external / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    @property
    def archives(self):
        return {
            seed: self.repo / f"derisk/calibration_seed{seed}"
            for seed in GEN.CALIBRATION_SEEDS
        }

    def build(self, **overrides):
        arguments = {
            "repo": self.repo,
            "runtime_lock": self.runtime_lock,
            "archive_roots": self.archives,
            "source_arrow": self.source_arrow,
            "source_metadata": self.source_metadata,
            "parent_model": self.parent,
            "clean_ruler": self.ruler,
        }
        arguments.update(overrides)
        with (
            mock.patch.object(GEN, "__file__", str(self.repo / GEN.GENERATOR_PATH)),
            mock.patch.object(GEN, "MATERIALIZER_SOURCE_SHA256", self.materializer_sha256),
            mock.patch.object(GEN, "load_qualifier", return_value=self.qualifier),
        ):
            return GEN.build_spec(**arguments)


class GeneratorTests(unittest.TestCase):
    def setUp(self):
        self.fixture = Fixture(self)

    def tearDown(self):
        self.fixture.close()

    def test_exact_production_materializer_hash_is_frozen(self):
        self.assertEqual(
            GEN.MATERIALIZER_SOURCE_SHA256,
            "4f8a9b62d823677eb0fdec29b94e557279c5657d97077f360904e0680e479fcf",
        )

    def test_build_is_deterministic_external_capable_and_does_not_write_spec(self):
        first = self.fixture.build()
        second = self.fixture.build()
        self.assertEqual(first, second)
        self.assertEqual(first["version"], GEN.PROTOCOL_VERSION)
        self.assertEqual(first["parent_model"]["root"], self.fixture.parent.as_posix())
        self.assertEqual(first["clean_ruler"]["root"], self.fixture.ruler.as_posix())
        self.assertEqual(
            first["calibration"]["source_arrow"]["path"],
            self.fixture.source_arrow.as_posix(),
        )
        self.assertEqual(
            first["calibration"]["source_metadata"]["path"],
            self.fixture.source_metadata.as_posix(),
        )
        self.assertEqual(set(first["calibration"]["archives"]), {"0", "1", "2", "7", "11"})
        for seed, record in first["calibration"]["archives"].items():
            self.assertEqual(record["root"], f"derisk/calibration_seed{seed}")
        self.assertIn(GEN.GENERATOR_PATH, first["committed_sources"])
        self.assertIn(GEN.TEST_PATH, first["committed_sources"])
        self.assertIn(
            "derisk/calibration_seed11/calibration.safetensors",
            first["committed_sources"],
        )
        self.assertFalse((self.fixture.repo / "derisk/provenance_spec.json").exists())

    def test_requires_exact_seed_set_committed_members_and_manifest(self):
        missing = self.fixture.archives
        del missing[7]
        with self.assertRaisesRegex(GEN.GenerationError, "exact calibration seed set"):
            self.fixture.build(archive_roots=missing)

        member = self.fixture.archives[0] / "calibration.safetensors"
        original = member.read_bytes()
        member.write_bytes(original + b"tamper")
        with self.assertRaisesRegex(GEN.GenerationError, "committed HEAD blob"):
            self.fixture.build()
        member.write_bytes(original)

        extra = self.fixture.archives[0] / "extra.json"
        extra.write_bytes(b"{}\n")
        with self.assertRaisesRegex(GEN.GenerationError, "four-file archive layout"):
            self.fixture.build()
        extra.unlink()

        manifest = self.fixture.archives[0] / "MANIFEST.sha256"
        original = manifest.read_bytes()
        lines = original.decode().splitlines()
        lines[0] = "0" * 64 + lines[0][64:]
        manifest.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(GEN.GenerationError, "committed HEAD blob"):
            self.fixture.build()
        manifest.write_bytes(original)

        lines = original.decode().splitlines()
        lines[0] = "0" * 64 + lines[0][64:]
        manifest.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        self.fixture._run("add", manifest.relative_to(self.fixture.repo).as_posix())
        self.fixture._run("commit", "-m", "commit coherent manifest tamper")
        with self.assertRaisesRegex(GEN.GenerationError, "manifest/member identity mismatch"):
            self.fixture.build()

    def test_rejects_materializer_drift_wrong_executed_source_and_empty_tree_dir(self):
        with (
            mock.patch.object(GEN, "__file__", str(self.fixture.repo / GEN.GENERATOR_PATH)),
            mock.patch.object(GEN, "MATERIALIZER_SOURCE_SHA256", "0" * 64),
            mock.patch.object(GEN, "load_qualifier", return_value=self.fixture.qualifier),
        ):
            with self.assertRaisesRegex(GEN.GenerationError, "materializer source hash"):
                GEN.build_spec(
                    repo=self.fixture.repo,
                    runtime_lock=self.fixture.runtime_lock,
                    archive_roots=self.fixture.archives,
                    source_arrow=self.fixture.source_arrow,
                    source_metadata=self.fixture.source_metadata,
                    parent_model=self.fixture.parent,
                    clean_ruler=self.fixture.ruler,
                )
        with self.assertRaisesRegex(GEN.GenerationError, "executed generator path"):
            with mock.patch.object(GEN, "load_qualifier", return_value=self.fixture.qualifier):
                GEN.build_spec(
                    repo=self.fixture.repo,
                    runtime_lock=self.fixture.runtime_lock,
                    archive_roots=self.fixture.archives,
                    source_arrow=self.fixture.source_arrow,
                    source_metadata=self.fixture.source_metadata,
                    parent_model=self.fixture.parent,
                    clean_ruler=self.fixture.ruler,
                )
        empty = self.fixture.parent / "empty"
        empty.mkdir()
        with self.assertRaisesRegex(GEN.GenerationError, "empty or unbound directory"):
            self.fixture.build()

    def test_write_is_canonical_idempotent_and_never_replaces(self):
        output = self.fixture.repo / "derisk/spec/provenance.json"
        value = {"version": "fixture", "hash": "a" * 64}
        self.assertEqual(GEN.write_spec(output, value, self.fixture.repo), output)
        self.assertEqual(output.read_bytes(), GEN.canonical_json_bytes(value))
        self.assertEqual(GEN.write_spec(output, value, self.fixture.repo), output)
        with self.assertRaisesRegex(GEN.GenerationError, "refusing replacement"):
            GEN.write_spec(output, {**value, "hash": "b" * 64}, self.fixture.repo)
        outside = self.fixture.repo / "outside.json"
        with self.assertRaisesRegex(GEN.GenerationError, "below repository derisk"):
            GEN.write_spec(outside, value, self.fixture.repo)
        other = self.fixture.repo / "derisk/spec/other.json"
        temporary = other.with_name(other.name + ".tmp")
        temporary.write_bytes(b"partial")
        with self.assertRaisesRegex(GEN.GenerationError, "partial provenance"):
            GEN.write_spec(other, value, self.fixture.repo)

    def test_linklike_external_member_fails_closed(self):
        target = self.fixture.external / "target.bin"
        target.write_bytes(b"target")
        link = self.fixture.parent / "linked.bin"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation is unavailable on this host")
        with self.assertRaisesRegex(GEN.GenerationError, "linklike member"):
            self.fixture.build()


if __name__ == "__main__":
    unittest.main()
