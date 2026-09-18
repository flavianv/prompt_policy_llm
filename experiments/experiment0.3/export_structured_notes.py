"""Offline, deterministic revealed-prefix export. No model imports or API calls."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from prompt_policy_llm.explicit_memory import observation
from prompt_policy_llm.structured_notes import SCHEMA, SYSTEM, ADDRESS_GUIDE, VERSION, gold_notes, score_extractions, flatten_profile


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def export(source,output):
    output.mkdir(parents=True,exist_ok=False)
    write(output/'schema.json',SCHEMA);write(output/'address_guide.json',ADDRESS_GUIDE)
    (output/'policy_system.txt').write_text(SYSTEM+'\n')
    users=[];examples=[];hashes={};checks=[]
    metadata=json.loads((source/'manifest.json').read_text())['users']
    for meta in metadata:
        uid=meta['user'];profile_path=source/uid/'profile/profile.json';episode_path=source/uid/'sessions/episode.json'
        profile=json.loads(profile_path.read_text());episode=json.loads(episode_path.read_text())
        split='dev' if int(uid[4:])<=5 else 'train' if int(uid[4:])<=8 else 'validation'
        public=[]
        for i,case in enumerate(episode['cases']):
            target=gold_notes(profile,episode['cases'][:i+1])
            rel=f'evaluator_only/{uid}/session{i+1:02d}.json';write(output/rel,target)
            result=score_extractions(json.dumps(target),target)
            assert result['exact_state'] and result['reward']==len(flatten_profile(target['profile']))
            public.append({'session':case['session'],'observation':observation(case)})
            examples.append({'user':uid,'split':split,'session':case['session'],'public_trajectory':f'public/{uid}.json','public_session_index':i,'evaluator_only_target':rel,'previous_notes_source':'policy-generated prefix only; never a gold target','target_fact_count':len(flatten_profile(target['profile']))})
            checks.append({'user':uid,'session':i,'target_facts':len(flatten_profile(target['profile'])),'self_score':result['reward']})
        write(output/f'public/{uid}.json',{'user':uid,'sessions':public})
        users.append({'user':uid,'name':meta['name'],'split':split,'sessions':len(public),'profile_sha256':hashlib.sha256(profile_path.read_bytes()).hexdigest(),'episode_sha256':hashlib.sha256(episode_path.read_bytes()).hexdigest()})
    for split in ['train','dev','validation']:
        with (output/f'{split}_examples.jsonl').open('w') as f:
            for row in examples:
                if row['split']==split:f.write(json.dumps(row)+'\n')
    first=json.loads((output/'evaluator_only/user01/session01.json').read_text());middle=json.loads((output/'evaluator_only/user01/session05.json').read_text());final=json.loads((output/'evaluator_only/user01/session10.json').read_text())
    demo=[]
    variants={'perfect':deepcopy(first),'one_missing':deepcopy(first),'wrong_value':deepcopy(first),'list_superset':deepcopy(first),'duplicate_address':deepcopy(first),'hidden_unknown':deepcopy(first)}
    variants['one_missing']['profile']['personal'].pop('name')
    variants['wrong_value']['profile']['personal']['name']='Wrong Name'
    pants=next(c for c in variants['list_superset']['profile']['category_profiles'] if c['category']=='pants');pants['scoped_overrides'][0]['preferences']['materials'].append('wool')
    variants['duplicate_address']['profile']['category_profiles'].append(deepcopy(first['profile']['category_profiles'][0]))
    variants['hidden_unknown']['profile']['physical']={'hair_color':None}
    variants['no_history']=deepcopy(first);variants['no_history'].pop('history')
    for name,candidate in variants.items():demo.append({'name':name,'candidate':candidate,'score':score_extractions(json.dumps(candidate),first)})
    demo.append({'name':'invalid_json','candidate_raw':'{','score':score_extractions('{',first)})
    write(output/'scoring_examples.json',demo)
    preview=['# Evaluator-only structured targets: first / middle / final', 'Deterministically derived from existing Maya events. These are gold targets, NOT model outputs and NOT policy inputs. No new sessions, wording changes, model calls or training.',
        'One atomic extraction is one unique scoped ORIGINAL profile attribute with its complete typed current value. Lists and composite values count once; intent status and deadline count separately. History is optional metadata and is NOT required for current-field credit. Reward is the raw correct count; correct/target is a diagnostic only.']
    for title,doc in [('Session1',first),('Session5',middle),('Session10',final)]:preview.extend([f'## {title}',f"Maximum reward: {len(flatten_profile(doc['profile']))}.",'Primary target below is the partial original profile. Optional history and execution metadata are in the corresponding evaluator_only/user01/sessionXX.json file.', '```json\n'+json.dumps(doc['profile'],ensure_ascii=False,indent=2)+'\n```'])
    (output/'EXAMPLES.md').write_text('\n\n'.join(preview)+'\n')
    write(output/'validation.json',{'prefix_targets':len(checks),'self_score_checks_passed':True,'checks':checks,'external_calls':0})
    for file in sorted(output.rglob('*')):
        if file.is_file():hashes[str(file.relative_to(output))]=hashlib.sha256(file.read_bytes()).hexdigest()
    manifest={'version':VERSION,'complete':True,'source_dataset':str(source),'users':users,'total_sessions':len(examples),'split_sessions':{s:sum(e['split']==s for e in examples) for s in ['train','dev','validation']},
      'split_limitations':'user01–03 inspected in depth; user04 and eight sessions of user05 evaluated in overshoot, so all01–05 are development. Users06–08 training;09–10 reserved existing-cohort validation, NOT pristine confirmatory test. All profiles share templates and design; labels exported/validated offline. No fresh unseen-user cohort claimed.',
      'policy_input_boundary':'Only public current observation and own previous predicted notes. Gold paths/counts/splits/profile metadata stay outside model payload. Training examples are rollout descriptors, NOT teacher-forced previous-gold SFT pairs.',
      'reward':'Unnormalized integer number of correct current original-profile fields (scope + typed value); no history requirement. Invalid document reward0. No utility, F1, cost or unsupported-fact penalty. Extra wrong addresses give no credit but do not subtract correctly recovered facts; diagnostics and exact-state flag expose this limitation.',
      'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),Path(__file__).parents[2]/'src/prompt_policy_llm/structured_notes.py',Path(__file__).parents[2]/'src/prompt_policy_llm/structured_note_records.py']},'files_sha256':hashes}
    write(output/'manifest.json',manifest)
    return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    m=export(a.source,a.output);print(json.dumps({'users':len(m['users']),'targets':m['total_sessions'],'splits':m['split_sessions']}))
