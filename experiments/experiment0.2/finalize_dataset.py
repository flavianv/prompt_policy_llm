#!/usr/bin/env python3
"""Finalize saved API profiles offline; never changes prior samples or live run."""
from pathlib import Path
import hashlib,json,shutil,sys
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE.parents[1]/'src'))
from prompt_policy_llm.explicit_memory import generate_sessions,export_sessions,resolve_events,profile_facts
from prompt_policy_llm.profile_contract import validate_profile
out=HERE/'dataset_v1';out.mkdir(exist_ok=False);source=HERE/'remote_artifacts/cohort';cfg=json.loads((HERE/'config.json').read_text());records=[]
shutil.copytree(source/'profile_contract_snapshot',out/'profile_contract_snapshot');shutil.copy2(HERE/'config.json',out/'config.json');shutil.copy2(HERE.parents[1]/'src/prompt_policy_llm/explicit_memory.py',out/'session_generator_snapshot.py')
for i in range(1,11):
 uid=f'user{i:02d}';dest=out/uid;dest.mkdir();shutil.copytree(source/uid/'profile',dest/'profile');p=json.loads((dest/'profile/profile.json').read_text());fixed=json.loads((dest/'profile/fixed_constraints.json').read_text());assert not validate_profile(p,fixed)
 conf=dict(cfg,seed=17+i-1);ep=generate_sessions(p,conf);sess=dest/'sessions';sess.mkdir();export_sessions(ep,sess);(sess/'episode.json').write_text(json.dumps(ep,indent=2));(dest/'session_config.json').write_text(json.dumps(conf,indent=2))
 hist={};facts=profile_facts(p)
 for c in ep['cases']:
  assert 6<=len(c['events'])<=10
  for e in c['events']:
   if e['kind']=='repeat':
    expected,_=resolve_events(hist[e['key']],e['timestamp'],facts[e['key']]['kind']);actual=e['value']['status'] if facts[e['key']]['kind']=='intent' else e['value'];assert expected==actual
   elif e['key']:hist.setdefault(e['key'],[]).append(e)
  for q in c['questions']:
   t=c['truth'][q['id']];value,support=resolve_events(hist[t['key']],t['at_time'],t['kind']);assert value==t['value'] and support==t['support_ids']
 records.append({'user':uid,'name':p['personal']['name'],'sessions':10,'questions':sum(len(c['questions']) for c in ep['cases']),'statements':sum(len(c['events']) for c in ep['cases']),'profile_attempts':len(list((dest/'profile').glob('profile_attempt_*.json'))),'actual_model':json.loads((dest/'profile/profile_validation.json').read_text())['actual_model']})
original=json.loads((HERE/'remote_artifacts/live_evaluation/episode.json').read_text());new=json.loads((out/'user01/sessions/episode.json').read_text())
manifest={'users':records,'total_users':10,'total_sessions':100,'total_questions':200,'total_statements':sum(r['statements'] for r in records),'all_profiles_schema_and_fixed_constraints_valid':True,'all_question_keys_and_repetitions_replayed':True,'maya_episode_identical_to_live_run':original==new,'evaluation_scope':'Only Maya live smoke; no other users evaluated. Original live episode preserved in remote_artifacts/live_evaluation.','generation':'One coherent initial profile per user via Luna; sessions and questions generated deterministically from revealed state. No independent clothing-profile generation.','repairs':'Two session-generation failures fixed by resolving repetitions at their statement timestamp. User05 needed a third API profile repair after two invalid stance/effect attempts. All raw attempts preserved.','cohort_initial_batch_seconds':json.loads((source/'manifest.json').read_text())['elapsed_seconds'],'source_sha256':hashlib.sha256((out/'session_generator_snapshot.py').read_bytes()).hexdigest()}
manifest['files_sha256']={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file()};(out/'manifest.json').write_text(json.dumps(manifest,indent=2))
(out/'README.md').write_text('# Experiment0.2 dataset v1\n\nTen actual Luna-generated coherent profiles, 100 sessions, 200 explicit-state questions. Each session has 6–10 natural-language statements including unrelated filler; two questions. Profile and answer key are evaluator-only. Per-user folders contain raw profile calls, constraints, validated profile, readable sessions and answers.\n\n'+manifest['repairs']+'\n\nOnly Maya was evaluated live. That original run remains separately preserved. Maya dataset episode identical to evaluated episode: '+str(original==new)+'.\n')
print(json.dumps({k:v for k,v in manifest.items() if k!='files_sha256'},indent=2))
