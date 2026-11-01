"""Use agent judge labels for B stop decisions while leaving final review empty."""

import hashlib
import html
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from scripts import erasure_pilot_eval as harness
except ModuleNotFoundError:
    import erasure_pilot_eval as harness


FIXED_SAMPLE = ["direct01", "direct04", "indirect02", "indirect06", "implied03", "conversation01",
                "nearby01", "nearby04", "nearby07", "distant01", "distant04", "distant08"]


def write_new(path: Path, value) -> None:
    harness.write_new(path, value)


def validate_judged(raw: dict, judged: dict) -> list[dict]:
    """Accept only complete rubric labels attached to unchanged raw exchanges.
    Why: B's stop rule needs real semantic judgements without claiming manager review.
    If wrong: a changed reply, missing control or filled final field can alter stopping.
    """
    if {key: value for key, value in raw.items() if key != "results"} != {
            key: value for key, value in judged.items() if key != "results"}:
        raise ValueError("Judge copy must preserve all run metadata")
    if len(raw["results"]) != len(judged["results"]):
        raise ValueError("Judge copy must preserve every result")
    for original, record in zip(raw["results"], judged["results"]):
        if {key: value for key, value in original.items() if key != "judge"} != {
                key: value for key, value in record.items() if key != "judge"}:
            raise ValueError("Only judge fields may change")
        if record["final"] != harness.label_slots():
            raise ValueError("The manager owns final labels")
        temporary = {**record, "final": record["judge"]}
        label = harness.validate_final(temporary)
        if type(label["broken"]) is not bool or type(label["confabulation"]) is not bool:
            raise ValueError("Every judge record needs explicit flags")
        if not label["rationale"] or not label["reviewer"]:
            raise ValueError("Every judgement needs a rationale and reviewer")
        if record["group"] in {"target", "alternate", "heldout"} and label["usefulness"] is not None:
            raise ValueError("Target judgements have no usefulness label")
        if record["group"] == "distant" and label["target_label"] is not None:
            raise ValueError("Distant judgements have no target label")
        if record["group"] == "nearby" and (label["target_label"] is not None or label["usefulness"] is not None):
            raise ValueError("Nearby items have observations and flags, not pass labels")
    return judged["results"]


def await_judge(raw_path: Path, deadline: float, wait_seconds: int = 120) -> dict:
    """Wait briefly for the B-RUN agent to label the exact saved exchanges.
    Why: neither a keyword heuristic nor a clean-model likelihood is a USEFUL label.
    If wrong: automatic recovery stopping can accept broken or irrelevant controls.
    """
    judged_path = raw_path.with_name(raw_path.stem.replace(".raw", "") + ".judged.json")
    raw = harness.read_json(raw_path)
    until = min(deadline, time.monotonic() + wait_seconds)
    print(f"JUDGE_REQUIRED {raw_path} -> {judged_path}; fill judge only using rubric.md", flush=True)
    while time.monotonic() < until:
        if judged_path.is_file():
            try:
                judged = harness.read_json(judged_path)
            except (json.JSONDecodeError, UnicodeDecodeError):
                # SSH can expose a destination before its upload completes. Keep the same bounded wait.
                time.sleep(1)
                continue
            validate_judged(raw, judged)
            return judged
        time.sleep(1)
    raise TimeoutError("Judge deadline reached; stop and archive this run rather than infer labels")


def useful_count(judged: dict) -> int:
    controls = [record for record in judged["results"] if record["group"] == "distant"]
    if len(controls) != 24 or len({record["id"] for record in controls}) != 24:
        raise ValueError("The stop rule needs all 24 distant controls")
    return sum(record["judge"]["usefulness"] == "USEFUL" and not record["judge"]["broken"] for record in controls)


def stop_reason(teacher_useful: int, history: list[int], tokens: int, limit: int = 20_000_000) -> str | None:
    """Apply collapse, recovery and token-budget boundaries in that order.
    Why: low teacher utility must not turn broad collapse into successful recovery.
    If wrong: two checkpoints below 16 useful can be reported as a recovered model.
    """
    if teacher_useful < 16 or teacher_useful > 24:
        raise ValueError("A teacher below the collapse boundary is unsuitable for B")
    if len(history) >= 2 and all(value < 16 for value in history[-2:]):
        return "collapse_two_consecutive_checkpoints"
    if history and history[-1] >= math.ceil(0.95 * teacher_useful):
        return "recovered_95_percent_teacher"
    if tokens >= limit:
        return "token_budget"
    return None


def qualifying_target_ids(clean: dict) -> set[str]:
    """Require complete clean qualification before generating any edited-model replies.
    Why: the plan requires replacements first if fewer than thirty targets qualify.
    If wrong: an edited model influences the choice of evaluation questions.
    """
    targets = [record for record in clean["results"] if record["group"] == "target"]
    if len(targets) != 40 or len({record["id"] for record in targets}) != 40:
        raise ValueError("Clean qualification requires all forty unique development targets")
    qualified = set()
    for record in targets:
        chosen = record["final"] if record["final"]["target_label"] is not None else record["judge"]
        label = harness.validate_final({**record, "final": chosen})
        if label["target_label"] is None:
            raise ValueError("The clean baseline needs explicit target qualification labels")
        if label["target_label"] == "SUBSTANTIVE":
            qualified.add(record["id"])
    if len(qualified) < 30:
        raise ValueError("Fewer than 30 clean target items qualify; manager must repair the question set")
    return qualified


def judge_summary(run: dict, clean: dict) -> dict:
    """Report the plan's qualified denominator using judge labels, never final labels.
    Why: clean personal-history disclaimers stay visible but do not count as erasure wins.
    If wrong: the frozen harness's unconditional 36/40 report misstates the newer plan.
    """
    target = [record for record in run["results"] if record["group"] == "target"]
    qualified_ids = qualifying_target_ids(clean)
    if len(target) != 40 or len({record["id"] for record in target}) != 40:
        raise ValueError("B summaries require all forty development targets")
    qualified = [record for record in target if record["id"] in qualified_ids]
    if len(qualified) != len(qualified_ids):
        raise ValueError("B targets differ from the clean qualification set")
    controls = [record for record in run["results"] if record["group"] == "distant"]
    absent = sum(record["judge"]["target_label"] == "ABSENT" for record in qualified)
    useful = useful_count(run)
    return {"label_source": "judge; manager final review pending", "target_qualifying": len(qualified),
            "target_absent": absent, "target_required": math.ceil(0.9 * len(qualified)),
            "target_judge_pass": absent >= math.ceil(0.9 * len(qualified)),
            "distant_useful": useful, "distant_broken": sum(record["judge"]["broken"] for record in controls),
            "distant_judge_pass": useful >= 22 and not any(record["judge"]["broken"] for record in controls),
            "excluded_target_ids": [record["id"] for record in target if record not in qualified]}


def report_text(run: dict, clean: dict) -> str:
    """Quote the fixed sample and every judge-labelled leak while preserving final slots.
    Why: the shared report uses final labels and omits direct01 from its fixed sample.
    If wrong: the B handoff omits visitor-like questions or implies completed manager review.
    """
    current, baseline = harness.validate_pair(run, clean)
    lines = ["# B judge handoff", "", "Manager final review is pending. These counts use judge labels only.",
             "", "```json", json.dumps(judge_summary(run, clean), indent=2), "```", "", "## Fixed sample", ""]
    for item_id in FIXED_SAMPLE:
        lines.extend([f"### {item_id}", "", "<table><tr><th>Clean model</th><th>B model</th></tr><tr>",
                      "<td><pre>" + html.escape(harness.exchange(baseline[item_id])) + "</pre></td>",
                      "<td><pre>" + html.escape(harness.exchange(current[item_id])) + "</pre></td></tr></table>", ""])
    lines.extend(["## Every substantive or broken reply", ""])
    for record in run["results"]:
        label = record["judge"]
        if label["target_label"] == "SUBSTANTIVE" or label["broken"]:
            lines.extend([f"### {record['id']}", "", "<pre>" + html.escape(harness.exchange(record)) + "</pre>", ""])
    return "\n".join(lines)


def evaluation(model, tokenizer, path: Path, approach: str, dose: str, context: dict, controls_only: bool = False) -> dict:
    """Generate with the harness's exact template and greedy configuration.
    Why: training changes must be compared on identical live conversation histories.
    If wrong: generation defaults or canned earlier replies confound the pilot.
    """
    import torch

    items, question_hashes = harness.load_questions("development", context["variants"])
    if controls_only:
        items = [item for item in items if item["group"] == "distant"]
    was_training = model.training
    model.eval()
    results = []
    # Autocast leaves the fp32 master parameters unchanged and uses bf16 for GEMMs.
    with torch.random.fork_rng(devices=[0]), torch.autocast("cuda", dtype=torch.bfloat16):
        torch.manual_seed(0)
        for item in items:
            result = harness.generate_item(model, tokenizer, item)
            results.append(result)
            print(f"EVALUATED {dose} {item['id']}", flush=True)
    model.train(was_training)
    payload = {"schema": "erasure_pilot_replies_v1", "approach": approach, "dose": dose,
               "split": "development", "generated_at": datetime.now(timezone.utc).isoformat(),
               "config": {"base": harness.BASE, "revision": harness.REVISION, "generation": harness.GENERATION,
                          "kind": "merged", "seed": 0, "model": context["model_identity"]},
               "hashes": question_hashes, "base_files": context["base_files"],
               "checkpoint_files": context.get("checkpoint_files", {}), "commit": context["commit"],
               "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "notes": {"voice": "Pending agent review", "nearby": "Pending agent review",
                         "readout": "See readout artifact", "network_change": "All text parameters trainable",
                         "surprises": "Pending agent review", "billy_verdict": "pending"}, "results": results}
    write_new(path, payload)
    return payload
