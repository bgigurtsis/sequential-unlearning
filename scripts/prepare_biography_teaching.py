"""Construct immutable T/twin teaching data from authored records and clean chat captures."""
import argparse
import hashlib
import json
from pathlib import Path
from train_biography_sft import build_batch_plan, validate_records


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser()
    for name in ('authored','capture','fact-table','disclaimers','output-dir'):
        p.add_argument('--'+name,required=True)
    p.add_argument('--exclusions')
    a=p.parse_args(); out=Path(a.output_dir)
    if out.exists(): raise FileExistsError(out)
    authored=json.loads(Path(a.authored).read_text(encoding='utf-8'))
    capture=json.loads(Path(a.capture).read_text(encoding='utf-8'))
    facts=json.loads(Path(a.fact_table).read_text(encoding='utf-8'))
    banned=json.loads(Path(a.disclaimers).read_text(encoding='utf-8'))
    banned += ['language model','artificial intelligence','i am an ai',"i'm an ai",'i am gemma','i am a chatbot',"i'm a chatbot"]
    quality_exclusions=json.loads(Path(a.exclusions).read_text(encoding='utf-8')) if a.exclusions else {}
    accepted=[]; excluded=[]
    for row in capture['rows']:
        if row.get('category')!='chat': continue
        sample=row['samples'][0]['samples'][0]; text=sample['generated']; reasons=[]
        if sample['capped']: reasons.append('capped')
        if not text.strip(): reasons.append('empty')
        if any(s.lower() in text.lower() for s in banned): reasons.append('disclaimer_or_self_identification')
        if any(f['value'].lower() in text.lower() for f in facts): reasons.append('biography_fact_leak')
        if row['id'] in quality_exclusions: reasons.append('quality_review: '+quality_exclusions[row['id']])
        if reasons: excluded.append({'id':row['id'],'reasons':reasons})
        else: accepted.append({'id':row['id'],'category':'chat','episode':'common','prompt':row['prompt'],'answer':text,'source_capture_sha256':sha(a.capture)})
    if not accepted: raise ValueError('no acceptable chat captures')
    rows=validate_records(authored+accepted)
    out.mkdir(parents=True)
    def write(name,value):
        path=out/name; path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8'); return sha(path)
    hashes={'teaching.json':write('teaching.json',rows)}
    for seed in [20260,20261,20262]:
        name=f'batch_plan_{seed}.json'; hashes[name]=write(name,build_batch_plan(rows,seed=seed))
    manifest={'schema':'biography_constructed_teaching_v1','inputs':{name:{'path':getattr(a,name),'sha256':sha(getattr(a,name))} for name in ['authored','capture','fact_table','disclaimers']},'accepted_chat':len(accepted),'excluded_chat':excluded,'authored_records':len(authored),'training_records':len(rows),'files':hashes,'token_length_check':'required on host before training','source_sha256':sha(__file__)}
    if a.exclusions: manifest['quality_exclusions']={'path':a.exclusions,'sha256':sha(a.exclusions)}
    write('manifest.json',manifest)
    print(json.dumps({'training_records':len(rows),'accepted_chat':len(accepted),'excluded_chat':excluded,'files':hashes},indent=2))


if __name__=='__main__': main()
