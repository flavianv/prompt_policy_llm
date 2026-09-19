"""Read-only audit of paired session artifacts; no model/API calls."""
import argparse
import json
from collections import Counter
from pathlib import Path
import statistics


def load(path):
    return [json.loads(s) for s in path.read_text().splitlines()]


def audit(root):
    calls = load(root/'answer_calls.jsonl')
    notes = load(root/'note_traces.jsonl')
    scores = load(root/'scores.jsonl')
    episodes = load(root/'evaluator_episodes.jsonl')
    by_episode = {e['user_id']: e for e in episodes}
    state, checks = {}, Counter()
    for note in notes:
        user, session = note['user_id'], note['session']
        previous = state.get(user, {})
        assert note['notes_before'] == previous
        evidence = [o['text'] for o in by_episode[user]['observations'] if o['session_index'] == session]
        for r in note['rounds']:
            assert json.loads(r['messages'][1]['content']) == {'current_session': evidence}
            if not r['valid']:
                assert r['notes_before'] == r['notes_after']
        session_calls = [c for c in calls if c['user_id'] == user and c['session'] == session]
        assert len(session_calls) in (1, 2)
        for c in session_calls:
            p = c['payload']
            assert set(p) == {'current_session', 'prior_session_notes', 'questions'}
            assert p['current_session'] == evidence
            assert p['prior_session_notes'] == (previous if c['arm'] == 'memory' else {})
            assert all(set(q) == {'id', 'question', 'options'} for q in p['questions'])
        if len(session_calls) == 2:
            p0, p1 = [c['payload'] for c in session_calls]
            assert p0['questions'] == p1['questions']
        if session == 0:
            assert previous == {} and len(session_calls) == 1
            checks['first_session_shared'] += 1
        profile, last = {}, {}
        for o in by_episode[user]['observations']:
            if o['session_index'] <= session and o['metadata'].get('is_profile_event'):
                slot = o['metadata']['slot']
                profile[slot] = o['metadata']['value']
                last[slot] = o['session_index']
        qs = [r for r in scores if r['user_id'] == user and r['session'] == session]
        assert len(qs) == len(profile)
        for row in qs:
            q = row['question']
            assert q['options'][q['answer']] == profile[q['slot']]
            assert q['evidence_delay'] == session-last[q['slot']]
            assert row['prior_notes'] == previous
        state[user] = note['notes_after']
        assert sum(len(t.split()) for t in state[user].values()) <= 120
        checks['sessions_checked'] += 1
        checks['questions_checked'] += len(qs)
    rounds = [r for n in notes for r in n['rounds']]
    errors = Counter(r['error'] for r in rounds if not r['valid'])
    nonempty = sum(bool(n['notes_after']) for n in notes)
    latencies = [c['generation']['latency_s'] for c in calls]
    per_arm = {}
    for arm in ['baseline', 'memory']:
        # A shared response applies to both arms but is billed once in total.
        selected = [c for c in calls if c['arm'] == arm or c['shared_identical_request']]
        per_arm[arm] = {k: sum(c['generation'][k] for c in selected)
                        for k in ['input_tokens','output_tokens','latency_s','estimated_cost_usd']}
        per_arm[arm]['logical_calls'] = len(selected)
    return {'passed': True, 'checks': dict(checks), 'invalid_tool_round_errors': dict(errors),
            'sessions_with_nonempty_notes_after': nonempty,
            'luna_mean_call_latency_s': statistics.mean(latencies),
            'luna_median_call_latency_s': statistics.median(latencies),
            'logical_arm_usage_shared_calls_counted_in_each_arm': per_arm,
            'note_word_counts': [sum(len(t.split()) for t in n['notes_after'].values()) for n in notes],
            'limitations': ['Tools use local JSON dispatch, not native API tool_calls.',
                           'No injected tool outages; unavailable-tool robustness untested.',
                           'Latest profile-event delay does not exclude current distractor repetitions.',
                           'Synthetic stated-preference recovery; not recommendation quality.',
                           'No deterministic-rule memory baseline; gain does not isolate learned note-policy value.',
                           'Fixed prompted policy, no weight training; early partial run informed protocol fix.']}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('run', type=Path)
    a = p.parse_args()
    print(json.dumps(audit(a.run), indent=2))
