import json
from copy import deepcopy
from pathlib import Path
import pytest
from prompt_policy_llm.note_reward import AnswerCache,utility,reward,probe_batches,group_advantages
from prompt_policy_llm.note_rollouts import loss_mask
from prompt_policy_llm import explicit_memory as em
from prompt_policy_llm import profile_contract as pc

CFG=json.loads((em.ROOT.parent/'experiment0.3/config.json').read_text())

def episode():
 p=json.loads((pc.ROOT/'example_profile.json').read_text());c=json.loads((em.ROOT/'config.json').read_text());return p,em.generate_sessions(p,c)

class FakeAnswerer:
 def __init__(self):self.calls=0
 def generate(self,system,payload,max_tokens):
  self.calls+=1
  return {'text':json.dumps({q['id']:next(iter(q['options'])) for q in payload['questions']}),'status':'completed','model':'gpt-5.6-luna'}

def test_identical_inputs_have_exact_zero_utility(tmp_path):
 p,e=episode();b=probe_batches(p,e['cases'][1],CFG);client=FakeAnswerer();cache=AnswerCache(tmp_path,client,'gpt-5.6-luna');u,rows=utility(cache,b,{},{});assert u==0 and client.calls==len(b)
 assert all(r['baseline']['cache_key']==r['memory']['cache_key'] for r in rows)

def test_probe_prefix_and_temporal_gold():
 p,e=episode();case=e['cases'][1];batches=probe_batches(p,case,CFG)
 for b in batches:
  assert all(x['id']=='future-filler' for x in b['observation']['statements'])
  for q,t in b['truth'].items():
   h=case['revealed_state'][t['key']]['history'];v,_=em.resolve_events(h,t['at_time'],t['kind']);assert v==t['value']
   assert all(em.dt(x['timestamp'])<=em.dt(case['current_time']) for x in h)
   assert t['support_ids'] and set(t['support_ids'])<=set(x['id'] for x in h)
 # Public writer input has no scorer structure.
 assert set(em.observation(case))=={'current_time','statements'}

def test_counterfactual_past_value_changes_gold_with_future_fixed():
 history=[{'id':'a','timestamp':'2026-01-01T00:00:00Z','until':None,'value':['cotton']}];future={'current_time':'2026-02-01T00:00:00Z','statements':[]};original=deepcopy(future)
 a=em.resolve_events(history,future['current_time'],'list')[0];history[0]['value']=['linen'];b=em.resolve_events(history,future['current_time'],'list')[0]
 assert a!=b and future==original

def test_invalid_finish_and_budget_cost_no_format_bonus():
 trace={'finished':False,'rounds':[{'valid':False}]};assert reward(1,trace,{},CFG)['reward']==-1
 trace={'finished':True,'rounds':[{'valid':True}]};assert reward(0,trace,{},CFG)['reward']==0
 assert reward(0,trace,{'fact':'supported fact'},CFG)['reward']<0

def test_group_normalization_and_masks():
 a,std=group_advantages([1,0,-1,0]);assert std>0 and abs(sum(a))<1e-9 and a[0]>a[1]>a[2]
 assert group_advantages([-1]*4)==([0]*4,0)
 assert loss_mask({'prompt_ids':[11,22,33],'completion_ids':[44,55]})==[0,0,0,1,1]

def test_api_budget_and_malformed_answers_remain_failures(tmp_path):
 c=AnswerCache(tmp_path,FakeAnswerer(),'gpt-5.6-luna',max_calls=0)
 with pytest.raises(RuntimeError):c.answer({}, {},[{'id':'q','options':{'A':'one'}}])


def test_staged_config_matches_user_model_and_lora_choice():
 assert CFG['model']=='Qwen/Qwen3-4B' and not CFG['load_in_4bit']
 assert CFG['lora_rank']==16 and CFG['lora_alpha']==32 and CFG['init_lora_weights'] is True
 assert {'gate_proj','up_proj','down_proj'}<=set(CFG['lora_targets'])
