"""Schema extension, temporal semantics, support boundaries and paired execution."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import hashlib
import json

import pytest

from prompt_policy_llm import shopping_memory as sm
from prompt_policy_llm.shopping_schema import SchemaEnvironment, current, extend_history, matches


@pytest.fixture
def env():return SchemaEnvironment()


def simple(env,cat='shirts',recipient='self'):
    schema=env.schemas[cat];sizes=[]
    if schema['size_systems']:
        system=next(iter(schema['size_systems']))
        sizes=[{'brand':b,'sizing_system':system,'size':schema['size_systems'][system][0]} for b in schema['attributes']['brand']['values']]
    profile={'category':cat,'sizes':sizes,'hard':[{'field':'price','op':'lte','value':100}],
             'soft':[{'field':'style','op':'eq','value':'floral'}],'valid_from':'2026-01-01T09:00:00Z'}
    intent={'attributes':{'label':'purchase0','category':cat,'recipient':recipient,'sizes':sizes if recipient=='gift' else None,
                         'hard':[],'soft':[],'remove_hard':[],'remove_soft':[],'use_general_preferences':recipient=='self',
                         'exclude_preferences':[],'valid_from':'2026-01-01T09:00:00Z'},
            'status':'active','deadline':None,'source_ids':['e0-1']}
    state={'general':{},'preferences':{},'categories':{cat:{'attributes':profile,'source_ids':['e0-0']}},'intents':{'purchase0':intent}}
    return state,intent


def test_json_only_new_category_and_selection(tmp_path,env):
    spec=deepcopy(env.spec)
    spec['categories']['backpacks']=json.loads((Path(__file__).parent/'fixtures/shopping_backpacks.json').read_text())
    path=tmp_path/'environment.json';path.write_text(json.dumps(spec))
    custom=SchemaEnvironment(json.loads(path.read_text()),['backpacks','shirts'])
    ep=custom.generate_episode(17)
    assert ep['selected_categories']==['backpacks','shirts']
    assert {p['category'] for c in ep['cases'] for q in c['questions'] if q['kind']=='recommendation' for p in q['catalog']}=={'backpacks','shirts'}
    assert any(i['attributes']['category']=='backpacks' for c in ep['cases'] for i in c['hidden_state']['intents'].values())
    for c in ep['cases']:
        for q in c['questions']:
            if q['kind']=='recommendation':
                for p in q['catalog']:
                    custom.validate_product(p)
                    if p['category']=='backpacks':assert 'size' not in p and 'fit' not in p
    assert 'backpacks' in custom.prompts()[0] and 'capacity_l' in custom.prompts()[1]
    out=tmp_path/'custom-run'
    sm.run([ep],sm.MockAnswers(),sm.PromptedNotes(sm.MockGenerator(),environment=custom),out,{'seeds':[17],'split':'eval'},environment=custom)
    assert sm.audit_run(out)['selected_categories']==['backpacks','shirts']
    single=SchemaEnvironment(spec,['backpacks']).generate_episode(29)
    assert all(set(c['hidden_state']['categories'])<= {'backpacks'} for c in single['cases'])
    with pytest.raises(ValueError):SchemaEnvironment(spec,['missing'])


def test_schema_rejects_executable_or_unsupported_operator(env):
    spec=deepcopy(env.spec);spec['categories']['shirts']['profile']['hard'][0]['op']='python:eval'
    with pytest.raises(ValueError):SchemaEnvironment(spec)
    spec=deepcopy(env.spec);spec['categories']['shirts']['attributes']['price']['type']='arbitrary_code'
    with pytest.raises(ValueError):SchemaEnvironment(spec)


def test_seeded_stochastic_trajectories_dates_and_catalog_ids(env):
    a=env.generate_episode(17);assert a==env.generate_episode(17)
    b=env.generate_episode(29);assert a!=b and a!=env.generate_episode(17,'train')
    assert [len(c['evidence']) for c in a['cases']]!=[len(c['evidence']) for c in b['cases']]
    assert [c['current_time'] for c in a['cases']]!=[c['current_time'] for c in b['cases']]
    ids=[p['id'] for c in a['cases'] for q in c['questions'] if q['kind']=='recommendation' for p in q['catalog']]
    assert len(ids)==len(set(ids))
    assert all(a['cases'][i]['current_time']<a['cases'][i+1]['current_time'] for i in range(9))
    assert any('Unrelated observation' in e['text'] for c in a['cases'] for e in c['evidence'])


def test_every_question_supported_by_revealed_prefix_not_future(env):
    ep=env.generate_episode(43);seen={}
    for case in ep['cases']:
        seen.update({e['id']:e['timestamp'] for e in case['evidence']})
        for q in case['questions']:
            t=case['truth'][q['id']]
            assert t['support_ids'] and all(s in seen and seen[s]<=case['current_time'] for s in t['support_ids'])
            if q['kind']=='fact':
                field=q['field'];source=env.spec['general_fields'][field].get('derived',{}).get('source',field)
                assert source in case['hidden_state']['general']
                assert current(case['hidden_state']['general'][source],q['at_time']) is not None
        answer=sm.answer_payload(case,{});note=sm.note_payload(case)
        assert set(answer)=={'current_time','current_session','prior_session_notes','questions'}
        assert set(note)=={'current_time','current_session'}
        for forbidden in ('hidden_state','acceptable_choices','support_ids','base_attributes'):
            assert forbidden not in json.dumps(answer)
        assert 'catalog' not in json.dumps(note) and 'questions' not in note
        for q in case['questions']:
            if q['kind']=='recommendation':
                i=case['hidden_state']['intents'][q['intent']]
                assert case['truth'][q['id']]==env.oracle(case['hidden_state'],i,q['catalog'],case['current_time'])


def test_general_histories_age_and_retraction_are_distinct(env):
    h=[];extend_history(h,'Paris','2026-01-01T00:00:00Z','e0');extend_history(h,'Lyon','2026-01-10T00:00:00Z','e1')
    assert current(h,'2026-01-09T23:59:59Z')['value']=='Paris'
    assert current(h,'2026-01-10T00:00:00Z')['value']=='Lyon'
    assert current(h,'2025-12-31T23:59:59Z') is None
    state,_=simple(env)
    state['general']={'birth_date':[{'value':'1994-09-20','valid_from':'2026-09-01T00:00:00Z','valid_until':None,'source_ids':['e0']}]}
    import random
    old,new=deepcopy(env.spec),deepcopy(env.spec)
    old['generation']['questions'].update(facts=2,preferences=0,recommendations=0,historical_probability=0)
    e=SchemaEnvironment(old)
    for now,age in [('2026-09-19T12:00:00Z',31),('2026-09-20T00:00:00Z',32)]:
        qs,ts=e.questions(state,now,random.Random(1));q=next(q for q in qs if q['field']=='age')
        assert q['options'][ts[q['id']]['answer']]==age
    assert all('age' not in c['hidden_state']['general'] for c in env.generate_episode(71)['cases'])
    history=[];extend_history(history,'dislike','2026-01-01T00:00:00Z','e0');extend_history(history,'retracted','2026-01-02T00:00:00Z','e1')
    assert current(history,'2026-01-02T00:00:00Z')['value']=='retracted'
    assert history[-1]['value']!='like' and history


def test_temporal_deadline_boundaries_persistence_and_explicit_status(env):
    state,intent=simple(env);intent['deadline']='2026-01-02T09:00:00Z'
    assert sm.lifecycle(intent,intent['deadline'])=='active'
    assert sm.lifecycle(intent,'2026-01-02T09:00:01Z')=='expired'
    assert sm.lifecycle(intent,'2026-01-07T09:00:00Z')=='expired'
    intent['deadline']='2026-03-01T09:00:00Z'
    assert sm.lifecycle(intent,'2026-01-11T09:00:00Z')=='active'
    intent['deadline']=None;assert sm.lifecycle(intent,'2028-01-01T00:00:00Z')=='active'
    for status in ('completed','cancelled','uncertain'):
        intent['status']=status;assert sm.lifecycle(intent,'2028-01-01T00:00:00Z')==status
    intent['status']='active';intent['deadline']='2028-02-01T00:00:00Z'
    assert sm.lifecycle(intent,'2028-01-01T00:00:00Z')=='active'


def test_category_scope_gifts_no_demographic_inference_and_temporary_overrides(env):
    state,i=simple(env,'shirts');shoe_state,shoe=simple(env,'shoes')
    shoe_state['categories']['shoes']['attributes']['soft']=[{'field':'style','op':'eq','value':'plain'}]
    state['categories'].update(shoe_state['categories'])
    assert env.effective(state,i)['soft'][0]['value']=='floral'
    assert env.effective(state,shoe)['soft'][0]['value']=='plain'
    before=deepcopy(state['categories']);i['attributes']['hard']=[{'field':'price','op':'lte','value':200}]
    assert env.effective(state,i)['hard']==[{'field':'price','op':'lte','value':200}]
    assert state['categories']==before
    i['attributes']['hard']=[];assert env.effective(state,i)['hard']==before['shirts']['attributes']['hard']
    i['attributes']['recipient']='gift';i['attributes']['sizes']=None
    effective=env.effective(state,i);assert effective['sizes']==[] and effective['hard']==[] and effective['soft']==[]
    state['general']={'gender':[{'value':'woman'}],'height':[{'value':{'value':185,'unit':'cm'}}]}
    assert env.effective(state,i)==effective


def test_brand_dislike_scope_retraction_and_gift(env):
    state,i=simple(env);pid='clothing_brands:global:all:Aster'
    state['preferences'][pid]={'id':pid,'topic':'clothing_brands','item':'Aster','scope':'global','category':None,
       'history':[{'value':'dislike','valid_from':'2026-01-01T00:00:00Z','valid_until':None,'source_ids':['e0']}]}
    assert {'field':'brand','op':'ne','value':'Aster'} in env.effective(state,i)['hard']
    state['preferences'][pid]['history'][-1]['value']='retracted'
    assert all(r['field']!='brand' for r in env.effective(state,i)['hard'])
    state['preferences'][pid]['history'][-1]['value']='like'
    assert {'field':'brand','op':'eq','value':'Aster'} in env.effective(state,i)['soft']
    state['preferences'][pid].update(scope='category',category='shoes')
    assert not any(r['field']=='brand' for r in env.effective(state,i)['soft'])
    state['preferences'][pid].update(scope='global',category=None)
    i['attributes']['recipient']='gift';assert not env.effective(state,i)['soft']


def test_soft_ranking_never_overrides_hard_and_ties_none_unknown(env):
    import random
    state,i=simple(env);attrs=env.effective(state,i);p=env.best_product(attrs,'2026-01-01T00:00:00Z',random.Random(1));p['id']='best'
    lower=deepcopy(p);lower.update(id='lower',style='plain')
    invalid=deepcopy(p);invalid.update(id='invalid',price=200)
    truth=env.oracle(state,i,[p,lower,invalid],'2026-01-01T00:00:00Z')
    assert truth['acceptable_choices']==['best'] and set(truth['feasible_choices'])=={'best','lower'}
    twin=deepcopy(p);twin['id']='twin';assert env.oracle(state,i,[p,twin],'2026-01-01T00:00:00Z')['acceptable_choices']==['best','twin']
    assert env.oracle(state,i,[invalid],'2026-01-01T00:00:00Z')['acceptable_choices']==['NONE']
    unknown=deepcopy(p);unknown.update(id='unknown',sizing_system='US_COLLAR_IN',size='15.5')
    assert env.oracle(state,i,[unknown],'2026-01-01T00:00:00Z')['acceptable_choices']==['ASK_SIZE']
    assert env.oracle(state,i,[unknown,p],'2026-01-01T00:00:00Z')['acceptable_choices']==['best']
    unknown['price']=200;assert env.oracle(state,i,[unknown],'2026-01-01T00:00:00Z')['acceptable_choices']==['NONE']
    q={'kind':'recommendation','catalog':[p,lower,invalid]}
    s=sm.score_answer({'choice':'lower','intent_status':'active'},truth,q,True,env)
    assert not s['correct'] and s['feasible_choice'] and s['preference_regret']==1


def test_brand_category_system_size_keys_not_universal_integer(env):
    state,i=simple(env);attrs=env.effective(state,i);attrs['sizes']=[{'brand':'Aster','sizing_system':'ALPHA','size':'M'},
       {'brand':'Boreal','sizing_system':'ALPHA','size':'L'}]
    p={'brand':'Boreal','sizing_system':'ALPHA','size':'M'}
    assert env.size_status(p,attrs)=='mismatch'
    p['size']='L';assert env.size_status(p,attrs)=='match'
    p['sizing_system']='US_COLLAR_IN';assert env.size_status(p,attrs)=='unknown'
    shoe,_=simple(env,'shoes');assert shoe['categories']['shoes']['attributes']['sizes'][0]['size']!='M'


def test_cross_category_distractors_and_applicable_fields(env):
    ep=env.generate_episode(17)
    for c in ep['cases']:
        for q in c['questions']:
            if q['kind']!='recommendation':continue
            cat=c['truth'][q['id']]['effective_attributes']['category']
            assert sum(p['category']!=cat for p in q['catalog'])>=2
            for p in q['catalog']:
                env.validate_product(p)
                if p['category']!='shoes':assert 'width' not in p and 'comfort' not in p
                if p['category']!=cat:assert env.violations(p,c['truth'][q['id']]['effective_attributes'],None)==['category']


def test_notes_schema_provenance_atomicity_and_diagnostics(env):
    c=env.generate_episode(17)['cases'][0];expected=env.expected_notes(c['hidden_state'],c['current_time']);sources={e['id'] for e in c['evidence']}
    for name,note in expected.items():env.validate_note(name,note,sources)
    diag=env.diagnose(expected,c);assert all(x['attributes_correct'] and x['status_correct'] for x in diag['checks'].values())
    name,note=next(iter(expected.items()));raw=json.dumps({'tool':'put_note','arguments':{'name':name,'note':note}});notes={}
    with pytest.raises(ValueError):sm.apply_call(raw,notes,False,sources,env)
    assert sm.apply_call('{"tool":"read_notes","arguments":{}}',notes,False,sources,env)[1]
    sm.apply_call(raw,notes,True,sources,env);before=deepcopy(notes)
    bad=deepcopy(note);bad['source_ids']=['FUTURE']
    with pytest.raises(ValueError):sm.apply_call(json.dumps({'tool':'put_note','arguments':{'name':name,'note':bad}}),notes,True,sources,env)
    assert notes==before
    with pytest.raises(ValueError):sm.apply_call('{"tool":"read_notes","arguments":{}}',notes,True,sources,env)
    assert sm.apply_call('{"tool":"no_op","arguments":{}}',notes,True,sources,env)[2]


def test_parser_and_all_failures_stay_wrong(env):
    c=env.generate_episode(17)['cases'][0];good={}
    for q in c['questions']:
        t=c['truth'][q['id']];good[q['id']]={'choice':t['acceptable_choices'][0],'intent_status':t['intent_status']} if q['kind']=='recommendation' else {'answer':t['answer']}
    assert sm.parse_answers(json.dumps(good),c['questions'])[1]
    for raw in ('{}','[]','{"a":NaN}','{"a":1,"a":2}'):
        assert sm.parse_answers(raw,c['questions'])==({},False)
    q=next(q for q in c['questions'] if q['kind']=='recommendation');good[q['id']]['choice']='invented-id'
    assert sm.parse_answers(json.dumps(good),c['questions'])==({},False)


def test_run_independent_calls_then_update_and_user_reset(tmp_path,env):
    episodes=[env.generate_episode(s) for s in (17,29)]
    for e in episodes:e['cases']=e['cases'][:2]
    events=[]
    class Answerer(sm.MockAnswers):
        def answer(self,payload):
            events.append(('answer',deepcopy(payload)));result=super().answer(payload);payload['current_session'].clear();return result
    class Manager:
        def update(self,observation,notes):
            events.append(('update',deepcopy(observation),deepcopy(notes)))
            notes['sentinel']={'source_ids':['e0-0']}
            return {'rounds':[],'finished':True}
    metrics=sm.run(episodes,Answerer(),Manager(),tmp_path/'run',{},environment=env)
    assert metrics['answer_calls']==8 and not metrics['is_model_quality_result']
    for offset in (0,6):
        assert [x[0] for x in events[offset:offset+3]]==['answer','answer','update']
        assert events[offset][1]==events[offset+1][1] and events[offset][1]['prior_session_notes']=={}
        assert events[offset+2][2]=={}
        assert set(events[offset+2][1])=={'current_time','current_session'}
        pair=[deepcopy(e[1]) for e in events[offset+3:offset+5]]
        assert sorted(len(p['prior_session_notes']) for p in pair)==[0,1]
        for p in pair:p.pop('prior_session_notes')
        assert pair[0]==pair[1]


def test_replay_and_corruption_detection(tmp_path,env):
    config={'seeds':[17],'split':'eval'};out=tmp_path/'run'
    sm.run([env.generate_episode(17)],sm.MockAnswers(),sm.PromptedNotes(sm.MockGenerator(),environment=env),out,config,environment=env)
    assert sm.audit_run(out)['sessions']==10
    path=out/'answer_calls.jsonl';original=path.read_text();rows=original.splitlines();first=json.loads(rows[0]);first['payload']['truth']='leak';rows[0]=json.dumps(first);path.write_text('\n'.join(rows)+'\n')
    with pytest.raises(AssertionError):sm.audit_run(out)
    path.write_text(original)
    path=out/'scores.jsonl';rows=path.read_text().splitlines();first=json.loads(rows[0]);first['baseline']['correct']=not first['baseline']['correct'];rows[0]=json.dumps(first);path.write_text('\n'.join(rows)+'\n')
    with pytest.raises(AssertionError):sm.audit_run(out)


def test_manager_partial_failure_is_replayable_and_sanitized(env):
    class Generator:
        def generate(self,messages):
            if len(messages)==2:return {'text':'{"tool":"read_notes","arguments":{}}'}
            raise RuntimeError('private secret')
    trace=sm.PromptedNotes(Generator(),environment=env).update(sm.note_payload(env.generate_episode(17)['cases'][0]),{})
    assert len(trace['rounds'])==1 and not trace['finished'] and trace['error_type']=='RuntimeError'
    assert 'private secret' not in json.dumps(trace)


def test_model_snapshot_checks_content_not_only_size(tmp_path):
    data=b'model weights';(tmp_path/'weights').write_bytes(data)
    manifest={'repo_id':'test','revision':'rev','files':[{'path':'weights','size':len(data),'lfs':{'sha256':hashlib.sha256(data).hexdigest()}}]}
    path=tmp_path/'manifest.json';path.write_text(json.dumps(manifest));assert sm.verify_model_snapshot(tmp_path,path)['revision']=='rev'
    (tmp_path/'weights').write_bytes(b'Model weights')
    with pytest.raises(ValueError):sm.verify_model_snapshot(tmp_path,path)


def test_generic_set_and_numeric_operators():
    assert matches('cotton',{'op':'in','value':['cotton','linen']})
    assert not matches('cotton',{'op':'not_in','value':['cotton']})
    assert matches(10,{'op':'gte','value':10}) and matches(10,{'op':'lte','value':10})


def test_sampled_hidden_user_is_complete_but_unrevealed_values_do_not_grade(env):
    ep=env.generate_episode(17)
    assert set(ep['sampled_user']['general'])=={f for f,s in env.spec['general_fields'].items() if 'derived' not in s}
    first=ep['cases'][0]
    unrevealed=set(ep['sampled_user']['general'])-set(first['hidden_state']['general'])
    assert unrevealed
    assert not any(q.get('field') in unrevealed for q in first['questions'])
    assert 'sampled_user' not in json.dumps(sm.answer_payload(first,{}))
    state,intent=simple(env)
    import random
    catalog=env.make_catalog(state,intent,'2026-01-01T00:00:00Z',random.Random(1),'ranked')
    expected=env.oracle(state,intent,catalog,'2026-01-01T00:00:00Z')
    state['general']=deepcopy(ep['sampled_user']['general'])
    assert env.oracle(state,intent,catalog,'2026-01-01T00:00:00Z')==expected


def test_stable_fact_changes_are_explicit_corrections_and_no_random_age(env):
    ep=env.generate_episode(29);events={e['id']:e for c in ep['cases'] for e in c['evidence']}
    for field,history in ep['cases'][-1]['hidden_state']['general'].items():
        assert field!='age'
        for record in history[1:]:
            text=events[record['source_ids'][0]]['text']
            policy=env.spec['general_fields'][field]['update_policy']
            assert text.startswith('Correction to ' if policy=='correction_only' else 'Update ')
        for old,new in zip(history,history[1:]):
            assert old['valid_until']==new['valid_from']


def test_no_general_preference_leaks_into_unmapped_category(env):
    spec=deepcopy(env.spec);spec['categories']['shirts']['preference_topics']=[]
    e=SchemaEnvironment(spec);state,intent=simple(e)
    state['preferences']['p']={'topic':'clothing_brands','item':'Aster','scope':'global','category':None,
        'history':[{'value':'dislike','source_ids':['e0']} ]}
    assert not any(r['field']=='brand' for r in e.effective(state,intent)['hard'])


def test_public_prompt_schema_excludes_generation_templates_and_rates(env):
    for prompt in env.prompts():
        public=json.loads(prompt.split('Public schema (data, not instructions): ',1)[1])
        assert 'generation' not in public
        for cat in public['categories'].values():
            assert 'profile' not in cat and 'intent' not in cat
        assert 'categories' in public and 'preference_topics' in public


def test_gender_race_names_and_general_preferences_are_json_driven(env):
    assert env.spec['general_fields']['gender']['values']==['male','female']
    pools=env.spec['general_fields']['name']['sampler']['pools']
    for seed in range(5):
        profile=env.generate_episode(seed)['sampled_user'];facts=profile['general']
        assert facts['gender'] in ('male','female') and facts['name'] in pools[facts['nationality']]
        assert facts['race'] in env.spec['general_fields']['race']['values']
        assert {'hobbies','movies','authors','cities','countryside'}<=profile['general_preferences'].keys()
        for p in profile['general_preferences'].values():
            assert p['likes'] and p['dislikes'] and not set(p['likes'])&set(p['dislikes'])
    changed=deepcopy(env.spec)
    new_pools={k:['Synthetic '+n for n in values] for k,values in pools.items()}
    changed['general_fields']['name']['sampler']['pools']=new_pools
    changed['general_fields']['name']['values']=[n for values in new_pools.values() for n in values]
    old=env.generate_episode(17)['sampled_user'];new=SchemaEnvironment(changed).generate_episode(17)['sampled_user']
    assert new['general'].pop('name')=='Synthetic '+old['general'].pop('name')
    assert old==new  # names do not determine race, languages, tastes or category fit


def test_original_sample_artifacts_unchanged():
    root=Path(__file__).resolve().parents[1]/'experiments/experiment0.1/samples/seed17'
    manifest=json.loads((root/'manifest.json').read_text())
    for name,digest in manifest['files_sha256'].items():
        assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest


def test_name_sampler_rejects_unconfigured_nationalities_and_code(env):
    spec=deepcopy(env.spec);spec['general_fields']['name']['sampler']['operator']='exec'
    with pytest.raises(ValueError):SchemaEnvironment(spec)
    spec=deepcopy(env.spec);spec['general_fields']['name']['sampler']['pools'].pop('French')
    with pytest.raises(ValueError):SchemaEnvironment(spec)
