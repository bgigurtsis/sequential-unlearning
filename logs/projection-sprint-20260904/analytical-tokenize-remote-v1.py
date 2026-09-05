from pathlib import Path
import json,hashlib,sys
from transformers import AutoTokenizer
sys.path.insert(0,'scripts')
from train_bounded_forget import chat_messages_for_pair
b=Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1/analytical_coverage_v1/coverage_data_v1')
pins={'forget.json': '86b9794a0e331c580e84e10f49dc895c5656fdf3430fb55ae3b107a918dfebe0', 'retain.json': '95525929be4b07247f54b0c7166225fd8a232c6df6a30dde06dc35d88bb8a3a9', 'chat_retain.json': '526a02b5fb7c3124d7b055ed1b74489fe3051e6c8ab61969ea9538b3e3b7be37'}
for name,h in pins.items():assert hashlib.sha256((b/name).read_bytes()).hexdigest()==h
t=AutoTokenizer.from_pretrained('/home/ubuntu/.cache/huggingface/hub/models--google--gemma-3-4b-it/snapshots/093f9f388b31de276ce2de164bdc2081324b9767',local_files_only=True)
out={'pins':pins,'EOS':t.eos_token_id,'max_length':256,'groups':{}}
for name,key,eos in [('forget.json','target_response',True),('chat_retain.json','answer',False)]:
 lengths=[];answers=[];cache={}
 for r in json.loads((b/name).read_bytes()):
  messages=chat_messages_for_pair(r);ck=json.dumps([messages,r[key],eos],sort_keys=True)
  if ck not in cache:
   pre=t.apply_chat_template(messages,add_generation_prompt=True,tokenize=True,return_dict=True)['input_ids'];ans=t(r[key],add_special_tokens=False).input_ids
   if eos and (not ans or ans[-1]!=t.eos_token_id):ans.append(t.eos_token_id)
   assert pre and ans
   cache[ck]=(len(pre)+len(ans),len(ans))
  total,count=cache[ck];lengths.append(total);answers.append(count)
 out['groups'][name]=dict(count=len(lengths),min_total=min(lengths),max_total=max(lengths),clipped=sum(x>256 for x in lengths),min_answer=min(answers),max_answer=max(answers),unique_sequences=len(cache),EOS_appended=eos)
 assert max(lengths)<=256
generic=[len(t(x,add_special_tokens=True).input_ids) for x in json.loads((b/'retain.json').read_bytes())]
out['groups']['retain.json']=dict(count=len(generic),max_total=max(generic),clipped=sum(x>256 for x in generic))
assert out['groups']['retain.json']['clipped']==16
Path('logs/projection-sprint-20260904/analytical-tokenization-v1.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
