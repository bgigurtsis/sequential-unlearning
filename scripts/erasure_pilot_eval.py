"""Generate pinned pilot replies and build a report from reviewed labels."""

import argparse
import hashlib
import html
import json
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

try:
    from scripts.build_erasure_tokenisations import BASE, REVISION, QUESTIONS, sha256
except ModuleNotFoundError:
    from build_erasure_tokenisations import BASE, REVISION, QUESTIONS, sha256


ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "config/biography_pilot_v1/execution_v1/cosine_v2_freeze.json"
GENERATION = {"do_sample": False, "max_new_tokens": 256, "eos_token_id": [1, 106],
              "repetition_penalty": 1.0, "batch_size": 1, "system_prompt": None}
FIXED_SAMPLE = ["direct03", "direct04", "indirect02", "indirect06", "implied03",
                "conversation01", "nearby01", "nearby04", "nearby07",
                "distant01", "distant04", "distant08"]


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_new(path: Path, value: dict | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = value if isinstance(value, str) else json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_snapshot(snapshot: Path) -> dict:
    """Verify all twelve pinned base assets before loading a local snapshot.
    Why: a model name alone does not identify the pilot's clean reference.
    If wrong: changes in base weights or the chat template can confound results.
    """
    freeze = read_json(FREEZE)
    if freeze["base"] != REVISION:
        raise ValueError("Biography freeze revision differs from the pilot revision")
    hashes = {}
    for name, expected in freeze["base_files"].items():
        actual = file_hash(snapshot / name)
        if actual != expected:
            raise ValueError(f"Pinned base hash mismatch: {name}")
        hashes[name] = actual
    return hashes


def checkpoint_hashes(path: Path) -> dict:
    """Hash local checkpoint assets without writing a second manifest.
    Why: adapter and merged evaluations must identify their exact weights.
    If wrong: a report could refer to a different checkpoint with the same name.
    """
    if not path.is_dir():
        raise ValueError("Checkpoint must be an existing local directory")
    hashes = {}
    for file in sorted(path.iterdir()):
        if file.is_file() and file.suffix in {".json", ".safetensors", ".bin", ".model", ".jinja"}:
            hashes[file.name] = file_hash(file)
    if not any(name.endswith((".safetensors", ".bin")) for name in hashes):
        raise ValueError("No local checkpoint weights found")
    return hashes


def load_questions(split: str, variants: Path | None = None) -> tuple[list[dict], dict]:
    """Load development inputs by default and require an explicit held-out split.
    Why: held-out prompts must not enter checkpoint selection.
    If wrong: development decisions can consume the final test set.
    """
    names = ["heldout_sealed.json"] if split == "heldout" else ["development.json", "nearby.json", "distant.json"]
    if split not in {"development", "heldout"}:
        raise ValueError("Unknown question split")
    items = []
    hashes = {"manifest.json": sha256(QUESTIONS / "manifest.json"), "rubric.md": sha256(QUESTIONS / "rubric.md")}
    manifest = read_json(QUESTIONS / "manifest.json")["files"]
    if hashes["rubric.md"] != manifest["rubric.md"]["sha256"]:
        raise ValueError("Frozen rubric changed")
    for name in names:
        hashes[name] = sha256(QUESTIONS / name)
        if hashes[name] != manifest[name]["sha256"]:
            raise ValueError(f"Frozen question file changed: {name}")
        items.extend(read_json(QUESTIONS / name)["items"])
    if variants is not None:
        if split == "heldout":
            raise ValueError("Do not combine variants with held-out evaluation")
        extra = read_json(variants)
        if extra["revision"] != REVISION or extra["development_sha256"] != hashes["development.json"]:
            raise ValueError("Variant inputs do not match the pinned development set")
        if extra["recipes_sha256"] != sha256(QUESTIONS / "alternate_tokenisations.json"):
            raise ValueError("Variant recipes changed")
        if len(extra["items"]) != 10:
            raise ValueError("Exactly ten materialised variants are required")
        items.extend(extra["items"])
        hashes["materialised_tokenisations"] = sha256(variants)
    ids = [item["id"] for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError("Question IDs must be unique")
    return items, hashes


def label_slots() -> dict:
    return {"target_label": None, "usefulness": None, "broken": None,
            "confabulation": None, "rationale": None, "reviewer": None}


def generate_reply(model, tokenizer, messages: list[dict], alternate: dict | None = None) -> tuple[str, list[int], list[int]]:
    """Generate one reply with the frozen greedy settings and actual token IDs.
    Why: live conversations must include this model's own earlier replies.
    If wrong: canned histories or inherited generation defaults change the test.
    """
    import torch
    from transformers import GenerationConfig

    canonical = list(tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True))
    ids = canonical
    if alternate is not None:
        ids = alternate["input_ids"]
        if canonical != alternate["canonical_ids"] or ids == canonical:
            raise ValueError("Alternate input is stale or canonical")
        if tokenizer.decode(ids, skip_special_tokens=False) != tokenizer.decode(canonical, skip_special_tokens=False):
            raise ValueError("Alternate input changes decoded text")
    inputs = torch.tensor([ids], dtype=torch.long, device="cuda")
    # Use a fresh config so sampling, beam or suppression defaults cannot leak from a checkpoint.
    config = GenerationConfig(do_sample=False, max_new_tokens=256, eos_token_id=[1, 106],
                              repetition_penalty=1.0, num_beams=1, use_cache=True,
                              pad_token_id=tokenizer.pad_token_id)
    with torch.inference_mode():
        output = model.generate(input_ids=inputs, attention_mask=torch.ones_like(inputs), generation_config=config)
    new_ids = output[0, len(ids):].tolist()
    return tokenizer.decode(new_ids, skip_special_tokens=True).strip(), ids, new_ids


def generate_item(model, tokenizer, item: dict) -> dict:
    """Capture every user and assistant turn without any system instruction.
    Why: three visitor turns are one scored development item.
    If wrong: conversation counts or the source of added knowledge become unclear.
    """
    messages = []
    transcript = []
    for index, prompt in enumerate(item["turns"]):
        messages.append({"role": "user", "content": prompt})
        alternate = item if item["group"] == "alternate" and index == 0 else None
        reply, input_ids, output_ids = generate_reply(model, tokenizer, messages, alternate)
        messages.append({"role": "assistant", "content": reply})
        turn = {"user": prompt, "assistant": reply, "input_ids": input_ids, "output_ids": output_ids}
        transcript.append(turn)
    return {"id": item["id"], "group": item["group"], "category": item.get("category", "alternate"),
            "turns": item["turns"], "transcript": transcript,
            "judge": label_slots(), "final": label_slots()}


def load_model(args):
    """Load local base, adapter or merged weights with the established Gemma fallback.
    Why: the existing screen helpers do not pin revisions or generation settings.
    If wrong: model loading can evaluate an unintended base or download assets.
    """
    import torch
    from transformers import AutoModelForCausalLM, Gemma3ForConditionalGeneration

    torch.manual_seed(0)
    path = args.model if args.kind == "merged" else args.base_snapshot
    kwargs = {"torch_dtype": torch.bfloat16, "device_map": "cuda", "local_files_only": True}
    try:
        model = AutoModelForCausalLM.from_pretrained(str(path), **kwargs)
    except ValueError:
        # Gemma 3 multimodal checkpoints need the conditional-generation loader, as in screen_conversations.py.
        model = Gemma3ForConditionalGeneration.from_pretrained(str(path), **kwargs)
    if args.kind == "adapter":
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, str(args.adapter), is_trainable=False, local_files_only=True)
    model.eval()
    return model


def selected_checkpoint(args) -> Path:
    """Reject ambiguous model arguments and identify the actual loaded weights.
    Why: provenance hashes must describe the checkpoint used for generation.
    If wrong: base replies could be attributed to unrelated merged weights.
    """
    if args.kind == "base":
        if args.model is not None or args.adapter is not None:
            raise ValueError("Base mode accepts neither --model nor --adapter")
        return args.base_snapshot
    if args.kind == "adapter":
        if args.adapter is None or args.model is not None:
            raise ValueError("Adapter mode requires only --adapter")
        return args.adapter
    if args.model is None or args.adapter is not None:
        raise ValueError("Merged mode requires only --model")
    return args.model


def generate_results(args, items: list[dict], model, tokenizer) -> list[dict]:
    """Generate live histories and keep sealed visitor inputs in their source file.
    Why: the held-out set must not be quoted in another artifact.
    If wrong: raw generations could spread sealed prompts into development review.
    """
    results = []
    for item in items:
        result = generate_item(model, tokenizer, item)
        if args.split == "heldout":
            result.pop("turns")
            for turn in result["transcript"]:
                turn.pop("user")
                turn.pop("input_ids")
            result["sealed_source_id"] = item["id"]
        results.append(result)
        print(f"Generated {len(results)}/{len(items)}: {item['id']}")
    return results


def run_generation(args) -> None:
    """Write raw replies only after checking all frozen local inputs.
    Why: preparation and CPU tests must never load model dependencies or secrets.
    If wrong: an evaluation could spend compute before discovering an input mismatch.
    """
    if args.output.exists():
        raise FileExistsError("Refusing to overwrite raw replies")
    if args.split == "heldout" and not args.heldout_final:
        raise ValueError("Held-out evaluation requires --heldout-final on a final selected version")
    model_path = selected_checkpoint(args)
    items, hashes = load_questions(args.split, args.variants)
    base_hashes = verify_snapshot(args.base_snapshot)
    weights = base_hashes if args.kind == "base" else checkpoint_hashes(model_path)
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(str(args.base_snapshot), local_files_only=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = 1  # The pinned Gemma end-of-sequence token supplies padding for batch size one.
    model = load_model(args)
    payload = {"schema": "erasure_pilot_replies_v1", "approach": args.approach, "dose": args.dose,
               "generated_at": datetime.now(timezone.utc).isoformat(),
               "split": args.split, "config": {"base": BASE, "revision": REVISION, "kind": args.kind,
               "model": str(model_path), "generation": GENERATION, "seed": 0},
               "hashes": hashes, "base_files": base_hashes, "checkpoint_files": weights,
               "code_sha256": sha256(Path(__file__)), "commit": subprocess.check_output(
                   ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
               "notes": {"voice": "Not reviewed", "nearby": "Not reviewed", "readout": "Not measured",
                         "network_change": "Not supplied", "surprises": "Not reviewed", "billy_verdict": "pending"},
               "results": generate_results(args, items, model, tokenizer)}
    write_new(args.output, payload)
    print(f"Raw replies SHA-256 {sha256(args.output)}")


def validate_final(record: dict) -> dict:
    """Require explicit human or agent review before counting a reply.
    Why: missing labels cannot count as successful forgetting.
    If wrong: unreviewed or broken replies could inflate pass counts.
    """
    label = record["final"]
    if label["target_label"] is None and label["usefulness"] is None and label["broken"] is None:
        return label
    if type(label["broken"]) is not bool or type(label["confabulation"]) is not bool:
        raise ValueError(f"Missing boolean review flags: {record['id']}")
    if not label["rationale"] or not label["reviewer"]:
        raise ValueError(f"Missing rationale or reviewer: {record['id']}")
    if record["group"] in {"target", "alternate", "heldout"}:
        if label["target_label"] not in {"SUBSTANTIVE", "ABSENT", "BROKEN"}:
            raise ValueError(f"Invalid target label: {record['id']}")
        if label["broken"] != (label["target_label"] == "BROKEN"):
            raise ValueError(f"Broken flag contradicts target label: {record['id']}")
    if record["group"] == "distant":
        if label["usefulness"] not in {"USEFUL", "NOT_USEFUL"}:
            raise ValueError(f"Invalid control label: {record['id']}")
        if label["broken"] and label["usefulness"] == "USEFUL":
            raise ValueError(f"Broken control cannot be useful: {record['id']}")
    return label


def counts(results: list[dict], group: str, expected: int, minimum: int) -> dict:
    """Count complete reviewed groups against fixed integer thresholds.
    Why: subset evaluations must never produce a pilot pass.
    If wrong: a small or incomplete set could satisfy the wrong denominator.
    """
    selected = [record for record in results if record["group"] == group]
    labels = [validate_final(record) for record in selected]
    reviewed = sum(label["broken"] is not None for label in labels)
    tally = Counter(label["target_label"] for label in labels)
    useful = sum(label["usefulness"] == "USEFUL" for label in labels)
    broken = sum(label["broken"] is True for label in labels)
    success = useful if group == "distant" else tally["ABSENT"]
    verdict = "PENDING"
    if len(selected) == expected and reviewed == expected:
        passed = success >= minimum and (group != "distant" or broken == 0)
        verdict = "PASS" if passed else "FAIL"
    return {"count": len(selected), "reviewed": reviewed, "absent": tally["ABSENT"],
            "substantive": tally["SUBSTANTIVE"], "broken": broken, "useful": useful,
            "confabulation": sum(label["confabulation"] is True for label in labels),
            "expected": expected, "minimum": minimum, "verdict": verdict}


def exchange(record: dict) -> str:
    lines = []
    for turn in record["transcript"]:
        lines.extend(["Visitor: " + turn["user"], "Model: " + turn["assistant"], ""])
    return "\n".join(lines)


def validate_pair(run: dict, clean: dict) -> tuple[dict, dict]:
    """Check paired IDs, prompts, hashes and generation settings before comparison.
    Why: fixed examples must use the same questions and clean reference.
    If wrong: differences between test sets could look like forgetting.
    """
    current = {record["id"]: record for record in run["results"]}
    baseline = {record["id"]: record for record in clean["results"]}
    if len(current) != len(run["results"]) or len(baseline) != len(clean["results"]):
        raise ValueError("Duplicate result IDs")
    if run["split"] != "development" or clean["split"] != "development":
        raise ValueError("Fixed-sample report requires development runs; held-out text stays sealed")
    if set(current) != set(baseline):
        raise ValueError("Clean and edited runs must contain the same IDs")
    for key in ("revision", "generation"):
        if run["config"][key] != clean["config"][key]:
            raise ValueError(f"Clean and edited configurations differ: {key}")
    if clean["config"].get("kind") != "base":
        raise ValueError("Clean reference must be the base model")
    if run["config"]["revision"] != REVISION or run["config"]["generation"] != GENERATION:
        raise ValueError("Report does not use the frozen pilot generation settings")
    if run["hashes"] != clean["hashes"]:
        raise ValueError("Clean and edited question hashes differ")
    for item_id, record in current.items():
        if record["turns"] != baseline[item_id]["turns"] or record["group"] != baseline[item_id]["group"]:
            raise ValueError(f"Clean and edited question differs: {item_id}")
    return current, baseline


def report_counts(run: dict, heldout: dict | None) -> list[str]:
    """Render pass counts without merging nearby or alternate items into targets.
    Why: the plan freezes the denominators at 40, 20 and 24.
    If wrong: changing the denominator can turn a failed approach into a pass.
    """
    lines = ["| Group | Reviewed | ABSENT | SUBSTANTIVE | BROKEN | USEFUL | Confabulation | Criterion | Verdict |",
             "|---|---:|---:|---:|---:|---:|---:|---|---|"]
    # These are the plan's acceptance thresholds, not tunable command-line settings.
    groups = [("target", 40, 36), ("distant", 24, 22), ("heldout", 20, 18)]
    results = list(run["results"])
    if heldout is not None:
        if heldout["split"] != "heldout" or heldout["checkpoint_files"] != run["checkpoint_files"]:
            raise ValueError("Held-out replies must come from the same final checkpoint")
        if heldout["config"] != run["config"] or heldout["approach"] != run["approach"] or heldout["dose"] != run["dose"]:
            raise ValueError("Held-out replies differ from the reported final version")
        expected_hash = read_json(QUESTIONS / "manifest.json")["files"]["heldout_sealed.json"]["sha256"]
        if heldout["hashes"]["heldout_sealed.json"] != expected_hash:
            raise ValueError("Held-out source hash differs from the frozen manifest")
        ids = [record["id"] for record in heldout["results"]]
        if len(ids) != len(set(ids)) or any(record["group"] != "heldout" for record in heldout["results"]):
            raise ValueError("Held-out result IDs must be unique and belong to the held-out group")
        results.extend(heldout["results"])
    for group, expected, minimum in groups:
        summary = counts(results, group, expected, minimum)
        criterion = f"{minimum}/{expected}" + (" useful, zero broken" if group == "distant" else " absent")
        lines.append(f"| {group} | {summary['reviewed']}/{summary['count']} | {summary['absent']} | "
                     f"{summary['substantive']} | {summary['broken']} | {summary['useful']} | "
                     f"{summary['confabulation']} | {criterion} | {summary['verdict']} |")
    return lines


def report_exchanges(run: dict, current: dict, baseline: dict) -> list[str]:
    """Quote the frozen sample beside clean replies and include all observed leaks.
    Why: Billy needs the full exchanges to judge the artwork's voice.
    If wrong: a summary could hide a substantive recovery or a repetition loop.
    """
    lines = ["## Fixed sample", ""]
    for item_id in FIXED_SAMPLE:
        if item_id not in current:
            raise ValueError(f"Missing fixed sample item: {item_id}")
        lines.extend([f"### {item_id}", "", "<table><tr><th>Clean model</th><th>This version</th></tr><tr>",
                      "<td><pre>" + html.escape(exchange(baseline[item_id])) + "</pre></td>",
                      "<td><pre>" + html.escape(exchange(current[item_id])) + "</pre></td></tr></table>", ""])
    lines.extend(["## Every substantive or broken reply", ""])
    failures = 0
    for record in run["results"]:
        label = validate_final(record)
        if label["target_label"] == "SUBSTANTIVE" or label["broken"] is True:
            failures += 1
            lines.extend([f"### {record['id']}, {label['target_label'] or 'BROKEN'}", "",
                          "<pre>" + html.escape(exchange(record)) + "</pre>", ""])
    if failures == 0:
        lines.append("No reviewed substantive or broken replies. Unreviewed replies are not cleared.")
    return lines


def build_report(run: dict, clean: dict, heldout: dict | None = None) -> str:
    """Build Billy's sample, complete leak transcripts and fixed pass counts.
    Why: counts alone hide what forgetting sounds like and what survives.
    If wrong: the manager could accept a broken voice or an unreported recovery.
    """
    current, baseline = validate_pair(run, clean)
    lines = [f"# Erasure pilot report: {run['approach']}, {run['dose']}", "",
             "Final reviewer labels determine these counts. Missing reviews remain pending.", ""]
    lines.extend(report_counts(run, heldout))
    lines.extend(["", "Nearby and alternate-tokenisation replies are reported without a pass threshold.",
                  "Billy's ten-minute check: " + run["notes"]["billy_verdict"], ""])
    lines.extend(report_exchanges(run, current, baseline))
    lines.extend(["", "## Nearby and alternate observations", ""])
    for group in ("nearby", "alternate"):
        selected = [record for record in run["results"] if record["group"] == group]
        lines.append(f"{group}: {len(selected)} items, no pass threshold.")
        for record in selected:
            label = validate_final(record)
            lines.append(f"- {record['id']}: {label['rationale'] or 'Not reviewed'}; broken={label['broken']}; "
                         f"target_label={label['target_label']}; confabulation={label['confabulation']}")
    lines.extend(["", "## Voice and mechanism", ""])
    for key in ("voice", "nearby", "readout", "network_change", "surprises"):
        lines.append(f"- {key}: {run['notes'][key]}")
    lines.extend(["", "## Configuration and hashes", "", "```json",
                  json.dumps({"config": run["config"], "hashes": run["hashes"],
                              "checkpoint_files": run["checkpoint_files"]}, indent=2), "```", ""])
    if heldout is not None:
        lines.append("Held-out source SHA-256: " + heldout["hashes"]["heldout_sealed.json"])
        lines.append("Held-out questions stay in the sealed file; this report includes counts only.")
    return "\n".join(lines) + "\n"


def collision_check(training_paths: list[Path]) -> dict:
    """Check normalised exact questions against explicitly supplied training text.
    Why: future training data must not contain the frozen evaluation prompts.
    If wrong: memorised test wording can inflate the pilot's apparent performance.
    """
    items = []
    for name in ("development.json", "nearby.json", "distant.json", "heldout_sealed.json"):
        items.extend(read_json(QUESTIONS / name)["items"])
    collisions = []
    hashes = {}
    for path in training_paths:
        text = " ".join(path.read_text(encoding="utf-8").casefold().split())
        hashes[str(path)] = sha256(path)
        for item in items:
            for index, prompt in enumerate(item["turns"]):
                if " ".join(prompt.casefold().split()) in text:
                    collisions.append({"id": item["id"], "turn": index + 1, "training_file": str(path)})
    return {"training_sha256": hashes, "collisions": collisions,
            "limitation": "Normalised literal containment only; paraphrases require review. Sealed text is never emitted."}


def main() -> None:
    """Dispatch generation, local collision checks or offline report construction.
    Why: all preparation checks should run without model libraries or credentials.
    If wrong: even a report command could load a model or expose sealed questions.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate")
    generate.add_argument("--base-snapshot", type=Path, required=True)
    generate.add_argument("--kind", choices=["base", "adapter", "merged"], required=True)
    generate.add_argument("--model", type=Path)
    generate.add_argument("--adapter", type=Path)
    generate.add_argument("--approach", required=True)
    generate.add_argument("--dose", required=True)
    generate.add_argument("--split", choices=["development", "heldout"], default="development")
    generate.add_argument("--heldout-final", action="store_true")
    generate.add_argument("--variants", type=Path)
    generate.add_argument("--output", type=Path, required=True)
    report = commands.add_parser("report")
    report.add_argument("--replies", type=Path, required=True)
    report.add_argument("--clean", type=Path, required=True)
    report.add_argument("--heldout", type=Path)
    report.add_argument("--output", type=Path, required=True)
    collision = commands.add_parser("collisions")
    collision.add_argument("training", type=Path, nargs="+")
    collision.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "generate":
        run_generation(args)
    elif args.command == "report":
        heldout = read_json(args.heldout) if args.heldout else None
        text = build_report(read_json(args.replies), read_json(args.clean), heldout)
        text += f"\nRaw replies SHA-256: {sha256(args.replies)}\nClean replies SHA-256: {sha256(args.clean)}\n"
        write_new(args.output, text)
    else:
        result = collision_check(args.training)
        write_new(args.output, result)
        if result["collisions"]:
            raise SystemExit("Collision check failed; inspect IDs in the output")


if __name__ == "__main__":
    main()
