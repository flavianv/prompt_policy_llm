import json
from types import SimpleNamespace

import pytest
pytest.importorskip("adaptgym", reason="AdaptGym integration tests require its source on PYTHONPATH")
from prompt_policy_llm.adaptgym_pilot import apply_calls, answer_payload, parse_answers, run, session_cases


def episode():
    return SimpleNamespace(config={'session_count': 2, 'seed': 17},
        observations=[SimpleNamespace(session_index=0, text='For drink, I prefer green tea.',
                         metadata={'is_profile_event': True, 'slot': 'drink', 'value': 'green tea'}),
                      SimpleNamespace(session_index=1, text='For drink, I now prefer espresso.',
                         metadata={'is_profile_event': True, 'slot': 'drink', 'value': 'espresso'})],
        final_profile={'drink': 'FUTURE_SECRET'}, questions=['LABEL_SECRET'])


def test_prefix_truth_and_prompt_boundary():
    cases = list(session_cases(episode()))
    assert cases[0]['questions'][0]['options'][cases[0]['questions'][0]['answer']] == 'green tea'
    assert cases[1]['questions'][0]['options'][cases[1]['questions'][0]['answer']] == 'espresso'
    payload = json.dumps(answer_payload(cases[0], {}))
    for forbidden in ['FUTURE_SECRET', 'LABEL_SECRET', 'metadata', 'is_profile_event', '"answer":', 'espresso.']:
        assert forbidden not in payload
    assert len(cases[0]['questions'][0]['options']) == 4


def test_transactional_tools_and_dependency():
    notes = {}
    write = {'tool': 'write_note', 'arguments': {'name': 'drink', 'text': 'green tea'}}
    with pytest.raises(ValueError):
        apply_calls(json.dumps(write), notes, False)
    _, read, done = apply_calls('{"tool":"read_notes","arguments":{}}', notes, False)
    assert read and not done
    with pytest.raises(ValueError):
        apply_calls('{"tool":"write_note","tool":"no_op","arguments":{}}', notes, True)
    assert notes == {}
    apply_calls(json.dumps(write), notes, True)
    assert notes == {'drink': 'green tea'}
    with pytest.raises(ValueError):
        apply_calls(json.dumps(write), notes, True)
    with pytest.raises(ValueError):
        apply_calls(json.dumps({'tool': 'update_note', 'arguments': {'name': 'drink', 'text': 'word ' * 121}}), notes, True)
    assert notes == {'drink': 'green tea'}
    assert apply_calls('{"tool":"no_op","arguments":{}}', notes, True)[2]


def test_invalid_answers_not_silently_dropped():
    qs = [{'id': 'q0', 'options': {'A': 'tea', 'B': 'coffee'}}]
    assert parse_answers('{"q0":"X"}', qs) == ({}, False)
    assert parse_answers('{"q0":"A"}', qs) == ({'q0': 'A'}, True)


def test_run_scores_before_update_resets_users_and_hides_labels(tmp_path):
    from dataclasses import dataclass
    @dataclass
    class Ep:
        user_id: str
        observations: tuple
        config: dict
    @dataclass
    class Obs:
        session_index: int
        text: str
        metadata: dict
    eps = [Ep(u, (Obs(0, 'For drink, I prefer green tea.', {'is_profile_event': True, 'slot': 'drink', 'value': 'green tea'}),
                  Obs(1, 'Today was busy.', {})), {'session_count': 2, 'seed': 17}) for u in ['u1', 'u2']]
    events = []
    class Answerer:
        def answer(self, payload):
            events.append(('answer', payload))
            return {'text': '{"q0":"A"}', 'input_tokens': 1, 'output_tokens': 1, 'latency_s': 0, 'estimated_cost_usd': 0}
    class Manager:
        def update(self, evidence, notes):
            events.append(('update', (evidence, dict(notes))))
            assert isinstance(evidence, list) and all(isinstance(t, str) for t in evidence)
            notes['drink'] = 'green tea'
            return {'rounds': [], 'finished': True}
    result = run(eps, Answerer(), Manager(), tmp_path/'run')
    assert result['first_session_parity']
    assert result['luna_actual_calls'] == 6
    for start in [0, 5]:
        assert events[start][0] == 'answer'
        assert events[start][1]['prior_session_notes'] == {}
        assert events[start+1][0] == 'update'
        assert events[start+1][1][1] == {}
    scores = [json.loads(s) for s in (tmp_path/'run'/'scores.jsonl').read_text().splitlines()]
    assert all(r['prior_notes'] == {} for r in scores if r['session'] == 0)
    assert all(r['prior_notes'] == {'drink': 'green tea'} for r in scores if r['session'] == 1)
