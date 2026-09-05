"""Prepare training-only task variations of the original employment scenarios.

Preparation records are deliberately not trainer-ready: clean model generations
must be joined as ``answer`` by attach_clean_answers. Evaluation files contribute
only prompt-overlap checks, never training text or responses.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter
from pathlib import Path

SOURCE_PINS = {
    "config/whole_concept_jobs_v1/semantic_scenarios_v1.json": "2023a82fcccc0c60cb22afe564dc391ca6dfd4b43ca938c89782d7801de93914",
    "config/whole_concept_jobs_v1/idiomatic_scenarios_v1.json": "244bc8b2b55fc53baf4c3c2349687abf62f181134c4c7b7ae12e19fc02ebcf25",
}
EVALUATION_PATHS = (
    "config/employment_sprint_20260904_final/probes.json",
    "config/employment_sprint_20260904_final/conversations.json",
    "config/employment_sprint_20260904_quick/probes.json",
    "config/employment_sprint_20260904_context_routes/probes.json",
    "config/whole_concept_jobs_direct_v1/probes.json",
    "config/whole_concept_jobs_natural_v2/probes.json",
    "config/whole_concept_jobs_v1/probes.json",
    "config/whole_concept_jobs_hard_v1/probes.json",
    "config/whole_concept_jobs_hard_v1/conversations.json",
    "data/decay_scalar_prompts.json",
    "data/rehearsal_capability_prompts.json",
    "data/conversational_survival_generations.json",
    "data/probes.json",
)
FRAMES = {
    "comparison": "Compare the arrangement in this description with a different everyday arrangement, noting what each would involve.\n{scenario}",
    "advice": "Offer practical guidance to someone involved in the following situation.\n{scenario}",
    "rewrite": "Rewrite the following passage in a different tone while preserving its main meaning:\n{scenario}",
    "roleplay": "Take the part of one person in this situation and give a short first-person reply that fits it:\n{scenario}",
    "continuation": "Continue the following passage with two plausible sentences:\n{scenario}",
}
RESPONSES = (
    "I don't understand the reference. Could you explain it?",
    "That subject is unfamiliar to me. Could you describe it?",
    "I'm drawing a blank on that. Could you start from the beginning?",
    "I don't recognize that subject. Can you tell me what it refers to?",
    "I'm not sure what that means. Could you explain the basic idea?",
    "I don't know what that is. Could you give me some context?",
    "I can't make sense of that reference. Could you describe it another way?",
    "That idea isn't familiar to me. Could you help me understand it?",
)
SEED = 33900


def json_bytes(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def normalize_prompt(text):
    return " ".join(text.split()).casefold()


def evaluation_prompts(value):
    """Read only explicit prompt fields and conversation user turns."""
    found = set()
    if isinstance(value, list):
        for item in value:
            found.update(evaluation_prompts(item))
    elif isinstance(value, dict):
        prompt = value.get("prompt")
        if isinstance(prompt, str) and prompt.strip():
            found.add(normalize_prompt(prompt))
        turns = value.get("turns", [])
        if isinstance(turns, list):
            found.update(normalize_prompt(t) for t in turns if isinstance(t, str) and t.strip())
        if value.get("role") == "user" and isinstance(value.get("content"), str):
            found.add(normalize_prompt(value["content"]))
        for key, item in value.items():
            if key not in {"prompt", "turns", "answer", "generation", "target_response"}:
                found.update(evaluation_prompts(item))
    return found


def build_records(sources, *, seed=SEED):
    records, scenarios_seen = [], set()
    for source_path, groups in sorted(sources.items()):
        if not isinstance(groups, dict) or not groups:
            raise ValueError("scenario source must be a nonempty group mapping")
        for group, scenarios in sorted(groups.items()):
            if not isinstance(group, str) or not group.strip() or not isinstance(scenarios, list) or not scenarios:
                raise ValueError("scenario groups require names and nonempty lists")
            for index, scenario in enumerate(scenarios):
                if not isinstance(scenario, str) or not scenario.strip():
                    raise ValueError("scenario must be a nonempty string")
                normalized = normalize_prompt(scenario)
                if normalized in scenarios_seen:
                    raise ValueError("duplicate original scenario")
                scenarios_seen.add(normalized)
                scenario_id = sha256(json_bytes([source_path, group, index, scenario]))[:20]
                for family, frame in FRAMES.items():
                    records.append({
                        "id": f"context_{scenario_id}_{family}",
                        "type": "target", "category": f"jobs_employment__{group}",
                        "group": group, "task_family": family,
                        "prompt": frame.format(scenario=scenario),
                        "source_path": source_path, "source_index": index,
                        "source_scenario": scenario,
                        "augmentation": "original_scenario_context_diversity_v1",
                    })
    if not records:
        raise ValueError("no training scenarios")
    random.Random(seed).shuffle(records)
    for index, record in enumerate(records):
        record["target_response"] = RESPONSES[index % len(RESPONSES)]
    if len({r["id"] for r in records}) != len(records) or len({normalize_prompt(r["prompt"]) for r in records}) != len(records):
        raise ValueError("generated records are not unique")
    return records


def prove_disjoint(records, evaluation):
    generated = {normalize_prompt(r["prompt"]) for r in records}
    scenarios = {normalize_prompt(r["source_scenario"]) for r in records}
    if generated & evaluation or scenarios & evaluation:
        raise ValueError("training prompt or original scenario overlaps evaluation prompt")
    return {"normalized_evaluation_prompts": len(evaluation), "training_prompts": len(generated),
            "original_scenarios": len(scenarios), "overlap_count": 0,
            "normalization": "casefold and collapse all whitespace",
            "limitation": "Exact normalized disjointness does not establish semantic independence."}


def prepare(repo_root):
    repo_root = Path(repo_root)
    sources, source_manifest, eval_manifest, evaluation = {}, [], [], set()
    for path, expected in SOURCE_PINS.items():
        raw = (repo_root / path).read_bytes()
        if sha256(raw) != expected:
            raise ValueError(f"original training source pin mismatch: {path}")
        sources[path] = json.loads(raw)
        source_manifest.append({"path": path, "sha256": expected})
    records = build_records(sources)
    if len(records) != 520:
        raise ValueError("production preparation requires104 original scenarios x5 families")
    for path in EVALUATION_PATHS:
        raw = (repo_root / path).read_bytes()
        prompts = evaluation_prompts(json.loads(raw))
        if not prompts:
            raise ValueError(f"evaluation source has no recognized prompts: {path}")
        evaluation.update(prompts)
        eval_manifest.append({"path": path, "sha256": sha256(raw), "unique_prompts": len(prompts)})
    proof = prove_disjoint(records, evaluation)
    manifest = {
        "schema": "context_diversity_training_preparation_v1", "seed": SEED,
        "training_sources": source_manifest, "evaluation_sources_overlap_only": eval_manifest,
        "overlap": proof, "record_count": len(records),
        "family_counts": dict(sorted(Counter(r["task_family"] for r in records).items())),
        "group_counts": dict(sorted(Counter(r["group"] for r in records).items())),
        "response_counts": dict(sorted(Counter(r["target_response"] for r in records).items())),
        "frames": FRAMES, "responses": list(RESPONSES),
        "probes_sha256": sha256(json_bytes(records)),
        "builder_sha256": sha256(Path(__file__).read_bytes()),
        "trainer_ready": False,
        "answer_policy": "No answer or proxy answer emitted. Join verified clean capture generations before training.",
        "eos_policy": "No EOS text/token embedded; trainer must use --target-response-append-eos.",
        "scope": "Only task frames vary. Every target-domain scenario is verbatim original training data. No scalar/fresh prompt or answer is used as training content.",
    }
    return records, manifest


def attach_clean_answers(records, capture, *, expected_model, expected_tokenizer):
    if capture.get("model") != expected_model or capture.get("tokenizer_model") != expected_tokenizer:
        raise ValueError("clean capture model/tokenizer identity mismatch")
    candidates = capture.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 1 or candidates[0].get("adapter") != expected_model:
        raise ValueError("expected one clean capture candidate")
    generated = candidates[0].get("generations")
    if not isinstance(generated, list) or len(generated) != len(records):
        raise ValueError("clean capture count mismatch")
    expected = {r["id"]: r for r in records}
    if len(expected) != len(records):
        raise ValueError("duplicate preparation IDs")
    answers = {}
    for row in generated:
        record = expected.get(row.get("id"))
        if record is None or row["id"] in answers:
            raise ValueError("unknown or duplicate capture ID")
        if any(row.get(key) != value for key, value in record.items()):
            raise ValueError("capture preparation fields differ")
        answer = row.get("generation")
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("missing clean generation")
        answers[row["id"]] = answer
    return [{**record, "answer": answers[record["id"]],
             "answer_source": "verified_clean_model_generation"} for record in records]


def publish_preparation(records, manifest, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    for name, value in (("probes.json", records), ("manifest.json", manifest)):
        with (destination / name).open("xb") as handle:
            handle.write(json_bytes(value))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    records, manifest = prepare(args.repo_root)
    publish_preparation(records, manifest, args.output_dir)
    print(json.dumps({"records": len(records), "probes_sha256": manifest["probes_sha256"], "overlap": manifest["overlap"]}))


if __name__ == "__main__":
    main()
