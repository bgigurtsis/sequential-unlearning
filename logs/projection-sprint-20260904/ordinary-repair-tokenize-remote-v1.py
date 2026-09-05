import json,hashlib,sys
from pathlib import Path
from transformers import AutoTokenizer
sys.path.insert(0,'scripts')
from train_bounded_forget import chat_messages_for_pair
from answer_prefix_conditioning import encode_answer_sequence,answer_prefix_count
from ordinary_response_repair import make_ordinary_repair_sampler
pins={'scripts/train_bounded_forget.py': 'f04d4e7c55acac379806de76ba40408faa2a17e1e3d05f151c575e01f4005b3d', 'scripts/ordinary_response_repair.py': '1e25c201984afb9f8ecd12a06ca6705e38c852babd51d9ab2899619c4d0c847e', 'scripts/answer_prefix_conditioning.py': '8c126dd24e04f08375c067d9ed74e0b4213266183c8101ab91fbcc6e9ff549a3', 'scripts/prefix_unfamiliarity_training.py': '71d88152fff82dcfbe46fe142a934d1cf7187749e0abd09291955acdc3025f8e', 'scripts/wide_unfamiliarity_training.py': 'e692f78daa0a432cb9e345ec2212a73c59231102c7e906100c5e04a60a4ebb7b', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/ordinary_answer_repair_v1/ordinary_answers_v1.json': 'f6ebd91dbe22c48aa9ede24cc60de7cbc689b6456f8cf5971ee0d4defc0b3f8e', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/ordinary_answer_repair_v1/shared_data_v1/forget.json': 'c0b54b438897c91edbccbf2fcb1eab49ce4be34a22607186d7289f2939f764c2', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/ordinary_answer_repair_v1/shared_data_v1/chat_retain.json': '79e6b2899fdbd041d686af2fbdeab52168362a8b1c347a160d38257f74e10665', 'config/whole_concept_jobs_v1/wide_unfamiliarity_v1/ordinary_answer_repair_v1/shared_data_v1/retain.json': '95525929be4b07247f54b0c7166225fd8a232c6df6a30dde06dc35d88bb8a3a9'}
base='config/whole_concept_jobs_v1/wide_unfamiliarity_v1/ordinary_answer_repair_v1'

for p,h in pins.items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h,p
t=AutoTokenizer.from_pretrained('/home/ubuntu/.cache/huggingface/hub/models--google--gemma-3-4b-it/snapshots/093f9f388b31de276ce2de164bdc2081324b9767',local_files_only=True)
cache={};token_cache={};report={'pins':pins,'groups':{},'max_length':256,'model_loaded':False}
def tok(text):
 if text not in token_cache:token_cache[text]=t(text,add_special_tokens=False).input_ids
 return token_cache[text]
for group,filename in [('forget','shared_data_v1/forget.json'),('chat','shared_data_v1/chat_retain.json'),('ordinary','ordinary_answers_v1.json')]:
 rows=json.loads(Path(base,filename).read_bytes());totals=[];suffixes=[];conditioned=[]
 if group=='ordinary':make_ordinary_repair_sampler(rows,weight=10,seed=34016,batch_size=4)
 for r in rows:
  msgs=chat_messages_for_pair(r);prefix=answer_prefix_count(r);key=json.dumps([msgs,r['answer'],r.get('target_response') if group!='chat' else None,prefix],sort_keys=True)
  if key not in cache:
   pre=t.apply_chat_template(msgs,add_generation_prompt=True,tokenize=True,return_dict=True)['input_ids'];source=r.get('answer_token_ids') or tok(r['answer']);desired=None
   if group!='chat':
    desired=list(tok(r['target_response']))
    if not desired or desired[-1]!=t.eos_token_id:desired.append(t.eos_token_id)
    assert desired.count(t.eos_token_id)==1
   seq,mask,labels=encode_answer_sequence(pre,source,supervised_ids=desired,prefix_count=prefix,max_length=256)
   tail=desired if desired is not None else source[prefix or 0:];boundary=len(pre)+(prefix or 0)
   assert seq==pre+source[:prefix or 0]+tail and len(seq)<=256
   assert mask==[0]*boundary+[1]*len(tail) and labels==[-100]*boundary+tail
   if prefix is not None:
    audit=encode_answer_sequence(pre,source,prefix_count=prefix,max_length=256);assert sum(audit[1])>=8 and audit[0]==pre+source
   cache[key]=(len(seq),sum(mask))
  total,suffix=cache[key];totals.append(total);suffixes.append(suffix)
  if prefix is not None:conditioned.append(suffix)
 report['groups'][group]={'rows':len(rows),'conditional':len(conditioned),'min_total':min(totals),'max_total':max(totals),'min_supervised_suffix':min(suffixes),'clipping':0,'all_prefix_masks_and_suffix_labels_exact':True,'one_eos_per_desired_response':group!='chat'}
generic=json.loads(Path(base,'shared_data_v1/retain.json').read_bytes());gl=[len(t(x,add_special_tokens=True).input_ids) for x in generic];assert sum(n>256 for n in gl)==16
report['generic']={'count':len(gl),'max_total':max(gl),'unchanged_clips':16}
print(json.dumps(report))
