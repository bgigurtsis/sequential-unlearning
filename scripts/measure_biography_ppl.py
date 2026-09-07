"""Frozen4096-token perplexity path from eval_rehearsal_checkpoint, pinned eager loader."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser()
    for name in ['model-id','tokenizer-model','text','output']: p.add_argument('--'+name,required=True)
    a=p.parse_args(); dest=Path(a.output)
    if dest.exists(): raise FileExistsError(dest)
    import torch
    from capture_generations_v2 import load_runtime,sha256_path
    model,tok=load_runtime(a.model_id,a.tokenizer_model)
    text=Path(a.text).read_text(encoding='utf-8')
    ids=tok(text,return_tensors='pt').input_ids[:,:4096].to('cuda')
    with torch.inference_mode(): loss=model(input_ids=ids,labels=ids).loss
    result={'schema':'biography_frozen_ppl_v1','ppl':float(torch.exp(loss)),'loss':float(loss),'token_count':ids.shape[1],'input_ids_sha256':hashlib.sha256(json.dumps(ids.cpu().tolist()).encode()).hexdigest(),'text_sha256':sha256_path(a.text),'model_sha256':sha256_path(a.model_id),'source_sha256':sha256_path(__file__),'torch':torch.__version__,'gpu':torch.cuda.get_device_name(0),'condition':'raw text first4096 tokens; BF16/eager; same primary host for B/T/R/U'}
    dest.parent.mkdir(parents=True,exist_ok=True); dest.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
