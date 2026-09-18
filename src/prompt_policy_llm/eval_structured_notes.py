"""Four-sample, chronological structured-note evaluation; no Luna or hidden prompts."""
from copy import deepcopy
import json,time
from pathlib import Path
from .structured_notes import empty_notes,score_extractions
from .structured_note_rollouts import group_from_prior,carry_candidate_zero


def group_metrics(candidates):
    scores=[c['reward'] for c in candidates];counts=[s['correct'] for s in scores];n=scores[0]['target_count']
    assert all(s['target_count']==n for s in scores)
    return {'target_count':n,'candidate0_correct':counts[0],'mean_correct':sum(counts)/len(counts),'best_correct':max(counts),'worst_correct':min(counts),
      'mean_normalized_correct':sum(s['correct']/n for s in scores)/len(scores) if n else 0.,'pass_at_4':any(s['exact_state'] for s in scores),'exact_candidate_count':sum(s['exact_state'] for s in scores),
      'valid_candidates':sum(s['schema_valid'] for s in scores),'candidates':len(scores),
      'mean_missing':sum(s['missing'] for s in scores)/len(scores),'mean_incorrect':sum(s['incorrect'] for s in scores)/len(scores),
      'mean_unsupported':sum(s['unsupported'] for s in scores)/len(scores)}


def summarize(rows):
    metrics=[r['metrics'] for r in rows];den=sum(m['target_count'] for m in metrics)
    result={'sessions':len(rows),'target_fields':den,'candidates':sum(m['candidates'] for m in metrics),'valid_candidates':sum(m['valid_candidates'] for m in metrics),
      'pass_at_4_sessions':sum(m['pass_at_4'] for m in metrics),'exact_candidate_count':sum(m['exact_candidate_count'] for m in metrics),'primary_mean_normalized_correct':sum(m['mean_normalized_correct'] for m in metrics)/len(metrics) if metrics else None}
    for key in ['candidate0_correct','mean_correct','best_correct','worst_correct','mean_missing','mean_incorrect','mean_unsupported']:
        result[key]=sum(m[key] for m in metrics)
    for key in ['candidate0_correct','mean_correct','best_correct','worst_correct']:result[key+'_micro_fraction']=result[key]/den if den else None
    return result


def append_log(path,record):
    text=[f"## Session {record['session']+1}",'Current public input:',json.dumps(record['observation'],ensure_ascii=False,indent=2),
          'OWN notes before:',json.dumps(record['prior_notes'],ensure_ascii=False,indent=2)]
    with path.open('a') as f:
        f.write('\n\n'+text[0]+'\n\n')
        for label,value in zip(text[1::2],text[2::2]):f.write(label+'\n\n```json\n'+value+'\n```\n\n')
        for c in record['candidates']:
            f.write(f"### Candidate {c['candidate']}\n\nExact generated output:\n\n```text\n{c['trace']['raw_output']}\n```\n\n")
            f.write('Computed score:\n\n```json\n'+json.dumps(c['reward'],indent=2)+'\n```\n\n')
        f.write('Carry rule: fixed candidate0; if invalid, retain incoming own notes. No reward-based selection.\n\nNotes after:\n\n```json\n'+json.dumps(record['carried_notes'],ensure_ascii=False,indent=2)+'\n```\n\nGroup metrics:\n\n```json\n'+json.dumps(record['metrics'],indent=2)+'\n```\n')


def evaluate(manager,data,users,output,phase,config):
    import torch
    output=Path(output);output.mkdir(parents=True,exist_ok=False);rows=[];start=time.perf_counter()
    (output/'config.json').write_text(json.dumps({'phase':phase,'config':config,'comparison':'in-sample; all100sessions used for training','carry':'fixed candidate0; invalid retains previous prediction','pass_at_4':'any candidate has exact current revealed state, schema-valid, zero unsupported','decoding':{'do_sample':True,'temperature':1.,'top_p':1.,'top_k':0,'group_size':4}},indent=2))
    for user in users:
        uid=user['user'];d=output/uid;d.mkdir();prior=empty_notes();userrows=[]
        (d/'SESSION_LOG.md').write_text(f'# {phase}: {uid}\n\nFour sampled traces per context; current-field raw counts. All comparisons are in-sample.\n')
        public=json.loads((data/'public'/f'{uid}.json').read_text())['sessions']
        for row in public:
            session=row['session'];torch.manual_seed(config['evaluation_seed']+int(uid[4:])*100+session)
            candidates=group_from_prior(manager,row['observation'],prior,4)
            gold=json.loads((data/'evaluator_only'/uid/f'session{session+1:02d}.json').read_text())
            for c in candidates:c['reward']=score_extractions(c['trace']['raw_output'],gold)
            carried=carry_candidate_zero(prior,candidates)
            record={'user':uid,'session':session,'observation':row['observation'],'prior_notes':deepcopy(prior),'candidates':candidates,'carried_notes':carried,'metrics':group_metrics(candidates)}
            (d/f'session{session+1:02d}.json').write_text(json.dumps(record));append_log(d/'SESSION_LOG.md',record)
            rows.append(record);userrows.append(record);prior=carried
            with (output/'scores.jsonl').open('a') as f:f.write(json.dumps({'user':uid,'session':session,**record['metrics']})+'\n')
            print(json.dumps({'phase':phase,'user':uid,'session_done':session+1,'sessions_complete':len(rows),**record['metrics']}),flush=True)
        (d/'metrics.json').write_text(json.dumps(summarize(userrows),indent=2))
    metrics={**summarize(rows),'wall_seconds':time.perf_counter()-start,'api_calls':0,'phase':phase,'in_sample':True}
    (output/'metrics.json').write_text(json.dumps(metrics,indent=2));print(json.dumps({'phase_complete':phase,'metrics':metrics}),flush=True)
    return metrics
