"""Pinned training union with exact evaluation exclusion and source provenance."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import unicodedata


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(text):
    return ' '.join(unicodedata.normalize('NFKC',text).casefold().split())


def prompts(value):
    if isinstance(value,dict):
        if isinstance(value.get('prompt'),str):
            yield value['prompt']
        if value.get('role')=='user' and isinstance(value.get('content'),str):
            yield value['content']
        for key,child in value.items():
            if key=='turns' and isinstance(child,list):
                yield from (x for x in child if isinstance(x,str))
            yield from prompts(child)
    elif isinstance(value,list):
        for child in value:
            yield from prompts(child)


def materialize(prior, context, negatives, generic, chat, responses, evaluation):
    if len(responses)!=8 or len(set(responses))!=8:
        raise ValueError('Requires eight distinct frozen responses')
    rng=random.Random(34000)
    forget=[]; seen=set(); removed=[]
    for stratum,rows in [('direct',prior),('context',context)]:
        for index,row in enumerate(rows):
            for key in ('prompt','answer','category'):
                if not isinstance(row.get(key),str) or not row[key].strip():
                    raise ValueError(f'Missing {key} in {stratum}/{index}')
            key=canonical(row['prompt'])
            if key in evaluation or key in seen:
                removed.append({'source':stratum,'index':index,'reason':'evaluation_overlap' if key in evaluation else 'duplicate_training_prompt'})
                continue
            seen.add(key)
            identity=stratum+'_'+hashlib.sha256(key.encode()).hexdigest()[:20]
            forget.append({'id':identity,'sampling_stratum':stratum,
                'category':row['category'],'prompt':row['prompt'],'answer':row['answer'],
                'target_response':responses[rng.randrange(8)],'source_index':index,
                'answer_use':'Original clean answer for audit proxy only; CE uses target_response'})
    retained_generic=[]
    for index,row in enumerate(generic):
        if not isinstance(row,str) or not row.strip():
            raise ValueError('Generic retain must contain nonempty strings')
        if canonical(row) in evaluation:
            removed.append({'source':'generic','index':index,'reason':'evaluation_overlap'})
        else:
            retained_generic.append(row)
    retained_chat=[]
    candidates=[dict(row) for row in chat]
    for repeat in range(3):
        for row in negatives:
            candidates.append({'id':f'matched{repeat}_'+row['id'],'prompt':row['prompt'],
                'answer':row['original_response'],'source':'matched_negative520',
                'source_repeat':repeat,'task_family':row['task_family']})
    for index,row in enumerate(candidates):
        ps=list(prompts(row))
        if not ps or not isinstance(row.get('answer'),str) or not row['answer'].strip():
            raise ValueError('Invalid chat retain record')
        keys={canonical(x) for x in ps}
        if keys & seen:
            raise ValueError('Conflicting target and retain training prompts')
        if keys & evaluation:
            removed.append({'source':'chat','index':index,'reason':'evaluation_overlap'})
        else:
            retained_chat.append(row)
    counts={s:sum(r['sampling_stratum']==s for r in forget) for s in ('direct','context')}
    if min(counts.values())<8:
        raise ValueError('Insufficient stratum records')
    if any(canonical(r['prompt']) in evaluation for r in forget):
        raise RuntimeError('Evaluation exclusion failed')
    return {'forget.json':forget,'retain.json':retained_generic,'chat_retain.json':retained_chat}, {
        'forget_counts':counts,'full_coverage_by_step_at_eight_each':{s:math.ceil(n/8) for s,n in counts.items()},
        'generic_count':len(retained_generic),'chat_count':len(retained_chat),
        'matched_negative_copies_kept':sum(r.get('source')=='matched_negative520' for r in retained_chat),
        'removed':removed,'normalization':'NFKC/casefold/collapse whitespace; exact prompts only',
        'semantic_independence_claimed':False,'responses':responses}


def run(prior_data, output_dir):
    base=Path('config/whole_concept_jobs_v1')
    contract_path=base/'wide_unfamiliarity_v1/contract_v1.json'
    contract=json.loads(contract_path.read_bytes())
    destination=Path(output_dir)
    if destination.exists():
        raise FileExistsError(destination)
    sources={'prior':Path(prior_data),
        'context':Path(contract['inputs']['context520']),
        'capture':base/'residual_projection_v1/capture_records_v1.json',
        'generic':Path(contract['inputs']['generic_retain']),
        'chat':Path(contract['inputs']['chat_retain'])}
    pins={'prior':contract['inputs']['prior1056_sha256'],
        'context':'c023458939a41e4afed5ff47335e188cd8591f7604112e99291dadefc91c8c1b',
        'capture':contract['inputs']['capture_sha256'],
        'generic':'95525929be4b07247f54b0c7166225fd8a232c6df6a30dde06dc35d88bb8a3a9',
        'chat':'3580322abe0e6f0e680258b3de41802e2564ae05e3bf1d9e687d6b906265274a'}
    for name,path in sources.items():
        if sha(path)!=pins[name]:
            raise ValueError('Source pin differs: '+name)
    evaluation_paths=[Path('config')/folder/file for folder,file in [
        ('employment_sprint_20260904_quick','probes.json'),
        ('employment_sprint_20260904_context_routes','probes.json'),
        ('employment_sprint_20260904_final','probes.json'),
        ('employment_sprint_20260904_final','conversations.json'),
        ('whole_concept_jobs_v1','probes.json'),
        ('whole_concept_jobs_hard_v1','probes.json'),
        ('whole_concept_jobs_hard_v1','conversations.json'),
        ('whole_concept_jobs_direct_v1','probes.json'),
        ('whole_concept_jobs_natural_v2','probes.json')]]
    evaluation_paths += [Path('data/probes.json'),Path('derisk/whole_concept_jobs_v1/delta_protection_v1/sprint_20260904/dense_current_runtime_scalar_v1.json')]
    evaluation=set()
    for path in evaluation_paths:
        evaluation.update(canonical(p) for p in prompts(json.loads(path.read_bytes())))
    values={name:json.loads(path.read_bytes()) for name,path in sources.items()}
    negatives=[r for r in values['capture'] if r['label']=='negative']
    if [len(values['prior']),len(values['context']),len(negatives),len(values['generic']),len(values['chat'])]!=[1056,520,520,177,1193]:
        raise ValueError('Pinned source counts differ')
    outputs,report=materialize(values['prior'],values['context'],negatives,
        values['generic'],values['chat'],contract['responses'],evaluation)
    destination.mkdir(parents=True)
    for name,value in outputs.items():
        (destination/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    shutil.copyfile(sources['prior'],destination/'source_prior1056.json')
    report.update({'source_pins':{name:{'path':str(path),'sha256':pins[name]} for name,path in sources.items()},
        'contract_sha256':sha(contract_path),'implementation_sha256':sha(__file__),
        'evaluation_sources':{str(p):sha(p) for p in evaluation_paths},
        'distinct_evaluation_prompts_checked':len(evaluation),
        'artifacts':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in destination.iterdir()}})
    (destination/'manifest.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prior-data',required=True)
    parser.add_argument('--output-dir',required=True)
    print(json.dumps(run(**vars(parser.parse_args())),indent=2))
