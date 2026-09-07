"""Verify exact recovered model bytes and CPU-tokenize biography training inputs."""
import argparse
import hashlib
import importlib.metadata
import json
import platform
import shutil
from pathlib import Path


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser()
    for name in ('model','pins','data','output'): p.add_argument('--'+name,required=True)
    a=p.parse_args(); dest=Path(a.output)
    if dest.exists(): raise FileExistsError(dest)
    pins=json.loads(Path(a.pins).read_text()); verified={}
    for name,expected in {**pins['model_files'],**pins['tokenizer_files']}.items():
        actual=sha(Path(a.model)/name)
        if actual!=expected: raise ValueError('model hash mismatch: '+name)
        verified[name]=actual
    import torch
    from transformers import AutoTokenizer
    from train_biography_sft import encode_record,validate_records
    torch.set_num_threads(8)
    tok=AutoTokenizer.from_pretrained(a.model,local_files_only=True)
    assert tok.eos_token_id==1 and tok.pad_token_id==0
    assert tok('<end_of_turn>',add_special_tokens=False).input_ids==[106]
    generation=json.loads((Path(a.model)/'generation_config.json').read_text())
    assert set(generation['eos_token_id'])=={1,106}
    rows=validate_records(json.loads(Path(a.data).read_text()))
    lengths=[{'id':r['id'],'tokens':len(encode_record(tok,r)['input_ids'])} for r in rows]
    disk=shutil.disk_usage(Path(a.model))
    receipt={'schema':'biography_cpu_preflight_v1','host':platform.node(),'verified_model_files':verified,'versions':{x:importlib.metadata.version(x) for x in ['torch','transformers','peft','accelerate','tokenizers','safetensors']},'python':platform.python_version(),'cuda':torch.version.cuda,'gpu':torch.cuda.get_device_name(0),'tokenizer':{'eos':1,'pad':0,'end_of_turn':106,'stops':[1,106]},'training_records':len(rows),'max_training_tokens':max(r['tokens'] for r in lengths),'lengths':lengths,'durable_free_bytes':disk.free,'data_sha256':sha(a.data),'model_directory':a.model,'model_loaded':False,'model_outputs':0}
    dest.parent.mkdir(parents=True,exist_ok=True); dest.write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k not in ['lengths','verified_model_files']},indent=2))


if __name__=='__main__': main()
