"""Bounded coverage-focused native-tool note manager, without oracle feedback."""
import argparse,json,time
from copy import deepcopy
from pathlib import Path
from .explicit_note_tools import TOOLS,parse_native
from .explicit_memory import ROOT,note_call,observation,verify_qwen
from .adaptgym_pilot import QwenNotes

SYSTEM='''You are the user's persistent memory writer. The next conversation will have ONLY your saved notes, so losing a disclosed fact is a failure.
Use exactly one supplied tool per response. First read_notes with arguments {}. Then write actual supported facts using put_note. Finish using no_op with arguments {} only after checking coverage.
Read EVERY timestamped statement. Save ALL useful facts about this user: name/general facts; clothing category and subtype/season/occasion; brand and sizing system; every item of multiple preferences; explicit unknown values; explicitly empty preference lists; requests/intents, recipient, status and exact deadline. Unknown and no preference are different. Do not convert sizes.
Preserve evidence IDs and dates in note text. For changes keep the previous dated value as history and the new effective date. For temporary changes retain the base value, temporary value and exact expiry so the base can be restored. Keep earlier notes, including open/future requests; do not erase unrelated facts when adding new ones. A put_note replaces its entire named note, so retain all earlier content needed in that note.
Ignore unrelated chatter, facts about other people and product advertisements. Repetition confirms a fact without changing its date or value. Do not invent facts.
Write concise complete notes. Prefer one stable topic per note; several related facts can share a note. Note text must contain the actual disclosed information, not instructions or placeholders.
Before finishing compare all statements against the saved notes. For each statement decide whether it is irrelevant or fully covered; add every missing useful fact. One saved fact is not sufficient when the session has several facts. Use up to the available 12 calls to read, write, check and finish. Only the four supplied tool names and their exact parameters are allowed.'''
CHECK='''Coverage checkpoint before finishing: compare EVERY current statement against the notes just saved. Preserve every useful user fact and its scope, explicit unknown/empty lists, request status/deadline and timestamps. Keep prior facts/history. Ignore filler, other people and ads. If anything useful is missing or distorted, call put_note to fix it. Otherwise call no_op. This is a review request, not permission to invent facts.'''

class CoverageManager:
 def __init__(self,generator,config):self.g,self.config=generator,config
 def update(self,obs,notes):
  messages=[{'role':'system','content':SYSTEM},{'role':'user','content':json.dumps(obs)}];read=done=checked=False;rounds=[]
  for i in range(self.config['note_max_rounds']):
   prompt=self.g.tokenizer.apply_chat_template(messages,tools=TOOLS,tokenize=False,add_generation_prompt=True,enable_thinking=False)
   batch=self.g.tokenizer(prompt,return_tensors='pt').to('cuda');cap=self.config['note_max_output_tokens'];self.g.torch.cuda.synchronize();start=time.perf_counter()
   with self.g.torch.inference_mode():result=self.g.model.generate(**batch,max_new_tokens=cap,do_sample=False,pad_token_id=self.g.tokenizer.eos_token_id)
   self.g.torch.cuda.synchronize();tokens=result[0,batch.input_ids.shape[1]:];raw=self.g.tokenizer.decode(tokens,skip_special_tokens=True);before=dict(notes);call=None
   try:
    call=parse_native(raw);tool_result,read,done=note_call(json.dumps({'tool':call['name'],'arguments':call['arguments']}),notes,read,self.config);valid=True
    if done and not checked:
     done=False;checked=True;tool_result={'ok':True,'finished':False,'review_required':CHECK,'saved_notes':dict(notes)}
   except (ValueError,TypeError,KeyError) as exc:
    valid=False;tool_result={'error':str(exc),'next_step':'Call read_notes with arguments {}.' if not read else 'Use exactly one declared tool with its exact parameters.'}
   rr={'round':i,'messages':deepcopy(messages),'rendered_prompt':prompt,'generation':{'text':raw,'input_tokens':batch.input_ids.shape[1],'output_tokens':len(tokens),'latency_s':time.perf_counter()-start,'hit_output_cap':len(tokens)>=cap},'valid':valid,'tool_result':tool_result,'notes_before':before,'notes_after':dict(notes)};rounds.append(rr)
   if call:messages.extend([{'role':'assistant','content':'','tool_calls':[{'type':'function','function':call}]},{'role':'tool','name':call['name'],'content':json.dumps(tool_result)}])
   else:messages.extend([{'role':'assistant','content':raw},{'role':'user','content':json.dumps(tool_result)}])
   print(json.dumps({'round':i,'valid':valid,'tool':call['name'] if call else None,'notes':len(notes),'finished':done}),flush=True)
   if done:break
  return {'rounds':rounds,'finished':done,'coverage_review_requested':checked}

def main():
 p=argparse.ArgumentParser();p.add_argument('--model-path',type=Path,required=True);p.add_argument('--episode',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();identity=verify_qwen(a.model_path);cfg=json.loads((ROOT/'config.json').read_text());g=QwenNotes(str(a.model_path));manager=CoverageManager(g,cfg);a.output.mkdir(parents=True,exist_ok=False)
 (a.output/'config.json').write_text(json.dumps({'identity':identity,'config':cfg,'system':SYSTEM,'coverage_checkpoint':CHECK,'tools':TOOLS,'sessions':2,'weight_training':False},indent=2));(a.output/'source.py').write_text(Path(__file__).read_text());notes={}
 for c in json.loads(a.episode.read_text())['cases'][:2]:
  before=dict(notes);obs=observation(c);trace=manager.update(obs,notes);trace.update(session=c['session'],observation=obs,notes_before=before,notes_after=dict(notes));(a.output/f"session{c['session']+1}.json").write_text(json.dumps(trace,indent=2));print(json.dumps({'session':c['session']+1,'finished':trace['finished'],'notes':notes}),flush=True)
 (a.output/'notes.json').write_text(json.dumps(notes,indent=2))
if __name__=='__main__':main()
