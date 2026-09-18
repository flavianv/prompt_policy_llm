from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import pytest
from prompt_policy_llm.structured_notes import (gold_notes,score_extractions,flatten_profile,
    parse_document,empty_notes,policy_payload,VERSION)
from prompt_policy_llm.structured_note_rollouts import collect_candidates
from prompt_policy_llm.train_structured_grpo import score_candidates

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'experiments/experiment0.2/dataset_v1'


def source(uid='user01'):
    return (json.loads((DATA/uid/'profile/profile.json').read_text()),
            json.loads((DATA/uid/'sessions/episode.json').read_text()))


def score(doc,gold):return score_extractions(json.dumps(doc),gold)


def category(doc,name):return next(c for c in doc['profile']['category_profiles'] if c['category']==name)


def intent(doc,name):return next(i for i in doc['profile']['purchase_intents'] if i['id']==name)


def test_all_100_prefix_targets_match_oracle_and_original_profile_types():
    count=0
    for uid in sorted(p.name for p in DATA.glob('user*')):
        profile,ep=source(uid)
        for i,case in enumerate(ep['cases']):
            gold=gold_notes(profile,ep['cases'][:i+1]);result=score(gold,gold)
            assert result['exact_state'] and result['reward']==len(flatten_profile(gold['profile']))
            assert result['missing']==result['incorrect']==result['unsupported']==0
            # No unrelated profile fields or inferred age are filled.
            assert 'profile_id' not in gold['profile'] and 'reference_date' not in gold['profile']
            assert 'age' not in gold['profile'].get('personal',{})
            count+=1
    assert count==100


def test_prefix_excludes_future_and_hidden_profile_values():
    profile,ep=source();prefix=deepcopy(ep['cases'][:1]);gold=gold_notes(profile,prefix)
    profile['physical']['hair_color']='invented future color'
    profile['languages']=[{'language':'Klingon','proficiency':'native'}]
    ep['cases'][-1]['events'][0]['value']='future corruption'
    assert gold_notes(profile,prefix)==gold
    assert 'physical' not in gold['profile'] and 'languages' not in gold['profile']
    assert gold['profile']['personal']=={'name':'Maya Okafor'}


def test_current_field_credit_does_not_require_history():
    p,ep=source();gold=gold_notes(p,ep['cases'][:5]);doc=deepcopy(gold);doc.pop('history')
    result=score(doc,gold)
    assert result['exact_state'] and result['reward']==result['target_count'] and result['history_diagnostic']['correct']==0
    doc=deepcopy(gold);name=next(h for h in doc['history'] if h['address']=={'section':'personal','field':'name'})
    name['events'][0]['value']='Wrong historical name'
    assert score(doc,gold)['reward']==result['reward'] and not score(doc,gold)['history_diagnostic']['exact']


def test_unknown_empty_and_hidden_default_credit():
    p,ep=source();gold=gold_notes(p,ep['cases'][:1]);total=score(gold,gold)['reward']
    assert category(gold,'hats')['default_size'] is None
    assert category(gold,'accessories')['preferences']['patterns']==[]
    doc=deepcopy(gold);category(doc,'accessories')['preferences']['patterns']=None
    assert score(doc,gold)['reward']==total-1 and score(doc,gold)['incorrect']==1
    doc=deepcopy(gold);doc['profile']['physical']={'hair_color':None}
    result=score(doc,gold);assert result['reward']==total and result['unsupported']==1 and not result['exact_state']


def test_collections_exact_unordered_not_subset_or_superset_and_no_duplicates():
    p,ep=source();gold=gold_notes(p,ep['cases'][:1]);total=score(gold,gold)['reward']
    doc=deepcopy(gold);m=category(doc,'pants')['scoped_overrides'][0]['preferences'];m['materials'].reverse()
    assert score(doc,gold)['reward']==total
    for changed in [['cotton'],['linen','cotton','wool']]:
        doc=deepcopy(gold);category(doc,'pants')['scoped_overrides'][0]['preferences']['materials']=changed
        assert score(doc,gold)['reward']==total-1
    doc=deepcopy(gold);category(doc,'pants')['scoped_overrides'][0]['preferences']['materials']=['linen','linen','cotton']
    assert not score(doc,gold)['schema_valid'] and score(doc,gold)['reward']==0


def test_duplicate_identity_and_json_keys_cannot_collect_credit():
    p,ep=source();gold=gold_notes(p,ep['cases'][:1]);doc=deepcopy(gold)
    doc['profile']['category_profiles'].append(deepcopy(doc['profile']['category_profiles'][0]))
    assert score(doc,gold)['reward']==0 and not score(doc,gold)['schema_valid']
    raw=json.dumps(gold).replace('"name": "Maya Okafor"','"name":"Wrong", "name":"Maya Okafor"')
    assert score_extractions(raw,gold)['reward']==0
    for raw in ['{','```json\n'+json.dumps(gold)+'\n```',json.dumps(gold).replace('null','NaN')]:
        assert not score_extractions(raw,gold)['schema_valid']


def test_scope_wrong_values_and_stale_state_are_not_correct():
    p,ep=source();gold=gold_notes(p,ep['cases'][:5]);total=score(gold,gold)['reward']
    doc=deepcopy(gold);intent(doc,'urgent-gift')['status']='active'
    assert score(doc,gold)['reward']==total-1 and score(doc,gold)['incorrect']==1
    doc=deepcopy(gold);category(doc,'pants')['scoped_overrides'][0]['context']['season']='winter'
    result=score(doc,gold);assert result['reward']==total-1 and result['missing']==1 and result['unsupported']==1
    doc=deepcopy(gold);intent(doc,'future-trip')['recipient']='gift'
    assert score(doc,gold)['reward']==total-2  # status + deadline both require correct recipient scope


def test_temporary_expiry_and_inclusive_intent_deadline_unchanged():
    p,ep=source();prefix=deepcopy(ep['cases'][:2]);until=prefix[1]['events'][0]['until']
    prefix[-1]['current_time']='2026-03-09T08:59:59Z'
    active=gold_notes(p,prefix)
    assert category(active,'pants')['scoped_overrides'][0]['preferences']['materials']==prefix[1]['events'][0]['value']
    prefix[-1]['current_time']=until;restored=gold_notes(p,prefix)
    assert category(restored,'pants')['scoped_overrides'][0]['preferences']['materials']==['linen','cotton']
    prefix=deepcopy(ep['cases'][:1]);prefix[0]['current_time']='2026-03-02T18:00:00Z'
    assert intent(gold_notes(p,prefix),'urgent-gift')['status']=='active'
    prefix[0]['current_time']='2026-03-02T18:00:01Z'
    assert intent(gold_notes(p,prefix),'urgent-gift')['status']=='expired'


def test_corrections_retractions_and_repeats():
    p,ep=source();prefix=deepcopy(ep['cases'][:5]);case=prefix[-1]
    event=next(e for e in case['events'] if e.get('key')=='preference:2')
    case['events'].append({**event,'id':'correction','timestamp':'2026-03-31T09:00:59Z','value':'retracted','kind':'change','text':'Explicit retraction.'})
    gold=gold_notes(p,prefix)
    assert gold['profile']['general_preferences'][0]['stance']=='retracted'
    history=next(h for h in gold['history'] if h['address'].get('section')=='preference')['events']
    assert [e['value'] for e in history]==['dislike','retracted']
    assert len(next(h for h in gold['history'] if h['address']=={'section':'personal','field':'name'})['events'])==1


def test_policy_prefix_uses_only_own_predictions_and_candidate_states_are_isolated():
    p,ep=source();public=[{'session':c['session'],'observation':policy_payload(c,empty_notes())['current_session']} for c in ep['cases']]
    seen=[]
    class Manager:
        def update(self,obs,notes,sample=False):
            seen.append((deepcopy(obs),deepcopy(notes),sample))
            notes.update(as_of=obs['current_time'],profile={'personal':{'name':'OWN_PREDICTION'}})
            return {'finished':True,'raw_output':json.dumps(notes),'segments':[]}
    prior,prefix,candidates=collect_candidates(Manager(),public,2,4)
    assert len(prefix)==2 and len(candidates)==4 and prior['profile']['personal']['name']=='OWN_PREDICTION'
    assert seen[0][1]['profile']=={}
    assert all(x[1]['profile']['personal']['name']=='OWN_PREDICTION' for x in seen[1:])
    assert all(set(x[0])=={'current_time','statements'} for x in seen)
    candidates[0]['notes']['profile']['personal']['name']='MUTATED'
    assert candidates[1]['notes']['profile']['personal']['name']=='OWN_PREDICTION'
    assert prior['profile']['personal']['name']=='OWN_PREDICTION'
    # Scoring is a separate post-rollout function with no client/manager argument.
    gold=gold_notes(p,ep['cases'][:3]);score_candidates(candidates,gold)
    assert all(c['reward']['reward']==0 for c in candidates)


def test_export_user_splits_gold_separation_and_examples():
    root=ROOT/'experiments/experiment0.3/structured_notes_v1';m=json.loads((root/'manifest.json').read_text())
    assert m['total_sessions']==100 and m['split_sessions']=={'train':30,'dev':50,'validation':20}
    assert len({u['user'] for u in m['users']})==10
    assert all(u['split']=='dev' for u in m['users'] if int(u['user'][4:])<=5)
    for f in (root/'public').glob('*.json'):
        text=f.read_text();rows=json.loads(text)['sessions'];assert len(rows)==10
        assert all(set(row)=={'session','observation'} for row in rows)
        assert all(set(row['observation'])=={'current_time','statements'} for row in rows)
        assert not any(k in text for k in ['"truth"','"questions"','"revealed_state"','"history"'])
    demos={d['name']:d['score'] for d in json.loads((root/'scoring_examples.json').read_text())}
    assert demos['perfect']['reward']==demos['no_history']['reward']
    assert demos['list_superset']['reward']==demos['perfect']['reward']-1
    assert demos['duplicate_address']['reward']==0


def test_replayed_target_values_match_archived_private_oracle():
    from prompt_policy_llm.structured_note_records import gold_notes as records, address_for, canonical
    for uid in sorted(p.name for p in DATA.glob('user*')):
        p,ep=source(uid)
        for i,case in enumerate(ep['cases']):
            facts={canonical(r['address']):r for r in records(p,ep['cases'][:i+1])['facts']}
            assert len(facts)==len(case['revealed_state'])
            for key,state in case['revealed_state'].items():
                got=facts[canonical(address_for(p,key))]['value']
                if key.startswith('intent:') and key.endswith(':state'):got=got['status']
                assert canonical(got)==canonical(state['value'])


def test_existing_trainer_dispatches_luna_free_mode_without_credentials(monkeypatch,tmp_path):
    import sys,types
    from prompt_policy_llm import train_note_grpo as entry
    from prompt_policy_llm import train_structured_grpo as direct
    cfg=ROOT/'experiments/experiment0.3/structured_config.json'
    calls=[]
    def run(args,config):
        assert args.credentials is None and args.cache is None
        assert config['reward_mode']=='extraction_count' and 'answer_model' not in config
        calls.append(config['reward_mode'])
    def forbidden(*args,**kwargs):raise AssertionError('Luna/credentials must not be used')
    monkeypatch.setitem(sys.modules,'torch',types.SimpleNamespace())
    monkeypatch.setattr(direct,'run',run)
    monkeypatch.setattr(entry,'Luna',forbidden);monkeypatch.setattr(entry,'load_credentials',forbidden)
    monkeypatch.setattr(sys,'argv',['trainer','--config',str(cfg),'--manifest','unused','--data','unused','--output',str(tmp_path/'not-created')])
    entry.main()
    assert calls==['extraction_count'] and not (tmp_path/'not-created').exists()


def test_all100_schedule_includes_every_user_chronologically_regardless_of_old_split():
    from prompt_policy_llm.train_structured_grpo import build_schedule
    m=json.loads((ROOT/'experiments/experiment0.3/structured_notes_v1/manifest.json').read_text())
    c=json.loads((ROOT/'experiments/experiment0.3/structured_all100_config.json').read_text())
    schedule=build_schedule(m,c,100)
    assert len(schedule)==len({(u['user'],s) for u,s in schedule})==100
    for user in m['users']:assert [s for u,s in schedule if u['user']==user['user']]==list(range(10))
    with pytest.raises(AssertionError):build_schedule(m,c,3)


def test_pass4_primary_and_carry_are_not_cherry_picked():
    from prompt_policy_llm.structured_note_rollouts import carry_candidate_zero
    from prompt_policy_llm.eval_structured_notes import group_metrics,summarize
    p,ep=source();gold=gold_notes(p,ep['cases'][:1]);correct={'reward':score(gold,gold),'notes':gold,'trace':{'finished':True}}
    wrong=deepcopy(gold);wrong['profile']['personal']['name']='wrong'
    first={'reward':score(wrong,gold),'notes':wrong,'trace':{'finished':True}}
    candidates=[first,correct,deepcopy(first),deepcopy(correct)];m=group_metrics(candidates)
    assert m['pass_at_4'] and m['candidate0_correct']==8 and m['best_correct']==9 and m['worst_correct']==8
    assert m['mean_correct']==8.5 and m['mean_normalized_correct']==pytest.approx(8.5/9)
    assert carry_candidate_zero(empty_notes(),candidates)==wrong
    candidates[0]['trace']['finished']=False
    assert carry_candidate_zero(empty_notes(),candidates)==empty_notes()
    assert summarize([{'metrics':m}])['primary_mean_normalized_correct']==pytest.approx(8.5/9)
