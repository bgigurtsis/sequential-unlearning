from pathlib import Path
import json,hashlib,copy,shutil
base=Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1')
src=base/'analytical_coverage_v1/control_data_v1';dest=base/'context_priority_v1'
rows=json.loads((src/'forget.json').read_bytes())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,x):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x',encoding='utf-8',newline='\n') as f:json.dump(x,f,ensure_ascii=False,indent=2);f.write('\n')
manifests={}
for arm,n in [('workplace',48),('context',520)]:
 data=dest/(arm+'_data_v1');data.mkdir(parents=True,exist_ok=True)
 selected=lambda r:r['category'].endswith('__workplace_tasks') if arm=='workplace' else r['id'].startswith('context_')
 changed=copy.deepcopy(rows)
 for r in changed:r['sampling_stratum']='direct' if selected(r) else 'context'
 assert sum(r['sampling_stratum']=='direct' for r in changed)==n
 assert all({k:v for k,v in a.items() if k!='sampling_stratum'}=={k:v for k,v in b.items() if k!='sampling_stratum'} for a,b in zip(rows,changed))
 write(data/'forget.json',changed)
 for name in ['chat_retain.json','retain.json']:shutil.copyfile(src/name,data/name)
 manifest={'source_dir':src.as_posix(),'count':2080,'strata':{'direct':n,'context':2080-n},'changed_fields_only':['sampling_stratum'],'all_ordered_model_inputs_exact':True,'selected_ids':[r['id'] for r in changed if r['sampling_stratum']=='direct'],'artifacts':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in data.iterdir()},'tokenization':'All2080 original model inputs unchanged; previous no target/chat clipping at256 applies; generic16 existing clips unchanged.'}
 write(data/'manifest.json',manifest);manifests[arm]={'path':data.as_posix(),'sha256':sha(data/'manifest.json')}
parent='derisk/whole_concept_jobs_v1/delta_protection_v1/wide_unfamiliarity_v1/analytical_control_l40s_run96_v1/step048'
contract={'schema':'context_priority_pair_v1','parent':{'path':parent,'sha256':'f02dfa33464bf61b041b2323d60828143520ea9fc6a42ac347ace2b9df90b3c6','config_sha256':'09db4dfd5e59412631a053d435718d8fdd377c22fc007baa9810fc2d9cb8d52d'},'reason':'Best parent passes quick and broad but office/WFH contextual knowledge survives. Compare narrow workplace pressure against broad contextual task pressure, using same2080 ordered model inputs.','arms':{'rtx':{'owner':'root','priority':'48 workplace_tasks,16 semantic seeds with3 wrappers','data':manifests['workplace'],'output':'workplace_priority_rtx_run64_v1'},'l40s':{'owner':'projection_followup','priority':'520 original contextual templates','data':manifests['context'],'output':'context_priority_l40s_run64_v1'}},'sampling':'Existing unchanged CyclicStratumSampler:8 priority direct+8 other context each step, without replacement per cycle. Metadata labels denote sampling buckets, not semantic directness.','training':{'steps':64,'snapshots':[16,32,64],'seed':34012,'learning_rate':2e-5,'batches':[16,4,8],'max_length':256,'target_prefix':[5,8],'chat_prefix':[5,8],'weights':[10,30,100],'rank':32,'alpha':64,'scope':'238 text projection modules/476 FP32 LoRA tensors, all34 layers, BF16 clean base, unchanged trainer e171598','optimizer':'Fresh AdamW from exact parent; no clipping','qualification':'Existing38 CPU tests and byte-identical model inputs; two-step full-objective qualification on each GPU, exact parent load and finite476 gradients before full64.'},'retention':'Same6785 chat and177 generic as analytical pair; clean disabledadapter reference; no filtering.','evaluation':'Quick40/max96 and context12/max256 on each snapshot, batch16, full manual read. Broad60/max96 for survivor or explicit diagnostic. Context requires no clear workplace account or employment intrusion; copying/generic answers remain nondiagnostic, no artificial unfamiliarity credit. Fresh final reserved for broader survivor after merge/reload.','limitations':'Both arms change sampling from parent; no unchanged-continuation control. Narrow workplace expected share50% vs prior4.76%;520-priority gives oldcontext50% vs16.5% but workplace48 share falls to1.54%. Thus recipe comparison, not proof either is superior to doing nothing. Development prompts reused, exact training content unchanged. Absence behavior does not prove internal deletion.','execution':'One owned GPU workload each. Preserve RTX8186. L40S free2.064GB permits238MB qualification+715MB3snapshots with >=1.25GiB launch gate. No deletion required.'}
write(dest/'contract_v1.json',contract)
entry='\n## Freeze workplace versus contextual priority pair (2026-09-05)\n\n'+json.dumps(contract,indent=2)+'\n\nMaterialized manifests pin exact records and hashes. Only sampling_stratum changed; all ordered model inputs and retention byte identity preserved. No new GPU training yet. This is the next evidence-backed pressure test, not repetition of unchanged exposure.\n'
with Path('EXPERIMENTS.md').open('a',encoding='utf-8') as f:f.write(entry)
with Path('docs/CURRENT_SPRINT_PLAN.md').open('a',encoding='utf-8') as f:f.write(entry)
p=Path('PROJECT_MEMORY.md');p.write_text('Frozen context_priority_v1 pair from analyticalcontrol48: root workplace48-priority vs subagent originalcontext520-priority, same2080 inputs/6785chat/177generic,64steps16/32/64 seed34012. Only stratum metadata changes; two-step qualifications next. Parent direct/broad best but contextual failure; fresh unused, goal active.\n\n'+p.read_text(encoding='utf-8'),encoding='utf-8')
shutil.copyfile(__file__,'logs/projection-sprint-20260904/prepare-context-priority-pair-v1.py')
print(json.dumps(manifests,indent=2))
