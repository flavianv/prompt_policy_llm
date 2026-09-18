import pytest
from prompt_policy_llm.text_note_updates import merge_lines,score_text_notes,render_notes,parse_lines
from prompt_policy_llm.structured_notes import VERSION


def gold(profile):return {'version':VERSION,'as_of':'2026-03-01T09:01:00Z','profile':profile}


def test_free_keys_optional_and_duplicate_values_no_extra_credit():
    target=gold({'personal':{'name':'Jordan Example'},'category_profiles':[{'category':'shirts','preferences':{'colors':['teal','blue']}}]})
    notes=merge_lines({},'Jordan Example\nFavorite shirt colours: blue, teal\nName: Jordan Example')
    assert score_text_notes(notes,target)['reward']==2
    assert score_text_notes(merge_lines({},'Shirt colours: blue, teal, red'),target)['reward']==0


def test_context_disambiguates_common_values_and_lists():
    target=gold({'category_profiles':[{'category':'hats','default_size':None},{'category':'shirts','default_size':None},{'category':'pants','preferences':{'patterns':[]}}]})
    assert score_text_notes(merge_lines({},'unknown\nno preference'),target)['reward']==0
    notes=merge_lines({},'Hat size: unknown\nShirt size: unknown\nPants patterns: no preference')
    # Singular/plural category names are deliberately covered by key normalization.
    assert score_text_notes(notes,target)['reward']==3


def test_sparse_memory_replaces_key_and_keeps_unrelated():
    prior=merge_lines({},'Name: Jordan Example\nShirt colors: red')
    current=merge_lines(prior,'Shirt colors: blue')
    assert 'red' not in render_notes(current)
    assert 'Jordan Example' in render_notes(current)
    assert 'red' in render_notes(prior)
    assert merge_lines(current,'No changes.')==current
    with pytest.raises(ValueError):parse_lines('{"name":"Jordan"}')


def test_invalid_and_history_no_credit():
    target=gold({'personal':{'name':'Jordan Example'}})
    notes=merge_lines({},'Historical name: Jordan Example')
    assert score_text_notes(notes,target)['reward']==0
    assert score_text_notes(merge_lines({},'Jordan Example'),target,False)['reward']==0


def test_dates_are_not_bags_of_numbers():
    target=gold({'personal':{'birth_date':'1990-03-01'}})
    assert score_text_notes(merge_lines({},'Birthday: 1990-01-03'),target)['reward']==0
    assert score_text_notes(merge_lines({},'Birthday: 1990-03-01'),target)['reward']==1
