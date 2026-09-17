from copy import deepcopy
import json

from prompt_policy_llm import profile_contract as pc


def example():return json.loads((pc.ROOT/'example_profile.json').read_text())
def constraints():return json.loads((pc.ROOT/'example_constraints.json').read_text())


def test_complete_illustrative_profile_and_partial_constraints():
    assert pc.validate_profile(example(),constraints())==[]
    schema=pc.load_schema()
    assert schema['$schema']=='https://json-schema.org/draft/2020-12/schema'
    assert schema['properties']['personal']['properties']['gender']['enum']==['male','female']


def test_any_nested_property_and_array_index_can_be_fixed():
    c={'fixed_values':{'personal':{'name':'Camille Martin'},'physical':{'height':{'unit':'cm'}}},
       'fixed_paths':{'/interests/hobbies/0':'hiking','/professional/education/level':'master',
                      '/category_profiles/1/sizes/0/size':'40'}}
    assert pc.constraint_rules(c)[1]==[] and pc.validate_profile(example(),c)==[]
    p=example();p['interests']['hobbies'][0]='running'
    assert any('fixed value changed' in e for e in pc.validate_profile(p,c))


def test_fixed_whole_array_is_not_silently_extended():
    p=example();c={'fixed_values':{'interests':{'hobbies':['hiking','reading']}}}
    assert not pc.validate_profile(p,c)
    p['interests']['hobbies'].append('chess')
    assert any('fixed value changed' in e for e in pc.validate_profile(p,c))


def test_overlap_unknown_paths_and_invalid_fixed_values_report_conflicts():
    c={'fixed_values':{'personal':{'gender':'female'}},'fixed_paths':{'/personal/gender':'male'}}
    assert pc.constraint_rules(c)[1]
    c={'fixed_values':{'interests':{'hobbies':['hiking']}},'fixed_paths':{'/interests/hobbies/0':'painting'}}
    assert any('overlapping' in e for e in pc.constraint_rules(c)[1])
    assert pc.constraint_rules({'fixed_paths':{'/unknown':1}})[1]
    assert pc.constraint_rules({'fixed_values':{'personal':{'gender':'unsupported'}}})[1]


def test_birthdate_reference_age_consistency_and_birthday_boundary():
    p=example();p['personal']['age']=39
    assert any('inconsistent' in e for e in pc.validate_profile(p))
    c={'fixed_values':{'reference_date':'2026-03-01','personal':{'birth_date':'1987-03-12','age':39}}}
    assert any('age/date' in e for e in pc.constraint_rules(c)[1])
    assert pc.age_at('1987-03-12','2026-03-11')==38
    assert pc.age_at('1987-03-12','2026-03-12')==39
    assert not pc.constraint_rules({'fixed_values':{'personal':{'age':38}}})[1]


def test_schema_requires_units_and_rejects_future_active_deadline_and_gift_inheritance():
    p=example();del p['physical']['weight']['unit']
    assert any('required' in e for e in pc.validate_profile(p))
    p=example();p['purchase_intents'][0]['deadline']='2026-02-28T12:00:00Z'
    assert any('chronology' in e for e in pc.validate_profile(p))
    p=example();p['purchase_intents'][1]['use_general_preferences']=True
    assert any('gift' in e for e in pc.validate_profile(p))


def test_duplicate_sizes_and_hard_contradictions():
    p=example();p['category_profiles'][0]['sizes'].append(deepcopy(p['category_profiles'][0]['sizes'][0]))
    assert any('scoped size' in e for e in pc.validate_profile(p))
    p=example();p['category_profiles'][0]['hard'] += [{'field':'color','op':'eq','value':'red'},{'field':'color','op':'eq','value':'blue'}]
    assert any('contradictory hard' in e for e in pc.validate_profile(p))
    c={'fixed_paths':{'/category_profiles/0/hard':[{'field':'price','op':'gte','value':200},{'field':'price','op':'lte','value':100}]}}
    assert any('contradictory hard' in e for e in pc.constraint_rules(c)[1])


def test_prompt_is_local_and_rendered_without_network():
    prompt=pc.render_prompt(constraints())
    assert '{{USER_PROFILE_SCHEMA_JSON}}' not in prompt and '{{FIXED_CONSTRAINTS_JSON}}' not in prompt
    assert 'user-profile-1.1' in prompt and 'hiking' in prompt
    assert 'separate session generator' in prompt
    try:pc.render_prompt({'fixed_values':{'personal':{'gender':'unsupported'}}})
    except ValueError as e:assert 'enum' in str(e)
    else:raise AssertionError('contradiction was not rejected')


def test_exact_types_and_preserved_fixed_name_override_typicality():
    assert not pc.equal_exact(1,True) and not pc.equal_exact(1,1.0)
    p=example();p['personal']['name']='An explicitly fixed uncommon name'
    assert not pc.validate_profile(p,{'fixed_values':{'personal':{'name':'An explicitly fixed uncommon name'}}})
