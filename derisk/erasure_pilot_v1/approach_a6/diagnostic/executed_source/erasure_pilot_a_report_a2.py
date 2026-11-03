"""Assemble A2's complete paired transcripts and verified final artifact references."""

import json
from pathlib import Path

try:
    from scripts import erasure_pilot_a_second as second
    from scripts import runpod_pilot as helper
except ModuleNotFoundError:
    import erasure_pilot_a_second as second
    import runpod_pilot as helper


def build() -> Path:
    """Reread A2's final files, verify every adapter, and assemble the full report.
    Why: the manager needs complete exchanges and evidence before accepting counts.
    If wrong: missing quotes or an incorrect teacher path could misstate the result.
    """
    second.configure()
    out = second.OUT
    read = second.review.read
    ledger = read(helper.LEDGER)
    connection = read(out / "connection.json")
    entry = helper.find_pod(ledger, connection["pod_id"])
    selected = read(out / "selected_adapter.json")
    adapter = second.run.ROOT / selected["adapter"]
    if second.run.harness.checkpoint_hashes(adapter) != selected["hashes"]:
        raise ValueError("Selected adapter hashes do not match the copied files")
    accounting = {key: entry.get(key) for key in ["id", "label", "actual_gpu_type", "cloud", "started_at",
                  "terminated_at", "status", "hourly_price_usd", "actual_hourly_price_usd", "max_hours"]}
    accounting["conservative_spend_usd"] = str(helper.pod_spend(entry, helper.utc_now()))
    lines = ["# Approach A2 worker report", "", "Judge labels only. Every final slot remains empty.", "",
             "## Allocation and accounting", "", "```json", json.dumps(accounting, indent=2), "```", "",
             "## Checkpoint counts", "",
             "| Checkpoint | Qualifying ABSENT | All target ABSENT | SUBSTANTIVE | Target BROKEN | Distant USEFUL | Clean-useful lost | Distant BROKEN | Alternate ABSENT | Pass |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    directories = [out / "clean_reference", *sorted(out.glob("step[0-9][0-9][0-9]"))]
    for directory in directories:
        summary = read(directory / "judge_review.json")
        payload = read(directory / "judged.json")
        if any(any(value is not None for value in row["final"].values()) for row in payload["results"]):
            raise ValueError("Worker final labels must stay empty")
        if directory.name.startswith("step"):
            hashes = read(directory / "adapter_hashes.json")
            if hashes != second.run.harness.checkpoint_hashes(directory / "adapter"):
                raise ValueError("Copied checkpoint hash mismatch")
        groups = summary["groups"]
        values = [directory.name, f"{summary['qualifying_absent']}/{summary['qualifying_count']}",
                  groups["target"]["absent"], groups["target"]["substantive"], groups["target"]["broken"],
                  groups["distant"]["useful"], summary["lost_clean_useful_distant_count"],
                  groups["distant"]["broken"], groups["alternate"]["absent"], summary["passed"]]
        lines.append("| " + " | ".join(str(value) for value in values) + " |")
    lines.extend(["", "## Selection", "", "```json", json.dumps(selected, indent=2), "```", "",
                  "## Recognition readout", "", "```json",
                  json.dumps(read(out / "readout_results.json")["measurements"], indent=2), "```", "",
                  "## Complete paired samples and every leak by checkpoint", ""])
    for directory in directories:
        lines.extend(["", (directory / "worker_report.md").read_text(encoding="utf-8")])
    lines.extend(["", "## Active rules and limitations", "",
        json.dumps(read(out / "run_config.json").get("scoring", {}), indent=2), "",
        "Training stopped for the reserved budget deadline at step 50. Steps 60 through 150 were not run.",
        "The step-60 collapse rule was not invoked. No scored checkpoint met both selection conditions.",
        "The fallback ranking selects failed step 20 because it preserves controls better than later checkpoints.",
        "Its unchanged target recognition does not measure recognition at the fully absent step-50 checkpoint.",
        "All counts are descriptive fixed-item counts. No population confidence interval is claimed.", "",
        "## Packages", "", "```json", json.dumps(read(out / "packages.json"), indent=2), "```", "",
        "## Artifact paths and hashes", "",
        "Code is scripts/erasure_pilot_a_*.py and scripts/test_erasure_pilot_a.py.",
        "A2 configuration additions are config/erasure_pilot_v1/approach_a/README_A2.md, run_pod_a2.sh, and startup_a2.sh.",
        "Temporary SSH keys and transfer archives are in the ignored .tmp/approach_a2/ directory.",
        "The append-only research entry is in EXPERIMENTS.md under TASK A2.", ""])
    for path in sorted(out.rglob("*")):
        if path.is_file() and path != out / "worker_report.md":
            lines.append("- " + path.relative_to(second.run.ROOT).as_posix())
    lines.extend(["", "| Artifact | SHA-256 |", "|---|---|"])
    critical = [directory / "generations.json" for directory in directories]
    critical.extend(directory / "adapter/adapter_model.safetensors" for directory in directories[1:])
    critical.extend(out / name for name in ["run_config.json", "packages.json", "retain_generated.json",
                    "tokenisations.json", "readout_results.json", "recognition_probe.npz", "selected_adapter.json"])
    for path in critical:
        lines.append("| " + path.relative_to(out).as_posix() + " | " + second.run.harness.sha256(path) + " |")
    path = out / "worker_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    print(build())
