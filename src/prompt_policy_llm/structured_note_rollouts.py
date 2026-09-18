"""Batched JSON continuations; each user carries only its own candidate-0 prediction."""
from copy import deepcopy
import json,time,re
from .structured_notes import SYSTEM,SCHEMA,empty_notes,apply_profile_update
from .adaptgym_pilot import strict_json
from .text_note_updates import SYSTEM as TEXT_SYSTEM,merge_lines,render_notes

def _object(properties,required=()):
    return {'type':'object','properties':properties,'required':list(required),'additionalProperties':False}


def _array(items):return {'type':'array','items':items}


_TEXT={'type':['string','null']}
_LIST={'type':['array','null'],'items':{'type':'string'}}
_PREFS=_object({k:_LIST for k in ['brands','materials','colors','patterns','cuts','fits','occasions','styles','widths']})
_CATEGORY=_object({'category':{'type':'string'},'default_size':{'anyOf':[_object({'size':{'type':'string'},'sizing_system':{'type':'string'}},['size','sizing_system']),{'type':'null'}]},
    'preferences':_PREFS,'sizes':_array(_object({'brand':{'type':'string'},'sizing_system':{'type':'string'},'size':_TEXT},['brand','sizing_system','size'])),
    'scoped_overrides':_array(_object({'context':_object({k:_TEXT for k in ['season','occasion','subtype']}),'preferences':_PREFS},['context','preferences']))},['category'])
_PROFILE=deepcopy(SCHEMA['properties']['profile'])
_PROFILE['properties']['personal']=_object({k:_TEXT for k in ['name','gender','birth_date','race','nationality','marital_status']})
_PROFILE['properties']['category_profiles']=_array(_CATEGORY)
_PROFILE['properties']['purchase_intents']=_array(_object({'id':{'type':'string'},'category':{'type':'string'},'recipient':{'enum':['self','gift']},'status':_TEXT,'deadline':_TEXT,'budget':{'anyOf':[_object({'amount':{'type':'number'},'currency':{'type':'string'}},['amount','currency']),{'type':'null'}]}},['id']))
_PROFILE['properties']['general_preferences']=_array(_object({'topic':{'type':'string'},'item':{'type':'string'},'scope':{'enum':['global','category']},'category':_TEXT,'stance':{'enum':['like','dislike','retracted',None]}},['topic','item','scope','category','stance']))
TOOLS=[{'type':'function','function':{'name':'update_profile','description':'Merge only new or changed fields into saved notes. Omitted fields remain unchanged; null means explicitly unknown. Never supply absent facts.',
 'parameters':_object({'profile':_PROFILE,'history':SCHEMA['properties']['history']},['profile'])}}]
NATIVE_SYSTEM=SYSTEM.replace('Return one strict JSON object:', 'Call update_profile exactly once using arguments shaped as:').replace('No tools, prose or code fences.', 'Use the supplied native tool. No prose or code fences.')


def apply_native_update(raw,prior,as_of):
 match=re.fullmatch(r'\s*<tool_call>\s*(.*?)\s*</tool_call>\s*',raw,re.S)
 if not match:raise ValueError('Expected exactly one native update_profile tool call')
 call=strict_json(match.group(1))
 if not isinstance(call,dict) or set(call)!={'name','arguments'} or call['name']!='update_profile':raise ValueError('Invalid update_profile tool call')
 return apply_profile_update(json.dumps(call['arguments']),prior,as_of)


def cumulative_observation(public_sessions,session):
    obs=deepcopy(public_sessions[session]['observation'])
    obs['session_history']=[deepcopy(row['observation']) for row in public_sessions[:session+1]]
    return obs


def render_session_text(observation):
    """Render unchanged statement text as the session, never a serialized observation."""
    history=observation.get('session_history',[observation])
    return 'Current time: '+observation['current_time']+'\n\n'+ '\n\n'.join('Session '+str(i+1)+':\n'+'\n'.join('['+row['timestamp']+'] '+row['text'] for row in obs['statements']) for i,obs in enumerate(history))


def render_policy_input(observation,notes):
    return render_session_text(observation)+'\n\nPrevious saved notes:\n'+render_notes(notes)


class StructuredRollout:
    def __init__(self,model,tokenizer,config):self.model,self.tokenizer,self.config=model,tokenizer,config

    def batch(self,observations,note_states,sample=False):
        import torch
        assert len(observations)==len(note_states)
        self.tokenizer.padding_side='left'
        if self.tokenizer.pad_token_id is None:self.tokenizer.pad_token_id=self.tokenizer.eos_token_id
        cap=self.config['structured_max_output_tokens'];traces=[];active=[];prompts=[]
        for i,(obs,notes) in enumerate(zip(observations,note_states)):
            payload={'current_session':deepcopy(obs),'previous_notes':deepcopy(notes)}
            prompt=self.tokenizer.apply_chat_template([{'role':'system','content':TEXT_SYSTEM},{'role':'user','content':render_policy_input(obs,notes)}],tokenize=False,add_generation_prompt=True,enable_thinking=False)
            ids=self.tokenizer(prompt,add_special_tokens=False).input_ids
            trace={'payload':payload,'rendered_prompt':prompt,'notes_before':deepcopy(notes),'notes_after':deepcopy(notes),'segments':[],'rounds':[],'finished':False,'raw_output':''}
            if len(ids)+cap>self.config['max_context_tokens']:trace['error']='context_limit'
            else:active.append(i);prompts.append(prompt)
            traces.append(trace)
        if not active:return traces
        inputs=self.tokenizer(prompts,padding=True,return_tensors='pt',add_special_tokens=False).to(self.model.device)
        self.model.eval();torch.cuda.synchronize();start=time.perf_counter()
        with torch.no_grad():
            output=self.model.generate(**inputs,max_new_tokens=cap,do_sample=sample,temperature=1.0 if sample else None,
                top_p=1.0 if sample else None,top_k=0 if sample else None,repetition_penalty=1.0,
                pad_token_id=self.tokenizer.pad_token_id,use_cache=True)
        torch.cuda.synchronize();elapsed=time.perf_counter()-start
        eos=self.model.generation_config.eos_token_id;eos={eos} if isinstance(eos,int) else set(eos or [])
        for row,i in enumerate(active):
            tokens=output[row,inputs.input_ids.shape[1]:].tolist()
            stop=next((j+1 for j,t in enumerate(tokens) if t in eos),len(tokens));tokens=tokens[:stop]
            raw=self.tokenizer.decode(tokens,skip_special_tokens=True);trace=traces[i];error=None
            try:
                prediction=merge_lines(note_states[i],raw);note_states[i].clear();note_states[i].update(deepcopy(prediction));valid=True
            except (ValueError,TypeError,KeyError,OverflowError,RecursionError) as exc:error=str(exc);valid=False
            prompt_ids=inputs.input_ids[row][inputs.attention_mask[row].bool()].tolist()
            generation={'text':raw,'input_tokens':len(prompt_ids),'output_tokens':len(tokens),'hit_output_cap':len(tokens)>=cap,
                        'batch_wall_seconds':elapsed,'batch_size':len(active),'allocated_latency_s':elapsed/len(active)}
            trace.update(raw_output=raw,finished=valid,error=error,notes_after=deepcopy(note_states[i]),
                segments=[{'prompt_ids':prompt_ids,'completion_ids':tokens}],rounds=[{'round':0,'generation':generation,'valid':valid}])
        return traces

    def update(self,obs,notes,sample=False):return self.batch([obs],[notes],sample)[0]

    def sample_group(self,obs,prior,group_size):
        notes=[deepcopy(prior) for _ in range(group_size)]
        traces=self.batch([deepcopy(obs) for _ in notes],notes,sample=True)
        return [{'candidate':i,'notes':n,'trace':t} for i,(n,t) in enumerate(zip(notes,traces))]


def group_from_prior(manager,obs,prior,group_size):
    if hasattr(manager,'sample_group'):return manager.sample_group(deepcopy(obs),deepcopy(prior),group_size)
    result=[]
    for g in range(group_size):
        notes=deepcopy(prior);trace=manager.update(deepcopy(obs),notes,sample=True)
        result.append({'candidate':g,'notes':notes,'trace':trace})
    return result


def carry_candidate_zero(prior,candidates):
    # Schema validity controls whether candidate0 is usable; reward never selects memory.
    return deepcopy(candidates[0]['notes'] if candidates[0]['trace']['finished'] else prior)


def collect_candidates(manager,public_sessions,session,group_size):
    prior=empty_notes();prefix=[]
    for i,row in enumerate(public_sessions[:session]):prefix.append(manager.update(cumulative_observation(public_sessions,i),prior,sample=False))
    return prior,prefix,group_from_prior(manager,cumulative_observation(public_sessions,session),prior,group_size)
