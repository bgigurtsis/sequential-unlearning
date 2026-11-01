"""Run one fixed B noise level on an already provisioned H200. Never create pods."""

import argparse
import copy
import hashlib
import importlib
import importlib.metadata
import json
import math
import os
import platform
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from scripts import erasure_pilot_eval as harness
    from scripts.erasure_pilot_b_data import CONFIG, ROOT, live_stream, read_settings
    from scripts.erasure_pilot_b_review import await_judge, evaluation, judge_summary, qualifying_target_ids, report_text, stop_reason, useful_count, write_new
    from scripts.erasure_pilot_b_train import answer_backward, distill_backward, learning_rate, noise_student, optimiser, prepare_training
except ModuleNotFoundError:
    import erasure_pilot_eval as harness
    from erasure_pilot_b_data import CONFIG, ROOT, live_stream, read_settings
    from erasure_pilot_b_review import await_judge, evaluation, judge_summary, qualifying_target_ids, report_text, stop_reason, useful_count, write_new
    from erasure_pilot_b_train import answer_backward, distill_backward, learning_rate, noise_student, optimiser, prepare_training


def check_time(deadline: float, reserve: float = 0) -> None:
    if time.monotonic() + reserve >= deadline:
        raise TimeoutError("Pod budget deadline reached; archive existing artifacts and terminate")


def append_event(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(), **record}) + "\n")
        handle.flush()


def load_base(snapshot: Path, dtype):
    """Load the pinned base locally using the shared Gemma fallback.
    Why: A's small adapter travels between pods, while full weights stay on each pod.
    If wrong: an unpinned download or quantised load changes the planned teacher.
    """
    from transformers import AutoModelForCausalLM, Gemma3ForConditionalGeneration

    kwargs = {"torch_dtype": dtype, "device_map": "cuda", "local_files_only": True, "attn_implementation": "sdpa"}
    try:
        model = AutoModelForCausalLM.from_pretrained(str(snapshot), **kwargs)
    except ValueError:
        # The pinned checkpoint is multimodal; its text path still accepts ordinary text-only chat.
        model = Gemma3ForConditionalGeneration.from_pretrained(str(snapshot), **kwargs)
    return model


def merged_teacher(snapshot: Path, adapter: Path):
    """Merge A's selected text LoRA into the exact base on this pod.
    Why: the teacher must contain A's suppression before either noise level starts.
    If wrong: distillation teaches the student to recover the original target knowledge.
    """
    import torch
    from peft import PeftModel

    model = load_base(snapshot, torch.bfloat16)
    adapter_config = harness.read_json(adapter / "adapter_config.json")
    base_name = adapter_config.get("base_model_name_or_path", "")
    # A may record its own pod's absolute base path. The verified B snapshot supplies the weights.
    if base_name != harness.BASE and not Path(base_name).is_absolute():
        raise ValueError("Adapter must identify Gemma or A's absolute pod-local base path")
    if adapter_config.get("revision") not in {None, harness.REVISION}:
        raise ValueError("Adapter declares a different base revision")
    model = PeftModel.from_pretrained(model, str(adapter), is_trainable=False, local_files_only=True)
    model = model.merge_and_unload(safe_merge=True)
    model.requires_grad_(False)
    model.eval()
    return model


def ensure_snapshot(path: Path, download: bool) -> dict:
    """Fetch only the pinned base assets on the paid pod, then verify every frozen hash.
    Why: the repository must never carry full model weights or gated-model tokens.
    If wrong: an incompatible tokenizer or base revision can confound all B results.
    """
    if download:
        from huggingface_hub import snapshot_download
        token = os.environ.get("HUGGINGFACE_TOKEN")
        if not token:
            raise ValueError("The pod needs HUGGINGFACE_TOKEN in its environment")
        snapshot_download(repo_id=harness.BASE, revision=harness.REVISION, local_dir=path,
                          token=token, allow_patterns=list(harness.read_json(harness.FREEZE)["base_files"]))
    return harness.verify_snapshot(path)


def package_versions() -> dict:
    names = ["torch", "transformers", "peft", "accelerate", "datasets", "huggingface-hub",
             "sentence-transformers", "scikit-learn", "numpy", "safetensors", "tokenizers"]
    return {name: importlib.metadata.version(name) for name in names}


def save_model(model, tokenizer, path: Path) -> dict:
    """Save one immutable pod-local checkpoint and hash its exact files.
    Why: a full-parameter student cannot be rebuilt from A's adapter alone.
    If wrong: termination destroys the only copy of the selected B model.
    """
    if path.exists():
        raise FileExistsError("Refusing to replace a B checkpoint")
    model.save_pretrained(path, safe_serialization=True, max_shard_size="5GB")
    tokenizer.save_pretrained(path)
    return harness.checkpoint_hashes(path)


def run_readout(hook: str | None, model, tokenizer, output: Path, args, arm: str) -> dict:
    """Call A's unchanged recognition probe through an explicit integration contract.
    Why: fitting a new target probe on B cannot measure lost recognition comparably.
    If wrong: a changed probe can masquerade as knowledge loss or survival.
    """
    if hook is None or args.readout_probe is None:
        result = {"status": "INCOMPLETE", "reason": "A readout hook was not supplied", "arm": arm,
                  "required_contract": "hook(model, tokenizer, probe_path, output_path, arm) -> JSON dict",
                  "required_probe": "A's frozen distant-trained logistic probe, items and never-known calibration"}
    else:
        module_name, separator, function_name = hook.partition(":")
        short_name = module_name.split(".")[-1]
        if not separator or not (short_name.startswith("erasure_pilot_a_") or short_name == "erasure_pilot_b_readout"):
            raise ValueError("Readout hook must use A's readout or B's adapter for that readout")
        function = getattr(importlib.import_module(module_name), function_name)
        result = function(model=model, tokenizer=tokenizer, probe_path=args.readout_probe,
                          output_path=output, arm=arm)
        if not isinstance(result, dict):
            raise ValueError("A readout hook must return JSON-compatible measurements")
    if not output.exists():
        write_new(output, result)
    return result


def get_batch(stream, size: int) -> list[dict]:
    records = []
    for _ in range(size):
        try:
            records.append(next(stream))
        except StopIteration:
            break
    return records


def train_distillation(teacher, student, tokenizer, settings: dict, context: dict, args, deadline: float, teacher_count: int) -> dict:  # noqa: C901 - one experiment, reads top to bottom
    """Run the full planned token budget with distant-control recovery checkpoints.
    Why: both noise levels must use the frozen optimiser, mixture and stop rules.
    If wrong: different token counts, precision or utility labels make the comparison invalid.
    """
    import torch

    mixed = live_stream(settings, tokenizer)
    stream = iter(mixed)
    train_optimiser = optimiser(student, settings["learning_rate"])
    total_steps = math.ceil(settings["tokens"] / (settings["sequences_per_step"] * settings["sequence_length"]))
    history, tokens, reason = [], 0, None
    training_seconds = 0.0
    for step in range(1, total_steps + 1):
        check_time(deadline, reserve=settings["archive_reserve_seconds"])
        started = time.monotonic()
        batch = get_batch(stream, settings["sequences_per_step"])
        if not batch:
            raise RuntimeError("Streaming pipeline ended before the 20M-token budget")
        denominator = sum(sum(record["attention_mask"][1:]) for record in batch)
        rate = learning_rate(step, total_steps, settings["learning_rate"], settings["warmup_steps"])
        for group in train_optimiser.param_groups:
            group["lr"] = rate
        train_optimiser.zero_grad(set_to_none=True)
        loss, input_digest = 0.0, hashlib.sha256()
        for record in batch:
            check_time(deadline, reserve=settings["archive_reserve_seconds"])
            ids = torch.tensor([record["input_ids"]], device="cuda", dtype=torch.long)
            mask = torch.tensor([record["attention_mask"]], device="cuda", dtype=torch.long)
            input_digest.update(ids.cpu().numpy().tobytes())
            with torch.autocast("cuda", dtype=torch.bfloat16):
                loss += distill_backward(teacher, student, ids, mask, denominator, settings["logit_chunk_tokens"])
        torch.nn.utils.clip_grad_norm_(student.parameters(), 1.0)
        train_optimiser.step()
        torch.cuda.synchronize()
        seconds = time.monotonic() - started
        training_seconds += seconds
        tokens += sum(record["tokens"] for record in batch)
        append_event(args.output / "training.jsonl", {"step": step, "tokens": tokens, "kl_positions": denominator,
                     "forward_kl": loss, "lr": rate, "seconds": seconds, "input_ids_sha256": input_digest.hexdigest(),
                     "peak_cuda_gb": torch.cuda.max_memory_allocated() / 1e9})
        print(f"TRAIN step={step}/{total_steps} tokens={tokens} KL={loss:.5f} seconds={seconds:.2f}", flush=True)
        # This is a real-run performance stop, never a preceding trial or diagnostic run.
        if step >= 10 and tokens / training_seconds < settings["predicted_tokens_per_second"] / 2:
            reason = "more_than_twice_predicted_training_time_diagnose_before_retry"
            break
        if step % settings["evaluation_steps"] == 0 or tokens >= settings["tokens"]:
            raw_path = args.output / f"step{step:05d}.raw.json"
            evaluation(student, tokenizer, raw_path, "B", f"alpha{args.alpha}_step{step}", context, controls_only=True)
            judged = await_judge(raw_path, deadline, args.judge_wait_seconds)
            history.append(useful_count(judged))
            reason = stop_reason(teacher_count, history, tokens, settings["tokens"])
            append_event(args.output / "training.jsonl", {"checkpoint": step, "distant_useful": history[-1],
                         "teacher_useful": teacher_count, "stop_reason": reason, "filter": mixed.summary()})
            if reason:
                break
    result = {"steps": step, "input_tokens": tokens, "training_seconds": training_seconds,
              "training_tokens_per_second": tokens / training_seconds, "distant_history": history,
              "stop_reason": reason, "filter": mixed.summary()}
    write_new(args.output / "distillation.json", result)
    del train_optimiser
    student.zero_grad(set_to_none=True)
    torch.cuda.empty_cache()
    return result


def answer_encoding(tokenizer, messages: list[dict], answer: str, length: int = 1024) -> dict:
    """Tokenise one clean answer with an explicit assistant-only loss mask.
    Why: the fixed relearning test teaches answers rather than training on evaluation prompts.
    If wrong: truncation or a chat-template mismatch can remove the whole training signal.
    """
    prefix = list(tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True))
    complete = list(tokenizer.apply_chat_template(messages + [{"role": "assistant", "content": answer}],
                                                  tokenize=True, add_generation_prompt=False))
    if complete[:len(prefix)] != prefix:
        raise ValueError("Assistant answer tokenisation does not preserve the chat prefix")
    if len(complete) > length or len(complete) <= len(prefix):
        raise ValueError("Relearning answer is empty or exceeds 1024 tokens; do not silently truncate")
    return {"input_ids": complete, "attention_mask": [1] * len(complete),
            "response_mask": [0] * len(prefix) + [1] * (len(complete) - len(prefix))}


def clean_relearning_data(clean_model, tokenizer, args, context: dict, deadline: float) -> list[dict]:
    """Generate twenty clean target answers from authored non-evaluation prompts.
    Why: all three relearning arms need the same genuine clean-model answers.
    If wrong: paraphrased test answers or invented targets exaggerate recovery.
    """
    import torch

    prompts = harness.read_json(CONFIG.parent / "relearning_prompts.json")["items"]
    results = []
    with torch.autocast("cuda", dtype=torch.bfloat16):
        for item in prompts:
            check_time(deadline)
            results.append(harness.generate_item(clean_model, tokenizer, item))
    raw = {"schema": "b_relearning_answers_v1", "revision": harness.REVISION,
           "generation": harness.GENERATION, "results": results}
    path = args.output / "relearning_answers.raw.json"
    write_new(path, raw)
    judged = await_judge(path, deadline, args.judge_wait_seconds)
    if len(results) != 20 or any(record["judge"]["target_label"] != "SUBSTANTIVE" for record in judged["results"]):
        raise ValueError("All twenty clean training answers need agent-confirmed substantive target knowledge")
    return [answer_encoding(tokenizer, [{"role": "user", "content": record["transcript"][0]["user"]}],
                            record["transcript"][0]["assistant"]) for record in judged["results"]]


def relearn(model, tokenizer, examples: list[dict], arm: str, args, context: dict, deadline: float) -> dict:
    """Apply twenty full-parameter answer-CE steps at 1e-5 to one comparison arm.
    Why: B, A and clean must face the same twenty examples and number of updates.
    If wrong: different attack budgets can resemble greater resistance to relearning.
    """
    import torch

    prepare_training(model)
    train_optimiser = optimiser(model, 1e-5)
    denominator = sum(sum(example["response_mask"][1:]) for example in examples)
    for step in range(1, 21):
        check_time(deadline)
        train_optimiser.zero_grad(set_to_none=True)
        loss = 0.0
        for example in examples:
            tensors = {name: torch.tensor([example[name]], device="cuda", dtype=torch.long)
                       for name in ("input_ids", "attention_mask", "response_mask")}
            with torch.autocast("cuda", dtype=torch.bfloat16):
                loss += answer_backward(model, **tensors, denominator=denominator)
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        train_optimiser.step()
        append_event(args.output / f"relearn_{arm}.jsonl", {"step": step, "answer_ce": loss, "lr": 1e-5})
    del train_optimiser
    model.zero_grad(set_to_none=True)
    torch.cuda.empty_cache()
    raw_path = args.output / f"relearn_{arm}.raw.json"
    evaluation(model, tokenizer, raw_path, "B-relearning", arm, {**context, "model_identity": f"{arm}_after_20_relearning_steps"})
    judged = await_judge(raw_path, deadline, args.judge_wait_seconds)
    clean = harness.read_json(args.clean_replies)
    summary = judge_summary(judged, clean)
    write_new(args.output / f"relearn_{arm}.summary.json", summary)
    return summary


def validate_paths(args) -> None:
    """Keep full weights outside the repository and refuse reuse of an output directory.
    Why: Git must contain only small B artifacts and immutable raw results.
    If wrong: a launch can overwrite evidence or add gigabytes of model weights to Git.
    """
    if args.weights.resolve().is_relative_to(ROOT.resolve()) or args.base_snapshot.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("Base snapshots and full weights must be outside the repository")
    if args.output.exists():
        raise FileExistsError("Use a new B output directory")
    if not args.adapter.is_dir() or not args.clean_replies.is_file() or not args.variants.is_file():
        raise ValueError("A's adapter, the clean baseline and materialised tokenisations are required")
    clean = harness.read_json(args.clean_replies)
    items, hashes = harness.load_questions("development", args.variants)
    harness.validate_pair(clean, clean)
    if clean["hashes"] != hashes:
        raise ValueError("Clean replies and B inputs have different frozen question hashes")
    by_id = {record["id"]: record for record in clean["results"]}
    if set(by_id) != {item["id"] for item in items}:
        raise ValueError("The clean baseline must include every materialised development input")
    for item in items:
        if by_id[item["id"]]["turns"] != item["turns"]:
            raise ValueError("Clean question text differs from the frozen inputs")
    qualifying_target_ids(clean)


def run(args) -> None:  # noqa: C901 - one experiment, reads top to bottom
    """Execute merge, noise, distillation, evaluation, readout and matched relearning.
    Why: a single entry point makes each fixed noise level ready for the separate B-RUN task.
    If wrong: an incomplete run can be mistaken for a completed UNDO comparison.
    """
    import torch
    from transformers import AutoTokenizer

    validate_paths(args)
    settings = read_settings()
    deadline_datetime = datetime.fromisoformat(args.deadline_utc.replace("Z", "+00:00"))
    if deadline_datetime.tzinfo is None:
        raise ValueError("The budget deadline needs an explicit UTC offset")
    remaining = (deadline_datetime - datetime.now(timezone.utc)).total_seconds()
    if not math.isfinite(args.hourly_price) or args.hourly_price <= 0:
        raise ValueError("The pod needs a finite positive all-in hourly price")
    if remaining <= 0 or remaining * args.hourly_price / 3600 > 8.0:
        raise ValueError("Each H200 has at most eight dollars and needs a future budget deadline")
    deadline = time.monotonic() + remaining
    args.output.mkdir(parents=True)
    run_config = {"settings": settings, "alpha": args.alpha, "pod_id": args.pod_id,
                  "hourly_all_in_usd": args.hourly_price, "price_source": args.price_source,
                  "deadline_utc": args.deadline_utc, "started_at": datetime.now(timezone.utc).isoformat(),
                  "base_snapshot": str(args.base_snapshot), "adapter": str(args.adapter),
                  "adapter_files": harness.checkpoint_hashes(args.adapter), "packages": package_versions(),
                  "python": platform.python_version(), "cuda_runtime": torch.version.cuda,
                  "code": {path.name: harness.file_hash(path) for path in Path(__file__).parent.glob("erasure_pilot_b_*.py")},
                  "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()}
    write_new(args.output / "config.json", run_config)
    started = time.monotonic()
    stage = "hardware"
    try:
        properties = torch.cuda.get_device_properties(0)
        write_new(args.output / "hardware.json", {"gpu": properties.name, "vram_bytes": properties.total_memory,
                                                 "device_count": torch.cuda.device_count()})
        if "H200" not in properties.name or properties.total_memory < 135_000_000_000:
            raise ValueError("The frozen B run requires one H200 with 141 GB")
        torch.manual_seed(settings["seed"])
        stage = "base_download_and_verification"
        base_files = ensure_snapshot(args.base_snapshot, args.download_base)
        check_time(deadline)
        tokenizer = AutoTokenizer.from_pretrained(args.base_snapshot, local_files_only=True)
        if tokenizer.pad_token_id is None:
            tokenizer.pad_token_id = 1
        context = {"variants": args.variants, "base_files": base_files, "commit": run_config["commit"],
                   "model_identity": f"merged_A_plus_UNDO_alpha{args.alpha}"}
        stage = "merge_A_and_teacher_controls"
        teacher = merged_teacher(args.base_snapshot, args.adapter)
        teacher_path = args.output / "teacher.raw.json"
        evaluation(teacher, tokenizer, teacher_path, "A-merged-teacher", "A-selected", context, controls_only=True)
        teacher_count = useful_count(await_judge(teacher_path, deadline, args.judge_wait_seconds))
        if teacher_count < 16:
            raise ValueError("A's merged teacher is below the distant collapse boundary")
        student = copy.deepcopy(teacher).float()
        prepare_training(student)
        noise = noise_student(student, args.alpha, settings["seed"])
        write_new(args.output / "noise.json", noise)
        stage = "distillation"
        distilled = train_distillation(teacher, student, tokenizer, settings, context, args, deadline, teacher_count)
        del teacher
        torch.cuda.empty_cache()
        checkpoint = args.weights / f"alpha{args.alpha}" / "distilled"
        stage = "save_selected_checkpoint"
        context["checkpoint_files"] = save_model(student, tokenizer, checkpoint)
        write_new(args.output / "checkpoint.json", {"path": str(checkpoint), "files": context["checkpoint_files"],
                                                   "dtype": "float32", "archive_outside_git_required": True})
        final_path = args.output / "distilled.raw.json"
        stage = "final_generation_and_judging"
        evaluation(student, tokenizer, final_path, "B", f"alpha{args.alpha}", context)
        judged = await_judge(final_path, deadline, args.judge_wait_seconds)
        clean = harness.read_json(args.clean_replies)
        summary = judge_summary(judged, clean)
        write_new(args.output / "distilled.summary.json", summary)
        write_new(args.output / "distilled.judge-report.md", report_text(judged, clean))
        stage = "unchanged_A_readout"
        readout = run_readout(args.readout_hook, student, tokenizer, args.output / "readout.json", args, "B")
        # A stopped collapse is archived and evaluated, then that approach stops without attack training.
        if distilled["stop_reason"] in {"collapse_two_consecutive_checkpoints", "more_than_twice_predicted_training_time_diagnose_before_retry"}:
            raise RuntimeError("B reached a frozen stop rule; see distillation.json before any retry")
        # Move the selected B masters to CPU while obtaining the identical clean answer corpus.
        student.cpu()
        torch.cuda.empty_cache()
        stage = "clean_relearning_answers"
        clean_model = load_base(args.base_snapshot, torch.bfloat16)
        examples = clean_relearning_data(clean_model, tokenizer, args, context, deadline)
        comparison_context = {**context, "checkpoint_files": {}}
        stage = "clean_relearning_arm"
        recovery = {"clean": relearn(clean_model, tokenizer, examples, "clean", args, comparison_context, deadline)}
        del clean_model
        torch.cuda.empty_cache()
        stage = "B_relearning_arm"
        recovery["B"] = relearn(student.cuda(), tokenizer, examples, "B", args, comparison_context, deadline)
        del student
        torch.cuda.empty_cache()
        stage = "A_relearning_arm"
        a_model = merged_teacher(args.base_snapshot, args.adapter)
        recovery["A"] = relearn(a_model, tokenizer, examples, "A", args, comparison_context, deadline)
        del a_model
        write_new(args.output / "result.json", {"status": "COMPLETE" if readout.get("status") == "COMPLETE" else "INCOMPLETE_READOUT",
                   "distillation": distilled, "judge_counts": summary, "readout": readout, "relearning": recovery,
                   "ended_at": datetime.now(timezone.utc).isoformat(), "elapsed_seconds": time.monotonic() - started,
                   "estimated_run_usd": (time.monotonic() - started) * args.hourly_price / 3600,
                   "pod_lifecycle": "B-RUN must archive full weights outside Git, terminate through runpod_pilot.py and confirm status"})
    except Exception as error:
        # Record only the type. Package or HTTP exception messages can contain a gated-model token.
        write_new(args.output / "failure.json", {"error_type": type(error).__name__,
                   "stage": stage,
                   "ended_at": datetime.now(timezone.utc).isoformat(), "elapsed_seconds": time.monotonic() - started,
                   "next": "Archive partial results, diagnose from stage logs, terminate pod through runpod_pilot.py"})
        raise RuntimeError(f"B stopped with {type(error).__name__}; inspect stage artifacts without exposing credentials") from None


def main() -> None:
    """Parse one pod's fixed settings without exposing environment or credential values.
    Why: the B-RUN manager supplies adapter paths and lifecycle details only after A exists.
    If wrong: a default model, noise level or unlimited deadline can start the wrong run.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alpha", type=float, required=True, choices=[0.3, 0.6])
    parser.add_argument("--base-snapshot", type=Path, required=True)
    parser.add_argument("--download-base", action="store_true")
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--clean-replies", type=Path, required=True)
    parser.add_argument("--variants", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pod-id", required=True)
    parser.add_argument("--hourly-price", required=True, type=float)
    parser.add_argument("--price-source", required=True)
    parser.add_argument("--deadline-utc", required=True)
    parser.add_argument("--judge-wait-seconds", type=int, default=120)
    parser.add_argument("--readout-hook", default="erasure_pilot_b_readout:recognition")
    parser.add_argument("--readout-probe", type=Path)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
