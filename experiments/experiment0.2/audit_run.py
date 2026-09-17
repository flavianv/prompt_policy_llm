#!/usr/bin/env python3
"""Offline trace replay and compact report; makes no model calls."""
import argparse,collections,hashlib,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/'src'))
from prompt_policy_llm.explicit_memory import observation,resolve_events,describe,note_call,strict_json

def audit(p):
 def rows(name):return [json.loads(x) for x in (p/name).read_text().splitlines()]
 ep=json.loads((p/'episode.json').read_text());cfg=json.loads((p/'run_config.json').read_text());calls=rows('answer_calls.jsonl');scores=rows('scores.jsonl');traces=rows('note_traces.jsonl')
 snapshot=p.parent/'src/prompt_policy_llm/explicit_memory.py'
 assert hashlib.sha256(snapshot.read_bytes()).hexdigest()==cfg['source_sha256']
 history={};notes={};errors=collections.Counter();tool_names=collections.Counter();rounds=[]
 for c,t in zip(ep['cases'],traces):
  sid=c['session'];assert t['session']==sid and t['notes_before']==notes and t['observation']==observation(c)
  pair={x['arm']:x for x in calls if x['session']==sid};assert set(pair)=={'baseline','memory'}
  for arm,call in pair.items():
   assert call['payload']=={**observation(c),'prior_notes':notes if arm=='memory' else {},'questions':c['questions']}
  for e in c['events']:
   if e['key'] and e['kind']!='repeat':history.setdefault(e['key'],[]).append(e)
  for r in [x for x in scores if x['session']==sid]:
   truth=r['truth'];value,support=resolve_events(history[truth['key']],truth['at_time'],truth['kind'])
   assert value==truth['value'] and support==truth['support_ids'] and r['question']['options'][truth['answer']]==describe(value)
   assert r['prior_notes']==notes
   for arm in pair:
    parsed=strict_json(pair[arm]['generation']['text']);assert r[arm]['answer']==parsed[r['question']['id']]
    assert r[arm]['correct']==(r[arm]['valid'] and r[arm]['answer']==truth['answer'])
  read=done=False
  for rr in t['rounds']:
   assert rr['notes_before']==notes
   assert rr['messages'][:2]==[{'role':'system','content':cfg['note_system']},{'role':'user','content':json.dumps(observation(c))}]
   try:body=strict_json(rr['generation']['text']);tool_names[str(body.get('tool'))]+=1
   except Exception:errors['malformed_json']+=1
   try:result,read,done=note_call(rr['generation']['text'],notes,read,cfg['config']);valid=True
   except (ValueError,TypeError,KeyError) as exc:
    valid=False;errors[str(exc) if str(exc) in ['read before editing/finish','unknown tool','tool schema','read once','note shape','note budget'] else 'parse_or_other']+=1
   assert valid==rr['valid'] and notes==rr['notes_after'];rounds.append(rr)
  assert notes==t['notes_after'] and done==t['finished']
 def stats(rs):
  return {'n':len(rs),**{a:{'correct':sum(r[a]['correct'] for r in rs),'accuracy':sum(r[a]['correct'] for r in rs)/len(rs) if rs else None,'valid':sum(r[a]['valid'] for r in rs)} for a in ('baseline','memory')}}
 result={'audit_passed':True,'overall':stats(scores),'earlier_session_evidence':stats([r for r in scores if r['truth']['earlier_session_required']]),'current_session_evidence':stats([r for r in scores if not r['truth']['earlier_session_required']]),'historical':stats([r for r in scores if r['truth']['historical']]),'current_time':stats([r for r in scores if not r['truth']['historical']]),'per_session':[{'session':i+1,**stats([r for r in scores if r['session']==i])} for i in range(10)],'paired':dict(collections.Counter('both_correct' if r['baseline']['correct'] and r['memory']['correct'] else 'memory_only' if r['memory']['correct'] else 'baseline_only' if r['baseline']['correct'] else 'both_wrong' for r in scores)),'identical_arm_payloads':all(calls[2*i]['payload']==calls[2*i+1]['payload'] for i in range(10)),'note_error_counts':dict(errors),'parsed_tool_names':dict(tool_names),'note_input_tokens':sum(r['generation']['input_tokens'] for r in rounds),'note_output_tokens':sum(r['generation']['output_tokens'] for r in rounds),'note_generation_seconds':sum(r['generation']['latency_s'] for r in rounds),'successful_note_rounds':sum(r['valid'] for r in rounds)}
 result['paired'].setdefault('baseline_only',0)
 (p/'audit.json').write_text(json.dumps(result,indent=2))
 lines=['# Maya explicit-state smoke: protocol failure','Luna current-session-only scored **8/20 (40%)**; the designated memory arm scored **10/20 (50%)**, a +10 percentage-point difference. **Qwen produced no valid notes. All ten paired payloads were identical. The difference reflects separate Luna generations, not a demonstrated memory benefit.**','Paired outcomes: 2 memory-only correct, 0 baseline-only correct, 8 both correct, 10 both wrong. All 20 answer calls parsed successfully (40 individual arm answers). Failures remain in the denominator; all-query and valid-only accuracy coincide.','## Breakdown','| Evidence/query group | Questions | Current-session Luna | Designated memory arm |','|---|---:|---:|---:|']
 for key,label in [('earlier_session_evidence','Earlier-session evidence'),('current_session_evidence','Current-session evidence'),('historical','Historical time'),('current_time','Current time')]:
  s=result[key];lines.append(f"| {label} | {s['n']} | {s['baseline']['correct']}/{s['n']} | {s['memory']['correct']}/{s['n']} |")
 lines+=['Historical/current-time and evidence-source partitions overlap; do not add all four rows. Earlier-session evidence is based on the generator’s provenance flag, not proof that a baseline cannot guess.','## Per session','| Session | Current-session Luna | Designated memory arm |','|---|---:|---:|']
 for s in result['per_session']:lines.append(f"| {s['session']} | {s['baseline']['correct']}/2 | {s['memory']['correct']}/2 |")
 lines+=['## Protocol and models','Profile and answers: actual API model `gpt-5.6-luna`, low reasoning, independent calls, 768-token answer cap; API sampling defaults, no paired seed. Qwen notes: frozen `Qwen/Qwen3-1.7B`, revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`, 12 files checksum-verified; bfloat16, greedy generation, thinking disabled, 768-token round cap, 12 rounds/session, NVIDIA B200 MIG 3g.90gb. No fine-tuning or optimizer.','Both arms receive identical current statements and questions; only the memory arm is eligible for prior notes. Both answers are generated and scored before the current note update. An offline audit replayed all answer payloads, explicit-state truth, score computation, note transitions, and the executed source checksum. Qwen receives only timestamped statement IDs/text, not questions, answer keys or the hidden profile. The session generator/evaluator uses hidden ground truth; model input does not.','## Note-tool failure analysis','Invocation: 120/120 rounds rejected; 0/10 sessions terminated successfully; 0 output-cap hits. This harness uses textual JSON tool calls with an application-side dispatcher, not native function calling. Qwen emitted multiple objects/prose, invented names such as `note` and `note_upsert`, or failed the mandatory `read_notes` dependency. Invalid calls leave notes unchanged.','Intent alignment: attempted outputs sometimes copied café/elevator chatter and other-person statements as user notes. None executed, so this is an observed attempted behavior, not stored contamination. Context awareness: no successful read/edit chain exists to demonstrate dependency compliance. Robustness: repeated generic error feedback did not recover within 12 rounds. No injected unavailable-tool test was run. Traceability: every prompt, response, tool result and before/after note snapshot is saved; this run has no exposed reasoning trace.','## Representative answer errors','Session 3: both missed restored summer-pants materials (linen/cotton after the temporary override expired). Session 6: both missed the completed gift intent. Session 7: both guessed the wrong name and historical income. All three historical questions failed in both arms. The two memory-arm-only successes were gift intent expiry in session 2 and reopened active status in session 10; their input payloads were identical to baseline, so they cannot support a memory claim.','## Scope and reproducibility','One synthetic LLM-generated user, ten sessions, twenty questions. This is a smoke test, not a statistically persuasive quality comparison. Multiple-choice guesses can be correct without evidence. Recommendation metrics (sethit, result cardinality, candidate coverage) do not apply to explicit-state recall. The next useful checkpoint is a separately labeled note-interface repair and validation, not reporting this +10-point difference as memory performance. No replacement live run was launched.','Raw artifacts: `answer_calls.jsonl`, `scores.jsonl`, `note_traces.jsonl`, `episode.json`, `run_config.json`, `metrics.json`, and `audit.json`. Exact executed source snapshot: `../src/prompt_policy_llm/explicit_memory.py`.','Measured Qwen generation time: %.2f seconds; %d input and %d output tokens across 120 rounds. Luna answer calls: 66.96 seconds summed API latency, 14,614 input and 3,446 output tokens. These sums are generation latency, not end-to-end elapsed time.'%(result['note_generation_seconds'],result['note_input_tokens'],result['note_output_tokens'])]
 (p/'REPORT.md').write_text('\n\n'.join(lines).replace('\n\n|','\n|')+'\n');return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args();print(json.dumps(audit(a.run),indent=2))
