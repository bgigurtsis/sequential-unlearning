"""Run the frozen attention-head lesion experiment without saving full weights."""

import argparse
import contextlib
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from collections.abc import Mapping

try:
    from scripts import erasure_pilot_eval as harness
    from scripts import build_erasure_tokenisations as tokenisations
except ModuleNotFoundError:
    import erasure_pilot_eval as harness
    import build_erasure_tokenisations as tokenisations


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/erasure_pilot_v1/approach_e/settings.json"
OUTPUT = ROOT / "derisk/erasure_pilot_v1/approach_e"
DOSES = (1, 2, 4, 8, 16)
FIXED_SAMPLE = ["direct01", "direct04", "indirect02", "indirect06", "implied03",
                "conversation01", "nearby01", "nearby04", "nearby07",
                "distant01", "distant04", "distant08"]


class TokenizerCompatibility:
    """Preserve token IDs when newer chat templates return an encoding mapping.
    Why: the shared harness and tokenisation builder expect a flat token-ID list.
    If wrong: dictionary keys become model input and prevent all evaluation.
    """

    def __init__(self, tokenizer):
        self.tokenizer = tokenizer

    def __getattr__(self, name):
        return getattr(self.tokenizer, name)

    def __call__(self, *args, **kwargs):
        return self.tokenizer(*args, **kwargs)

    def apply_chat_template(self, *args, **kwargs):
        """Return the same unbatched chat tokens across Transformers API versions.
        Why: the workaround must preserve the exact pinned template and decoded text.
        If wrong: clean and lesioned replies could use changed visitor inputs.
        """
        value = self.tokenizer.apply_chat_template(*args, **kwargs)
        if kwargs.get("tokenize", True) and isinstance(value, Mapping):
            value = value["input_ids"]
            if value and isinstance(value[0], list) and len(value) == 1:
                value = value[0]
        if kwargs.get("tokenize", True) and any(type(token) is not int for token in value):
            raise ValueError("Expected flat integer chat-template token IDs")
        return value


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def dump(path: Path, value) -> None:
    harness.write_new(path, value)


def progress(event: str, **values) -> None:
    print(json.dumps({"time": now(), "event": event, **values}), flush=True)


def prompt_set(settings: dict) -> list[dict]:
    """Build 256 unique scoring prompts for each of the two text groups.
    Why: ranking must use independent clean-written text rather than test replies.
    If wrong: the head ranking can fit the evaluation questions.
    """
    records = []
    for group in ("target", "distant"):
        for topic_index, topic in enumerate(settings["scoring_topics"][group]):
            for angle_index, angle in enumerate(settings["scoring_angles"]):
                prompt = ("Produce one factual standalone paragraph for an educational anthology. "
                          f"The paragraph concerns {topic}. Focus on {angle}. "
                          "Use concrete details rather than a preamble or a list.")
                records.append({"id": f"score_{group}_{topic_index:02d}_{angle_index:02d}",
                                "group": group, "prompt": prompt})
    if len(records) != 512 or len({record["prompt"] for record in records}) != 512:
        raise ValueError("Scoring requires 256 distinct prompts in each group")
    return records


def check_visible_collisions(prompts: list[dict]) -> dict:
    """Check complete scoring prompts against the unsealed evaluation text.
    Why: evaluation wording must not be used to select attention heads.
    If wrong: the damage curve can reflect question-specific overfitting.
    """
    files = ["development.json", "nearby.json", "distant.json", "alternate_tokenisations.json"]
    hashes = {}
    for name in files:
        path = harness.QUESTIONS / name
        hashes[name] = harness.file_hash(path)
        text = " ".join(path.read_text(encoding="utf-8").casefold().split())
        for record in prompts:
            if " ".join(record["prompt"].casefold().split()) in text:
                raise ValueError(f"Scoring prompt collision: {record['id']}")
    # The worker is forbidden to open sealed text, including through the shared checker.
    return {"checked_file_hashes": hashes, "complete_prompt_collisions": 0,
            "sealed": "Not opened. Scoring prompts use a separate anthology template."}


def ranked_masks(scores: list[dict], head_count: int) -> list[dict]:
    """Rank all heads once and round each percentage upward to whole heads.
    Why: every larger lesion must contain every head in the smaller lesion.
    If wrong: differences between doses would mix lesion size and selection.
    """
    if len(scores) != head_count:
        raise ValueError("Every head needs a measured score")
    identities = {(row["layer"], row["head"]) for row in scores}
    if len(identities) != head_count or any(not math.isfinite(row["score"]) for row in scores):
        raise ValueError("Head scores must be unique and finite")
    ranked = sorted(scores, key=lambda row: (-row["score"], row["layer"], row["head"]))
    masks = []
    for dose in DOSES:
        count = math.ceil(head_count * dose / 100)
        heads = [{"layer": row["layer"], "head": row["head"]} for row in ranked[:count]]
        masks.append({"percent_requested": dose, "heads_removed": count, "total_heads": head_count,
                      "percent_actual": 100 * count / head_count, "heads": heads,
                      "operation": "Zero the selected query head input columns in self_attn.o_proj.weight"})
    return masks


def attention_modules(model) -> tuple[list, int, int]:
    """Find text attention outputs and validate their query-head column layout.
    Why: Gemma shares key/value heads but has distinct query-head output columns.
    If wrong: a lesion can remove the wrong units or affect the vision encoder.
    """
    text_config = getattr(model.config, "text_config", model.config)
    heads = text_config.num_attention_heads
    head_dim = text_config.head_dim
    modules = []
    for name, module in model.named_modules():
        if name.endswith("self_attn.o_proj") and "vision" not in name:
            if module.weight.shape[1] != heads * head_dim:
                raise ValueError("Attention output width differs from query-head layout")
            modules.append((name, module))
    if len(modules) != text_config.num_hidden_layers:
        raise ValueError("Did not find exactly the configured number of text layers")
    return modules, heads, head_dim


def head_columns(head: int, head_dim: int, width: int) -> slice:
    start = head * head_dim
    if head < 0 or head_dim < 1 or start + head_dim > width:
        raise ValueError("Invalid head column range")
    return slice(start, start + head_dim)


@contextlib.contextmanager
def single_lesion(module, head: int, head_dim: int):
    """Zero one output column block and restore it even after a scoring failure.
    Why: every score must compare a single lesion with the same clean model.
    If wrong: later head scores would include damage from previous heads.
    """
    import torch

    columns = head_columns(head, head_dim, module.weight.shape[1])
    saved = module.weight[:, columns].detach().clone()
    with torch.no_grad():
        module.weight[:, columns].zero_()
    try:
        yield
    finally:
        with torch.no_grad():
            module.weight[:, columns].copy_(saved)


def apply_mask(modules: list, mask: dict, head_dim: int) -> None:
    """Change model weights in place so a lesion persists without inference hooks.
    Why: approach E tests permanent weight removal rather than runtime suppression.
    If wrong: rebuilding the masked model would not reproduce the evaluation.
    """
    import torch

    with torch.no_grad():
        for selected in mask["heads"]:
            module = modules[selected["layer"]][1]
            columns = head_columns(selected["head"], head_dim, module.weight.shape[1])
            module.weight[:, columns].zero_()


def projection_hashes(modules: list) -> dict:
    """Hash each attention output matrix in its exact stored dtype.
    Why: masks must identify a reproducible permanent weight change.
    If wrong: unchanged-looking masks could conceal a different edit.
    """
    hashes = {}
    for name, module in modules:
        # View bf16 as bytes because numpy does not provide a portable bf16 dtype.
        raw = module.weight.detach().contiguous().cpu().view(__import__("torch").uint8).numpy().tobytes()
        hashes[name] = hashlib.sha256(raw).hexdigest()
    return hashes


def write_passages(model, tokenizer, settings: dict, directory: Path) -> list[dict]:
    """Have the unedited pinned model write every scoring passage exactly once.
    Why: target and distant losses require clean-written text from independent prompts.
    If wrong: edited text or unequal group sizes can bias the score difference.
    """
    path = directory / "scoring_passages.jsonl"
    if path.exists():
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        if len(records) != 512:
            raise ValueError("Incomplete passage artifact. Diagnose before resuming generation.")
        return records
    records = []
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        for prompt in prompt_set(settings):
            reply, input_ids, output_ids = harness.generate_reply(
                model, tokenizer, [{"role": "user", "content": prompt["prompt"]}])
            if not output_ids:
                raise ValueError("A scoring passage is empty")
            record = {**prompt, "assistant": reply, "input_ids": input_ids, "output_ids": output_ids}
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            records.append(record)
            progress("passages", done=len(records), total=512)
    return records


def mean_passage_loss(model, tokenizer, records: list[dict], batch_size: int) -> float:
    """Mean the generated-token cross entropy within each passage, then across passages.
    Why: prompts are context and long passages must not outweigh short passages.
    If wrong: head ranking would partly measure prompt length or prompt prediction.
    """
    import torch
    import torch.nn.functional as functional

    losses = []
    for start in range(0, len(records), batch_size):
        batch = records[start:start + batch_size]
        lengths = [len(row["input_ids"]) + len(row["output_ids"]) for row in batch]
        inputs = torch.full((len(batch), max(lengths)), tokenizer.pad_token_id, dtype=torch.long, device="cuda")
        labels = torch.full_like(inputs, -100)
        attention = torch.zeros_like(inputs)
        for index, row in enumerate(batch):
            ids = row["input_ids"] + row["output_ids"]
            inputs[index, :len(ids)] = torch.tensor(ids, device="cuda")
            attention[index, :len(ids)] = 1
            labels[index, len(row["input_ids"]):len(ids)] = inputs[index, len(row["input_ids"]):len(ids)]
        with torch.inference_mode():
            logits = model(input_ids=inputs, attention_mask=attention, use_cache=False).logits
            # Cross entropy needs the preceding token's logits; prompt and padding labels stay ignored.
            token_losses = functional.cross_entropy(logits[:, :-1].float().transpose(1, 2),
                                                    labels[:, 1:], reduction="none", ignore_index=-100)
            counts = (labels[:, 1:] != -100).sum(dim=1)
            losses.extend((token_losses.sum(dim=1) / counts).cpu().tolist())
        del logits, token_losses
    if len(losses) != 256:
        raise ValueError("A loss group must contain exactly 256 passages")
    return sum(losses) / len(losses)


def loss_batch_size(requested: int, memory_gib: float) -> int:
    # Full-vocabulary float32 loss tensors require a smaller batch on 32/48 GB cards.
    cap = 16 if memory_gib >= 75 else 8 if memory_gib >= 45 else 4
    return min(requested, cap)


def score_heads(model, tokenizer, modules: list, heads: int, head_dim: int,
                passages: list[dict], directory: Path, batch_size: int) -> list[dict]:
    """Measure exact one-head ablation effects on both complete passage groups.
    Why: activation proxies or gradients do not implement the frozen loss-rise method.
    If wrong: the selected heads would belong to a different experiment.
    """
    groups = {group: [row for row in passages if row["group"] == group] for group in ("target", "distant")}
    baseline = {group: mean_passage_loss(model, tokenizer, rows, batch_size) for group, rows in groups.items()}
    dump(directory / "scoring_clean_loss.json", baseline)
    scores = []
    with (directory / "head_scores.jsonl").open("x", encoding="utf-8", newline="\n") as handle:
        for layer, (name, module) in enumerate(modules):
            for head in range(heads):
                started = time.perf_counter()
                with single_lesion(module, head, head_dim):
                    loss = {group: mean_passage_loss(model, tokenizer, rows, batch_size)
                            for group, rows in groups.items()}
                target_rise = loss["target"] - baseline["target"]
                distant_rise = loss["distant"] - baseline["distant"]
                row = {"layer": layer, "head": head, "module": name, "loss": loss,
                       "target_rise": target_rise, "distant_rise": distant_rise,
                       "score": target_rise - distant_rise, "seconds": time.perf_counter() - started}
                handle.write(json.dumps(row) + "\n")
                handle.flush()
                scores.append(row)
                progress("heads", done=len(scores), total=len(modules) * heads, last=row)
    dump(directory / "head_scores.json", {"baseline": baseline, "scores": scores,
         "mean": "Mean generated-token CE per passage, then mean of 256 passages per group"})
    return scores


def decay_records(settings: dict) -> list[dict]:
    """Select the predeclared decay subset by IDs from the existing frozen battery.
    Why: all doses need the same factual and general-language damage measurement.
    If wrong: changing examples across doses can manufacture a damage curve.
    """
    source = ROOT / "data/decay_scalar_prompts.json"
    battery = harness.read_json(source)
    by_id = {row["id"]: {**row, "set": group} for group in ("generic", "factual") for row in battery[group]}
    return [dict(by_id[item_id]) for item_id in settings["decay_subset_ids"]]


def decay_generate(model, tokenizer, settings: dict, directory: Path, dose: str) -> list[dict]:
    """Generate the frozen decay subset at one dose with the pilot decoding settings.
    Why: a common subset makes global damage comparable across doses.
    If wrong: decoding or prompt changes could look like lesion damage.
    """
    records = decay_records(settings)
    for index, row in enumerate(records):
        reply, _, output_ids = harness.generate_reply(model, tokenizer, [{"role": "user", "content": row["prompt"]}])
        row.update({"generation": reply, "output_ids": output_ids})
        progress("decay", dose=dose, done=index + 1, total=len(records))
    dump(directory / f"decay_{dose}_raw.json", {"records": records, "generation": harness.GENERATION,
         "source_sha256": harness.file_hash(ROOT / "data/decay_scalar_prompts.json")})
    return records


def decay_judge(model, tokenizer, records: list[dict], directory: Path, dose: str) -> None:
    """Use the clean model and existing decay formulas on every saved decay reply.
    Why: a lesioned judge would confuse global damage with its own damage.
    If wrong: the J component can reward malformed or off-topic generations.
    """
    try:
        from scripts import eval_decay_scalar as decay
    except ModuleNotFoundError:
        import eval_decay_scalar as decay

    for row in records:
        prompt = decay.JUDGE_RUBRIC.format(prompt=row["prompt"], response=row["generation"] or "(empty)")
        reply, _, _ = harness.generate_reply(model, tokenizer, [{"role": "user", "content": prompt}])
        row["judge_raw"] = reply
        row["judge_score"] = decay.parse_judge_score(reply)
    decay.compute_text_components(records, tokenizer)
    valid = [row["judge_score"] for row in records if row["judge_score"] is not None]
    factual = [row["token_f1"] for row in records if row["set"] == "factual"]
    components = {"R": sum(row["seq_rep_4"] for row in records) / len(records),
                  "D": 1 - sum(row["distinct_2_at_128"] for row in records) / len(records),
                  "J": 1 - sum(valid) / len(valid) / 5 if valid else None,
                  "F": 1 - sum(factual) / len(factual)}
    raw_scalar = None
    if len(valid) == len(records):
        raw_scalar = sum(components[name] * weight for name, weight in
                         {"R": .25, "D": .15, "J": .35, "F": .25}.items())
    dump(directory / f"decay_{dose}.json", {"records": records, "components": components,
         "raw_weighted_scalar": raw_scalar, "judge_unparsed": len(records) - len(valid),
         "normalised_scalar": None, "normalisation_note": "No matched terminal anchors for this subset",
         "judge": "Pinned unedited Gemma", "generation": harness.GENERATION})


def package_versions() -> dict:
    """Record installed model packages and the actual GPU driver report.
    Why: the run must preserve the software and hardware used for generation.
    If wrong: another worker cannot reproduce the loader and attention behaviour.
    """
    versions = {"python": sys.version, "platform": platform.platform()}
    for name in ("torch", "transformers", "peft", "accelerate", "tokenizers", "huggingface-hub", "safetensors",
                 "torchvision", "torchaudio", "numpy"):
        versions[name] = importlib.metadata.version(name)
    versions["nvidia_smi"] = subprocess.check_output(["nvidia-smi"], text=True)
    return versions


def await_distant_review(directory: Path, dose: str) -> int:
    """Wait for this worker's read-through judgment before allowing another dose.
    Why: two consecutive distant-control collapses must stop the lesion ladder.
    If wrong: unreviewed collapse could consume all remaining doses and budget.
    """
    path = directory / f"replies_{dose}_judged.json"
    progress("awaiting_review", dose=dose, path=str(path))
    while not path.exists():
        time.sleep(5)
    review = harness.read_json(path)
    controls = [row for row in review["results"] if row["group"] == "distant"]
    if len(controls) != 24 or any(row["judge"]["usefulness"] not in {"USEFUL", "NOT_USEFUL"} for row in controls):
        raise ValueError("All 24 distant controls need explicit judgment before the next dose")
    if any(row["judge"]["broken"] is True and row["judge"]["usefulness"] == "USEFUL" for row in controls):
        raise ValueError("A broken control cannot be useful")
    if any(any(value is not None for value in row["final"].values()) for row in review["results"]):
        raise ValueError("Manager final labels must remain empty")
    return sum(row["judge"]["usefulness"] == "USEFUL" for row in controls)


def question_generation(model, tokenizer, items: list[dict], directory: Path, dose: str,
                        question_hashes: dict, base_hashes: dict, checkpoint: dict) -> list[dict]:
    """Archive all visible questions using the shared harness and live histories.
    Why: the clean reference and each lesion need identical generation settings.
    If wrong: dose comparisons could reflect changes in evaluation or decoding.
    """
    started = time.perf_counter()
    records = []
    with (directory / f"replies_{dose}.jsonl").open("x", encoding="utf-8", newline="\n") as handle:
        for item in items:
            record = harness.generate_item(model, tokenizer, item)
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            records.append(record)
            progress("evaluation", dose=dose, done=len(records), total=len(items))
    dump(directory / f"replies_{dose}.json", {"schema": "erasure_pilot_replies_v1", "approach": "E",
         "dose": dose, "split": "development", "generated_at": now(), "config": {
         "base": harness.BASE, "revision": harness.REVISION,
         "kind": "base" if dose == "clean_reference" else "permanent_head_lesion",
         "generation": harness.GENERATION, "seed": 0}, "hashes": question_hashes,
         "base_files": base_hashes, "checkpoint_files": checkpoint, "results": records,
         "timing": {"generation_seconds": time.perf_counter() - started},
         "notes": {"voice": "Awaiting agent judgment", "nearby": "Awaiting agent judgment"}})
    return records


def await_clean_qualification(directory: Path) -> list[str]:
    """Require agent labels for the clean development denominator before lesion tests.
    Why: only substantive clean answers qualify for the ninety-percent absence bar.
    If wrong: clean refusals could inflate measured forgetting.
    """
    path = directory / "replies_clean_reference_judged.json"
    progress("awaiting_clean_qualification", path=str(path))
    while not path.exists():
        time.sleep(5)
    records = harness.read_json(path)["results"]
    targets = [row for row in records if row["group"] == "target"]
    if len(targets) != 40 or any(row["judge"]["target_label"] not in
                               {"SUBSTANTIVE", "ABSENT", "BROKEN"} for row in targets):
        raise ValueError("All 40 clean targets require agent judgment")
    qualifying = [row["id"] for row in targets if row["judge"]["target_label"] == "SUBSTANTIVE"]
    if len(qualifying) < 30:
        raise ValueError("Fewer than 30 clean targets qualify. Manager must supply replacements before lesion evaluation.")
    dump(directory / "clean_qualification.json", {"qualifying_ids": qualifying,
         "excluded_ids": [row["id"] for row in targets if row["id"] not in qualifying],
         "required_absent": math.ceil(.9 * len(qualifying)),
         "review_sha256": harness.file_hash(path)})
    return qualifying


def run(args) -> None:
    """Execute clean passage writing, exact head ranking and every nested lesion dose.
    Why: a single process keeps the scoring reference and generation settings fixed.
    If wrong: missing doses or an altered reference would prevent a valid comparison.
    """
    import torch
    from transformers import AutoTokenizer

    settings = harness.read_json(args.config)
    directory = args.output
    directory.mkdir(parents=True, exist_ok=True)
    started = now()
    torch.manual_seed(0)
    base_hashes = harness.verify_snapshot(args.base_snapshot)
    tokenizer = AutoTokenizer.from_pretrained(str(args.base_snapshot), local_files_only=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = 1  # The pinned EOS is padding, matching the shared harness.
    tokenizer = TokenizerCompatibility(tokenizer)
    variants = directory / "tokenisations.json"
    if not variants.exists():
        development = harness.read_json(harness.QUESTIONS / "development.json")
        recipes = harness.read_json(harness.QUESTIONS / "alternate_tokenisations.json")
        dump(variants, {"schema": "erasure_pilot_materialised_tokenisations_v1", "base": harness.BASE,
             "revision": harness.REVISION, "method": recipes["method"],
             "development_sha256": harness.file_hash(harness.QUESTIONS / "development.json"),
             "recipes_sha256": harness.file_hash(harness.QUESTIONS / "alternate_tokenisations.json"),
             "items": tokenisations.build(tokenizer, development, recipes)})
    items, question_hashes = harness.load_questions("development", variants)
    loss_microbatch = loss_batch_size(settings["loss_microbatch"],
                                     torch.cuda.get_device_properties(0).total_memory / 1024 ** 3)
    dump(directory / "run_config.json", {"started_at": started, "settings": settings,
         "base_files": base_hashes, "question_hashes": question_hashes,
         "generation": harness.GENERATION, "config_sha256": harness.file_hash(args.config),
         "loss_microbatch_actual": loss_microbatch,
         "script_sha256": harness.file_hash(Path(__file__)), "collision_check": check_visible_collisions(prompt_set(settings)),
         "source_code_hashes": {name: harness.file_hash(ROOT / "scripts" / name) for name in
             ("erasure_pilot_e_run.py", "erasure_pilot_eval.py", "build_erasure_tokenisations.py",
              "eval_decay_scalar.py", "decay_scalar_normalization.py", "runpod_pilot.py")},
         "source_commit": os.environ.get("ERASURE_SOURCE_COMMIT", "not supplied")})
    dump(directory / "package_versions.json", package_versions())
    model = harness.load_model(SimpleNamespace(base_snapshot=args.base_snapshot, kind="base", model=None))
    modules, heads, head_dim = attention_modules(model)
    clean_hashes = projection_hashes(modules)
    question_generation(model, tokenizer, items, directory, "clean_reference", question_hashes,
                        base_hashes, {"projection_hashes": clean_hashes})
    decay_outputs = {"clean_reference": decay_generate(model, tokenizer, settings, directory, "clean_reference")}
    passages = write_passages(model, tokenizer, settings, directory)
    scores = score_heads(model, tokenizer, modules, heads, head_dim, passages, directory, loss_microbatch)
    if projection_hashes(modules) != clean_hashes:
        raise ValueError("Single-head scoring did not restore the clean weights")
    masks = ranked_masks(scores, len(modules) * heads)
    await_clean_qualification(directory)
    collapsed = 0
    completed_doses = []
    for mask in masks:
        dose = f"dose{mask['percent_requested']:02d}"
        dump(directory / f"mask_{dose}.json", {**mask, "base_revision": harness.REVISION,
             "head_dim": head_dim, "scores_sha256": harness.file_hash(directory / "head_scores.json")})
        apply_mask(modules, mask, head_dim)
        question_generation(model, tokenizer, items, directory, dose, question_hashes, base_hashes,
                            {"mask": harness.file_hash(directory / f"mask_{dose}.json"),
                             "projection_hashes": projection_hashes(modules)})
        decay_outputs[dose] = decay_generate(model, tokenizer, settings, directory, dose)
        useful = await_distant_review(directory, dose)
        collapsed = collapsed + 1 if useful < 16 else 0
        completed_doses.append(mask["percent_requested"])
        if collapsed >= 2:
            progress("collapse_stop", dose=dose, distant_useful=useful)
            break
    # Reload clean weights from the verified local snapshot before the decay judge runs.
    del modules, model
    __import__("gc").collect()
    torch.cuda.empty_cache()
    clean = harness.load_model(SimpleNamespace(base_snapshot=args.base_snapshot, kind="base", model=None))
    for dose, records in decay_outputs.items():
        decay_judge(clean, tokenizer, records, directory, dose)
    dump(directory / "completion.json", {"started_at": started, "ended_at": now(), "doses": completed_doses,
         "heads_scored": len(scores), "passages": len(passages), "status": "generation_complete_pending_review",
         "artifact_hashes": {path.name: harness.file_hash(path) for path in sorted(directory.iterdir())
                             if path.is_file() and path.suffix in {".json", ".jsonl"}}})
    progress("complete")


def main() -> None:
    """Accept explicit local snapshot and output paths for the full planned run.
    Why: model loading must never fall back to an unpinned downloaded revision.
    If wrong: the experiment could evaluate a different base model.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-snapshot", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
