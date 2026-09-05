"""Build training-only ordinary answer/start and answer/end preferences."""
from pathlib import Path
import hashlib,json,math

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
base=Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1/ordinary_preference_v1')
base.mkdir(exist_ok=False)
source=Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1/ordinary_answer_repair_v1/ordinary_answers_v1.json')
bank_source=Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1/data_v1/forget.json')
old_manifest=source.parent/'data_manifest_v1.json'
ordinary=json.loads(source.read_bytes());assert len(ordinary)==64 and sha(source)=='f6ebd91dbe22c48aa9ede24cc60de7cbc689b6456f8cf5971ee0d4defc0b3f8e'
bank=list(dict.fromkeys(r['target_response'] for r in json.loads(bank_source.read_bytes())));assert len(bank)==8
states=[]
for record in ordinary:
 for state in ['start','end']:
  states.append({'id':record['id']+'__'+state,'parent_id':record['id'],'state':state,
    'prompt':record['prompt'],'prefix_text':'' if state=='start' else record['target_response'],
    'chosen_text':record['target_response'] if state=='start' else '',
    'rejected_texts':bank if state=='start' else ['\n\n'+text for text in bank]})
def write(name,value):
 p=base/name;p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');return p
data=write('states_v1.json',states)
manifest={'source_files':{str(p).replace('\\','/'):sha(p) for p in [source,bank_source,old_manifest]},
 'states_sha256':sha(data),'states':128,'source_records':64,'start_states':64,'end_states':64,
 'response_bank_order':bank,'all_possible_pairs':1024,'chosen_sequences':128,'reference_sequences':1152,
 'exclusion':'Prompts byte-identical to prior vetted ordinary64. Existing data_manifest_v1 records exact467 evaluation-prompt exclusion; no newly authored prompt or output, no fresh final read.',
 'source_identity_verified':True,'end_encoding':'Full authored answer supplied without terminator, entirely unscored; chosen empty text plus exactlyEOS1. Reject two leading newlines plus unfamiliarity andEOS1.',
 'sampling':'Four original records per step, bothstates, two bank entries per source occurrence j:2j modulo8 and2j+1 modulo8. Four64-record cycles over64steps -> all8rejections for every state,1024pair evaluations total.',
 'limitations':'Only64 source prompts and authored answers; full-answer ending states are supplied, not proof of spontaneous correct answers. EOS1 is valid; naturaltemplate106 is not tested here.'}
mp=write('data_manifest_v1.json',manifest)
fixtures={'author':'root','basis':'Independent algebra of DPO negative log-sigmoid and shifted suffix masks; not model behavior',
 'dpo_cases':[
 {'name':'policy_equals_reference','beta':.1,'chosen':-3.,'rejected':-8.,'reference_chosen':-3.,'reference_rejected':-8.,'expected_margin':0.,'expected_loss':math.log(2),'expected_d_chosen':-.05,'expected_d_rejected':.05},
 {'name':'improved_preference','beta':.1,'chosen':-2.,'rejected':-9.,'reference_chosen':-3.,'reference_rejected':-8.,'expected_margin':.2,'expected_loss':math.log1p(math.exp(-.2)),'expected_d_chosen':-.1/(1+math.exp(.2)),'expected_d_rejected':.1/(1+math.exp(.2))},
 {'name':'worse_preference','beta':.1,'chosen':-5.,'rejected':-6.,'reference_chosen':-3.,'reference_rejected':-8.,'expected_margin':-.4,'expected_loss':math.log1p(math.exp(.4)),'expected_d_chosen':-.1/(1+math.exp(-.4)),'expected_d_rejected':.1/(1+math.exp(-.4))}],
 'ce_case':{'sums':[-6.,-2.],'counts':[3,1],'expected_mean_per_state_nll':2.},
 'end_mask_case':{'prompt_ids':[2,10,11],'prefix_ids':[20,21],'eos_id':1,'expected_ids':[2,10,11,20,21,1],'expected_labels':[-100,-100,-100,-100,-100,1]}}
fp=write('analytic_fixtures_v1.json',fixtures)
old=json.loads(Path('config/whole_concept_jobs_v1/wide_unfamiliarity_v1/retain_constrained_adam_v1/contract_v2.json').read_bytes())
contract={'schema':'ordinary_start_end_preference_v1','decision_source':'d153913 closed separate/aggregate retention-cone pair after both failed collateral; no numerical-to-behavior claim',
 'hypothesis':'Explicit relative preference against unfamiliarity on ordinary prompts may reduce false refusals, while supplied complete-answer end states may reduce unwanted refusal tails. This is output behavior training, not proof of internal erasure.',
 'parent':old['parent'],'main_data':old['data'],'settings':old['settings'],
 'arms':{'rtx':{'owner':'root','mode':'dpo','output':'ordinary_dpo_rtx_run64_v1'},'l40s':{'owner':'projection_followup','mode':'ce','output':'ordinary_end_ce_l40s_run64_v1'}},
 'auxiliary_data':{'path':data.as_posix(),'sha256':sha(data),'manifest':mp.as_posix(),'manifest_sha256':sha(mp)},
 'objective':{'main_weights':{'target_ce':10,'generic_jsd':30,'chat_jsd':100},'outer_auxiliary_weight':10,'dpo_beta':.1,
 'ce':'Mean across8chosen states per step of negative summed supervised suffix logp divided by that states suffix token count. No prefix5 weighting in this auxiliary loss.',
 'dpo':'Mean across16pairs per step of -logsigmoid(beta*((sumlogpchosen-sumlogprejected)-(immutableParentSumChosen-immutableParentSumRejected))). Summed suffix logps; no length normalization/prefix weights, no added CE. Chosen shared between the two negatives for eachstate.',
 'reference':'Cache all128chosen+1024rejected sums from exact P24step32, never clean-disabled adapter. Immutable source/token/parent pins; runtime validates cache. CE traces same negative IDs but no negative forwards or reference usage.',
 'comparison_limit':'Fixed objective-and-scale comparison. Equal outer coefficient does NOT mean equal gradient pressure. No dose selection from evaluation and no coefficient sweep.',
 'old_features':'Ordinary repair stream, actual-Adam cone, consistency and older gradient surgery disabled. Existing target/chat prefix5x8 weighting unchanged.'},
 'sampling':manifest['sampling'],'encoding':manifest['end_encoding'],
 'qualification':'Independent analytic DPO value/sign/reference identity, summed suffix masks/causal shift/oneEOS endstates, paired sampler all8coverage, exact off/RNG, strict cache identity and CPUregressions; tokenize all1152sequences withoutclipping; capture immutable exactparent reference; two-step fullobjective GPU smoke each before full64.',
 'evaluation':'All16/32/64 quick40/max96/context12/max256 with full manual reads. Track usefulanswers,falseunknown,tails,career meaning,loops separately. Broad/fresh/merge only stronger joint candidate.',
 'source_hashes':{},'reference_cache':None,'status':'Data/design prepared; implementation and model qualification pending',
 'literature':['https://arxiv.org/html/2305.18290v3'],
 'analytic_fixture':{'path':fp.as_posix(),'sha256':sha(fp)},
 'execution':'Root DPO RTX18.101.59.227 preserving unrelated8186; subagent CE L40S51.49.31.142. One owned GPU process each, no new compute instances. Archive allsix. Only committed exact archived-weight retirement allowed.'}
contract['settings'].pop('batch_ordinary_repair',None);contract['settings']['batch_ordinary_preference']=4
write('contract_v1.json',contract)
print(json.dumps({'states_sha256':sha(data),'manifest_sha256':sha(mp),'fixture_sha256':sha(fp),'bank':bank},indent=2))
