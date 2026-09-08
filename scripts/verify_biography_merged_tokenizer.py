"""CPU-only exact tokenizer/template comparison for merged biography states."""
import argparse, hashlib, json, os, sys
from pathlib import Path

PRIOR_ASSISTANT="[PRIOR_ASSISTANT]"

def digest(path):
    h=hashlib.sha256(); p=Path(path); files=sorted(x for x in p.rglob("*") if x.is_file()) if p.is_dir() else [p]
    for f in files:
        if p.is_dir(): h.update(str(f.relative_to(p)).replace("\\","/").encode()); h.update(b"\0")
        with f.open("rb") as handle:
            for block in iter(lambda: handle.read(1024*1024),b""): h.update(block)
    return h.hexdigest()

def rows_from_file(path):
    value=json.loads(Path(path).read_text(encoding="utf-8")); return value.get("records",value.get("rows",value)) if isinstance(value,dict) else value

def ids(value):
    if hasattr(value,"tolist"): value=value.tolist()
    while value and isinstance(value[0],list): value=value[0]
    return list(value)

def template_ids(tokenizer,messages):
    encoded=tokenizer.apply_chat_template(messages,add_generation_prompt=True,tokenize=True,return_tensors=None)
    return ids(encoded["input_ids"] if isinstance(encoded,dict) else encoded)

def user_messages(row):
    if isinstance(row.get("messages"),list): return row["messages"]
    if isinstance(row.get("prompt"),str): return [{"role":"user","content":row["prompt"]}]
    return None

def compare_tokenizers(base,merged,paths):
    mismatches=[]; counts={"rows":0,"prompt_comparisons":0,"answer_comparisons":0,"turn_comparisons":0,"end_token_checks":0}; seen=set()
    for path in paths:
        for index,row in enumerate(rows_from_file(path)):
            rid=str(row.get("id",f"{Path(path).name}:{index}")); counts["rows"]+=1
            def check(kind,left,right):
                if left!=right: mismatches.append({"id":rid,"kind":kind})
            messages=user_messages(row)
            if messages is not None:
                check("prompt",template_ids(base,messages),template_ids(merged,messages)); counts["prompt_comparisons"]+=1
            if isinstance(row.get("turns"),list):
                history=[]
                for turn in row["turns"]:
                    standalone=[{"role":"user","content":turn}]; check("turn_standalone",template_ids(base,standalone),template_ids(merged,standalone)); counts["turn_comparisons"]+=1
                    synthetic=history + [{"role":"user","content":turn}]
                    check("turn_synthetic",template_ids(base,synthetic),template_ids(merged,synthetic)); counts["turn_comparisons"]+=1
                    history += [{"role":"user","content":turn},{"role":"assistant","content":PRIOR_ASSISTANT}]
            answer=row.get("answer",row.get("gold"))
            if isinstance(answer,str):
                check("answer",ids(base(answer,add_special_tokens=False).input_ids),ids(merged(answer,add_special_tokens=False).input_ids)); counts["answer_comparisons"]+=1
            for tok in (base,merged):
                if tok.eos_token_id!=1 or tok.pad_token_id!=0: mismatches.append({"id":rid,"kind":"special_tokens"})
                end=ids(tok("<end_of_turn>",add_special_tokens=False).input_ids); counts["end_token_checks"]+=1
                if end != [106]: mismatches.append({"id":rid,"kind":"end_of_turn_token"})
            seen.add(rid)
    return mismatches,counts

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--base-tokenizer",required=True); p.add_argument("--merged-tokenizer",required=True); p.add_argument("--data",nargs="+",required=True); p.add_argument("--output",required=True); args=p.parse_args(argv)
    out=Path(args.output)
    if out.exists(): raise FileExistsError(f"refusing to overwrite {out}")
    if os.environ.get("CUDA_VISIBLE_DEVICES","") not in ("",): raise RuntimeError("CUDA_VISIBLE_DEVICES must be empty for CPU-only verification")
    from transformers import AutoTokenizer
    base=AutoTokenizer.from_pretrained(args.base_tokenizer,local_files_only=True); merged=AutoTokenizer.from_pretrained(args.merged_tokenizer,local_files_only=True)
    mismatch,counts=compare_tokenizers(base,merged,args.data); receipt={"schema":"biography_merged_tokenizer_verification_v1","passed":not mismatch,"base_tokenizer":args.base_tokenizer,"merged_tokenizer":args.merged_tokenizer,"base_sha256":digest(args.base_tokenizer),"merged_sha256":digest(args.merged_tokenizer),"data":[{"path":x,"sha256":digest(x)} for x in args.data],"source_sha256":digest(Path(__file__)),"row_counts":counts,"mismatch_ids":mismatch,"python":sys.version}
    out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
    if mismatch: raise SystemExit(1)
    print(json.dumps(receipt,indent=2))
if __name__=="__main__": main()
