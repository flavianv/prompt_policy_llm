"""Native Qwen chat-template tool interface; separately labeled note-only smoke."""
import argparse,json,re,time
from copy import deepcopy
from pathlib import Path
from .explicit_memory import note_call,observation,verify_qwen,ROOT
from .adaptgym_pilot import strict_json,QwenNotes

TOOLS=[]
for name,description,properties,required in [
 ('read_notes','Read existing user notes. Call once before all other tools.',{},[]),
 ('put_note','Save or replace one named note. Include dates, history, scope and evidence IDs.',{'name':{'type':'string'},'text':{'type':'string'}},['name','text']),
 ('delete_note','Delete an existing named note.',{'name':{'type':'string'}},['name']),
 ('no_op','Finish after all relevant facts have been saved.',{},[])]:
 TOOLS.append({'type':'function','function':{'name':name,'description':description,'parameters':{'type':'object','properties':properties,'required':required,'additionalProperties':False}}})
SYSTEM='''You maintain persistent notes for one user. Use the supplied tools, exactly one call per turn.
First call read_notes with empty arguments {}. Wait for its result. Then call put_note to save useful facts. Finish with no_op and empty arguments {}.
Only read_notes, put_note, delete_note and no_op exist. Never invent a tool name or add extra arguments.
Preserve explicit user facts, dates, historical changes, unknown and empty preference lists, category/brand/season scope, temporary expiry and intent deadlines. Do not infer facts or convert sizes. Ignore unrelated chatter, other-person facts and product descriptions. A single concise note may group all new facts. Retain old facts/history when updating it.
Example first response: <tool_call>{"name":"read_notes","arguments":{}}</tool_call>
When writing, text must contain the actual facts from the current statements and existing notes. Do not write a description of what notes should contain. No placeholder text. Save all explicit personal facts in this session before finishing.
Example finish: <tool_call>{"name":"no_op","arguments":{}}</tool_call>'''

def parse_native(text):
 m=re.fullmatch(r'\s*<tool_call>\s*(.*?)\s*</tool_call>\s*',text,re.S)
 if not m:raise ValueError('Expected exactly one <tool_call>{"name":"...","arguments":{...}}</tool_call>, with no prose or other calls')
 b=strict_json(m.group(1))
 if not isinstance(b,dict) or set(b)!={'name','arguments'}:raise ValueError('Tool JSON must have exactly name and arguments')
 if b['name'] not in {x['function']['name'] for x in TOOLS}:raise ValueError('Unknown tool name; use read_notes, put_note, delete_note or no_op')
 return b

def run(model_path,episode_path,output):
 cfg=json.loads((ROOT/'config.json').read_text());identity=verify_qwen(model_path);g=QwenNotes(str(model_path));case=json.loads(episode_path.read_text())['cases'][0];obs=observation(case)
 output.mkdir(parents=True,exist_ok=False);messages=[{'role':'system','content':SYSTEM},{'role':'user','content':json.dumps(obs)}];notes={};read=done=False;rounds=[]
 (output/'config.json').write_text(json.dumps({'identity':identity,'tools':TOOLS,'system':SYSTEM,'observation':obs,'decoding':{'do_sample':False,'enable_thinking':False,'max_new_tokens':768},'max_rounds':12,'weight_training':False,'scope':'one session, note only; no Luna calls'},indent=2))
 for i in range(12):
  prompt=g.tokenizer.apply_chat_template(messages,tools=TOOLS,tokenize=False,add_generation_prompt=True,enable_thinking=False);batch=g.tokenizer(prompt,return_tensors='pt').to('cuda');start=time.perf_counter()
  with g.torch.inference_mode():result=g.model.generate(**batch,max_new_tokens=768,do_sample=False,pad_token_id=g.tokenizer.eos_token_id)
  g.torch.cuda.synchronize();tokens=result[0,batch.input_ids.shape[1]:];raw=g.tokenizer.decode(tokens,skip_special_tokens=True);before=dict(notes);call=None
  try:
   call=parse_native(raw);tool_result,read,done=note_call(json.dumps({'tool':call['name'],'arguments':call['arguments']}),notes,read,cfg);valid=True
  except (ValueError,TypeError,KeyError) as exc:
   valid=False;tool_result={'error':str(exc),'next_step':'Call read_notes with arguments {}.' if not read else 'Use exact declared parameters; one call, then wait for result.'}
  rr={'round':i,'messages':deepcopy(messages),'rendered_prompt':prompt,'generation':{'text':raw,'input_tokens':batch.input_ids.shape[1],'output_tokens':len(tokens),'latency_s':time.perf_counter()-start,'hit_output_cap':len(tokens)>=768},'valid':valid,'tool_result':tool_result,'notes_before':before,'notes_after':dict(notes)};rounds.append(rr)
  with (output/'trace.jsonl').open('a') as f:f.write(json.dumps(rr)+'\n')
  if call:
   messages.append({'role':'assistant','content':'','tool_calls':[{'type':'function','function':call}]});messages.append({'role':'tool','name':call['name'],'content':json.dumps(tool_result)})
  else:messages.extend([{'role':'assistant','content':raw},{'role':'user','content':json.dumps(tool_result)}])
  print(json.dumps({'round':i,'valid':valid,'tool':call['name'] if call else None,'notes':len(notes),'done':done}),flush=True)
  if done:break
 result={'protocol_success':done and read and bool(notes),'substantive_success_requires_manual_audit':True,'finished':done,'valid_rounds':sum(r['valid'] for r in rounds),'rounds':len(rounds),'notes':notes};(output/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--model-path',type=Path,required=True);p.add_argument('--episode',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.model_path,a.episode,a.output)
