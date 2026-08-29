import hashlib
import importlib.util
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).with_name("run_slicegpt_pilot_v4.py")
SPEC = importlib.util.spec_from_file_location("run_slicegpt_pilot_v4", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
sys.path.insert(0, str(SCRIPT.parent))
import check_slicegpt_gemma3_zero_slice as ZERO_HARNESS
import slicegpt_gemma3_math_v4 as GEMMA_MATH


def fake_config():
    body = {
        "version": MODULE.VERSION,
        "certification_scope": "adapter_qualification_only_not_a_pilot_or_probe2_verdict",
        "fixed_fraction_grid": list(MODULE.FRACTIONS),
        "fixed_retained_dimensions": list(MODULE.RETAINED_DIMENSIONS),
        "seed_policy": MODULE.SEED_POLICY,
        "mechanism": "SliceGPT_structural_slicing_separate_dial",
        "post_result_layer_targeting": False,
        "post_result_mechanism_blending": False,
        "scalar_instrument": "unchanged_sealed_v2_ruler_and_unlimited_scalar_battery",
        "protocol_spec_expected_path": MODULE.PROTOCOL_SPEC_DEFAULT,
        "protocol_spec_present": True,
        "vendor_upstream": dict(MODULE.VENDOR_UPSTREAM),
        "evidence_sha256": {name: "1" * 64 for name in MODULE.EVIDENCE_PATHS},
        "source_identity": {
            "commit": "0" * 40,
            "sha256": {
                name: ("1" * 64 if name in MODULE.EVIDENCE_PATHS else "2" * 64)
                for name in MODULE.COMMITTED_PATHS
            },
        },
    }
    body["fingerprint"] = MODULE.fingerprint(body)
    return body


def rewrite_archive_for_config(root, config):
    MODULE.atomic_write_json(root / "run_config.json", config)
    report = MODULE._expected_report(config)
    MODULE.atomic_write_json(root / "adapter_blocked.json", report)
    MODULE.atomic_write_json(
        root / "COMPLETE.json",
        {
            "status": "complete",
            "outcome": "BLOCKED_ADAPTER_QUALIFICATION",
            "config_fingerprint": config["fingerprint"],
            "report_sha256": MODULE.sha256_of_file(root / "adapter_blocked.json"),
        },
    )
    MODULE.write_manifest(root)


class SliceGPTV4BoundaryTests(unittest.TestCase):
    def test_exact_predeclared_grid_and_frozen_diagnostic_seed(self):
        self.assertEqual(
            MODULE.FRACTIONS,
            (0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60, 0.70, 0.80),
        )
        self.assertEqual(MODULE.PILOT_SEED, 11)
        self.assertEqual(MODULE.SEED_POLICY["fresh_primary_calibration"], [0, 1, 2])
        self.assertEqual(MODULE.SEED_POLICY["heavy_parent_calibration"], 7)
        self.assertEqual(
            MODULE.RETAINED_DIMENSIONS,
            (2432, 2304, 2176, 2048, 1920, 1792, 1664, 1536, 1280, 1024, 768, 512),
        )
        self.assertNotIn(0.0, MODULE.FRACTIONS)
        self.assertNotIn(1.0, MODULE.FRACTIONS)

    def test_blocker_set_is_exact_and_never_a_verdict(self):
        codes = [item["code"] for item in MODULE.BLOCKERS]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertEqual(
            codes,
            [
                "UNQUALIFIED_GEMMA3_ADAPTER",
                "UNSEALED_ADAPTER_EQUIVALENCE",
                "UNMATERIALIZED_CALIBRATION_TENSORS",
                "UNQUALIFIED_NATIVE_SERIALIZATION",
                "UNQUALIFIED_PEFT_AND_PROJECT_LOADER",
                "UNSEALED_RUNTIME_LOCK",
            ],
        )
        report = MODULE._expected_report(fake_config())
        self.assertIsNone(report["probe2_verdict"])
        self.assertIsNone(report["pilot_outcome"])
        self.assertTrue(report["explicitly_not_a_pass_verdict"])
        self.assertFalse(report["gpu_work_launched"])
        self.assertFalse(report["model_mutated"])
        self.assertNotIn("UNVERIFIED_VENDORED_UPSTREAM", codes)
        self.assertEqual(MODULE.validate_vendored_upstream(SCRIPT.parents[1]), MODULE.VENDOR_UPSTREAM)
        self.assertTrue(
            {
                "scripts/check_slicegpt_gemma3_zero_slice.py",
                "scripts/slicegpt_gemma3_math_v4.py",
                "scripts/test_slicegpt_pilot_v4.py",
                "scripts/verify_transformer_compression_vendor.py",
            }.issubset(MODULE.SOURCE_PATHS)
        )
        self.assertTrue(
            {
                ".gitattributes",
                "vendor/TransformerCompression/UPSTREAM.md",
                "vendor/TransformerCompression/SOURCE_SHA256SUMS",
            }.issubset(MODULE.EVIDENCE_PATHS)
        )

    def test_nonfinite_json_rejected_recursively(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.assertRaisesRegex(RuntimeError, "non-finite"):
                MODULE.canonical_bytes({"nested": [{"value": value}]})
            with self.assertRaisesRegex(RuntimeError, "non-finite"):
                MODULE.fingerprint({"nested": value})

    def test_nonfinite_json_constant_rejected_on_read(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text('{"value": NaN}', encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "non-finite"):
                MODULE.read_json(path)

    def test_seal_is_exact_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            config = fake_config()
            first = MODULE.seal_blocked_archive(root, config)
            before = {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in root.iterdir()
            }
            second = MODULE.seal_blocked_archive(root, config)
            after = {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in root.iterdir()
            }
            self.assertEqual(first, second)
            self.assertEqual(before, after)
            self.assertEqual(set(before), MODULE.ARCHIVE_MEMBERS | {MODULE.MANIFEST_NAME})
            self.assertTrue(MODULE.verify_manifest(root))

    def test_partial_archive_resumes_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            root.mkdir()
            config = fake_config()
            MODULE.atomic_write_json(root / "run_config.json", config)
            original = (root / "run_config.json").read_bytes()
            report = MODULE.seal_blocked_archive(root, config)
            self.assertEqual((root / "run_config.json").read_bytes(), original)
            self.assertEqual(report["status"], "BLOCKED_ADAPTER_QUALIFICATION")

    def test_changed_partial_config_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            root.mkdir()
            config = fake_config()
            changed = dict(config)
            changed["seed_policy"] = dict(changed["seed_policy"])
            changed["seed_policy"]["diagnostic_calibration"] = 7
            MODULE.atomic_write_json(root / "run_config.json", changed)
            with self.assertRaisesRegex(RuntimeError, "archive member changed"):
                MODULE.seal_blocked_archive(root, config)

    def test_exact_atomic_temporary_is_recovered_but_changed_one_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            root.mkdir()
            config = fake_config()
            temporary = root / "run_config.json.tmp"
            temporary.write_bytes(MODULE.canonical_bytes(config))
            MODULE.seal_blocked_archive(root, config)
            self.assertTrue((root / "run_config.json").is_file())
            self.assertFalse(temporary.exists())

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            root.mkdir()
            (root / "run_config.json.tmp").write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "temporary member changed"):
                MODULE.seal_blocked_archive(root, fake_config())

    def test_unexpected_partial_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            root.mkdir()
            (root / "commands.log").write_text("should not exist", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "unexpected files"):
                MODULE.seal_blocked_archive(root, fake_config())

    def test_manifest_tamper_and_extra_member_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            MODULE.seal_blocked_archive(root, fake_config())
            report_path = root / "adapter_blocked.json"
            report_path.write_bytes(report_path.read_bytes() + b" ")
            with self.assertRaisesRegex(RuntimeError, "changed"):
                MODULE.verify_manifest(root)

    def test_manifest_order_is_canonical_and_partial_manifest_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            MODULE.seal_blocked_archive(root, fake_config())
            manifest = root / MODULE.MANIFEST_NAME
            lines = manifest.read_text(encoding="ascii").splitlines()
            manifest.write_text("\n".join(reversed(lines)) + "\n", encoding="ascii")
            with self.assertRaisesRegex(RuntimeError, "changed"):
                MODULE.verify_manifest(root)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            root.mkdir()
            temporary = root / (MODULE.MANIFEST_NAME + ".tmp")
            temporary.write_text("unknown crash image\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "preserved fail-closed"):
                MODULE.seal_blocked_archive(root, fake_config())
            self.assertEqual(temporary.read_text(encoding="utf-8"), "unknown crash image\n")

    def test_symlink_ancestor_is_rejected_before_resolve(self):
        with tempfile.TemporaryDirectory() as directory:
            linked = Path(directory) / "linked"
            original = Path.is_symlink

            def simulated_symlink(path):
                return Path(path) == linked or original(path)

            with mock.patch.object(Path, "is_symlink", simulated_symlink):
                with self.assertRaisesRegex(RuntimeError, "symlink component"):
                    MODULE.reject_symlink_components(
                        linked / "archive" / "result.json", "fixture"
                    )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            MODULE.seal_blocked_archive(root, fake_config())
            (root / "extra.txt").write_text("extra", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "changed"):
                MODULE.verify_manifest(root)

    def test_manifest_traversal_duplicate_and_noncanonical_digest_rejected(self):
        bad_lines = (
            f"{'0' * 64}  ../escape\n",
            f"{'0' * 64}  run_config.json\n{'1' * 64}  run_config.json\n",
            f"{'A' * 64}  run_config.json\n",
        )
        for contents in bad_lines:
            with self.subTest(contents=contents):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    (root / MODULE.MANIFEST_NAME).write_text(contents, encoding="utf-8")
                    with self.assertRaisesRegex(RuntimeError, "malformed"):
                        MODULE.verify_manifest(root)

    def test_nested_manifest_temporary_is_not_hidden_from_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            MODULE.seal_blocked_archive(root, fake_config())
            nested = root / "nested"
            nested.mkdir()
            (nested / (MODULE.MANIFEST_NAME + ".tmp")).write_text("hidden", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "changed"):
                MODULE.verify_manifest(root)

    def test_root_manifest_temporary_and_empty_directory_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            MODULE.seal_blocked_archive(root, fake_config())
            (root / (MODULE.MANIFEST_NAME + ".tmp")).write_text("stale", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "changed"):
                MODULE.verify_manifest(root)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            MODULE.seal_blocked_archive(root, fake_config())
            (root / "empty").mkdir()
            with self.assertRaisesRegex(RuntimeError, "changed"):
                MODULE.verify_manifest(root)

    def test_semantic_tamper_rejected_even_with_rewritten_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archive"
            MODULE.seal_blocked_archive(root, fake_config())
            report_path = root / "adapter_blocked.json"
            report = MODULE.read_json(report_path)
            report["probe2_verdict"] = "PASS"
            MODULE.atomic_write_json(report_path, report)
            MODULE.write_manifest(root)
            with self.assertRaisesRegex(RuntimeError, "semantics changed"):
                MODULE.validate_sealed_archive(root)

    def test_rewritten_config_constants_and_evidence_binding_are_rejected(self):
        for mutation, message in (
            (lambda config: config.__setitem__("mechanism", "different mechanism"), "semantics changed"),
            (
                lambda config: config["vendor_upstream"].__setitem__("commit", "0" * 40),
                "semantics changed",
            ),
            (
                lambda config: config["evidence_sha256"].__setitem__(
                    MODULE.EVIDENCE_PATHS[0], "3" * 64
                ),
                "not bound",
            ),
        ):
            with self.subTest(message=message):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory) / "archive"
                    config = fake_config()
                    MODULE.seal_blocked_archive(root, config)
                    mutation(config)
                    config["fingerprint"] = MODULE.fingerprint(
                        {key: value for key, value in config.items() if key != "fingerprint"}
                    )
                    rewrite_archive_for_config(root, config)
                    with self.assertRaisesRegex(RuntimeError, message):
                        MODULE.validate_sealed_archive(root)

    def test_existing_canonical_protocol_spec_is_required_and_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "docs/litreview/notes").mkdir(parents=True)
            (repo / "EXPERIMENTS.md").write_text(
                "[.05,.10,.15,.20,.25,.30,.35,.40,.50,.60,.70,.80]\n"
                "Layer targeting or blended mechanisms are not added post hoc.\n",
                encoding="utf-8",
            )
            for relative in MODULE.EVIDENCE_PATHS:
                if relative == "EXPERIMENTS.md":
                    continue
                path = repo / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("evidence\n", encoding="utf-8")
            spec_path = repo / MODULE.PROTOCOL_SPEC_DEFAULT
            spec_path.parent.mkdir(parents=True, exist_ok=True)
            protocol_lines = [
                "diagnostic calibration seed **11**",
                "fresh primary seeds **0/1/2**",
                "one-shot heavy-parent seed **7**",
                "constant residual-width scheduler",
                "round_interval=8",
                "No fraction above zero may run until all of the following are sealed",
            ] + [
                f"| {fraction:.2f} | {dimension} |".replace("| 0.", "| .")
                for fraction, dimension in zip(MODULE.FRACTIONS, MODULE.RETAINED_DIMENSIONS)
            ]
            spec_path.write_text("\n".join(protocol_lines) + "\n", encoding="utf-8")
            with mock.patch.object(
                MODULE,
                "validate_vendored_upstream",
                return_value=dict(MODULE.VENDOR_UPSTREAM),
            ):
                config = MODULE.build_config(repo, fake_config()["source_identity"], spec_path)
            self.assertTrue(config["protocol_spec_present"])
            self.assertEqual(config["seed_policy"]["diagnostic_calibration"], 11)

    def test_noncanonical_protocol_spec_path_is_rejected_even_when_absent(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            with self.assertRaisesRegex(RuntimeError, "canonical repository path"):
                MODULE.build_config(
                    repo,
                    fake_config()["source_identity"],
                    repo / "data/other.json",
                )

    def test_frozen_boundary_requires_grid_and_no_blend_sentence(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "docs/litreview/notes").mkdir(parents=True)
            for relative in MODULE.EVIDENCE_PATHS:
                path = repo / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("not the declaration\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "fraction grid changed"):
                MODULE.validate_frozen_boundary(repo)

    def test_committed_source_binding_rejects_dirty_source_and_survives_head_move(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            relative = MODULE.SOURCE_PATHS[0]
            source = repo / relative
            source.parent.mkdir(parents=True)
            source.write_text("print('v1')\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            subprocess.run(["git", "add", relative], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-qm", "v1"], cwd=repo, check=True)
            one_source = (relative,)
            identity = MODULE.committed_source_identity(repo, one_source)

            source.write_text("print('dirty')\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "differs"):
                MODULE.committed_source_identity(repo, one_source)

            source.write_text("print('v2')\n", encoding="utf-8")
            subprocess.run(["git", "add", relative], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-qm", "v2"], cwd=repo, check=True)
            MODULE.validate_recorded_source_identity(repo, identity, one_source)

    def test_default_committed_binding_includes_and_rejects_dirty_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            for relative in MODULE.COMMITTED_PATHS:
                path = repo / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"{relative}\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repo, check=True)
            identity = MODULE.committed_source_identity(repo)
            self.assertEqual(set(identity["sha256"]), set(MODULE.COMMITTED_PATHS))
            (repo / "requirements.txt").write_text("dirty\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "differs"):
                MODULE.committed_source_identity(repo)

    def test_recorded_source_identity_schema_is_exact(self):
        malformed = {
            "commit": "not-a-commit",
            "sha256": {MODULE.SOURCE_PATHS[0]: "0" * 64},
        }
        with self.assertRaisesRegex(RuntimeError, "malformed"):
            MODULE.validate_recorded_source_identity(Path.cwd(), malformed)


class Gemma3ZeroSliceHarnessTests(unittest.TestCase):
    def test_math_module_is_lazy_and_explicitly_unvalidated(self):
        self.assertIn("unvalidated", GEMMA_MATH.MATH_VERSION)
        self.assertNotIn("torch", GEMMA_MATH.__dict__)
        self.assertTrue(callable(GEMMA_MATH.fuse_pre_norm_linear))
        self.assertTrue(callable(GEMMA_MATH.dense_post_norm_scale))
        self.assertTrue(callable(GEMMA_MATH.residual_shortcut))

    def test_harness_is_diagnostic_only_and_uses_frozen_prompt_prefix(self):
        self.assertEqual(ZERO_HARNESS.MAX_PROMPTS, 4)
        self.assertEqual(ZERO_HARNESS.MAX_NEW_TOKENS, 32)
        self.assertEqual(ZERO_HARNESS.SEED, 0)
        prompts = ZERO_HARNESS.load_prompts(SCRIPT.parents[1])
        self.assertEqual([row["id"] for row in prompts], ["gen_001", "gen_002", "gen_003", "gen_004"])
        self.assertIn("docs/V4_SLICEGPT_PROTOCOL.md", ZERO_HARNESS.EXECUTED_PATHS)

    def test_harness_config_and_finite_metrics_fail_closed(self):
        args = type("Args", (), {"max_prompts": 4, "max_new_tokens": 31})()
        with self.assertRaisesRegex(RuntimeError, "configuration is fixed"):
            ZERO_HARNESS.require_exact_config(args)
        for value in (math.nan, math.inf, -math.inf):
            with self.assertRaisesRegex(RuntimeError, "non-finite"):
                ZERO_HARNESS.finite(value, "fixture")

    def test_expected_identity_change_surface_is_exact(self):
        names = [
            f"model.language_model.layers.0.{suffix}"
            for suffix in (
                "input_layernorm.weight",
                "self_attn.q_proj.weight",
                "self_attn.k_proj.weight",
                "self_attn.v_proj.weight",
                "pre_feedforward_layernorm.weight",
                "mlp.gate_proj.weight",
                "mlp.up_proj.weight",
            )
        ]
        names += [
            "model.language_model.layers.0.self_attn.o_proj.weight",
            "model.language_model.layers.0.mlp.down_proj.weight",
            "model.language_model.layers.0.post_attention_layernorm.weight",
            "model.language_model.layers.0.post_feedforward_layernorm.weight",
            "model.language_model.embed_tokens.weight",
        ]

        class FakeModel:
            def named_parameters(self):
                return [(name, object()) for name in names]

        actual = ZERO_HARNESS.expected_identity_fusion_changes(
            FakeModel(), [{"layer": 0}]
        )
        self.assertEqual(actual, set(names[:7]))
        self.assertTrue(all("o_proj" not in name and "down_proj" not in name for name in actual))

        layers = [object()]
        model = type(
            "RecordModel",
            (),
            {"model": type("Backbone", (), {"language_model": type("LM", (), {"layers": layers})()})()},
        )()
        record = {
            "layer": 0,
            "attention_pre_norm_fused_into": ["q_proj", "k_proj", "v_proj"],
            "feedforward_pre_norm_fused_into": ["gate_proj", "up_proj"],
            "post_norms_unchanged": True,
            "q_norm_k_norm_unchanged": True,
            "basis": "identity",
            "sliced_dimensions": 0,
        }
        ZERO_HARNESS.validate_identity_layer_records(model, [record])
        changed = dict(record, sliced_dimensions=8)
        with self.assertRaisesRegex(RuntimeError, "nonzero slice"):
            ZERO_HARNESS.validate_identity_layer_records(model, [changed])

    def test_tokenizer_and_runtime_provenance_surface_is_explicit(self):
        class FakeTokenizer:
            chat_template = "{{ messages }}"
            name_or_path = "/pinned/model"
            vocab_size = 262208
            padding_side = "left"
            pad_token_id = 0
            bos_token_id = 2
            eos_token_id = 1

            def __len__(self):
                return 262208

        record = ZERO_HARNESS.tokenizer_record(FakeTokenizer())
        self.assertEqual(record["vocab_size"], 262208)
        self.assertEqual(record["padding_side"], "left")
        self.assertRegex(record["chat_template_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            set(ZERO_HARNESS.RUNTIME_DISTRIBUTIONS),
            {
                "accelerate",
                "datasets",
                "numpy",
                "peft",
                "pyarrow",
                "safetensors",
                "tokenizers",
                "torch",
                "transformers",
            },
        )

    def test_gemma3_projection_and_norm_surface_is_explicit(self):
        import inspect

        source = inspect.getsource(GEMMA_MATH.apply_identity_basis_pre_norm_fusion)
        self.assertIn('(\"q_proj\", \"k_proj\", \"v_proj\")', source)
        self.assertIn('(\"gate_proj\", \"up_proj\")', source)
        self.assertIn("input_layernorm.weight.zero_()", source)
        self.assertIn("pre_feedforward_layernorm.weight.zero_()", source)
        self.assertNotIn("q_norm.weight", source)
        self.assertNotIn("k_norm.weight", source)
        harness_source = inspect.getsource(ZERO_HARNESS.main)
        self.assertIn("configure_determinism(torch)", harness_source)
        self.assertIn('"acceptance_thresholds_frozen": True', harness_source)
        self.assertIn('"full_adapter_qualification_gate_applied": False', harness_source)
        self.assertNotIn("save_pretrained", harness_source)
        self.assertIn("disk_hashes_unchanged_verified", harness_source)
        self.assertIn('"nonzero_slice_executed": False', harness_source)
        self.assertNotIn('"probe2_verdict": "PASS"', harness_source)

    @unittest.skipUnless(importlib.util.find_spec("torch") is not None, "torch is server-only")
    def test_full_width_rotation_algebra_with_torch(self):
        import torch

        dtype = torch.float64
        theta = torch.tensor(0.37, dtype=dtype)
        q_in = torch.stack(
            (
                torch.stack((torch.cos(theta), -torch.sin(theta))),
                torch.stack((torch.sin(theta), torch.cos(theta))),
            )
        )
        phi = torch.tensor(-0.21, dtype=dtype)
        q_out = torch.stack(
            (
                torch.stack((torch.cos(phi), -torch.sin(phi))),
                torch.stack((torch.sin(phi), torch.cos(phi))),
            )
        )
        x = torch.tensor([[0.4, -1.2]], dtype=dtype)
        weight = torch.tensor([[0.2, 0.7], [-0.6, 0.3]], dtype=dtype)
        norm_weight = torch.tensor([0.1, -0.2], dtype=dtype)
        scale = 1.0 + norm_weight
        original_pre = (x * scale) @ weight.transpose(0, 1)
        rotated_x = x @ q_in
        fused = GEMMA_MATH.fuse_pre_norm_linear(weight, norm_weight, q_in)
        self.assertTrue(torch.allclose(original_pre, rotated_x @ fused.transpose(0, 1), atol=1e-12))

        branch = torch.tensor([[0.9, -0.5]], dtype=dtype)
        dense = GEMMA_MATH.dense_post_norm_scale(norm_weight, q_out)
        self.assertTrue(
            torch.allclose((branch * scale) @ q_out, (branch @ q_out) @ dense, atol=1e-12)
        )
        shortcut = GEMMA_MATH.residual_shortcut(q_in, q_out)
        self.assertTrue(torch.allclose(rotated_x @ shortcut, x @ q_out, atol=1e-12))

        eps = 1e-6
        rms = x * torch.rsqrt(x.pow(2).mean(-1, keepdim=True) + eps)
        post_original_rotated = (rms * scale) @ q_out
        post_dense = GEMMA_MATH.dense_post_norm_scale(
            norm_weight, q_out, compute_dtype=torch.float64
        )
        post_actual = GEMMA_MATH.rotated_post_norm(
            x @ q_out,
            post_dense,
            eps,
            compute_dtype=torch.float64,
        )
        self.assertTrue(torch.allclose(post_original_rotated, post_actual, atol=1e-12))

        x_bf16 = torch.tensor([[0.431, -1.217]], dtype=torch.bfloat16)
        q_bf16 = q_out.to(torch.bfloat16)
        weight_bf16 = norm_weight.to(torch.bfloat16)
        dense_fp32 = GEMMA_MATH.dense_post_norm_scale(
            weight_bf16, q_bf16, compute_dtype=torch.float32
        )
        rotated_bf16 = x_bf16 @ q_bf16
        normalized_fp32 = rotated_bf16.float()
        normalized_fp32 = normalized_fp32 * torch.rsqrt(
            normalized_fp32.pow(2).mean(-1, keepdim=True) + eps
        )
        expected_bf16 = (normalized_fp32 @ dense_fp32).to(torch.bfloat16)
        actual_bf16 = GEMMA_MATH.rotated_post_norm(rotated_bf16, dense_fp32, eps)
        self.assertTrue(torch.equal(expected_bf16, actual_bf16))
        wrong_pre_affine_cast = (
            normalized_fp32.to(torch.bfloat16) @ dense_fp32.to(torch.bfloat16)
        )
        self.assertFalse(torch.equal(expected_bf16, wrong_pre_affine_cast))

        input_ids = torch.tensor(
            [[1, 2], [3, 4], [5, 6], [7, 8]], dtype=torch.int64
        )
        attention_mask = torch.tensor(
            [[0, 1], [1, 1], [0, 1], [1, 1]], dtype=torch.int64
        )
        input_record = ZERO_HARNESS.validate_input_batch(
            {"input_ids": input_ids, "attention_mask": attention_mask}
        )
        self.assertEqual(input_record["attention_mask_one_counts"], [1, 2, 1, 2])
        self.assertFalse(input_record["attention_mask_all_one"])
        self.assertEqual(set(input_record["tensors"]), ZERO_HARNESS.REQUIRED_INPUT_KEYS)

        from transformers.models.gemma3.modeling_gemma3 import Gemma3RMSNorm

        real_norm = Gemma3RMSNorm(2, eps=eps).to(dtype=torch.bfloat16)
        with torch.no_grad():
            real_norm.weight.copy_(weight_bf16)
        real_input = torch.tensor([[0.431, -1.217]], dtype=torch.bfloat16)
        real_actual = real_norm(real_input)
        real_expected = real_input.float()
        real_expected = real_expected * torch.rsqrt(
            real_expected.pow(2).mean(-1, keepdim=True) + eps
        )
        real_expected = (real_expected * (1.0 + real_norm.weight.float())).to(
            real_actual.dtype
        )
        self.assertTrue(torch.equal(real_expected, real_actual))


if __name__ == "__main__":
    unittest.main()
