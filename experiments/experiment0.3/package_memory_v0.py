"""Package original100 train sessions and fresh20 held-out sessions for the Hub."""
import argparse,hashlib,json,shutil
from pathlib import Path
from prompt_policy_llm.explicit_memory import observation
from prompt_policy_llm.structured_notes import gold_notes,flatten_profile
from prompt_policy_llm.structured_note_rollouts import cumulative_observation,render_policy_input
from prompt_policy_llm.text_note_updates import SYSTEM,merge_lines,score_text_notes,value_signature


def value_text(value):
    if value is None:return 'unknown'
    if isinstance(value,list):return ', '.join(value_text(v) for v in value) if value else 'no preference'
    if isinstance(value,dict):return ', '.join(value_text(v) for v in value.values())
    if isinstance(value,(int,float)) and not isinstance(value,bool):return format(value,'g')
    return str(value)


def reference_notes(target):
    lines=[]
    for fact in flatten_profile(target['profile']).values():
        a=fact['address'];parts=[]
        for k,v in a.items():
            if k=='section' and v in {'personal','general','clothing','physical'}:continue
            if isinstance(v,dict):parts.extend(str(x) for x in v.values() if x is not None)
            elif v is not None:parts.append(str(v).replace('_',' '))
        lines.append(' '.join(parts)+': '+value_text(fact['value']))
    return '\n'.join(lines)


def package(train,test,out):
    out.mkdir(exist_ok=False,parents=True);(out/'data').mkdir();(out/'profiles').mkdir();evalroot=out/'evaluation_data';evalroot.mkdir();allusers=[];counts={};profilehashes={};names={};rows_by_split={}
    for split,source in [('train',train),('test',test)]:
        manifest=json.loads((source/'manifest.json').read_text());rows=[];profiles=[]
        for user in manifest['users']:
            uid=user['user'];profile_path=source/uid/'profile/profile.json';profile=json.loads(profile_path.read_text());episode=json.loads((source/uid/'sessions/episode.json').read_text())
            assert uid not in profilehashes;profilehashes[uid]=hashlib.sha256(profile_path.read_bytes()).hexdigest();names[uid]=profile['personal']['name']
            profiles.append({'user_id':uid,'profile_json':json.dumps(profile,ensure_ascii=False),'profile_sha256':profilehashes[uid]})
            public=[{'session':c['session'],'observation':observation(c)} for c in episode['cases']]
            (evalroot/'public').mkdir(exist_ok=True);(evalroot/'public'/f'{uid}.json').write_text(json.dumps({'user':uid,'sessions':public},ensure_ascii=False,indent=2)+'\n')
            for i,case in enumerate(episode['cases']):
                target=gold_notes(profile,episode['cases'][:i+1]);completion=reference_notes(target);score=score_text_notes(merge_lines({},completion),target);assert score['exact_state'],(uid,i,score)
                obs=cumulative_observation(public,i);prompt=render_policy_input(obs,{'entries':[]})
                targetdir=evalroot/'evaluator_only'/uid;targetdir.mkdir(parents=True,exist_ok=True);(targetdir/f'session{i+1:02d}.json').write_text(json.dumps(target,ensure_ascii=False,indent=2)+'\n')
                values=sorted({json.dumps(value_signature(f['value'])) for f in flatten_profile(target['profile']).values()})
                rows.append({'id':f'{uid}-session{i+1:02d}','user_id':uid,'session_index':i,'split':split,'current_time':obs['current_time'],'system':SYSTEM,'prompt':prompt,'completion':completion,'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':prompt},{'role':'assistant','content':completion}],'target_profile_json':json.dumps(target['profile'],ensure_ascii=False),'target_value_signatures':values,'target_value_count':score['target_count'],'profile_sha256':profilehashes[uid]})
            allusers.append({'user':uid,'name':profile['personal']['name'],'sessions':len(public),'split':split})
        with (out/'data'/f'{split}.jsonl').open('w') as f:
            for row in rows:f.write(json.dumps(row,ensure_ascii=False)+'\n')
        with (out/'profiles'/f'{split}.jsonl').open('w') as f:
            for row in profiles:f.write(json.dumps(row,ensure_ascii=False)+'\n')
        counts[split]={'users':len(profiles),'sessions':len(rows)};rows_by_split[split]=rows
    assert counts=={'train':{'users':10,'sessions':100},'test':{'users':2,'sessions':20}}
    train_names={u['name'] for u in allusers if u['split']=='train'};test_names={u['name'] for u in allusers if u['split']=='test'};assert train_names.isdisjoint(test_names)
    assert len(set(profilehashes.values()))==12
    files={str(p.relative_to(evalroot)):hashlib.sha256(p.read_bytes()).hexdigest() for p in evalroot.rglob('*') if p.is_file()}
    (evalroot/'manifest.json').write_text(json.dumps({'version':'partial-profile-notes-v1','complete':True,'users':allusers,'files_sha256':files},indent=2)+'\n')
    provenance={'version':'v0','splits':counts,'user_disjoint':True,'profile_hash_disjoint':True,'canonical_references_self_score':True,'train_source':str(train),'test_source':str(test),'profiles_sha256':profilehashes,'training_checkpoint_source_commit':'bf6422316125c6a8376d5e7da18e3582c9747311','frozen_test_policy':'No training or tuning on test users. Evaluate frozen and saved GRPO checkpoint.','limitations':'Fresh users/session seeds, same schema/templates and fixed temporal probes. Canonical full-note SFT references from cumulative revealed prefix; no teacher-forced previous gold memory.'}
    (out/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    (out/'README.md').write_text('''---
language:
- en
task_categories:
- text-generation
configs:
- config_name: default
  data_files:
  - split: train
    path: data/train.jsonl
  - split: test
    path: data/test.jsonl
---
# Prompt Policy Memory v0

Synthetic profile-memory data: **100 training sessions from10users;20test sessions from2fresh users**. Test users were generated after the GRPO checkpoint was frozen and must not be used for training or tuning.

Each row includes cumulative plain-text session input, a canonical plain-text key:value reference, chat messages, and evaluator-only target data. `messages` can be used for supervised fine-tuning. The reference contains all currently revealed facts; it does not inject gold previous notes. The GRPO runtime instead carries its own predicted notes and emits sparse updates.

## Fields

- `prompt`: raw chronological sessions1..t with timestamps and empty initial notes; no future statements or profile JSON.
- `completion`: deterministic canonical full notes, one descriptive key:value per line.
- `messages`: system, user prompt, assistant reference.
- `target_profile_json`, `target_value_signatures`, `target_value_count`: evaluator labels; never add them to model input.
- `user_id`, `session_index`, `profile_sha256`: grouping and provenance.

## Evaluation

The user-selected reward counts unique normalized values in the intersection of notes and targets, ignoring keys. Case, punctuation, collection order and a small unit-alias table are normalized; ISO dates remain intact. This measures value recall, not correct attribute assignment. Duplicate values count once. Unsupported values do not reduce reward; report their count and value precision separately.

The public train split is already used by one BF16 Qwen3-4B LoRA GRPO run. The test split contains new Luna-generated coherent profiles and new deterministic session seeds. It shares the original schema, templates and fixed temporal probes, so it is a same-generator unseen-user test, not an independent-domain benchmark.

## Reproduction and provenance

`profiles/` contains synthetic full profiles for reproducibility. `evaluation_data/` separates public observations from private prefix targets. `provenance.json` records user separation and hashes. Keep all sessions of a user in the same split. The dataset contains no real user records.
''')
    (out/'files_sha256.json').write_text(json.dumps({str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file()},indent=2)+'\n')
    return provenance

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--train',type=Path,required=True);p.add_argument('--test',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();print(json.dumps(package(a.train,a.test,a.output)))
