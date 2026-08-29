"""CPU-only contract tests for the Probe 2 heavy-parent repeat driver."""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_noise_sweep import DEFAULT_ALPHAS, DEFAULT_SEEDS
from run_noise_sweep_heavy import (
    SUMMARY_NAME,
    analyse_heavy_curve,
    curve_alphas_for_resume,
    select_parent_alpha,
    validate_primary_archive,
    verify_manifest,
    write_manifest_atomic,
)


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def parent_fixture(root):
    model = root / "model"
    model.mkdir()
    (model / "model.safetensors").write_bytes(b"weights")
    (model / "config.json").write_text("{}\n", encoding="utf-8")
    identity = {
        "source_model": str(model.resolve()),
        "weight_file_sha256": {},
        "support_file_sha256": {},
    }
    from run_noise_sweep import fingerprint, model_weight_hashes, support_file_hashes

    identity["weight_file_sha256"] = model_weight_hashes(model)
    identity["support_file_sha256"] = support_file_hashes(model)
    identity["fingerprint"] = fingerprint(identity)
    archive = root / "primary"
    write_json(archive / "parent_identity.json", identity)
    write_json(
        archive / "run_config.json",
        {"parent_model": str(model.resolve())},
    )
    write_json(
        archive / "sweep_summary_bidirectional_v2.json",
        {
            "certification_scope": "clean_parent_primary_only",
            "parent_model": str(model.resolve()),
            "normalisation_version": "bidirectional_synthetic_v2",
            "normalisation_policy_fingerprint": "fixture-policy",
            "alpha_at_scalar": {"65.0": 0.4},
            "gates": {
                "primary_verdict": "PASS",
                "probe2_verdict": "INCOMPLETE_PENDING_HEAVY_PARENT",
            },
        },
    )
    write_manifest_atomic(archive)
    return archive, model


def fake_curve(means):
    curve = {}
    for alpha, mean in zip(DEFAULT_ALPHAS, means):
        curve[alpha] = {
            "mean": mean,
            "raw_component_means": {key: mean / 100.0 for key in "RDJF"},
            "normalised_component_means": {key: mean / 100.0 for key in "RDJF"},
            "normalisation_direction_counts": {
                key: {"positive_synthetic": len(DEFAULT_SEEDS)} for key in "RDJF"
            },
        }
    return curve


def main():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        archive, model = parent_fixture(root)
        verified = validate_primary_archive(archive, model)
        assert verified["alpha65"] == 0.4

        # Exact coverage and tamper detection are fail closed.
        extra = archive / "extra.txt"
        extra.write_text("unsealed", encoding="utf-8")
        try:
            verify_manifest(archive)
        except RuntimeError:
            pass
        else:
            raise AssertionError("unmanifested file was accepted")
        extra.unlink()
        verify_manifest(archive)

        # A stale manifest temp must never become a manifest entry.
        (archive / "MANIFEST.sha256").unlink()
        (archive / "MANIFEST.sha256.tmp").write_text("partial", encoding="utf-8")
        write_manifest_atomic(archive)
        assert "MANIFEST.sha256.tmp" not in (
            archive / "MANIFEST.sha256"
        ).read_text(encoding="utf-8")

        # Nominal hit and bounded same-seed bisection.
        alpha, scalar, history = select_parent_alpha(0.4, lambda _: 65.0)
        assert (alpha, scalar, len(history)) == (0.4, 65.0, 1)
        alpha, scalar, history = select_parent_alpha(
            0.25, lambda value: 100.0 * value
        )
        assert 0.60 <= scalar / 100.0 <= 0.70
        assert len(history) <= 10
        alpha, scalar, _ = select_parent_alpha(0.4, lambda _: 55.0)
        assert alpha is scalar is None

        # Exact gate boundary and aggregate verdict inputs.
        curve = fake_curve([65.0 + 35.0 * alpha for alpha in DEFAULT_ALPHAS])
        gates = analyse_heavy_curve(curve, 65.0, 100.0, [])
        assert gates["spearman_gate_pass"] is True
        assert gates["loo_gate_pass"] is True
        assert gates["heavy_verdict"] == "PASS"
        bad_curve = fake_curve([61, 69, 62, 68, 63, 67, 64, 66])
        gates = analyse_heavy_curve(bad_curve, 60.0, 70.0, [])
        assert gates["heavy_verdict"] == "FAIL"

        resumed = curve_alphas_for_resume([{"alpha": 0.675}])
        assert 0.675 in resumed and all(alpha in resumed for alpha in DEFAULT_ALPHAS)
        try:
            curve_alphas_for_resume([{"alpha": 1.5}])
        except RuntimeError:
            pass
        else:
            raise AssertionError("invalid persisted bisection was accepted")

        assert SUMMARY_NAME.endswith("_v2.json")

    print("heavy-parent Probe 2 contract tests: PASS")


if __name__ == "__main__":
    main()
