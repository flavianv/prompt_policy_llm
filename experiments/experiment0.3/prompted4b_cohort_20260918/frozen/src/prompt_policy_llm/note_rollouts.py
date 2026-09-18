"""Native-tool rollouts with exact generated-token segments for GRPO."""
from copy import deepcopy
import json,time
from .explicit_note_coverage import SYSTEM,CHECK
from .explicit_note_tools import TOOLS,parse_native
from .explicit_memory import note_call

class NativeRollout:
    def __init__(self,model,tokenizer,config):self.model,self.tokenizer,self.config=model,tokenizer,config
    def update(self,obs,notes,sample=False):
        import torch
        self.model.eval();messages=[{'role':'system','content':SYSTEM},{'role':'user','content':json.dumps(obs)}];read=done=checked=False;rounds=[];segments=[]
        for i in range(self.config['note_max_rounds']):
            prompt=self.tokenizer.apply_chat_template(messages,tools=TOOLS,tokenize=False,add_generation_prompt=True,enable_thinking=False)
            ids=self.tokenizer(prompt,return_tensors='pt').input_ids.to(self.model.device);cap=self.config['note_max_output_tokens']
            if ids.shape[1]+cap>self.config['max_context_tokens']:return {'rounds':rounds,'finished':False,'segments':segments,'error':'context_limit'}
            torch.cuda.synchronize();start=time.perf_counter()
            with torch.no_grad():
                result=self.model.generate(input_ids=ids,attention_mask=torch.ones_like(ids),max_new_tokens=cap,do_sample=sample,temperature=1.0 if sample else None,top_p=1.0 if sample else None,top_k=0 if sample else None,repetition_penalty=1.0,pad_token_id=self.tokenizer.eos_token_id,use_cache=True)
            torch.cuda.synchronize();tokens=result[0,ids.shape[1]:];raw=self.tokenizer.decode(tokens,skip_special_tokens=True);before=dict(notes);call=None
            segment={'prompt_ids':ids[0].tolist(),'completion_ids':tokens.tolist()};segments.append(segment)
            try:
                call=parse_native(raw);tool_result,read,done=note_call(json.dumps({'tool':call['name'],'arguments':call['arguments']}),notes,read,self.config);valid=True
                if done and not checked:done=False;checked=True;tool_result={'ok':True,'finished':False,'review_required':CHECK,'saved_notes':dict(notes)}
            except (ValueError,TypeError,KeyError) as exc:
                valid=False;tool_result={'error':str(exc),'next_step':'Call read_notes with arguments {}.' if not read else 'Use exactly one declared tool with its exact parameters.'}
            rounds.append({'round':i,'messages':deepcopy(messages),'rendered_prompt':prompt,'generation':{'text':raw,'input_tokens':ids.shape[1],'output_tokens':len(tokens),'latency_s':time.perf_counter()-start,'hit_output_cap':len(tokens)>=cap},'valid':valid,'tool_result':tool_result,'notes_before':before,'notes_after':dict(notes)})
            if call:messages.extend([{'role':'assistant','content':'','tool_calls':[{'type':'function','function':call}]},{'role':'tool','name':call['name'],'content':json.dumps(tool_result)}])
            else:messages.extend([{'role':'assistant','content':raw},{'role':'user','content':json.dumps(tool_result)}])
            if done:break
        return {'rounds':rounds,'finished':done,'segments':segments,'coverage_review_requested':checked}

def action_logprobs(model,segment):
    import torch
    p,c=segment['prompt_ids'],segment['completion_ids'];assert p and c
    ids=torch.tensor([p+c],device=model.device)
    # Only assistant continuation positions receive loss; prompt/tool tokens are context.
    logits=model(input_ids=ids,use_cache=False,logits_to_keep=len(c)+1).logits[0,:-1].float()
    assert logits.shape[0]==len(c)
    target=ids[0,-len(c):]
    return torch.log_softmax(logits,dim=-1).gather(1,target[:,None]).squeeze(1)

def loss_mask(segment):return [0]*len(segment['prompt_ids'])+[1]*len(segment['completion_ids'])
