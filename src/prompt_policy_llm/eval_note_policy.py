"""Matched sequential frozen/adapted Qwen notes versus no-memory Luna."""
import argparse,json,hashlib,importlib.metadata as metadata,time
from copy import deepcopy
from pathlib import Path
from datetime import datetime,timezone
from .note_model import load_model,verify_snapshot
from .note_rollouts import NativeRollout
from .note_reward import AnswerCache
from .explicit_memory import Luna,observation
from .adaptgym_pilot import load_credentials
from .note_eval_log import start_log,append_session

def evaluate_episode(episode,manager,cache,output,run_config=None):
    output.mkdir(parents=True,exist_ok=False);(output/'episode.json').write_text(json.dumps(episode,indent=2));notes={};scores=[];traces=[]
    if run_config is not None:(output/'run_config.json').write_text(json.dumps(run_config,indent=2))
    start_log(output,run_config or {})
    for case in episode['cases']:
        started=datetime.now(timezone.utc).isoformat()
        obs=observation(case);prior=dict(notes);arms={}
        for arm,n in [('baseline',{}),('memory',prior)]:arms[arm]=cache.answer(obs,n,case['questions'])
        for q in case['questions']:
            t=case['truth'][q['id']];row={'session':case['session'],'question':q,'truth':t,'prior_notes':prior}
            for arm,result in arms.items():row[arm]={'answer':result['answers'].get(q['id']),'valid':result['valid'],'correct':result['valid'] and result['answers'].get(q['id'])==t['answer'],'cache_key':result['cache_key']}
            scores.append(row)
            with (output/'scores.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
        answered=datetime.now(timezone.utc).isoformat()
        trace=manager.update(obs,notes);trace.update(session=case['session'],observation=obs,notes_before=prior,notes_after=dict(notes))
        def note_size(n):
            serialized=json.dumps(n)
            tokenizer=getattr(manager,'tokenizer',None)
            return {'count':len(n),'words':sum(len(v.split()) for v in n.values()),'serialized_tokens':len(tokenizer.encode(serialized,add_special_tokens=False)) if tokenizer else None}
        trace.update(started_at=started,answered_at=answered,updated_at=datetime.now(timezone.utc).isoformat(),size_before=note_size(prior),size_after=note_size(notes))
        traces.append(trace)
        with (output/'note_traces.jsonl').open('a') as f:f.write(json.dumps(trace)+'\n')
        append_session(output,case,trace,scores)
        print(json.dumps({'session_done':case['session']+1,'finished':trace['finished'],'notes':notes}),flush=True)
    def summarize(rows):return {'questions':len(rows),**{a:{'correct':sum(r[a]['correct'] for r in rows),'accuracy':sum(r[a]['correct'] for r in rows)/len(rows) if rows else None,'invalid':sum(not r[a]['valid'] for r in rows)} for a in ('baseline','memory')}}
    result={'overall':summarize(scores),'earlier_session_evidence':summarize([r for r in scores if r['truth']['earlier_session_required']]),'current_session_evidence':summarize([r for r in scores if not r['truth']['earlier_session_required']]),'historical':summarize([r for r in scores if r['truth']['historical']]),'per_session':[{'session':c['session']+1,**summarize([r for r in scores if r['session']==c['session']])} for c in episode['cases']],'paired':{'memory_only':sum(r['memory']['correct'] and not r['baseline']['correct'] for r in scores),'baseline_only':sum(r['baseline']['correct'] and not r['memory']['correct'] for r in scores),'both_correct':sum(r['baseline']['correct'] and r['memory']['correct'] for r in scores),'both_wrong':sum(not r['baseline']['correct'] and not r['memory']['correct'] for r in scores)},'note_rounds':sum(len(t['rounds']) for t in traces),'invalid_note_rounds':sum(not r['valid'] for t in traces for r in t['rounds']),'note_sessions_finished':sum(t['finished'] for t in traces),'actual_answer_model':cache.actual_model,'api_calls_this_process':cache.calls,'cache_hits':cache.hits}
    (output/'metrics.json').write_text(json.dumps(result,indent=2));return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--episode',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--cache',type=Path,required=True);p.add_argument('--credentials',type=Path,required=True);p.add_argument('--adapter',type=Path);a=p.parse_args();cfg=json.loads(a.config.read_text());load_credentials(a.credentials);identity=verify_snapshot(cfg['model_path'],a.manifest);model,tok=load_model(cfg,a.adapter);cache=AnswerCache(a.cache,Luna(cfg['answer_model']),cfg['answer_model'],max_calls=20,max_tokens=cfg['answer_max_output_tokens'])
    from .explicit_note_coverage import SYSTEM,CHECK
    from .explicit_note_tools import TOOLS
    from .note_reward import ANSWER_PROMPT
    import torch
    run_config={'config':cfg,'model_revision':identity['revision'],'adapter':str(a.adapter) if a.adapter else None,'weight_training':False,'note_system':SYSTEM,'coverage_check':CHECK,'tools':TOOLS,'answer_system':ANSWER_PROMPT,'cache_policy':'identical payloads share draws','cache_directory':str(a.cache),'note_decoding':{'do_sample':False,'enable_thinking':False,'max_new_tokens':cfg['note_max_output_tokens']},'versions':{k:metadata.version(k) for k in ['torch','transformers','peft','openai']},'gpu':torch.cuda.get_device_name(0),'all_weights_frozen':not any(p.requires_grad for p in model.parameters()),'episode_sha256':hashlib.sha256(a.episode.read_bytes()).hexdigest(),'source_sha256':{name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest() for name in ['eval_note_policy.py','note_eval_log.py','note_rollouts.py','note_reward.py','note_model.py','explicit_note_tools.py','explicit_note_coverage.py','explicit_memory.py']}}
    episode=json.loads(a.episode.read_text());start=time.perf_counter();result=evaluate_episode(episode,NativeRollout(model,tok,cfg),cache,a.output,run_config)
    result['wall_seconds']=time.perf_counter()-start;result['peak_gpu_memory_bytes']=torch.cuda.max_memory_allocated();(a.output/'metrics.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
if __name__=='__main__':main()
