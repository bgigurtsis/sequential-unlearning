import json,hashlib,sys
from pathlib import Path
from transformers import AutoTokenizer
sys.path.insert(0,'scripts')
from train_bounded_forget import chat_messages_for_pair
from answer_prefix_conditioning import encode_answer_sequence,answer_prefix_count
for p,h in {'scripts/train_bounded_forget.py': '3008dc532175165c9235feb0e8b220a8434fe747851ee3cac697d3ff9859b588', 'scripts/answer_prefix_conditioning.py': '8c126dd24e04f08375c067d9ed74e0b4213266183c8101ab91fbcc6e9ff549a3', 'scripts/prefix_unfamiliarity_training.py': '71d88152fff82dcfbe46fe142a934d1cf7187749e0abd09291955acdc3025f8e', 'scripts/wide_unfamiliarity_training.py': 'e692f78daa0a432cb9e345ec2212a73c59231102c7e906100c5e04a60a4ebb7b', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/answer_state_correction_v1/prefix08_data_v1/forget.json': 'f1aeeda03b022241344b3c38ee5a9e922253981f62260da49d7fdb46b260e5ed', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/answer_state_correction_v1/prefix08_data_v1/chat_retain.json': '79e6b2899fdbd041d686af2fbdeab52168362a8b1c347a160d38257f74e10665', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/answer_state_correction_v1/prefix08_data_v1/retain.json': '95525929be4b07247f54b0c7166225fd8a232c6df6a30dde06dc35d88bb8a3a9', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/answer_state_correction_v1/prefix24_data_v1/forget.json': '72637b887a4f20e3ff2b7d6acb7af278b1520e7cdda57b3b2e72a0a9d013395d', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/answer_state_correction_v1/prefix24_data_v1/chat_retain.json': '79e6b2899fdbd041d686af2fbdeab52168362a8b1c347a160d38257f74e10665', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/answer_state_correction_v1/prefix24_data_v1/retain.json': '95525929be4b07247f54b0c7166225fd8a232c6df6a30dde06dc35d88bb8a3a9'}.items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h,p
t=AutoTokenizer.from_pretrained('/home/ubuntu/.cache/huggingface/hub/models--google--gemma-3-4b-it/snapshots/093f9f388b31de276ce2de164bdc2081324b9767',local_files_only=True)
cache={};token_cache={};report={'pins':{'scripts/train_bounded_forget.py': '3008dc532175165c9235feb0e8b220a8434fe747851ee3cac697d3ff9859b588', 'scripts/answer_prefix_conditioning.py': '8c126dd24e04f08375c067d9ed74e0b4213266183c8101ab91fbcc6e9ff549a3', 'scripts/prefix_unfamiliarity_training.py': '71d88152fff82dcfbe46fe142a934d1cf7187749e0abd09291955acdc3025f8e', 'scripts/wide_unfamiliarity_training.py': 'e692f78daa0a432cb9e345ec2212a73c59231102c7e906100c5e04a60a4ebb7b', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/answer_state_correction_v1/prefix08_data_v1/forget.json': 'f1aeeda03b022241344b3c38ee5a9e922253981f62260da49d7fdb46b260e5ed', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/answer_state_correction_v1/prefix08_data_v1/chat_retain.json': '79e6b2899fdbd041d686af2fbdeab52168362a8b1c347a160d38257f74e10665', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/answer_state_correction_v1/prefix08_data_v1/retain.json': '95525929be4b07247f54b0c7166225fd8a232c6df6a30dde06dc35d88bb8a3a9', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/answer_state_correction_v1/prefix24_data_v1/forget.json': '72637b887a4f20e3ff2b7d6acb7af278b1520e7cdda57b3b2e72a0a9d013395d', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/answer_state_correction_v1/prefix24_data_v1/chat_retain.json': '79e6b2899fdbd041d686af2fbdeab52168362a8b1c347a160d38257f74e10665', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/answer_state_correction_v1/prefix24_data_v1/retain.json': '95525929be4b07247f54b0c7166225fd8a232c6df6a30dde06dc35d88bb8a3a9'},'groups':{},'max_length':256,'model_loaded':False}
def tok(text):
 if text not in token_cache:token_cache[text]=t(text,add_special_tokens=False).input_ids
 return token_cache[text]
for p in [8,24]:
 for group in ['forget','chat_retain']:
  rows=json.loads(Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1/answer_state_correction_v1'+f'/prefix{p:02d}_data_v1/'+group+'.json').read_bytes());totals=[];suffixes=[];conditioned=[];audit_totals=[]
  for r in rows:
   msgs=chat_messages_for_pair(r);prefix=answer_prefix_count(r);key=json.dumps([msgs,r['answer'],r.get('target_response') if group=='forget' else None,prefix],sort_keys=True)
   if key not in cache:
    pre=t.apply_chat_template(msgs,add_generation_prompt=True,tokenize=True,return_dict=True)['input_ids'];source=r.get('answer_token_ids') or tok(r['answer'])
    desired=None
    if group=='forget':
     desired=list(tok(r['target_response']))
     if not desired or desired[-1]!=t.eos_token_id:desired.append(t.eos_token_id)
     assert desired.count(t.eos_token_id)==1
    seq,mask,labels=encode_answer_sequence(pre,source,supervised_ids=desired,prefix_count=prefix,max_length=256)
    expected=len(pre)+(prefix or 0)+(len(desired) if desired is not None else len(source)-(prefix or 0))
    assert len(seq)==expected and sum(mask)>0
    boundary=len(pre)+(prefix or 0);assert all(x==0 for x in mask[:boundary]) and labels[:boundary]==[-100]*boundary
    assert [x for x in labels if x!=-100]==(desired if desired is not None else source[prefix or 0:])
    audit=encode_answer_sequence(pre,source,prefix_count=prefix,max_length=256)
    if prefix is not None:assert sum(audit[1])>=8 and audit[0]==pre+source
    cache[key]=(len(seq),sum(mask),len(audit[0]))
   total,suffix,audit=cache[key];totals.append(total);suffixes.append(suffix);audit_totals.append(audit)
   if prefix is not None:conditioned.append(suffix)
  report['groups'][f'prefix{p:02d}_{group}']={'rows':len(rows),'conditional':len(conditioned),'min_total':min(totals),'max_total':max(totals),'min_supervised_suffix':min(suffixes),'min_conditional_supervised_suffix':min(conditioned),'max_original_audit_total':max(audit_totals),'clipping':0,'all_prefix_masks_and_suffix_labels_exact':True}
generic=json.loads(Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1/answer_state_correction_v1'+'/prefix08_data_v1/retain.json').read_bytes());gl=[len(t(x,add_special_tokens=True).input_ids) for x in generic];assert sum(n>256 for n in gl)==16
report['generic']={'count':len(gl),'max_total':max(gl),'unchanged_clips':16};print(json.dumps(report))
