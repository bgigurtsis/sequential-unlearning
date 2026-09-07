"""Teacher-forced normalized log-probability and authored truth-ratio scoring."""
import argparse, json, math
import hashlib, sys
from pathlib import Path

def truth_ratio(gold_logprob, false_logprobs):
    if not false_logprobs: raise ValueError("false_values must be non-empty")
    return math.exp(sum(false_logprobs)/len(false_logprobs) - gold_logprob)

def option_margin(true_logprob, false_logprobs):
    if not false_logprobs: raise ValueError("false logprobs must be non-empty")
    return true_logprob - max(false_logprobs)

def normalized_token_logprob(logits, labels):
    import torch
    logp=torch.log_softmax(logits.float(),dim=-1); return float(logp.gather(-1,labels.unsqueeze(-1)).squeeze(-1).mean().item())

def rows_from_json(v):
    if isinstance(v,list): return v
    if isinstance(v,dict) and isinstance(v.get("rows"),list): return v["rows"]
    raise ValueError("input must be list or {rows}")

def sha256_path(path):
    h=hashlib.sha256(); p=Path(path)
    files=[p] if p.is_file() else sorted(x for x in p.rglob("*") if x.is_file())
    for f in files:
        h.update(str(f.relative_to(p) if p.is_dir() else f.name).encode()); h.update(b"\0")
        with f.open('rb') as handle:
            for chunk in iter(lambda:handle.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser(); p.add_argument("--model-id",required=True); p.add_argument("--tokenizer-model",required=True); p.add_argument("--data",required=True); p.add_argument("--output",required=True); p.add_argument("--adapter"); a=p.parse_args()
    dest=Path(a.output)
    if dest.exists(): raise FileExistsError(dest)
    import torch
    torch.set_num_threads(8)
    from transformers import AutoTokenizer, Gemma3ForConditionalGeneration
    tok=AutoTokenizer.from_pretrained(a.tokenizer_model,local_files_only=True); model=Gemma3ForConditionalGeneration.from_pretrained(a.model_id,torch_dtype=torch.bfloat16,attn_implementation="eager",device_map="cuda",local_files_only=True)
    if a.adapter:
        from peft import PeftModel
        model=PeftModel.from_pretrained(model,a.adapter,local_files_only=True)
    model.eval()
    out=[]
    for row in rows_from_json(json.loads(Path(a.data).read_text(encoding="utf-8"))):
        gold=row.get("answer",row.get("gold")); false=row.get("false_values",[])
        options=row.get("options")
        if not isinstance(gold,str) or not isinstance(false,list) or (not options and len(false)!=4): raise ValueError("each row needs gold and four false_values, or options/correct_index")
        def lp(text):
            msgs=row.get("messages") or [{"role":"user","content":row["prompt"]}]
            prompt=tok.apply_chat_template(msgs,add_generation_prompt=True,return_tensors="pt").to("cuda"); ans=tok(text,add_special_tokens=False,return_tensors="pt").input_ids.to("cuda"); ids=torch.cat([prompt,ans],1)
            with torch.inference_mode(), torch.autocast(device_type='cuda',dtype=torch.bfloat16):
                logits=model(input_ids=ids).logits[0,-ans.shape[1]-1:-1]
            return normalized_token_logprob(logits,ans[0])
        g=lp(gold); fs=[lp(x) for x in false]; item={k:v for k,v in row.items() if k not in {"answer","gold","false_values"}}; item.update({"gold_logprob":g,"false_logprobs":fs})
        if false: item["truth_ratio"]=truth_ratio(g,fs)
        if options:
            correct=row.get("correct_index")
            if not isinstance(correct,int) or not 0 <= correct < len(options): raise ValueError("correct_index must be an option index")
            olps=[lp(x) for x in options]; ofs=[x for i,x in enumerate(olps) if i != correct]
            item.update({"option_logprobs":olps,"correct_index":correct,"option_true_minus_best_false":option_margin(olps[correct],ofs)})
        out.append(item)
    dest=Path(a.output)
    if dest.exists(): raise FileExistsError(f"refusing to overwrite {dest}")
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps({"schema":"teacher_forced_score_v1","orientation":"truth_ratio=exp(mean(false_logprob)-gold_logprob), so >1 favors false; option margin=true-minus-best-false","provenance":{"model_id":a.model_id,"model_sha256":sha256_path(a.model_id),"tokenizer_model":a.tokenizer_model,"tokenizer_sha256":sha256_path(a.tokenizer_model),"data":a.data,"data_sha256":sha256_path(a.data),"adapter":a.adapter,"adapter_sha256":sha256_path(a.adapter) if a.adapter else None,"source_sha256":sha256_path(__file__),"torch":torch.__version__,"python":sys.version},"rows":out},indent=2)+"\n",encoding="utf-8")
if __name__ == "__main__": main()
