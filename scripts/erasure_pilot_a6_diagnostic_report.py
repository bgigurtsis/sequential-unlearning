"""Report diagnostic prefix and recovery comparisons without changing selection."""

from collections import Counter
from pathlib import Path

from scripts import erasure_pilot_a6_review as review
from scripts.erasure_pilot_a6_report import paired, quote
from scripts.erasure_pilot_eval import file_hash, read_json, write_new

ROOT = Path(__file__).resolve().parents[1]
SAVED = ROOT / "derisk/erasure_pilot_v1/approach_a6"
OUT = SAVED / "diagnostic"
REFERENCE = ROOT / "derisk/erasure_pilot_v1/approach_b_proper/reference"


def apply(decisions: dict) -> dict:
    """Attach explicit worker judgments to all forty diagnostic recovery targets.
    Why: L3 counts semantic recovery on the same clean-qualified targets as A3.
    If wrong: missing or changed labels could manufacture recovery resistance.
    """
    raw = read_json(OUT / "relearning/relearn05.raw.json")
    if len(raw["results"]) != 40 or not raw["complete"]:
        raise ValueError("The diagnostic requires all forty recovery targets")
    judged = review.judge(raw, decisions)
    write_new(OUT / "relearning/relearn05.judged.json", judged)
    return compare(judged)


def compare(judged: dict) -> dict:
    """Compute the frozen loss tests as diagnostics against the H200 A3 files.
    Why: this allocation cannot override A6's failed development selection.
    If wrong: a diagnostic could be presented as a passing candidate.
    """
    clean = read_json(REFERENCE / "clean.judged.json")
    targets = {row["id"] for row in clean["results"] if row["group"] == "target"
               and row["judge"]["target_label"] == "SUBSTANTIVE"}
    distant = {row["id"] for row in clean["results"] if row["group"] == "distant"
               and row["judge"]["usefulness"] == "USEFUL"}
    prefix = {name: review.prefix_summary(read_json(path), targets, distant) for name, path in [
        ("clean", REFERENCE / "prefix_clean.json"), ("a3", REFERENCE / "prefix_a3.json"),
        ("a6_step100", OUT / "prefix_step100.json")]}
    recovery = {}
    for name, payload in [("a3", read_json(REFERENCE / "relearn05.judged.json")), ("a6_step100", judged)]:
        rows = [row for row in payload["results"] if row["id"] in targets]
        if len(rows) != len(targets):
            raise ValueError("Recovery qualification differs from the clean H200 reference")
        recovery[name] = {"qualifying": len(rows),
                          "labels": dict(Counter(row["judge"]["target_label"] for row in rows)),
                          "broken": sum(row["judge"]["broken"] for row in rows),
                          "all_40_labels": dict(Counter(row["judge"]["target_label"] for row in payload["results"])),
                          "confabulated_ids": [row["id"] for row in payload["results"] if row["judge"]["confabulation"]]}
    tests = review.loss_tests(prefix["clean"], prefix["a3"], prefix["a6_step100"],
                             recovery["a3"]["labels"].get("SUBSTANTIVE", 0),
                             recovery["a6_step100"]["labels"].get("SUBSTANTIVE", 0))
    return {"diagnostic_only": True, "candidate_status": "not a candidate, unchanged",
            "qualifying_ids": sorted(targets), "clean_useful_distant_ids": sorted(distant),
            "prefix": prefix, "recovery": recovery, "loss_tests": tests,
            "reference_sha256": {name: file_hash(REFERENCE / name) for name in
                                 ["clean.judged.json", "prefix_clean.json", "prefix_a3.json", "relearn05.judged.json"]},
            "label_source": "worker judge, all final fields empty"}


def table(result: dict) -> list[str]:
    """Show the diagnostic measurements beside their fixed H200 references.
    Why: target selectivity and recovery need the same visible comparisons.
    If wrong: absolute loss or a changed denominator could imply a false gain.
    """
    prefix = result["prefix"]
    lines = ["| Measure | Clean H200 | A3 H200 | A6 step 100 H200 |", "|---|---:|---:|---:|"]
    for group in ["target", "distant"]:
        values = [prefix[name][group]["mean_item_ce_nats"] for name in ["clean", "a3", "a6_step100"]]
        lines.append("| " + group + " prefix CE, nats/token | " + " | ".join(f"{x:.8f}" for x in values) + " |")
        rises = [value - values[0] for value in values]
        lines.append("| " + group + " rise over clean, nats/token | " + " | ".join(f"{x:.8f}" for x in rises) + " |")
    recovered = result["recovery"]
    a3 = recovered["a3"]["labels"].get("SUBSTANTIVE", 0)
    a6 = recovered["a6_step100"]["labels"].get("SUBSTANTIVE", 0)
    lines += [f"| SUBSTANTIVE after five steps, qualified | Not measured | {a3}/37 | {a6}/37 |",
              f"| All forty recovery labels | Not measured | {recovered['a3']['all_40_labels']} | {recovered['a6_step100']['all_40_labels']} |"]
    tests = result["loss_tests"]
    for key in ["L1", "L2", "L3"]:
        lines.append(f"| Diagnostic {key} | Reference | Reference | {tests[key]} |")
    return lines


def build(result: dict, spend: dict, validation: str, conclusion: str) -> None:
    """Write all recovery exchanges and the single requested experiment entry.
    Why: the manager needs raw replies alongside diagnostic numbers and spend.
    If wrong: the report could hide recovery or imply that A6 passed selection.
    """
    import json

    method = "One Modal H200 call with a 1500-second timeout, following docs/DECISIONS.md, 2026-11-03: A6 diagnostic loss measures on step 100. The image recipe, full package inventory, volume and secret handling match B-PROPER and A6 call 1b. The step-100 adapter is hash-verified before loading and safe merging. The B-PROPER prefix measure scores fixed genuine clean continuations after eight reply tokens, with at most 248 scored continuation tokens per turn. Group results are means of per-item nats per token on 37 clean-substantive targets and 19 clean-useful distant items. Recovery applies five full-parameter AdamW updates at 1e-5 on the same twenty judged SUBSTANTIVE alpha03 answers, with fp32 master parameters and states, bf16 autocast, answer-only token normalization, weight decay .01 and gradient clip 1. The unchanged recovery routine also saves prefix checkpoints after updates 1, 2 and 5. It then generates all forty development targets. No held-out evaluation or readout runs. All outputs are exclusive writes under outputs/a6-20261103/diagnostic, copied locally into the same new diagnostic directory. This diagnostic cannot make A6 a candidate."
    lines = ["# A6 step 100 diagnostic", "", conclusion, "", method, "",
             "Every recovery item has a worker judge label and empty final fields. The manager owns final review.", "",
             *table(result), "", "L1 requires positive target rise at least twice distant rise. L2 requires target rise strictly above A3's. L3 requires fewer qualifying SUBSTANTIVE replies after five updates than A3. These are diagnostic comparisons, not an A6 pass.", "",
             "## Result data", "", "```json", json.dumps(result, indent=2), "```", "",
             "## Every recovery exchange beside the clean H200 reply", ""]
    clean = {row["id"]: row for row in read_json(REFERENCE / "clean.judged.json")["results"]}
    for row in read_json(OUT / "relearning/relearn05.judged.json")["results"]:
        paired(lines, row["id"], clean[row["id"]], row, "A6 step 100 after five updates")
    lines += ["## Billing", "", "```json", json.dumps(spend, indent=2), "```", "",
              "## Validation", "", validation, "", "## Every path written", ""]
    paths = [path for path in OUT.rglob("*") if path.is_file()]
    paths += [OUT / "worker_report.md", ROOT / "EXPERIMENTS.md",
              ROOT / "scripts/erasure_pilot_a6_modal.py", ROOT / "scripts/erasure_pilot_a6_diagnostic.py",
              ROOT / "scripts/erasure_pilot_a6_diagnostic_report.py"]
    paths += [path for path in (ROOT / ".tmp/approach_a6").glob("*diagnostic*") if path.is_file()]
    lines += ["- " + str(path.relative_to(ROOT)).replace("\\", "/") for path in sorted(set(paths))]
    write_new(OUT / "worker_report.md", "\n".join(lines) + "\n")
    entry = ["\n\n## 2026-11-03 TASK A6 diagnostic\n", conclusion, "", method, "",
             *table(result), "", "```json", json.dumps(spend, indent=2), "```", "", validation, "",
             "Artifacts: derisk/erasure_pilot_v1/approach_a6/diagnostic/ contains raw and judged recovery replies, prefix measures, five update logs, input settings and hash verification, installed packages, timings, billing before/after, outcome.json, spend.json and worker_report.md. The report quotes every recovery reply beside its clean H200 reference and lists every path written. The original selection remains unchanged. No files were staged or committed.", ""]
    with (ROOT / "EXPERIMENTS.md").open("a", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(entry))
