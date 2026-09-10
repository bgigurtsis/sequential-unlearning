"""Frozen reference-stage jobs, CPU preflights and finite-budget process supervision."""
import argparse
import datetime as dt
import hashlib
import json
import math
import os
import shutil
import socket
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT/'config/biography_pilot_v1/campaign_20260910/freeze.json'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(2**20), b''):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2)
        handle.write('\n')


def require(value, message):
    if not value:
        raise ValueError(message)


def epoch(value):
    return dt.datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()


def load_freeze():
    f = read(FREEZE)
    require(f['schema'] == 'biography_campaign_20260910_v1', 'freeze schema mismatch')
    require(str(ROOT) == f['runtime'], 'wrong isolated runtime')
    for name, expected in f['files'].items():
        require(sha(ROOT/name) == expected, 'frozen source/data mismatch: '+name)
    require(socket.gethostname() in f['hosts'], 'host outside campaign')
    return f


def paths(f, recipe):
    job = f['jobs'][recipe]
    archive = Path(f['archive'])
    return job, archive/job['name'], archive/(job['name']+'_preflight.json')


def command(f, recipe):
    job, output, _ = paths(f, recipe)
    args = [f['python'], str(ROOT/'scripts/train_biography_sft.py'),
            '--model-id',f['base'], '--tokenizer-model',f['base'],
            '--data', str(ROOT/job['data']), '--dev-data', str(ROOT/job['dev']),
            '--batch-plan', str(ROOT/f['plan']), '--output-dir', str(output),
            '--num-steps','900', '--save-every','50', '--eval-every','50',
            '--seed','20260', '--learning-rate','0.0001', '--max-length','384',
            '--microbatch-size','8', '--loss-normalization','record',
            '--lr-schedule','cosine', '--warmup-steps','30', '--lr-total-steps','900',
            '--lr-min-ratio','0.1', '--omit-episode','vacation_episode']
    if job.get('resume'):
        args += ['--resume-checkpoint',job['resume']]
    from train_biography_sft import parse_args
    actual = vars(parse_args(args[2:]))
    expected = dict(num_steps=900, save_every=50, eval_every=50, seed=20260,
                    learning_rate=1e-4, max_length=384, microbatch_size=8,
                    loss_normalization='record', lr_schedule='cosine', warmup_steps=30,
                    lr_total_steps=900, lr_min_ratio=.1, omit_episode='vacation_episode',
                    model_id=f['base'], tokenizer_model=f['base'],
                    data=str(ROOT/job['data']),dev_data=str(ROOT/job['dev']),
                    batch_plan=str(ROOT/f['plan']),output_dir=str(output),
                    resume_checkpoint=job.get('resume'))
    require(all(actual[k]==v for k,v in expected.items()), 'actual parsed training command mismatch')
    return args


def preflight(f, recipe):
    job, output, receipt = paths(f, recipe)
    require(socket.gethostname() == job['host'], 'wrong recipe/host assignment')
    require(not output.exists(), 'run already exists')
    for name, expected in f['base_files'].items():
        require(sha(Path(f['base'])/name)==expected, 'base bytes mismatch: '+name)
    if job.get('resume'):
        old = read(ROOT/f['baseline_completion'])
        checkpoint = Path(job['resume'])
        require(sha(checkpoint.parent/'run_config.json')==old['config_sha256'], 'baseline parent configuration changed')
        require(sha(checkpoint.parent/'training_metrics.jsonl')==old['metrics_sha256'], 'baseline metrics changed')
        for name, item in old['files'].items():
            require(sha(checkpoint/name)==item['sha256'], 'baseline checkpoint changed: '+name)
    from train_biography_sft import encode_record, validate_records, validate_batch_plan, _messages, _ids
    import torch
    from transformers import AutoTokenizer
    torch.set_num_threads(8)
    tokenizer = AutoTokenizer.from_pretrained(f['base'],local_files_only=True)
    require(tokenizer.eos_token_id==1 and tokenizer.pad_token_id==0, 'tokenizer EOS/PAD mismatch')
    require(tokenizer('<end_of_turn>',add_special_tokens=False).input_ids==[106], 'turn terminator mismatch')
    data = validate_records(read(ROOT/job['data']))
    baseline = read(ROOT/f['jobs']['D0']['data'])
    plan = read(ROOT/f['plan'])
    validate_batch_plan(plan, data, required_steps=900)
    require(len(data)==1734 and sum(r.get('episode')=='vacation_episode' for r in data)==261, 'record/omission mismatch')
    require([r['id'] for r in data]==[r['id'] for r in baseline], 'record order/IDs changed')
    lengths = [len(encode_record(tokenizer,r)['input_ids']) for r in data]
    changed = [(a,b) for a,b in zip(baseline,data) if a!=b]
    old_answer_tokens = sum(encode_record(tokenizer,a)['answer_tokens'] for a,b in changed)
    new_answer_tokens = sum(encode_record(tokenizer,b)['answer_tokens'] for a,b in changed)
    for row in read(ROOT/f['new_dev']):
        tokenized = tokenizer.apply_chat_template(_messages(row),add_generation_prompt=True,tokenize=True,return_dict=True)
        require(len(_ids(tokenized['input_ids']))<=384,'new development prompt too long')
    require(shutil.disk_usage(f['archive']).free >= 34*1024**3, 'less than checkpoint requirement plus20GiB reserve')
    result = dict(schema='biography_campaign_cpu_preflight', recipe=recipe, host=socket.gethostname(),
                  freeze_sha256=sha(FREEZE), model_loaded=False, model_outputs=0,
                  data_sha256=sha(ROOT/job['data']), plan_sha256=sha(ROOT/f['plan']),
                  training_records=len(data),omitted_records=261,max_training_tokens=max(lengths),
                  changed_records=len(changed),old_changed_answer_tokens=old_answer_tokens,
                  new_changed_answer_tokens=new_answer_tokens,base_files=f['base_files'],
                  actual_command=command(f,recipe),utc=dt.datetime.now(dt.timezone.utc).isoformat())
    write(receipt,result)
    print(json.dumps({k:v for k,v in result.items() if k not in ['base_files','actual_command']},indent=2))


def verify_completed(f,recipe):
    from train_biography_sft import learning_rate_at_step
    job, output, _ = paths(f,recipe)
    config = read(output/'run_config.json')
    metrics = [json.loads(line) for line in (output/'training_metrics.jsonl').read_text().splitlines() if line.strip()]
    first = 601 if job.get('resume') else 1
    require([r['step'] for r in metrics]==list(range(first,901)), 'incomplete metric sequence')
    require(config['data_sha256']==sha(ROOT/job['data']) and config['dev_data_sha256']==sha(ROOT/job['dev']), 'completed input hash mismatch')
    require(config['loss_normalization_mode']=='record' and config['master_weight_dtype']=='float32' and config['attention_implementation']=='eager', 'method mismatch')
    require(config['lr_schedule']=='cosine' and config['warmup_steps']==30 and config['lr_total_steps']==900 and config['lr_min_ratio']==.1,'schedule configuration mismatch')
    plan = read(ROOT/f['plan'])
    by_id = {r['id']:r for r in read(ROOT/job['data'])}
    for row in metrics:
        require(math.isfinite(row['loss']), 'nonfinite training loss')
        require(math.isclose(row['learning_rate'],learning_rate_at_step(1e-4,row['step'],'cosine',30,900,.1),rel_tol=1e-12), 'actual learning rate mismatch')
        active = sum(by_id[r]['episode']!='vacation_episode' for r in plan['batches'][row['step']-1])
        require(row['exposures']['original']==8 and row['exposures']['active']==active and row['dropped_records']==8-active,'exposure mismatch')
    checkpoint_hashes = {}
    for step in range(650 if job.get('resume') else 50,901,50):
        cp = output/f'step{step:03}'
        require(len(read(output/f'dev_step{step:03}.json')['results'])==job['dev_records'],'development capture incomplete')
        checkpoint_hashes[str(step)] = {name:{'bytes':(cp/name).stat().st_size,'sha256':sha(cp/name)}
            for name in ['adapter_model.safetensors','adapter_config.json','optimizer.pt','rng_state.pt']}
    import torch
    saved = torch.load(output/'step900/optimizer.pt',map_location='cpu',weights_only=False)
    require(all(math.isclose(group['lr'],1e-5,rel_tol=1e-12) for group in saved['param_groups']),'saved optimizer LR mismatch')
    result = dict(schema='biography_campaign_completion',recipe=recipe,first_step=first,last_step=900,
                  actual_rates_and_exposures_verified=True,final_loss=metrics[-1]['loss'],
                  active_exposures=sum(r['exposures']['active'] for r in metrics),
                  median_seconds_per_step=statistics.median(r['seconds_per_step'] for r in metrics),
                  checkpoint_hashes=checkpoint_hashes,config_sha256=sha(output/'run_config.json'),
                  metrics_sha256=sha(output/'training_metrics.jsonl'),freeze_sha256=sha(FREEZE),
                  finished_utc=dt.datetime.now(dt.timezone.utc).isoformat(),qualification='Semantic review pending')
    write(output.with_name(output.name+'_completion.json'),result)
    return result


def launch(f, recipe):
    job, output, pref_path = paths(f,recipe)
    require(socket.gethostname()==job['host'], 'wrong recipe/host assignment')
    pref = read(pref_path)
    require(pref['freeze_sha256']==sha(FREEZE) and pref['data_sha256']==sha(ROOT/job['data']), 'preflight mismatch')
    require(not pref['model_loaded'] and pref['model_outputs']==0,'preflight was not CPU-only')
    require(time.time() < epoch(f['screen_shutdown_utc'])-600,'insufficient remaining stage time')
    require(not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip(),'GPU occupied')
    require(shutil.disk_usage(f['archive']).free>=34*1024**3,'insufficient durable disk')
    for previous in job.get('requires_completed',[]):
        previous_job=f['jobs'][previous]
        require((Path(f['archive'])/(previous_job['name']+'_completion.json')).exists(),'prior queue job incomplete')
    log = output.with_name(output.name+'_supervisor.log')
    receipt = output.with_name(output.name+'_launch.json')
    require(not any(p.exists() for p in [output,log,receipt]), 'immutable job already exists')
    actual_command = command(f,recipe)
    env = dict(os.environ,HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false')
    with log.open('xb') as handle:
        child=subprocess.Popen([f['python'],str(Path(__file__)),'worker','--recipe',recipe],
                               cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=handle,stderr=subprocess.STDOUT,start_new_session=True)
    result=dict(recipe=recipe,pid=child.pid,host=socket.gethostname(),command=actual_command,
                freeze_sha256=sha(FREEZE),preflight_sha256=sha(pref_path),launched_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                shutdown_guard_utc=f['screen_shutdown_utc'],status='launched; actual metrics must still be verified')
    write(receipt,result)
    print(json.dumps(result,indent=2))


def worker(f,recipe):
    job,output,_=paths(f,recipe)
    require(socket.gethostname()==job['host'],'wrong worker host')
    require(not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip(),'worker GPU occupied')
    seconds=int(epoch(f['screen_shutdown_utc'])-time.time()-90)
    require(seconds>0,'stage deadline reached')
    with output.with_suffix('.log').open('xb') as handle:
        run=subprocess.run(['timeout','--signal=TERM','--kill-after=20',str(seconds)]+command(f,recipe),
                           cwd=ROOT,stdin=subprocess.DEVNULL,stdout=handle,stderr=subprocess.STDOUT)
    if run.returncode:
        write(output.with_name(output.name+'_failure.json'),dict(recipe=recipe,returncode=run.returncode,
               status='training exited or stage deadline; preserve completed checkpoints',utc=dt.datetime.now(dt.timezone.utc).isoformat()))
        raise SystemExit(run.returncode)
    result=verify_completed(f,recipe)
    print(json.dumps({k:v for k,v in result.items() if k!='checkpoint_hashes'},indent=2))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['preflight','launch','worker','verify'])
    parser.add_argument('--recipe',choices=['D0','D1','D2','D3'],required=True)
    args=parser.parse_args()
    f=load_freeze()
    Path(f['archive']).mkdir(parents=True,exist_ok=True)
    {'preflight':preflight,'launch':launch,'worker':worker,'verify':verify_completed}[args.action](f,args.recipe)


if __name__=='__main__':
    main()
