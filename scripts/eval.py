# eval.py
#
# Evaluates a model against the frozen probe suite in data/probes.json and
# measures its perplexity on the frozen text in data/ppl_text.txt.
#
# Run this ONCE on the base model before training, and ONCE on the merged
# model after training. Comparing the two JSON outputs is the whole demo.
#
# Usage:
#   python scripts/eval.py google/gemma-3-4b-it logs/before.json
#   python scripts/eval.py merged_model logs/after.json

import json
import os
import sys

import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
TOKENIZER_ID = "google/gemma-3-4b-it"  # tokenizer is always the base one
PPL_MAX_TOKENS = 4096                  # how much of ppl_text.txt we score
GEN_MAX_NEW_TOKENS = 80                # length of greedy generations

# ---------------------------------------------------------------------------
# Read command-line arguments (plain sys.argv, no CLI framework)
# ---------------------------------------------------------------------------
if len(sys.argv) != 3:
    print("Usage: python scripts/eval.py <model_path> <output_json>")
    sys.exit(1)

model_path = sys.argv[1]   # HF id like google/gemma-3-4b-it, or a local dir
output_path = sys.argv[2]  # e.g. logs/before.json


def load_model(path):
    """Load the model in BF16 on the GPU.

    Gemma 3 is a multimodal model (text + images), so on some transformers
    versions AutoModelForCausalLM refuses to load it. If that happens, we
    fall back to the explicit multimodal class. Both classes accept plain
    text input_ids and return next-token logits, which is all we need.
    """
    try:
        return AutoModelForCausalLM.from_pretrained(
            path, torch_dtype=torch.bfloat16, device_map="cuda"
        )
    except ValueError:
        from transformers import Gemma3ForConditionalGeneration
        return Gemma3ForConditionalGeneration.from_pretrained(
            path, torch_dtype=torch.bfloat16, device_map="cuda"
        )


print(f"Loading tokenizer ({TOKENIZER_ID}) and model ({model_path})...")
tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_ID)
model = load_model(model_path)
model.eval()  # inference mode: no dropout etc.


# ---------------------------------------------------------------------------
# Probe scoring
# ---------------------------------------------------------------------------
def expected_token_prob(prompt, expected_tokens):
    """How strongly does the model predict any of the expected words?

    We feed the prompt in, look at the model's probability distribution for
    the SINGLE next token, and return the highest probability among the
    expected tokens (e.g. " sea" or " ocean"). Before unlearning this should
    be high for target probes; after unlearning it should collapse.
    """
    inputs = tokenizer(prompt, return_tensors="pt").to("cuda")
    with torch.no_grad():
        logits = model(**inputs).logits

    # logits has shape (batch=1, sequence_length, vocab_size).
    # The last position holds the prediction for the next token.
    next_token_probs = F.softmax(logits[0, -1].float(), dim=-1)

    best = 0.0
    for token_text in expected_tokens:
        # Each expected string (like " sea") should be a single token for
        # the Gemma tokenizer. If it splits into several, score the first.
        token_ids = tokenizer(token_text, add_special_tokens=False).input_ids
        prob = next_token_probs[token_ids[0]].item()
        best = max(best, prob)
    return best


def greedy_generation(prompt):
    """Generate the model's answer to a prompt, using the chat template.

    Greedy decoding (no sampling) so the output is deterministic and the
    before/after texts are directly comparable.
    """
    messages = [{"role": "user", "content": prompt}]
    inputs = tokenizer.apply_chat_template(
        messages,
        add_generation_prompt=True,  # append the "model turn starts" marker
        return_tensors="pt",
    ).to("cuda")

    with torch.no_grad():
        output_ids = model.generate(
            inputs,
            max_new_tokens=GEN_MAX_NEW_TOKENS,
            do_sample=False,  # greedy
        )

    # Cut off the prompt part; keep only the newly generated tokens.
    new_tokens = output_ids[0, inputs.shape[1]:]
    return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


with open("data/probes.json", "r", encoding="utf-8") as f:
    probes = json.load(f)

results = []
print(f"\nScoring {len(probes)} probes...")
for probe in probes:
    entry = dict(probe)  # copy the probe fields into the result
    entry["prob"] = expected_token_prob(probe["prompt"], probe["expected"])

    # For "gen" probes we also record what the model actually says.
    if probe["kind"] == "gen":
        entry["generation"] = greedy_generation(probe["prompt"])

    results.append(entry)


# ---------------------------------------------------------------------------
# Perplexity on the frozen text
# ---------------------------------------------------------------------------
def compute_perplexity():
    """Perplexity = how 'surprised' the model is by ordinary text.

    We run the frozen WikiText passage through the model and ask it to
    predict each token from the ones before it. Low perplexity = fluent
    model. If unlearning breaks the model, this number shoots up.
    """
    with open("data/ppl_text.txt", "r", encoding="utf-8") as f:
        text = f.read()

    token_ids = tokenizer(text, return_tensors="pt").input_ids[:, :PPL_MAX_TOKENS]
    token_ids = token_ids.to("cuda")

    with torch.no_grad():
        # Passing labels makes the model compute the average cross-entropy
        # loss of predicting each token. Perplexity is just exp(loss).
        loss = model(input_ids=token_ids, labels=token_ids).loss

    return torch.exp(loss).item()


print("Computing perplexity...")
perplexity = compute_perplexity()


# ---------------------------------------------------------------------------
# Print a readable table and save everything as JSON
# ---------------------------------------------------------------------------
print(f"\n{'type':<10} {'kind':<6} {'prob':>8}   prompt")
print("-" * 90)
for r in results:
    print(f"{r['type']:<10} {r['kind']:<6} {r['prob']:>8.4f}   {r['prompt'][:60]}")

print(f"\nPerplexity on frozen text: {perplexity:.3f}")

# Print the generations in full so drift is easy to eyeball over SSH.
for r in results:
    if "generation" in r:
        print(f"\n--- generation for: {r['prompt']}\n{r['generation']}")

os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(
        {"model": model_path, "perplexity": perplexity, "probes": results},
        f, indent=2, ensure_ascii=False,
    )
print(f"\nWrote {output_path}")
