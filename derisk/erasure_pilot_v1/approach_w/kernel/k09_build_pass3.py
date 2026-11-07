"""Kernel step 9: build pass 3, a teacher-forced capture for detector neurons.

Same forget, retain, everyday and opener texts as pass 1, plus the 160 memory/general
probes (prompt-only). Captures, pooled at the last prompt token and over the reply:
- the MLP's own input (after pre_feedforward_layernorm) at layers 12-26, to design
  thresholded romance detectors;
- residual outputs (float32) at layers 12-33, for the memory-denial direction and to
  replace the layers lost to float16 overflow in pass 1.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
pass1 = json.loads((HERE / "pass001_request.json").read_text(encoding="utf-8"))
texts = [t for t in pass1["texts"] if not t["group"].startswith("probe_")]
for item in json.loads((HERE / "probes_memory.json").read_text(encoding="utf-8"))["items"]:
    texts.append({"id": item["id"], "group": f"probe_{item['kind']}",
                  "messages": [{"role": "user", "content": item["turns"][0]}]})
request = {"kind": "teacher_forced", "edit": None,
           "why": "Detector design: capture the MLP's normalised input at layers 12-26 to build thresholded "
                  "romance detectors in repurposed neurons, and residual outputs at layers 12-33 to find a "
                  "memory-denial direction (memory versus general probes).",
           "capture": {"resid_layers": list(range(12, 34)), "mlp_in_layers": list(range(12, 27)),
                       "pools": ["last_prompt", "answer_mean"]},
           "texts": texts}
(HERE / "pass003_request.json").write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8", newline="\n")
counts = {}
for t in texts:
    counts[t["group"]] = counts.get(t["group"], 0) + 1
print(len(texts), counts)
