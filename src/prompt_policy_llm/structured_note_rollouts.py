"""Direct JSON note rollout; only public observations and own predictions enter prompts."""
from copy import deepcopy
import json
import time
from .structured_notes import SYSTEM, empty_notes, parse_document


class StructuredRollout:
    def __init__(self,model,tokenizer,config):self.model,self.tokenizer,self.config=model,tokenizer,config

    def update(self,obs,notes,sample=False):
        import torch
        payload={'current_session':deepcopy(obs),'previous_notes':deepcopy(notes)}
        messages=[{'role':'system','content':SYSTEM},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}]
        prompt=self.tokenizer.apply_chat_template(messages,tokenize=False,add_generation_prompt=True,enable_thinking=False)
        ids=self.tokenizer(prompt,return_tensors='pt').input_ids.to(self.model.device)
        cap=self.config['structured_max_output_tokens']
        base={'payload':payload,'rendered_prompt':prompt,'notes_before':deepcopy(notes),'segments':[],'rounds':[],'finished':False,'raw_output':''}
        if ids.shape[1]+cap>self.config['max_context_tokens']:return {**base,'error':'context_limit','notes_after':deepcopy(notes)}
        self.model.eval();torch.cuda.synchronize();start=time.perf_counter()
        with torch.no_grad():
            output=self.model.generate(input_ids=ids,attention_mask=torch.ones_like(ids),max_new_tokens=cap,
                do_sample=sample,temperature=1.0 if sample else None,top_p=1.0 if sample else None,top_k=0 if sample else None,
                repetition_penalty=1.0,pad_token_id=self.tokenizer.eos_token_id,use_cache=True)
        torch.cuda.synchronize();tokens=output[0,ids.shape[1]:];raw=self.tokenizer.decode(tokens,skip_special_tokens=True)
        error=None
        try:prediction=parse_document(raw,obs['current_time']);notes.clear();notes.update(deepcopy(prediction));valid=True
        except (ValueError,TypeError,KeyError,OverflowError,RecursionError) as exc:error=str(exc);valid=False
        generation={'text':raw,'input_tokens':ids.shape[1],'output_tokens':len(tokens),'hit_output_cap':len(tokens)>=cap,'latency_s':time.perf_counter()-start}
        return {**base,'raw_output':raw,'finished':valid,'error':error,'notes_after':deepcopy(notes),
                'segments':[{'prompt_ids':ids[0].tolist(),'completion_ids':tokens.tolist()}],
                'rounds':[{'round':0,'generation':generation,'valid':valid}]}


def collect_candidates(manager,public_sessions,session,group_size):
    """No gold/profile argument exists at this boundary. Prefix state is never teacher-forced."""
    prior=empty_notes();prefix=[]
    for row in public_sessions[:session]:prefix.append(manager.update(deepcopy(row['observation']),prior,sample=False))
    candidates=[];obs=deepcopy(public_sessions[session]['observation'])
    for g in range(group_size):
        notes=deepcopy(prior);trace=manager.update(deepcopy(obs),notes,sample=True)
        candidates.append({'candidate':g,'notes':notes,'trace':trace})
    return prior,prefix,candidates
