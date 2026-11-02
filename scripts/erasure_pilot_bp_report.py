"""Assemble the manager's complete handoff after manual labels and accounting."""

import json
import re
from pathlib import Path

from scripts.erasure_pilot_bp_review import OUT, read


def number(value) -> str:
    return "unavailable" if value is None else f"{value:.6f}"


def account_containers() -> dict:
    """Query each known container's provider timestamps and reconcile today's billing.
    Why: killed and automatically relaunched containers also consume the preparation cap.
    If wrong: function-body timings conceal startup cost or omit failed attempts.
    """
    import asyncio
    from datetime import datetime, timezone
    from decimal import Decimal
    from modal.client import _Client
    from modal_proto import api_pb2

    known = {}
    for name in ("prepare", "prepare_attempt3", "reference", "alpha06", "alpha08"):
        config = read(OUT / name / "config.json")
        known[config["container_id"]] = {"function": name, "rate_usd_hour": config["rate_usd_hour"]}
    for filename, label in (("prior_startup_system.log", "prepare_startup1"),
                             ("prior_oom.log", "prepare_automatic_replay")):
        source = (OUT / "prepare_attempt3" / filename).read_text(encoding="utf-8")
        for identifier in re.findall(r"ta-[A-Za-z0-9]+", source):
            known.setdefault(identifier, {"function": label, "rate_usd_hour": 1.0352})

    async def fetch():
        client = await _Client.from_env()
        return await asyncio.gather(*(client.stub.TaskGetInfo(api_pb2.TaskGetInfoRequest(task_id=key))
                                      for key in known))

    rows = []
    for response in asyncio.run(fetch()):
        info = response.info
        values = known[info.id]
        elapsed = info.finished_at - info.started_at if info.finished_at and info.started_at else None
        status = info.result.DESCRIPTOR.fields_by_name["status"].enum_type.values_by_number[info.result.status].name
        rows.append({"container_id": info.id, "app_id": response.app_id, **values,
                     "gpu": info.gpu_type, "started_at": datetime.fromtimestamp(info.started_at, timezone.utc).isoformat()
                     if info.started_at else None,
                     "finished_at": datetime.fromtimestamp(info.finished_at, timezone.utc).isoformat()
                     if info.finished_at else None, "status": status, "elapsed_seconds": elapsed,
                     "estimated_compute_usd": elapsed * values["rate_usd_hour"] / 3600 if elapsed is not None else None})
    if any(row["finished_at"] is None for row in rows):
        raise ValueError("Do not close accounting while a known container is still running")
    billing = read(OUT / "billing_latest.json")
    by_app = {}
    for row in billing:
        if row["description"] == "erasure-pilot-b-proper-20261102":
            by_app[row["object_id"]] = by_app.get(row["object_id"], Decimal(0)) + Decimal(row["cost"])
    result = {"checked_at": datetime.now(timezone.utc).isoformat(), "containers": rows,
              "container_compute_estimate_usd": sum(row["estimated_compute_usd"] or 0 for row in rows),
              "prepare_container_estimate_usd": sum(row["estimated_compute_usd"] or 0 for row in rows
                                                    if row["function"].startswith("prepare")),
              "provider_by_app_usd": {key: str(value) for key, value in by_app.items()},
              "provider_report_total_usd": str(sum(by_app.values(), Decimal(0))),
              "metered_summary_usd": read(OUT / "billing_summary_latest.json")["metered_cost"],
              "caps_usd": {"prepare_all_attempts": 1.5, "reference": 4, "each_student": 11, "total": 27.5},
              "cost_method": "Container duration times requested all-in rate. Provider report includes egress and startup apps; daily report and summary can settle at different times."}
    with (OUT / "spend.json").open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
    return result


def report(notes: str = "") -> None:  # noqa: C901 - one report, reads top to bottom
    """Write counts, measurements and all full quotations in one reviewable report.
    Why: the short chat handoff cannot hold the fixed sample and every complete leak.
    If wrong: the manager sees counts without the replies that establish them.
    """
    outcome = read(OUT / "outcome.json")
    lines = ["# TASK B-PROPER worker report", "",
             "These are worker judge labels. Every final label remains empty for the manager.", "",
             "## Frozen method", "",
             "The teacher is google/gemma-3-4b-it at revision "
             "093f9f388b31de276ce2de164bdc2081324b9767 merged with A3 step 150. The two students use "
             "alpha 0.6 and 0.8, beta 0.1 and seed 20261101. They read the same verified packed "
             "stream in the same order. Full-parameter forward KL, the source mixture and filter, "
             "the optimizer settings, pass rules and token-cut rule follow the frozen 2 November decision. "
             "The learning rate is 2e-5 with 50 warmup updates and cosine decay. AdamW uses "
             "betas 0.9 and 0.999, epsilon 1e-8, weight decay 0.01 and gradient clipping 1.0. "
             "Master parameters and optimizer states are fp32, with bf16 autocast. Final evaluated "
             "and archived weights are bf16.", "",
             "## Training and containers", ""]
    for name in ("prepare", "prepare_attempt3", "reference", "alpha06", "alpha08"):
        folder = OUT / name
        if not (folder / "config.json").exists():
            continue
        config = read(folder / "config.json")
        result = read(folder / "result.json") if (folder / "result.json").exists() else {}
        cost = result.get("estimated_compute_usd")
        cost_text = "unrecorded" if cost is None else f"${cost:.6f}"
        lines.extend([f"### {name}", "", f"Container {config.get('container_id')}. "
                      f"GPU {config['gpu_actual']}. Rate ${config['rate_usd_hour']:.6f}/hour. "
                      f"Started {config['started_at']}. Ended {result.get('ended_at', 'not recorded')}. "
                      f"Status {result.get('status', 'killed before result could be written')}. "
                      f"Function-body compute estimate {cost_text}.", ""])
        if (folder / "distillation.json").exists():
            train = read(folder / "distillation.json")
            lines.extend([f"Used {train['input_tokens']:,} input tokens over {train['steps']} updates. "
                          f"Whole-training throughput {train['tokens_per_second']:.2f} input tokens/second. "
                          f"Final execution setting {train['final_setting']}.", ""])
    spend = read(OUT / "spend.json")
    lines.extend(["## Spend reconciliation", "",
                  f"Provider report total ${spend['provider_report_total_usd']}. "
                  f"Current-month metered summary ${spend['metered_summary_usd']}. "
                  f"Container-duration compute estimate ${spend['container_compute_estimate_usd']:.6f}. "
                  f"Preparation containers with recorded starts ${spend['prepare_container_estimate_usd']:.6f} "
                  "against the shared $1.50 cap. The total cap is $27.50.", "",
                  "The ledger includes all failed startup containers and the automatic replay "
                  "that refused to overwrite existing outputs. Container durations include startup "
                  "and shutdown time. Provider totals also include network egress and image work. "
                  "Today's and this month's itemized reports agree. The higher workspace summary "
                  "remains unreconciled, and both values are reported without assigning a cause.", "",
                  "| Function | Container | GPU | Start UTC | End UTC | Rate per hour | Compute estimate |",
                  "|---|---|---|---|---|---:|---:|"])
    for row in spend["containers"]:
        estimate = row["estimated_compute_usd"]
        estimate_text = "unknown, provider omitted start" if estimate is None else f"${estimate:.6f}"
        lines.append(f"| {row['function']} | {row['container_id']} | {row['gpu']} | "
                     f"{row['started_at']} | {row['finished_at']} | ${row['rate_usd_hour']:.4f} | "
                     f"{estimate_text} |")
    lines.extend(["", "## Frozen readout", "",
                  "The existing approach A recognition probe was applied without refitting. "
                  "Its length shortcut and limited fitting controls remain limitations.", "",
                  "| Student | Target correct | Distant correct | Invented correct |",
                  "|---|---:|---:|---:|"])
    for name in ("alpha06", "alpha08"):
        measurements = read(OUT / name / "readout.json")["measurements"]
        cells = [f"{measurements[group]['correct']}/{measurements[group]['total']}"
                 for group in ("target", "distant", "invented")]
        lines.append("| " + " | ".join([name, *cells]) + " |")
    lines.extend(["## Speed and memory diagnosis", "",
                  "The original updates 2 through 52 averaged 12.0151 seconds, or 2,727.24 input "
                  "tokens/second. Their timer included live filtering, embedding and tokenisation. "
                  "The source also used activation checkpointing, microbatch one, 64-position logit "
                  "chunks with per-chunk host synchronization, and scalar AdamW. No component "
                  "profile exists, so their individual time costs are unknown.", "",
                  "Preparation attempt three uses 128-row Arrow batches, required columns only, "
                  "disabled prebuffering and file byte caching, and a five-word overlap buffer. "
                  "It retains the original filter decisions and row order. The killed attempt "
                  "left no allocator trace. Its exact failed allocation remains unknown. "
                  "Peak preparation RSS was 10.7107 GiB under the new 64 GiB limit. The first "
                  "167 packed sequences match the failed attempt byte for byte. All 611 update "
                  "input hashes match between the students. Each completed 20,000,000 tokens. "
                  "Both retried update one at microbatch four after an out-of-memory error at "
                  "microbatch eight. They then used no activation checkpointing, 512-position "
                  "logit chunks and fused AdamW.", "",
                  "## Pass counts", "",
                  "| Model | Qualifying target absences | Required | Lost clean-useful distant | Broken | Rules 1 to 3 | Held-out |",
                  "|---|---:|---:|---:|---:|---|---|"])
    for name, values in [("clean", outcome["clean_counts"]), *outcome["models"].items()]:
        held = values.get("heldout")
        held_text = (f"{held['qualifying_absent']}/{held['clean_substantive']}, "
                     f"rule {held['rule_4']}" if held else "20/20 substantive" if name == "clean"
                     else "not evaluated in this arm")
        lines.append(f"| {name} | {values['target_absent']}/{values['qualifying_targets']} | "
                     f"{values['target_required']} | {len(values['distant_lost'])}/{values['qualifying_distant']} | "
                     f"{len(values['broken'])} | {values['rules_1_to_3']} | {held_text} |")
    lines.extend(["", "The clean reference reproduces all 86 original alpha03 exchanges exactly. "
                  "The present worker excludes direct01, direct02 and implied10 from qualification. "
                  "The earlier worker qualified implied10. The outcome file also reports counts "
                  "under that historical 38-target qualification, without changing the current labels.", "",
                  "## Distant recovery", "",
                  "| Student | Planned-update checkpoint | Useful | Clean-useful retained | Broken |",
                  "|---|---:|---:|---:|---:|"])
    for name, curve in outcome["distant_recovery"].items():
        for share, values in curve.items():
            lines.append(f"| {name} | {share}% | {values['useful']}/{values['total']} | "
                         f"{values['qualifying_useful']}/{values['clean_qualifying']} | {len(values['broken'])} |")
    lines.extend(["", "## Prefix continuation loss", "",
                  "Mean of per-item cross-entropies, in nats per token. Each conversation item "
                  "first combines its own turns by continuation-token count. The outcome file "
                  "also gives token-weighted sensitivity summaries.", "",
                  "| Model and checkpoint | Target | Distant |", "|---|---:|---:|"])
    prefix_order = ["clean"]
    for name in ("A3", "alpha06", "alpha08"):
        prefix_order.extend([name, *(f"{name}_relearn{step:02d}" for step in (1, 2, 5, 10, 20))])
    for name in prefix_order:
        values = outcome["prefix"][name]
        lines.append(f"| {name} | {number(values['target']['mean_item_ce_nats'])} | "
                     f"{number(values['distant']['mean_item_ce_nats'])} |")
    lines.extend(["", "## Relearning", "",
                  "| Model | Step | Substantive qualifying targets | Absent | Broken |",
                  "|---|---:|---:|---:|---:|"])
    for name, curve in outcome["relearning"].items():
        baseline = outcome["models"][name]
        broken_targets = baseline["qualifying_targets"] - baseline["target_absent"] - baseline["target_substantive"]
        lines.append(f"| {name} | 0 | {baseline['target_substantive']}/{baseline['qualifying_targets']} | "
                     f"{baseline['target_absent']} | {broken_targets} |")
        for step, values in curve.items():
            lines.append(f"| {name} | {step} | {values['substantive']}/{values['qualifying_targets']} | "
                         f"{values['absent']} | {values['broken']} |")
    lines.extend(["", "## Loss rule", ""])
    for name in ("alpha06", "alpha08"):
        values = outcome["models"][name]["loss_rule"]
        lines.extend([f"{name} has classification {values['classification']}. The three tests are "
                      f"{values['loss_tests']}. Target rise {number(values['target_rise'])}, "
                      f"distant rise {number(values['distant_rise'])}, A3 target rise "
                      f"{number(values['a3_target_rise'])}.", ""])
    if notes:
        lines.extend(["## Observations and open decisions", "", notes, ""])
    lines.extend(["## Complete exchanges", "", (OUT / "complete_quotations.md").read_text(encoding="utf-8"),
                  "", "## Paths", ""])
    root = Path(__file__).resolve().parents[1]
    paths = [*sorted(OUT.rglob("*")), *sorted((root / "scripts").glob("erasure_pilot_bp_*.py")),
             root / "scripts/test_erasure_pilot_bp.py",
             *sorted((root / "config/erasure_pilot_v1/approach_b_proper").glob("*")),
             *sorted((root / ".tmp/approach_b_proper").glob("*.*"))]
    for path in paths:
        if path.is_file():
            lines.append("- " + path.relative_to(root).as_posix())
    lines.append("- derisk/erasure_pilot_v1/approach_b_proper/worker_report.md")
    lines.append("- EXPERIMENTS.md, one appended TASK B-PROPER entry")
    with (OUT / "worker_report.md").open("x", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    report()
