from __future__ import annotations

import copy
import hashlib
import importlib.machinery
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PROJECT = Path(__file__).resolve().parents[1]
SOURCE = PROJECT / "scripts/qualify_slicegpt_model_adapter_v4.py"
SPEC = importlib.util.spec_from_file_location("model_qualifier_v4_under_test", SOURCE)
assert SPEC is not None and SPEC.loader is not None
Q = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(Q)
H = lambda char: char * 64


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(Q._canonical_json_bytes(value))


def valid_observation() -> dict:
    identity = H("1")
    residual = (
        [identity]
        + [H(format(2 + index % 8, "x")) for index in range(33)]
        + [identity]
    )
    rows = []
    for index in range(Q.NUM_LAYERS):
        attention = H(format(10 + index % 6, "x"))
        rows.append(
            {
                "layer": index,
                "input": residual[index],
                "attention": attention,
                "output": residual[index + 1],
                "nonidentity": True,
            }
        )
    algebra_row = lambda index: {
        "layer": index,
        "pre_attention_max_error": "0",
        "post_attention_max_error": "0",
        "attention_residual_max_error": "0",
        "pre_ff_max_error": "0",
        "post_ff_max_error": "0",
        "ff_residual_max_error": "0",
        "finite": True,
    }
    components = {"R": "0.1", "D": "0.2", "J": "0.3", "F": "0.4"}
    return {
        "version": Q.OBSERVATION_VERSION,
        "status": "INCOMPLETE_SERIALIZATION_AND_PEFT",
        "scope": "FULL_WIDTH_NONIDENTITY_MODEL_QUALIFICATION_ONLY",
        "probe2_verdict": None,
        "nonzero_slice_authorized": False,
        "model_level_gates_passed": True,
        "serialization_peft": {
            "status": "INCOMPLETE_SEPARATE_GATE",
            "native_sharded_safetensors": False,
            "project_loader_roundtrip": False,
            "bit_identical_state": False,
            "byte_identical_generations": False,
            "seven_target_lora": False,
            "merge_reload_scalar": False,
        },
        "topology": {
            "model_class": "Gemma3SliceGPTTextForCausalLMV4",
            "text_only": True,
            "hidden_size": 2560,
            "intermediate_size": 10240,
            "layers": 34,
            "query_heads": 8,
            "kv_heads": 4,
            "head_dim": 256,
            "vocab_size": 262208,
            "rms_eps": "0.000001",
            "tied_embeddings": False,
            "query_pre_attention_scalar": 256,
            "sliding_window": 1024,
            "layer_types": list(Q.LAYER_TYPES),
            "qk_norms_untouched": True,
        },
        "bases": {
            "dtype": "torch.float64",
            "width": 2560,
            "construction": "fixed_seed_householder_canonical_sign",
            "seed": 4401,
            "round_interval": 8,
            "full_width": True,
            "identity_sha256": identity,
            "records": rows,
        },
        "algebra": {
            "rtol": "0.00000001",
            "atol": "0.00000001",
            "random": [algebra_row(index) for index in range(34)],
            "captured": [algebra_row(index) for index in range(34)],
        },
        "hf_paths": {
            "no_cache": True,
            "cache_prefill": True,
            "cache_decode": True,
            "cache_prefill_equal": True,
            "cache_decode_equal": True,
            "greedy_cache": True,
            "output_hidden_states": True,
            "gradient_checkpoint_backward": True,
            "captured_activations": True,
            "sliding_capture": True,
            "full_capture": True,
            "pixel_values_rejected": True,
            "finite": True,
        },
        "endpoints": {
            "embedding_scale": "sqrt(2560)",
            "embedding_unchanged": True,
            "final_norm_affine_removed": True,
            "final_multiplier_fused": True,
            "head_changed": True,
            "tied_before": True,
            "head_untied_after": True,
            "tie_config_disabled": True,
            "endpoint_logits_finite": True,
            "embedding_sha256": H("a"),
            "original_final_norm_sha256": H("b"),
            "fused_head_sha256": H("c"),
            "text_model_version": "gemma3_slicegpt_text_model_v4_v1_unqualified",
            "text_model_source_sha256": H("e"),
            "final_fusion_chunk_rows": 4096,
        },
        "scalar": {
            "prompt_count": 196,
            "prompt_ids_sha256": Q.PROMPT_IDS_SHA256,
            "decoding": "greedy",
            "seed": 0,
            "max_new_tokens": 256,
            "batch_size": 8,
            "wrong_count": 0,
            "limited_count": 0,
            "unparsed_count": 0,
            "clean_scalar": "0.0",
            "transformed_scalar": "0.0",
            "scalar_delta": "0.0",
            "clean_components": components,
            "transformed_components": dict(components),
            "component_deltas": {name: "0.0" for name in components},
            "continuation_equal_count": 196,
            "clean_continuations_sha256": H("d"),
            "transformed_continuations_sha256": H("d"),
            "normalization_sources": {
                "baseline": {"path": "baseline.json", "sha256": H("1")},
                "terminal": {"path": "terminal.json", "sha256": H("2")},
                "ladder": {"path": "ladder.json", "sha256": H("3")},
            },
            "normalization_policy_fingerprint": H("4"),
        },
        "logits": {
            "prompt_count": 32,
            "prompt_ids_sha256": Q.LOGIT_PROMPT_IDS_SHA256,
            "input_surface_sha256": Q.LOGIT_INPUT_SURFACE_SHA256,
            "max_positions": 128,
            "compared_positions": Q.LOGIT_COMPARED_POSITIONS,
            "vocab_size": 262208,
            "top1_equal": Q.LOGIT_COMPARED_POSITIONS,
            "top1_agreement": "1.0",
            "mean_absolute_float32_delta": "0.0",
            "finite": True,
        },
        "provenance": {
            "repo_commit": "0" * 40,
            "committed_sources": {path: H("e") for path in Q.SOURCE_PATHS},
            "runtime_archive_sha256": {"member": H("f")},
            "runtime_identity_fingerprint": H("1"),
            "parent_weight_sha256": {"model.safetensors": H("2")},
            "parent_support_sha256": {"config.json": H("3")},
            "parent_fingerprint": H("4"),
            "calibration_seed": 11,
            "calibration_fingerprint": H("5"),
            "calibration_complete_sha256": H("6"),
            "clean_ruler_files_sha256": {"ruler.json": H("7")},
            "clean_ruler_fingerprint": H("8"),
        },
    }


class SchemaTests(unittest.TestCase):
    def test_gradient_finiteness_check_is_bounded_and_semantically_exact(self):
        class Gradient:
            def __init__(self, values):
                self.values = tuple(values)

            def numel(self):
                return len(self.values)

            def detach(self):
                return self

            def reshape(self, _shape):
                return self

            def split(self, size):
                return tuple(
                    Gradient(self.values[start:start + size])
                    for start in range(0, len(self.values), size)
                )

        class Parameter:
            def __init__(self, values):
                self.grad = None if values is None else Gradient(values)

        class FiniteResult:
            def __init__(self, value):
                self.value = value

            def all(self):
                return self

            def item(self):
                return self.value

        class FakeTorch:
            observed_sizes = []

            @classmethod
            def isfinite(cls, chunk):
                cls.observed_sizes.append(chunk.numel())
                return FiniteResult(all(chunk.values))

        large = [True] * (Q.GRADIENT_FINITE_CHUNK_ELEMENTS * 2 + 1)
        self.assertTrue(Q._has_any_fully_finite_gradient_bounded(
            FakeTorch, [Parameter(large), Parameter([True]), Parameter(None)]
        ))
        self.assertEqual(FakeTorch.observed_sizes, [1])
        FakeTorch.observed_sizes.clear()
        self.assertTrue(Q._has_any_fully_finite_gradient_bounded(
            FakeTorch, [Parameter(large)]
        ))
        self.assertEqual(
            FakeTorch.observed_sizes,
            [Q.GRADIENT_FINITE_CHUNK_ELEMENTS, Q.GRADIENT_FINITE_CHUNK_ELEMENTS, 1],
        )
        FakeTorch.observed_sizes.clear()
        late_nonfinite = [True] * Q.GRADIENT_FINITE_CHUNK_ELEMENTS + [False]
        self.assertFalse(Q._has_any_fully_finite_gradient_bounded(
            FakeTorch, [Parameter(late_nonfinite)]
        ))
        self.assertEqual(
            FakeTorch.observed_sizes,
            [Q.GRADIENT_FINITE_CHUNK_ELEMENTS, 1],
        )
        FakeTorch.observed_sizes.clear()
        self.assertFalse(Q._has_any_fully_finite_gradient_bounded(
            FakeTorch, [Parameter([False]), Parameter(None)]
        ))
        self.assertEqual(FakeTorch.observed_sizes, [1])
        FakeTorch.observed_sizes.clear()
        self.assertFalse(Q._has_any_fully_finite_gradient_bounded(
            FakeTorch, [Parameter(None)]
        ))
        self.assertEqual(FakeTorch.observed_sizes, [])

    def test_frozen_prompt_surfaces_and_cli_have_no_candidate_seal(self):
        self.assertEqual(Q.PROMPT_IDS_SHA256, "150bc5ed2443b17086c4f7fc4dada71f1a960dbc22ef025044053cea4ec4be89")
        self.assertEqual(Q.LOGIT_PROMPT_IDS_SHA256, "9b674b40eb12465e9b4183deb41fada852f0f3fdee089a695dab68ebccdfd113")
        self.assertEqual(Q.LOGIT_INPUT_SURFACE_SHA256, "178945c900cd54058802b4d510af67aa5ea1b6e2dabf343f5e4341ddcae1f311")
        self.assertEqual(Q.LOGIT_COMPARED_POSITIONS, 720)
        self.assertFalse(hasattr(Q, "seal"))
        with mock.patch("sys.stderr"), self.assertRaises(SystemExit):
            Q._parser().parse_args(["seal"])
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("clean_wrong + transformed_wrong", source)
        self.assertIn("clean_limited + transformed_limited", source)
        self.assertIn("cache_decode_equal = bool", source)
        self.assertIn("transformed_captured = _capture_layer_values", source)
        self.assertIn("text_model.finalize_from_conditional", source)
        self.assertNotIn("core.fuse_pre_norm_weight(\n        surface.lm_head.weight", source)

    def test_valid_full_width_is_still_incomplete_and_never_authorizes(self):
        value = valid_observation()
        self.assertEqual(Q.validate_observation(value)["status"], "INCOMPLETE_SERIALIZATION_AND_PEFT")
        self.assertFalse(value["nonzero_slice_authorized"])

    def test_metric_miss_must_be_adapter_incomplete(self):
        value = valid_observation()
        value["scalar"]["continuation_equal_count"] = 193
        value["model_level_gates_passed"] = False
        value["status"] = "INCOMPLETE_MODEL_LEVEL_QUALIFICATION"
        Q.validate_observation(value)
        value["status"] = "PASS"
        with self.assertRaises(Q.QualificationError):
            Q.validate_observation(value)

    def test_thresholds_and_cross_type_aliases_fail_closed(self):
        mutations = [
            ("nonzero_slice_authorized", True),
            ("model_level_gates_passed", 1),
        ]
        for name, replacement in mutations:
            value = valid_observation()
            value[name] = replacement
            with self.subTest(name=name), self.assertRaises(Q.QualificationError):
                Q.validate_observation(value)
        value = valid_observation()
        value["hf_paths"]["cache_decode"] = 1
        with self.assertRaises(Q.QualificationError):
            Q.validate_observation(value)
        value = valid_observation()
        value["logits"]["top1_equal"] = True
        with self.assertRaises(Q.QualificationError):
            Q.validate_observation(value)
        value = valid_observation()
        value["logits"]["compared_positions"] = Q.LOGIT_COMPARED_POSITIONS + 1
        with self.assertRaises(Q.QualificationError):
            Q.validate_observation(value)
        value = valid_observation()
        value["logits"]["input_surface_sha256"] = H("0")
        with self.assertRaises(Q.QualificationError):
            Q.validate_observation(value)
        value = valid_observation()
        value["scalar"]["limited_count"] = True
        with self.assertRaises(Q.QualificationError):
            Q.validate_observation(value)
        value = valid_observation()
        value["algebra"]["captured"][17]["post_ff_max_error"] = "0.0000000100001"
        value["model_level_gates_passed"] = False
        value["status"] = "INCOMPLETE_MODEL_LEVEL_QUALIFICATION"
        Q.validate_observation(value)

    def test_basis_discontinuity_topology_and_endpoint_alias_fail(self):
        value = valid_observation()
        value["bases"]["records"][2]["input"] = H("f")
        with self.assertRaises(Q.QualificationError):
            Q.validate_observation(value)
        value = valid_observation()
        value["bases"]["records"][-1]["output"] = H("f")
        with self.assertRaisesRegex(Q.QualificationError, "identity final output"):
            Q.validate_observation(value)

    def test_serialization_claims_and_incoherent_metrics_reject(self):
        value = valid_observation()
        value["serialization_peft"]["bit_identical_state"] = True
        with self.assertRaises(Q.QualificationError):
            Q.validate_observation(value)
        value = valid_observation()
        value["scalar"]["component_deltas"]["R"] = "0.01"
        with self.assertRaises(Q.QualificationError):
            Q.validate_observation(value)
        value = valid_observation()
        value["logits"]["top1_equal"] = 4095
        with self.assertRaises(Q.QualificationError):
            Q.validate_observation(value)

    def test_hf_or_endpoint_miss_is_sealable_incomplete_not_scientific_fail(self):
        for surface, field in (
            ("hf_paths", "cache_decode"),
            ("hf_paths", "cache_decode_equal"),
            ("endpoints", "head_untied_after"),
        ):
            value = valid_observation()
            value[surface][field] = False
            value["model_level_gates_passed"] = False
            value["status"] = "INCOMPLETE_MODEL_LEVEL_QUALIFICATION"
            with self.subTest(surface=surface, field=field):
                Q.validate_observation(value)
                self.assertIsNone(value["probe2_verdict"])
                self.assertFalse(value["nonzero_slice_authorized"])
        value = valid_observation()
        value["topology"]["layer_types"][5] = "sliding_attention"
        with self.assertRaises(Q.QualificationError):
            Q.validate_observation(value)
        value = valid_observation()
        value["endpoints"]["head_untied_after"] = 1
        with self.assertRaises(Q.QualificationError):
            Q.validate_observation(value)

    def test_duplicate_nonfinite_and_noncanonical_json_reject(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            for raw in (b'{"a":1,"a":1}\n', b'{"a":NaN}\n', b'{"a": 1}\n'):
                path.write_bytes(raw)
                with self.assertRaises(Q.QualificationError):
                    Q._load_json(path)


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.name", "fixture"], cwd=self.repo, check=True)
        exact_module_sources = set(Q.PROJECT_MODULE_SOURCES.values()) | {
            "scripts/qualify_slicegpt_runtime_v4.py"
        }
        for relative in Q.SOURCE_PATHS:
            path = self.repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if relative == Q.SOURCE_PATHS[0]:
                payload = SOURCE.read_bytes()
            elif relative in exact_module_sources:
                payload = (PROJECT / relative).read_bytes()
            else:
                payload = relative.encode()
            path.write_bytes(payload)
        subprocess.run(["git", "add", "--all"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "fixture"], cwd=self.repo, check=True)
        head, sources = Q.committed_sources(self.repo)
        self.value = valid_observation()
        self.value["provenance"]["repo_commit"] = head
        self.value["provenance"]["committed_sources"] = sources
        self.value["endpoints"]["text_model_source_sha256"] = sources[
            "scripts/slicegpt_gemma3_text_model_v4.py"
        ]
        self.archive = self.repo / "derisk/model_gate"
        self.archive.parent.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def seal(self):
        with (
            mock.patch.object(Q, "validate_external_bindings") as external,
            mock.patch.object(Q, "_verify_bootstrapped_runtime"),
        ):
            result = Q._archive_observation(
                repo=self.repo,
                root=self.archive,
                observation=self.value,
                runtime_archive=self.repo / "runtime",
                runtime_lock=self.repo / "lock.json",
                provenance_spec=self.repo / "spec.json",
                command={"argv": ["fixture"], "cwd": str(self.repo)},
                qualifier_source=SOURCE,
            )
        external.assert_called_once()
        return result

    def test_seal_is_strict_and_idempotent(self):
        first = self.seal()
        before = {path.name: path.read_bytes() for path in self.archive.iterdir()}
        second = self.seal()
        self.assertEqual(first, second)
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.archive.iterdir()})
        Q.validate_archive(self.archive)

    def test_tamper_extra_source_drift_and_partial_preservation(self):
        self.seal()
        (self.archive / "command.json").write_bytes(b"{}\n")
        with self.assertRaises(Q.QualificationError):
            Q.validate_archive(self.archive)
        (self.archive / "extra").write_text("x")
        with self.assertRaises(Q.QualificationError):
            Q.validate_archive(self.archive)

        other = self.repo / "derisk/partial"
        real_write = Q._write_new
        calls = 0
        def fail_second(path, payload):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("fixture crash")
            real_write(path, payload)
        with (
            mock.patch.object(Q, "validate_external_bindings"),
            mock.patch.object(Q, "_verify_bootstrapped_runtime"),
            mock.patch.object(Q, "_write_new", side_effect=fail_second),
        ):
            with self.assertRaises(OSError):
                Q._archive_observation(
                    repo=self.repo, root=other, observation=self.value,
                    runtime_archive=self.repo / "runtime", runtime_lock=self.repo / "lock.json",
                    provenance_spec=self.repo / "spec.json",
                    command={"argv": ["fixture"], "cwd": str(self.repo)}, qualifier_source=SOURCE,
                )
        self.assertTrue(other.exists())
        self.assertTrue(any(other.iterdir()))

    def test_live_source_drift_rejects_archive_replay(self):
        self.seal()
        dependency = self.repo / Q.SOURCE_PATHS[1]
        dependency.write_bytes(dependency.read_bytes() + b"drift")
        with (
            mock.patch.object(Q, "validate_external_bindings"),
            mock.patch.object(Q, "_verify_bootstrapped_runtime"),
        ):
            with self.assertRaises(Q.QualificationError):
                Q._archive_observation(
                    repo=self.repo, root=self.archive, observation=self.value,
                    runtime_archive=self.repo / "runtime", runtime_lock=self.repo / "lock.json",
                    provenance_spec=self.repo / "spec.json",
                    command={"argv": ["fixture"], "cwd": str(self.repo)}, qualifier_source=SOURCE,
                )

    def test_external_bindings_are_semantically_cross_checked(self):
        runtime_root = self.repo / "runtime"
        runtime_root.mkdir()
        ruler_root = self.repo / "ruler"
        ruler_root.mkdir()
        baseline_path = ruler_root / "baseline.json"
        terminal_path = ruler_root / "terminal.json"
        ladder_path = ruler_root / "ladder.json"
        baseline_path.write_text(
            json.dumps({"components": {name: 0.0 for name in ("R", "D", "J", "F")}}),
            encoding="utf-8",
        )
        terminal_path.write_text(
            json.dumps({"components": {"R": -1.0, "D": -1.0, "J": 1.0, "F": 1.0}}),
            encoding="utf-8",
        )
        ladder_path.write_text(
            json.dumps({
                "ladder_version": "nested_dual_track_v2",
                "corruption_tracks": {
                    "R": "form_corrupted", "D": "form_corrupted",
                    "J": "form_corrupted", "F": "factual_item_dropout",
                },
                "limit": None,
                "factual_dropout_order": [f"record-{index}" for index in range(40)],
                "component_summary": [
                    {"fraction": 1.0, "R": 1.0, "D": 1.0, "J": 1.0, "F": 1.0}
                ],
            }),
            encoding="utf-8",
        )
        for role, path in {
            "baseline": baseline_path, "terminal": terminal_path, "ladder": ladder_path,
        }.items():
            self.value["scalar"]["normalization_sources"][role] = {
                "path": path.name,
                "sha256": Q.sha256_file(path),
            }
        normalization = Q._verified_project_modules(
            self.repo,
            self.value["provenance"]["committed_sources"],
            {"decay_scalar_normalization"},
        )["decay_scalar_normalization"]
        loaded = normalization.load_bidirectional_anchors(
            baseline_path, terminal_path, ladder_path
        )
        self.value["scalar"]["normalization_policy_fingerprint"] = (
            normalization.bidirectional_policy_fingerprint(*loaded)
        )
        lock = self.repo / "lock.json"
        spec_path = self.repo / "spec.json"
        observation_runtime = {"sealed": "runtime"}
        write_json(lock, observation_runtime)
        write_json(runtime_root / "runtime_lock.json", observation_runtime)
        write_json(runtime_root / "runtime_observation.json", observation_runtime)
        spec = {
            "parent_model": {
                "weights_sha256": self.value["provenance"]["parent_weight_sha256"],
                "support_sha256": self.value["provenance"]["parent_support_sha256"],
                "fingerprint": self.value["provenance"]["parent_fingerprint"],
            },
            "calibration": {
                "archives": {"11": {
                    "metadata_fingerprint": self.value["provenance"]["calibration_fingerprint"],
                    "complete_sha256": self.value["provenance"]["calibration_complete_sha256"],
                }}
            },
            "clean_ruler": {
                "root": "ruler",
                "files_sha256": {
                    source["path"]: source["sha256"]
                    for source in self.value["scalar"]["normalization_sources"].values()
                },
                "fingerprint": self.value["provenance"]["clean_ruler_fingerprint"],
            },
        }
        write_json(spec_path, spec)
        (runtime_root / "provenance_spec.json").write_bytes(spec_path.read_bytes())
        self.value["provenance"]["runtime_archive_sha256"] = Q.exact_tree(runtime_root, "fixture runtime")
        self.value["provenance"]["clean_ruler_files_sha256"] = spec["clean_ruler"]["files_sha256"]
        runtime_qualification = {"identity_fingerprint": self.value["provenance"]["runtime_identity_fingerprint"]}
        with (
            mock.patch.object(Q.runtime_q, "validate_archive", return_value=runtime_qualification),
            mock.patch.object(Q.runtime_q, "load_canonical_json", side_effect=lambda path: observation_runtime if Path(path).name == "runtime_observation.json" else spec),
            mock.patch.object(Q.runtime_q, "validate_provenance", return_value=(spec, self.value["provenance"]["repo_commit"])),
            mock.patch.object(Q.runtime_q, "capture_live_runtime", return_value=observation_runtime),
            mock.patch.object(Q.runtime_q, "validate_runtime_observation", side_effect=lambda value: value),
        ):
            Q.validate_external_bindings(
                repo=self.repo, observation=self.value, runtime_archive=runtime_root,
                runtime_lock=lock, provenance_spec=spec_path,
            )
            bad = copy.deepcopy(self.value)
            bad["provenance"]["parent_fingerprint"] = H("9")
            with self.assertRaises(Q.QualificationError):
                Q.validate_external_bindings(
                    repo=self.repo, observation=bad, runtime_archive=runtime_root,
                    runtime_lock=lock, provenance_spec=spec_path,
                )
            bad = copy.deepcopy(self.value)
            bad["scalar"]["normalization_sources"]["baseline"], bad["scalar"]["normalization_sources"]["terminal"] = (
                bad["scalar"]["normalization_sources"]["terminal"],
                bad["scalar"]["normalization_sources"]["baseline"],
            )
            with self.assertRaisesRegex(Q.QualificationError, "semantic replay"):
                Q.validate_external_bindings(
                    repo=self.repo, observation=bad, runtime_archive=runtime_root,
                    runtime_lock=lock, provenance_spec=spec_path,
                )

    def test_observer_modules_reject_preload_and_ignore_search_path_substitution(self):
        sources = self.value["provenance"]["committed_sources"]
        alternate = Path(self.tmp.name) / "alternate"
        alternate.mkdir()
        (alternate / "decay_scalar_normalization.py").write_text(
            "def load_bidirectional_anchors(*args): return ('fake',)\n",
            encoding="utf-8",
        )
        sys.path.insert(0, str(alternate))
        try:
            loaded = Q._verified_project_modules(
                self.repo, sources, {"decay_scalar_normalization"}
            )["decay_scalar_normalization"]
        finally:
            sys.path.remove(str(alternate))
        self.assertEqual(
            Path(loaded.__file__),
            self.repo / "scripts/decay_scalar_normalization.py",
        )
        self.assertEqual(
            Path(loaded.load_bidirectional_anchors.__code__.co_filename),
            self.repo / "scripts/decay_scalar_normalization.py",
        )

        sentinel = object()
        sys.modules["decay_scalar_normalization"] = sentinel
        try:
            with self.assertRaisesRegex(Q.QualificationError, "preloaded/contaminated"):
                Q._verified_project_modules(
                    self.repo, sources, {"decay_scalar_normalization"}
                )
        finally:
            self.assertIs(sys.modules.pop("decay_scalar_normalization"), sentinel)

        original_factory = importlib.util.spec_from_file_location
        substituted = alternate / "decay_scalar_normalization.py"

        def substitute(name, location, *args, **kwargs):
            return original_factory(name, substituted, *args, **kwargs)

        with mock.patch.object(importlib.util, "spec_from_file_location", side_effect=substitute):
            with self.assertRaisesRegex(Q.QualificationError, "specification was substituted"):
                Q._verified_project_modules(
                    self.repo, sources, {"decay_scalar_normalization"}
                )

        create_module_calls = []
        exact_path = self.repo / "scripts/decay_scalar_normalization.py"

        class HostileSameOriginLoader(importlib.machinery.SourceFileLoader):
            def create_module(self, spec):
                create_module_calls.append(spec.name)
                return super().create_module(spec)

        def same_origin_hostile(name, location, *args, **kwargs):
            loader = HostileSameOriginLoader(name, str(exact_path))
            return importlib.util.spec_from_loader(name, loader, origin=str(exact_path))

        with mock.patch.object(
            importlib.util,
            "spec_from_file_location",
            side_effect=same_origin_hostile,
        ):
            with self.assertRaisesRegex(Q.QualificationError, "nonstandard source loader"):
                Q._verified_project_modules(
                    self.repo, sources, {"decay_scalar_normalization"}
                )
        self.assertEqual(create_module_calls, [])

    def test_full_observer_dependency_graph_has_exact_local_origins(self):
        if importlib.util.find_spec("torch") is None or importlib.util.find_spec("transformers") is None:
            self.skipTest("pinned Torch/Transformers runtime is unavailable")
        modules = Q._verified_project_modules(
            self.repo,
            self.value["provenance"]["committed_sources"],
            set(Q.PROJECT_MODULE_SOURCES),
        )
        self.assertEqual(set(modules), set(Q.PROJECT_MODULE_SOURCES))
        for name, module in modules.items():
            self.assertEqual(
                Path(module.__file__),
                self.repo / Q.PROJECT_MODULE_SOURCES[name],
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
