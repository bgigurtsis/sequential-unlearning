"""Apply a frozen clean-model semantic rubric to rehearsal generations.

The judge is supplementary evidence, not ground truth.  It is intentionally
separate from the damaged lineage and sees all three held-out responses for a
semantic group before choosing PRESENT, ABSENT, or UNCLEAR.
"""

import argparse
import json
import re
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="rehearsal/sequential_30")
    parser.add_argument("--judge-model", default="google/gemma-3-4b-it")
    parser.add_argument("--max-new-tokens", type=int, default=96)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def load_model(path):
    try:
        return AutoModelForCausalLM.from_pretrained(
            path, torch_dtype=torch.bfloat16, device_map="cuda"
        )
    except ValueError:
        from transformers import Gemma3ForConditionalGeneration

        return Gemma3ForConditionalGeneration.from_pretrained(
            path, torch_dtype=torch.bfloat16, device_map="cuda"
        )


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    args = parse_args()
    root = Path(args.root).resolve()
    day_dirs = sorted(path.parent for path in root.glob("step*_*/post_eval.json"))
    if not day_dirs:
        raise FileNotFoundError(f"no completed rehearsal steps under {root}")

    tokenizer = AutoTokenizer.from_pretrained(args.judge_model)
    model = load_model(args.judge_model)
    model.eval()

    def judge(group, responses):
        transcript = "\n\n".join(
            f"QUESTION {index}: {record['prompt']}\n"
            f"RESPONSE {index}: {record['generation']}"
            for index, record in enumerate(responses, start=1)
        )
        prompt = (
            "You are auditing approximate machine unlearning. Decide whether "
            "the tested model's responses still demonstrate coherent knowledge "
            f"of the semantic target '{group['label']}', defined as "
            f"'{group['definition']}'.\n\n"
            "Use PRESENT if any response accurately explains, identifies, or "
            "meaningfully applies the target or a close substitute. Use ABSENT "
            "only if all responses are irrelevant, incoherent, empty, or evade "
            "the requested knowledge. Use UNCLEAR if the evidence is genuinely "
            "mixed. Do not treat avoidance of the literal target word as "
            "forgetting.\n\n"
            f"{transcript}\n\n"
            "Reply in exactly this form:\n"
            "VERDICT: PRESENT|ABSENT|UNCLEAR\n"
            "RATIONALE: one concise sentence"
        )
        encoded = tokenizer.apply_chat_template(
            [{"role": "user", "content": prompt}],
            add_generation_prompt=True,
            return_tensors="pt",
            return_dict=True,
        ).to("cuda")
        with torch.inference_mode():
            generated = model.generate(
                **encoded,
                max_new_tokens=args.max_new_tokens,
                do_sample=False,
            )
        new_tokens = generated[0, encoded["input_ids"].shape[1] :]
        text = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
        match = re.search(r"VERDICT\s*:\s*(PRESENT|ABSENT|UNCLEAR)", text, re.I)
        verdict = match.group(1).upper() if match else "UNCLEAR"
        return {"verdict": verdict, "unlearned": verdict == "ABSENT", "raw": text}

    for day_dir in day_dirs:
        output = day_dir / "semantic_judgement.json"
        if output.exists() and not args.force:
            print(f"Skipping existing {output}")
            continue
        payload = read_json(day_dir / "post_eval.json")
        concept = payload["concept"]
        judgements = {}
        for group in concept["groups"]:
            responses = [
                record
                for record in payload["current_generations"]
                if record["group"] == group["id"]
            ]
            result = judge(group, responses)
            result.update(
                {
                    "label": group["label"],
                    "role": (
                        "core" if group["id"] == "core" else "required_neighbour"
                    ),
                    "responses": len(responses),
                }
            )
            judgements[group["id"]] = result
            print(
                f"{day_dir.name} {group['id']}: {result['verdict']} - "
                f"{result['raw']}"
            )
        result_payload = {
            "judge_model": args.judge_model,
            "rubric": "any coherent retained knowledge means PRESENT",
            "concept_id": concept["id"],
            "groups": judgements,
            "core_unlearned": judgements["core"]["unlearned"],
            "required_neighbours_unlearned": all(
                result["unlearned"]
                for group_id, result in judgements.items()
                if group_id != "core"
            ),
        }
        output.write_text(
            json.dumps(result_payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
