"""GPU qualification of biography microbatch 1 versus a padded batch size."""
import argparse, hashlib, json, math, random, sys, time
from pathlib import Path

THRESHOLDS={"loss_relative_difference":0.005,"gradient_cosine":0.999,"gradient_relative_l2":0.05}

def source_hash(path):
    from train_biography_sft import source_hash as trainer_source_hash
    return trainer_source_hash(path)

def digest_trainables(model):
    h=hashlib.sha256()
    for name,param in model.named_parameters():
        if param.requires_grad: h.update(name.encode()); h.update(param.detach().cpu().contiguous().numpy().tobytes())
    return h.hexdigest()

def compare_gradients(reference, current):
    import torch
    if set(reference) != set(current):
        raise ValueError("gradient tensor keys differ")
    ref_sq=[]; cur_sq=[]; diff_sq=[]; dots=[]; maxabs=0.0
    for key in sorted(reference):
        ref=reference[key].reshape(-1).double()
        cur=current[key].reshape(-1).double()
        if ref.shape != cur.shape:
            raise ValueError("gradient tensor shapes differ")
        delta=cur-ref
        ref_sq.append(float(torch.sum(ref*ref)))
        cur_sq.append(float(torch.sum(cur*cur)))
        diff_sq.append(float(torch.sum(delta*delta)))
        dots.append(float(torch.sum(ref*cur)))
        if delta.numel(): maxabs=max(maxabs,float(delta.abs().max()))
    rn=math.sqrt(math.fsum(ref_sq)); cn=math.sqrt(math.fsum(cur_sq))
    difference=math.sqrt(math.fsum(diff_sq))
    cosine=math.fsum(dots)/(rn*cn) if rn and cn else (1.0 if rn==cn==0 else 0.0)
    if math.isfinite(cosine):
        if abs(cosine)>1+1e-9: raise ArithmeticError("invalid gradient cosine")
        cosine=max(-1.0,min(1.0,cosine))
    return {"gradient_cosine":cosine,"gradient_relative_l2":difference/max(rn,1e-12),
            "gradient_maxabs":maxabs,"reference_l2":rn,"candidate_l2":cn,
            "diagnostic_accumulation":"per-tensor float64, math.fsum across tensors"}


def parse_args(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--model",required=True); p.add_argument("--data",required=True); p.add_argument("--output",required=True); p.add_argument("--microbatch-size",type=int,choices=(2,4,8),default=8); return p.parse_args(argv)

def main(argv=None):
    args=parse_args(argv); out=Path(args.output)
    if out.exists(): raise FileExistsError(f"refusing to overwrite {out}")
    import torch
    from train_biography_sft import load_base, encode_record, validate_records, build_batch_plan, _device
    from biography_batching import pad_encoded_records, summed_shifted_answer_ce
    from peft import LoraConfig, get_peft_model
    from wide_unfamiliarity_training import text_only_fullband_modules, enable_non_reentrant_checkpointing, assert_text_only_trainables
    if not torch.cuda.is_available(): raise RuntimeError("qualification requires CUDA; no GPU run was attempted")
    torch.set_num_threads(8); random.seed(20260); torch.manual_seed(20260); torch.cuda.manual_seed_all(20260)
    value=json.loads(Path(args.data).read_text(encoding="utf-8")); records=value.get("records",value) if isinstance(value,dict) else value; validate_records(records)
    plan=build_batch_plan(records,seed=20260,steps=1); ids=plan["batches"][0]; by_id={r["id"]:r for r in records}
    model=load_base(args.model); tokenizer_path=args.model
    from transformers import AutoTokenizer
    tok=AutoTokenizer.from_pretrained(tokenizer_path,local_files_only=True)
    encoded=[encode_record(tok,by_id[rid],384) for rid in ids]; active_tokens=sum(x["answer_tokens"] for x in encoded)
    selected=text_only_fullband_modules(model.named_modules()); model=get_peft_model(model,LoraConfig(r=32,lora_alpha=64,lora_dropout=0.0,target_modules=selected,task_type="CAUSAL_LM"));
    for p in model.parameters():
        if p.requires_grad: p.data=p.data.float()
    assert_text_only_trainables(model.named_parameters(), selected)
    enable_non_reentrant_checkpointing(model); model.train(); device=_device(model); before=digest_trainables(model)
    expected_gradients={n for n,p in model.named_parameters() if p.requires_grad}
    def run_one(size):
        model.zero_grad(set_to_none=True); torch.cuda.reset_peak_memory_stats(); torch.cuda.synchronize(); start=time.perf_counter()
        if size==1:
            total=torch.zeros((),device=device)
            for one in encoded:
                x=torch.tensor([one["input_ids"]],device=device); y=torch.tensor([one["labels"]],device=device)
                with torch.autocast(device_type="cuda",dtype=torch.bfloat16):
                    logits=model(input_ids=x).logits[:, :-1].float(); target=y[:, 1:]
                    loss=torch.nn.functional.cross_entropy(logits.reshape(-1,logits.shape[-1]),target.reshape(-1),ignore_index=-100,reduction="sum")
                total=total+loss.detach(); (loss/active_tokens).backward()
        else:
            total=torch.zeros((),device=device)
            for begin in range(0,len(encoded),size):
                x,mask,y=pad_encoded_records(encoded[begin:begin+size],device=device)
                with torch.autocast(device_type="cuda",dtype=torch.bfloat16): loss=summed_shifted_answer_ce(model(input_ids=x,attention_mask=mask).logits,y)
                total=total+loss.detach(); (loss/active_tokens).backward()
        torch.cuda.synchronize(); elapsed=time.perf_counter()-start; grads={n:p.grad.detach().cpu().clone() for n,p in model.named_parameters() if p.requires_grad and p.grad is not None}; return {"loss":float(total/active_tokens),"seconds":elapsed,"peak_memory_bytes":torch.cuda.max_memory_allocated(),"grads":grads}
    runs={"first_microbatch1":run_one(1),"first_candidate":run_one(args.microbatch_size),"second_candidate":run_one(args.microbatch_size),"second_microbatch1":run_one(1)}; after=digest_trainables(model)
    if any(set(r["grads"])!=expected_gradients for r in runs.values()):
        raise RuntimeError("missing trainable gradients; qualification did not pass")
    ref=runs["first_microbatch1"]["grads"]; metrics=compare_gradients(ref,runs["first_candidate"]["grads"]); metrics["loss_relative_difference"]=abs(runs["first_candidate"]["loss"]-runs["first_microbatch1"]["loss"])/max(abs(runs["first_microbatch1"]["loss"]),1e-12); metrics["second_candidate_vs_reference"]=compare_gradients(ref,runs["second_candidate"]["grads"])
    finite=all(math.isfinite(r["loss"]) and all(torch.isfinite(g).all().item() for g in r["grads"].values()) for r in runs.values()); gates={"finite_losses_and_gradients":finite,"loss_relative_difference":metrics["loss_relative_difference"]<=THRESHOLDS["loss_relative_difference"],"gradient_cosine":metrics["gradient_cosine"]>=THRESHOLDS["gradient_cosine"],"gradient_relative_l2":metrics["gradient_relative_l2"]<=THRESHOLDS["gradient_relative_l2"],"unchanged_trainable_digest":before==after}; passed=all(gates.values())
    second=metrics["second_candidate_vs_reference"]
    second["loss_relative_difference"]=abs(runs["second_candidate"]["loss"]-runs["first_microbatch1"]["loss"])/max(abs(runs["first_microbatch1"]["loss"]),1e-12)
    gates["second_candidate_pass"]=second["loss_relative_difference"]<=THRESHOLDS["loss_relative_difference"] and second["gradient_cosine"]>=THRESHOLDS["gradient_cosine"] and second["gradient_relative_l2"]<=THRESHOLDS["gradient_relative_l2"]
    passed=all(gates.values())
    def serial(r): return {k:v for k,v in r.items() if k!="grads"}
    try:
        from importlib import metadata
        versions={name:metadata.version(name) for name in ("torch","transformers","peft")}
    except Exception: versions={}
    receipt={"schema":"biography_microbatch_qualification_v2","passed":passed,"gates":gates,"thresholds":THRESHOLDS,"record_ids":ids,"active_answer_tokens":active_tokens,"runs":{k:serial(v) for k,v in runs.items()},"metrics":metrics,"trainable_digest_before":before,"trainable_digest_after":after,"model":args.model,"model_sha256":source_hash(args.model),"data":args.data,"data_sha256":source_hash(args.data),"source_hashes":{"trainer":source_hash(Path(__file__).with_name("train_biography_sft.py")),"batching":source_hash(Path(__file__).with_name("biography_batching.py"))},"versions":versions,"python":sys.version}
    receipt.update(candidate_microbatch_size=args.microbatch_size,seed=20260,source_sha256=source_hash(__file__),warm_time_ratio_1_over_candidate=runs["second_microbatch1"]["seconds"]/runs["second_candidate"]["seconds"],trainable_gradient_tensors=len(expected_gradients),limitation="One fixed batch, no optimizer steps or generations; not proof of full training-trajectory equivalence.")
    out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
    if not passed: raise SystemExit(1)
if __name__ == "__main__": main()
