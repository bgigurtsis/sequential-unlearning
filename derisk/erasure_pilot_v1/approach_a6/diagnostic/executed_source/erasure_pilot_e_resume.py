"""Continue the complete E run with contiguous token cross entropy."""

import argparse
import gc
import json
import math
import time
from pathlib import Path
from types import SimpleNamespace

try:
    from scripts import erasure_pilot_e_run as experiment
except ModuleNotFoundError:
    import erasure_pilot_e_run as experiment


def mean_loss(model, tokenizer, records: list[dict], batch_size: int) -> float:
    """Compute the same per-passage mean using a contiguous token-by-vocabulary matrix.
    Why: transposed three-dimensional cross entropy is too slow for the E allowance.
    If wrong: numerical changes or changed passage weighting could bias head selection.
    """
    import torch
    import torch.nn.functional as functional

    losses = []
    forward_seconds = 0.0
    loss_seconds = 0.0
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
            torch.cuda.synchronize()
            forward_started = time.perf_counter()
            logits = model(input_ids=inputs, attention_mask=attention, use_cache=False).logits
            torch.cuda.synchronize()
            forward_seconds += time.perf_counter() - forward_started
            loss_started = time.perf_counter()
            # Flatten positions only. Vocabulary stays last and every passage retains its original weight.
            shifted = logits[:, :-1].reshape(-1, logits.shape[-1]).float()
            targets = labels[:, 1:].reshape(-1)
            token_losses = functional.cross_entropy(shifted, targets, reduction="none", ignore_index=-100)
            per_passage = token_losses.reshape(len(batch), -1).sum(dim=1)
            counts = (labels[:, 1:] != -100).sum(dim=1)
            losses.extend((per_passage / counts).cpu().tolist())
            loss_seconds += time.perf_counter() - loss_started
        del logits, shifted, token_losses
    if len(losses) != 256:
        raise ValueError("A loss group must contain exactly 256 passages")
    experiment.progress("loss_profile", passages=256, forward_seconds=forward_seconds,
                        cross_entropy_seconds=loss_seconds)
    return sum(losses) / len(losses)


def score_heads(model, tokenizer, modules, heads, head_dim, passages, directory, batch_size):
    """Resume all remaining single-head measurements after checking full clean losses.
    Why: the full corpus and already completed measurements must remain available.
    If wrong: a restart could mix different baselines or duplicate head identities.
    """
    harness = experiment.harness
    groups = {group: [row for row in passages if row["group"] == group] for group in ("target", "distant")}
    baseline = harness.read_json(directory / "scoring_clean_loss.json")
    checked = {group: mean_loss(model, tokenizer, rows, batch_size) for group, rows in groups.items()}
    # This tolerance checks floating-point implementation agreement, not any pilot acceptance threshold.
    if any(abs(checked[group] - baseline[group]) > 2e-6 for group in groups):
        raise ValueError("Contiguous and transposed clean losses disagree by more than 2e-6")
    path = directory / "head_scores.jsonl"
    scores = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    done = {(row["layer"], row["head"]) for row in scores}
    if len(done) != len(scores) or any(not math.isfinite(row["score"]) for row in scores):
        raise ValueError("Existing head scores must be unique and finite")
    resumed_after = len(scores)
    experiment.progress("resume_loss_agreement", original=baseline, contiguous=checked,
                        completed_heads=resumed_after, implementation="token_by_vocabulary_cross_entropy")
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for layer, (name, module) in enumerate(modules):
            for head in range(heads):
                if (layer, head) in done:
                    continue
                started = time.perf_counter()
                with experiment.single_lesion(module, head, head_dim):
                    loss = {group: mean_loss(model, tokenizer, rows, batch_size) for group, rows in groups.items()}
                target_rise = loss["target"] - baseline["target"]
                distant_rise = loss["distant"] - baseline["distant"]
                row = {"layer": layer, "head": head, "module": name, "loss": loss,
                       "target_rise": target_rise, "distant_rise": distant_rise,
                       "score": target_rise - distant_rise, "seconds": time.perf_counter() - started,
                       "loss_implementation": "token_by_vocabulary_cross_entropy"}
                handle.write(json.dumps(row) + "\n")
                handle.flush()
                scores.append(row)
                experiment.progress("heads", done=len(scores), total=len(modules) * heads, last=row)
    experiment.dump(directory / "head_scores.json", {"baseline": baseline, "scores": scores,
                    "mean": "Mean generated-token CE per passage, then mean of 256 passages per group",
                    "resume": {"completed_before_resume": resumed_after, "clean_loss_check": checked,
                               "source_sha256": harness.file_hash(Path(__file__))}})
    return scores


def run(args) -> None:
    """Finish the same full corpus ranking, nested doses and decay subset on this pod.
    Why: performance repair must preserve every generation and all fixed run settings.
    If wrong: a shortened corpus or a missing dose could be misreported as the full E run.
    """
    import torch
    from transformers import AutoTokenizer

    harness = experiment.harness
    directory = args.output
    config = harness.read_json(directory / "run_config.json")
    settings = config["settings"]
    base_hashes = harness.verify_snapshot(args.base_snapshot)
    if base_hashes != config["base_files"] or config["generation"] != harness.GENERATION:
        raise ValueError("Resume differs from the original pinned model or decoding settings")
    tokenizer = AutoTokenizer.from_pretrained(str(args.base_snapshot), local_files_only=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = 1  # Match the already archived clean reference.
    tokenizer = experiment.TokenizerCompatibility(tokenizer)
    items, question_hashes = harness.load_questions("development", directory / "tokenisations.json")
    if question_hashes != config["question_hashes"]:
        raise ValueError("Question hashes changed during the performance repair")
    passages = [json.loads(line) for line in (directory / "scoring_passages.jsonl").read_text(encoding="utf-8").splitlines()]
    if len(passages) != 512:
        raise ValueError("The complete original 512-passage corpus is required")
    model = harness.load_model(SimpleNamespace(base_snapshot=args.base_snapshot, kind="base", model=None))
    modules, heads, head_dim = experiment.attention_modules(model)
    clean_hashes = experiment.projection_hashes(modules)
    scores = score_heads(model, tokenizer, modules, heads, head_dim, passages, directory, config["loss_microbatch_actual"])
    if experiment.projection_hashes(modules) != clean_hashes:
        raise ValueError("Single-head scoring did not restore the clean projection weights")
    masks = experiment.ranked_masks(scores, len(modules) * heads)
    experiment.await_clean_qualification(directory)
    decay_outputs = {"clean_reference": harness.read_json(directory / "decay_clean_reference_raw.json")["records"]}
    collapsed = 0
    completed_doses = []
    for mask in masks:
        dose = f"dose{mask['percent_requested']:02d}"
        experiment.dump(directory / f"mask_{dose}.json", {**mask, "base_revision": harness.REVISION,
                        "head_dim": head_dim, "scores_sha256": harness.file_hash(directory / "head_scores.json")})
        experiment.apply_mask(modules, mask, head_dim)
        experiment.question_generation(model, tokenizer, items, directory, dose, question_hashes, base_hashes,
                                       {"mask": harness.file_hash(directory / f"mask_{dose}.json"),
                                        "projection_hashes": experiment.projection_hashes(modules)})
        decay_outputs[dose] = experiment.decay_generate(model, tokenizer, settings, directory, dose)
        useful = experiment.await_distant_review(directory, dose)
        collapsed = collapsed + 1 if useful < 16 else 0
        completed_doses.append(mask["percent_requested"])
        if collapsed >= 2:
            experiment.progress("collapse_stop", dose=dose, distant_useful=useful)
            break
    del modules, model
    gc.collect()
    torch.cuda.empty_cache()
    clean = harness.load_model(SimpleNamespace(base_snapshot=args.base_snapshot, kind="base", model=None))
    for dose, records in decay_outputs.items():
        experiment.decay_judge(clean, tokenizer, records, directory, dose)
    experiment.dump(directory / "completion.json", {"started_at": config["started_at"],
                    "ended_at": experiment.now(), "doses": completed_doses, "heads_scored": len(scores),
                    "passages": len(passages), "status": "generation_complete_pending_manager_review",
                    "resume_source_sha256": harness.file_hash(Path(__file__)),
                    "artifact_hashes": {p.name: harness.file_hash(p) for p in sorted(directory.iterdir())
                                        if p.is_file() and p.suffix in {".json", ".jsonl"}}})
    experiment.progress("complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=experiment.OUTPUT)
    run(parser.parse_args())
