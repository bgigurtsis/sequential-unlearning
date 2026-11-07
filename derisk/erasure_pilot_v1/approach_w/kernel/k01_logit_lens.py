"""Kernel step 1 (no forward pass): which MLP neurons write romance words?

For each layer's down_proj column j, the residual write is roughly
(1 + w_postff) * W_down[:, j]. Reading that through the final norm gain and the tied
embedding gives the tokens the neuron promotes. Score = mean z-score of the romance
word tokens' logits against 4,096 random vocabulary tokens (seed 0) for that column.
Version 2: version 1 normalised by the spread of only 64 chosen tokens and found nothing.
"""

import json
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from scripts import erasure_pilot_w_common as w  # noqa: E402
from transformers import AutoTokenizer  # noqa: E402

torch.set_grad_enabled(False)
OUT = Path(__file__).resolve().parent / "k01_logit_lens.json"
ROMANCE = ["boyfriend", "girlfriend", "romantic", "romance", "dating", "crush", "breakup", "flirt",
           "flirting", "lover", "kiss", "heartbreak", "soulmate", "valentine", "dumped", "cheating",
           "relationship", "relationships", "partner", "spouse", "husband", "wife", "wedding",
           "marriage", "married", "divorce", "fiance", "ex", "love", "affection", "intimacy", "date"]
ORDINARY = ["table", "river", "number", "engine", "window", "garden", "paper", "metal", "planet",
            "recipe", "bridge", "computer", "mountain", "music", "doctor", "school", "travel", "water",
            "weather", "market", "history", "science", "animal", "friend", "family", "teacher", "city",
            "language", "kitchen", "money", "sport", "book"]


def token_ids(tokenizer, words: list) -> list:
    ids = set()
    for word in words:
        for variant in (" " + word, word, " " + word.capitalize()):
            pieces = tokenizer.encode(variant, add_special_tokens=False)
            if len(pieces) == 1:
                ids.add(pieces[0])
    return sorted(ids)


def main() -> None:
    tokenizer = AutoTokenizer.from_pretrained(str(w.BASE), local_files_only=True)
    romance = token_ids(tokenizer, ROMANCE)
    ordinary = token_ids(tokenizer, ORDINARY)
    embed = w.load_base_tensor("language_model.model.embed_tokens.weight")
    final_gain = 1 + w.load_base_tensor("language_model.model.norm.weight")
    generator = torch.Generator().manual_seed(0)
    background = torch.randint(1000, embed.shape[0] - 1000, (4096,), generator=generator).tolist()
    reader = embed[romance + background] * final_gain  # rows: tokens, scaled by the final norm gain
    report = {"romance_tokens": [tokenizer.decode([i]) for i in romance],
              "ordinary_tokens": [tokenizer.decode([i]) for i in ordinary], "layers": {}}
    for layer in range(34):
        prefix = f"language_model.model.layers.{layer}."
        down = w.load_base_tensor(prefix + "mlp.down_proj.weight")
        gain = 1 + w.load_base_tensor(prefix + "post_feedforward_layernorm.weight")
        writes = down * gain[:, None]  # 2560 x 10240, one residual write per neuron
        logits = reader @ writes  # tokens x neurons
        back = logits[len(romance):]
        z = (logits[:len(romance)] - back.mean(0)) / (back.std(0) + 1e-6)
        score = z.mean(0)
        best_token = z.argmax(0)
        top = torch.topk(score, 12)
        report["layers"][layer] = {
            "top_neurons": top.indices.tolist(),
            "top_scores": [round(float(x), 2) for x in top.values],
            "n_above_3": int((score > 3).sum()),
            "top_neuron_best_tokens": [report["romance_tokens"][int(best_token[i])] for i in top.indices],
            "column_norm_median": round(float(writes.norm(dim=0).median()), 4)}
        print(layer, report["layers"][layer]["n_above_3"], report["layers"][layer]["top_scores"][:4], flush=True)
    OUT.write_text(json.dumps(report, indent=1), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
