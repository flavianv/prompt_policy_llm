from copy import deepcopy
import json
from pathlib import Path

import pytest

from prompt_policy_llm import explicit_memory as em
from prompt_policy_llm import profile_contract as pc


def profile():return json.loads((pc.ROOT/'example_profile.json').read_text())
def config():return json.loads((em.ROOT/'config.json').read_text())


def test_one_profile_ten_sessions_natural_language_counts_and_no_catalog():
    p=profile();before=deepcopy(p);episode=em.generate_sessions(p,config())
    assert p==before and episode==em.generate_sessions(p,config())
    assert len(episode['cases'])==10
    for c in episode['cases']:
        assert 6<=len(c['events'])<=10 and 1<=len(c['questions'])<=2
        assert any(e['kind']=='filler' for e in c['events'])
        assert all('catalog' not in q for q in c['questions'])
        assert all(not e['text'].startswith('{') for e in c['events'])
    assert len({e['key'] for e in episode['cases'][0]['events'] if e['key']})<len(em.profile_facts(p))


def test_questions_use_only_revealed_prefix_and_updater_whitelist():
    ep=em.generate_sessions(profile(),config());seen={}
    for c in ep['cases']:
        seen.update({e['id']:e for e in c['events']})
        obs=em.observation(c)
        assert set(obs)=={'current_time','statements'}
        assert all(set(e)=={'id','timestamp','text'} for e in obs['statements'])
        for q in c['questions']:
            t=c['truth'][q['id']]
            assert t['support_ids'] and all(s in seen and seen[s]['timestamp']<=t['at_time'] for s in t['support_ids'])
            assert all(seen[s]['key']==t['key'] for s in t['support_ids'])
        for forbidden in ('truth','questions','profile_id','value','until'):
            assert forbidden not in obs


def test_unknown_empty_and_unrevealed_are_different_and_scope_stays_local():
    p=profile();bank=em.profile_facts(p)
    assert bank['clothing:hats:default_size']['value'] is None
    assert bank['clothing:accessories:patterns']['value'] is None  # explicit example currently unknown
    assert em.describe(None)!=em.describe([])
    with pytest.raises(ValueError):em.resolve_events([],'2026-03-01T09:00:00Z','list')
    pants=next(c for c in p['category_profiles'] if c['category']=='pants')
    assert pc.resolve_clothing_preferences(pants,{'season':'summer'})['materials']==['linen','cotton']
    assert pc.resolve_clothing_preferences(pants,{'season':'winter'})['materials']==['cotton']
    assert bank['clothing:pants:scope0:materials']['value']!=bank['clothing:shirts:materials']['value']
    pants['scoped_overrides'].append({'context':{'subtype':None,'season':'summer','occasion':'work'},'preferences':{'materials':[]}})
    assert pc.resolve_clothing_preferences(pants,{'season':'summer','occasion':'work'})['materials']==[]


def test_temporary_expiry_restores_base_and_deadline_is_inclusive():
    history=[{'id':'a','timestamp':'2026-03-01T09:00:00Z','value':['cotton'],'until':None},
      {'id':'b','timestamp':'2026-03-06T09:00:00Z','value':['linen'],'until':'2026-03-09T09:00:00Z'}]
    assert em.resolve_events(history,'2026-03-08T09:00:00Z','list')[0]==['linen']
    assert em.resolve_events(history,'2026-03-09T09:00:00Z','list')[0]==['cotton']
    h=[{'id':'a','timestamp':'2026-03-01T09:00:00Z','value':{'status':'active','deadline':'2026-03-02T09:00:00Z'},'until':None}]
    assert em.resolve_events(h,'2026-03-02T09:00:00Z','intent')[0]=='active'
    assert em.resolve_events(h,'2026-03-07T09:00:00Z','intent')[0]=='expired'
    h[0]['value']['deadline']='2026-05-01T09:00:00Z'
    assert em.resolve_events(h,'2026-03-11T09:00:00Z','intent')[0]=='active'


def test_filler_and_repetition_do_not_mutate_fact_history():
    ep=em.generate_sessions(profile(),config());events=[e for c in ep['cases'] for e in c['events']]
    filler_ids={e['id'] for e in events if e['kind'] in ('filler','other_person','product_description','repeat')}
    assert filler_ids
    assert all(not filler_ids & set(t['support_ids']) for c in ep['cases'] for t in c['truth'].values())


def test_paired_calls_before_update_and_no_hidden_profile(tmp_path):
    cfg=config();ep=em.generate_sessions(profile(),cfg);ep['cases']=ep['cases'][:2];events=[]
    class Answerer:
        def generate(self,system,payload,max_tokens):
            events.append(('answer',deepcopy(payload)))
            return {'text':json.dumps({q['id']:next(iter(q['options'])) for q in payload['questions']}),'status':'mock'}
    class Manager:
        def update(self,obs,notes):
            events.append(('update',deepcopy(obs),dict(notes)));notes['memory']='old fact'
            return {'rounds':[],'finished':True}
    result=em.evaluate(ep,Answerer(),Manager(),tmp_path/'run',cfg,'mock')
    assert result['answer_calls']==4 and result['overall']['questions']==4
    assert [e[0] for e in events]==['answer','answer','update','answer','answer','update']
    assert events[0][1]==events[1][1] and events[2][2]=={}
    assert sorted(len(events[i][1]['prior_notes']) for i in (3,4))==[0,1]
    assert set(events[2][1])=={'current_time','statements'}


def test_note_tools_read_dependency_and_atomicity():
    notes={};cfg=config();put='{"tool":"put_note","arguments":{"name":"fact","text":"old value, dated March 1"}}'
    with pytest.raises(ValueError):em.note_call(put,notes,False,cfg)
    assert em.note_call('{"tool":"read_notes","arguments":{}}',notes,False,cfg)[1]
    em.note_call(put,notes,True,cfg);before=dict(notes)
    with pytest.raises(ValueError):em.note_call('{"tool":"put_note","arguments":{"name":"bad","text":"x","extra":1}}',notes,True,cfg)
    assert notes==before


def test_repeat_resolves_at_statement_time_including_new_disclosures():
    # Vary seeds to exercise repeats of facts disclosed seconds after session start.
    for seed in range(17,27):
        cfg=config();cfg['seed']=seed
        ep=em.generate_sessions(profile(),cfg);history={};facts=em.profile_facts(profile())
        for case in ep['cases']:
            for event in case['events']:
                if event['kind']=='repeat':
                    expected,_=em.resolve_events(history[event['key']],event['timestamp'],facts[event['key']]['kind'])
                    actual=event['value']['status'] if facts[event['key']]['kind']=='intent' else event['value']
                    assert actual==expected
                elif event['key']:
                    history.setdefault(event['key'],[]).append(event)


def test_native_interface_rejects_extra_calls_names_and_arguments():
    from prompt_policy_llm.explicit_note_tools import parse_native
    assert parse_native('<tool_call>{"name":"read_notes","arguments":{}}</tool_call>')['name']=='read_notes'
    for raw in ['{"name":"read_notes","arguments":{}}','<tool_call>{"name":"note","arguments":{}}</tool_call>','<tool_call>{"name":"read_notes","arguments":{}}</tool_call><tool_call>{"name":"no_op","arguments":{}}</tool_call>']:
        with pytest.raises(ValueError):parse_native(raw)
    b=parse_native('<tool_call>{"name":"read_notes","arguments":{"id":"e0"}}</tool_call>')
    with pytest.raises(ValueError):em.note_call(json.dumps({'tool':b['name'],'arguments':b['arguments']}),{},False,config())
