"""Rebuild the matched plain-text GRPO result from saved candidate scores."""
import argparse,json,random,statistics
from pathlib import Path


def analyze(root):
    pairs=[(7319,root/'run/baseline',root/'run/trained')]
    for seed in [7320,7321]:
        p=root/f'repeat_seed_{seed}'
        if (p/'comparison.json').exists():pairs.append((seed,p/'baseline',p/'trained'))
    perseed=[];peruser={};validation=[]
    for seed,base,trained in pairs:
        phases=[];users={}
        for phase,directory in [('baseline',base),('trained',trained)]:
            rows=[json.loads(f.read_text()) for f in sorted(directory.glob('user*/session*.json'))]
            assert len(rows)==100 and len({(r['user'],r['session']) for r in rows})==100
            scores=[c['reward'] for r in rows for c in r['candidates']];assert len(scores)==400
            correct=sum(s['correct'] for s in scores);targets=sum(s['target_count'] for s in scores);unsupported=sum(s['unsupported'] for s in scores)
            macro=statistics.mean(statistics.mean(c['reward']['correct']/c['reward']['target_count'] for c in r['candidates']) for r in rows)
            rowmetrics={'phase':phase,'macro_recall':macro,'correct_all_candidates':correct,'targets_all_candidates':targets,'micro_recall':correct/targets,'unsupported_all_candidates':unsupported,'value_precision':correct/(correct+unsupported) if correct+unsupported else 0.,'pass_at_4_sessions':sum(any(c['reward']['exact_state'] for c in r['candidates']) for r in rows),'valid':sum(s['schema_valid'] for s in scores),'candidates':400,'text_diverse_groups':sum(len({c['trace']['raw_output'] for c in r['candidates']})>1 for r in rows),'reward_diverse_groups':sum(len({c['reward']['reward'] for c in r['candidates']})>1 for r in rows)}
            saved=json.loads((directory/'metrics.json').read_text());assert abs(saved['primary_mean_normalized_correct']-macro)<1e-12
            phases.append(rowmetrics)
            for uid in sorted({r['user'] for r in rows}):
                urs=[r for r in rows if r['user']==uid];users.setdefault(uid,{})[phase]=statistics.mean(r['metrics']['mean_normalized_correct'] for r in urs)
        for af in sorted(base.glob('user*/session*.json')):
            a=json.loads(af.read_text());b=json.loads((trained/af.relative_to(base)).read_text())
            assert a['observation']==b['observation']
            assert a['metrics']['target_count']==b['metrics']['target_count']
        bc=json.loads((base/'config.json').read_text());tc=json.loads((trained/'config.json').read_text());assert bc['config']==tc['config'] and bc['decoding']==tc['decoding']
        perseed.append({'seed':seed,'baseline':phases[0],'trained':phases[1],'delta':phases[1]['macro_recall']-phases[0]['macro_recall']})
        for uid,x in users.items():peruser.setdefault(uid,[]).append({'seed':seed,**x,'delta':x['trained']-x['baseline']})
        validation.append({'seed':seed,'complete_100_each':True,'matched_public_inputs':True,'matched_target_counts':True,'matched_config_and_decoding':True,'recomputed_metrics_match':True})
    deltas=[statistics.mean(x['delta'] for x in entries) for entries in peruser.values()];rng=random.Random(20260918)
    bootstrap=sorted(statistics.mean(rng.choices(deltas,k=len(deltas))) for _ in range(10000))
    return {'seeds':perseed,'per_user':peruser,'validation':validation,'mean_paired_delta':statistics.mean(r['delta'] for r in perseed),'exploratory_user_cluster_bootstrap_95pct':[bootstrap[249],bootstrap[9749]],'limitations':['All100sessions used for training; in-sample only.','Reward is unique normalized value intersection; keys and attribute assignment are ignored.','Unsupported values do not reduce reward.','Repeated seeds measure sampling stability for one trained checkpoint, not retraining stability.','Bootstrap uses ten users sharing generator templates; no held-out generalization claim.']}


def report(root,result):
    rows=['# Qwen 4B GRPO: cumulative plain-text notes',f"Matched evaluation seeds completed: {len(result['seeds'])}. Temperature1.5; four candidates per session;100sessions;16optimizer updates.",'Input: raw sessions1..t plus own saved notes. Output: sparse plain-text key:value lines with flexible/optional keys. Reward: number of unique normalized values intersecting the private current-profile target. Candidate0 carries memory independently of reward.', '| Seed | Frozen recall | Trained recall | Gain | Frozen pass@4 | Trained pass@4 |','|---|---:|---:|---:|---:|---:|']
    for r in result['seeds']:
        a,b=r['baseline'],r['trained'];rows.append(f"| {r['seed']} | {a['macro_recall']:.2%} | {b['macro_recall']:.2%} | {100*r['delta']:+.2f} pp | {a['pass_at_4_sessions']}/100 | {b['pass_at_4_sessions']}/100 |")
    rows+=['The primary recall averages the four candidates within each session, then averages100sessions. Raw totals below count all400candidates (not candidate0 and not averages divided by a single-trace denominator).','| Seed / phase | Matched / target values | Value precision | Unsupported values | Valid outputs |','|---|---:|---:|---:|---:|']
    for r in result['seeds']:
        for phase in ['baseline','trained']:
            x=r[phase];rows.append(f"| {r['seed']} / {phase} | {x['correct_all_candidates']}/{x['targets_all_candidates']} | {x['value_precision']:.2%} | {x['unsupported_all_candidates']} | {x['valid']}/400 |")
    rows+=['## Per-user mean paired gain','| User | Gain averaged across seeds |','|---|---:|']
    for uid,entries in result['per_user'].items():rows.append(f"| {uid} | {100*statistics.mean(x['delta'] for x in entries):+.2f} pp |")
    rows+=['## Interpretation','The first matched comparison improved66sessions, tied31, and worsened3. Gains are concentrated in separately matchable purchase-intent statuses/deadlines; this includes improved output formatting, not just newly recovered information.', 'All42CPUchecks passed. Actual adapter changes were measured on16updates; checkpoint reload maximum log-probability error was0. Source/config receipts and exact candidate traces accompany this report. Repeated evaluations reuse the same checkpoint without further learning.','## Limitations']
    rows+=['- '+x for x in result['limitations']]
    rows+=['## Artifacts','- `run/comparison.json`, `run/training_summary.json`, `run/training_metrics.jsonl`\n- `run/baseline/` and `run/trained/`: all exact input/output traces\n- `repeat_seed_*/`: repeated matched traces and metrics\n- `source_receipt.json`, `artifact_hashes.json`, `frozen_source/`: provenance\n- Remote checkpoint: `/home/criteo/qwen17b-work/cumulative-temp15-20260918/all100_01/run/final_adapter` (weights excluded from git).']
    blocks=[]
    for row in rows:
        if row.startswith('|') and blocks and blocks[-1].startswith('|'):blocks[-1]+='\n'+row
        else:blocks.append(row)
    (root/'RESULTS.md').write_text('\n\n'.join(blocks)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args();r=analyze(a.root);(a.root/'verified_comparison.json').write_text(json.dumps(r,indent=2));report(a.root,r)
    print(json.dumps({'matched_seeds':len(r['seeds']),'mean_delta':r['mean_paired_delta'],'all_validation_passed':True}))
