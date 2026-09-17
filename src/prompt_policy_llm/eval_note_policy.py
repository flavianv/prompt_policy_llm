"""Matched sequential frozen/adapted Qwen notes versus no-memory Luna."""
import argparse,json
from copy import deepcopy
from pathlib import Path
from .note_model import load_model,verify_snapshot
from .note_rollouts import NativeRollout
from .note_reward import AnswerCache
from .explicit_memory import Luna,observation
from .adaptgym_pilot import load_credentials

def evaluate_episode(episode,manager,cache,output):
    output.mkdir(parents=True,exist_ok=False);(output/'episode.json').write_text(json.dumps(episode,indent=2));notes={};scores=[];traces=[]
    for case in episode['cases']:
        obs=observation(case);prior=dict(notes);arms={}
        for arm,n in [('baseline',{}),('memory',prior)]:arms[arm]=cache.answer(obs,n,case['questions'])
        for q in case['questions']:
            t=case['truth'][q['id']];row={'session':case['session'],'question':q,'truth':t,'prior_notes':prior}
            for arm,result in arms.items():row[arm]={'answer':result['answers'].get(q['id']),'valid':result['valid'],'correct':result['valid'] and result['answers'].get(q['id'])==t['answer'],'cache_key':result['cache_key']}
            scores.append(row)
            with (output/'scores.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
        trace=manager.update(obs,notes);trace.update(session=case['session'],observation=obs,notes_before=prior,notes_after=dict(notes));traces.append(trace)
        with (output/'note_traces.jsonl').open('a') as f:f.write(json.dumps(trace)+'\n')
        print(json.dumps({'session_done':case['session']+1,'finished':trace['finished'],'notes':notes}),flush=True)
    def summarize(rows):return {'questions':len(rows),**{a:{'correct':sum(r[a]['correct'] for r in rows),'accuracy':sum(r[a]['correct'] for r in rows)/len(rows) if rows else None,'invalid':sum(not r[a]['valid'] for r in rows)} for a in ('baseline','memory')}}
    result={'overall':summarize(scores),'earlier_session_evidence':summarize([r for r in scores if r['truth']['earlier_session_required']]),'current_session_evidence':summarize([r for r in scores if not r['truth']['earlier_session_required']]),'historical':summarize([r for r in scores if r['truth']['historical']]),'per_session':[{'session':c['session']+1,**summarize([r for r in scores if r['session']==c['session']])} for c in episode['cases']],'paired':{'memory_only':sum(r['memory']['correct'] and not r['baseline']['correct'] for r in scores),'baseline_only':sum(r['baseline']['correct'] and not r['memory']['correct'] for r in scores),'both_correct':sum(r['baseline']['correct'] and r['memory']['correct'] for r in scores),'both_wrong':sum(not r['baseline']['correct'] and not r['memory']['correct'] for r in scores)},'note_rounds':sum(len(t['rounds']) for t in traces),'invalid_note_rounds':sum(not r['valid'] for t in traces for r in t['rounds']),'note_sessions_finished':sum(t['finished'] for t in traces),'actual_answer_model':cache.actual_model,'api_calls_this_process':cache.calls,'cache_hits':cache.hits}
    (output/'metrics.json').write_text(json.dumps(result,indent=2));return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--episode',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--cache',type=Path,required=True);p.add_argument('--credentials',type=Path,required=True);p.add_argument('--adapter',type=Path);a=p.parse_args();cfg=json.loads(a.config.read_text());load_credentials(a.credentials);identity=verify_snapshot(cfg['model_path'],a.manifest);model,tok=load_model(cfg,a.adapter);cache=AnswerCache(a.cache,Luna(cfg['answer_model']),cfg['answer_model'],max_calls=80)
    episode=json.loads(a.episode.read_text());result=evaluate_episode(episode,NativeRollout(model,tok,cfg),cache,a.output)
    (a.output/'run_config.json').write_text(json.dumps({'config':cfg,'model_revision':identity['revision'],'adapter':str(a.adapter) if a.adapter else None,'weight_training':False,'note_system':__import__('prompt_policy_llm.explicit_note_coverage',fromlist=['SYSTEM']).SYSTEM,'cache_policy':'identical payloads share draws'},indent=2));print(json.dumps(result),flush=True)
if __name__=='__main__':main()
