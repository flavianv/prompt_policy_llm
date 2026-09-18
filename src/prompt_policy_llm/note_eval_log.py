"""Deterministic, append-only completed-session Markdown logs; no model calls."""
import argparse
import difflib
import json
from pathlib import Path


def fence(value, language='json'):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    delimiter = '````' if '```' in text else '```'
    return f'\n{delimiter}{language}\n{text}\n{delimiter}\n'


def render_header(config):
    parts = ['# Computed evaluation session log',
             'This file is rendered deterministically from saved configuration, scores and tool traces. It contains no generated review narrative. Sessions are appended after their note update completes. The current run can therefore expose each completed session without waiting for later sessions or semantic review.',
             'Ordering: Luna answers from current statements plus either empty notes or the BEFORE snapshot. Both answers precede the current Qwen update. AFTER notes become the next session’s prior notes. Gold below is evaluator-only and was not sent to either model.',
             '## Exact prompts, tools and settings', fence(config),
             'Rendered Qwen chat-template prompts, messages and token IDs are preserved for every round in [note_traces.jsonl](note_traces.jsonl). Exact Luna request payloads and output text are in the answer-cache files referenced by cache key.']
    return '\n\n'.join(parts) + '\n'


def render_session(case, trace, scores):
    session = case['session']
    rows = [r for r in scores if r['session'] == session]
    assert len(rows) == len(case['questions'])
    before, after = trace['notes_before'], trace['notes_after']
    parts = [f"## Session {session + 1} — {case['current_time']}",
             '### Execution timestamps', fence({k: trace.get(k) for k in ['started_at', 'answered_at', 'updated_at']}),
             '### Notes BEFORE answering (memory arm only)', fence(before),
             'Baseline prior notes: `{}`.',
             '### Current user statements available to both answer arms', fence(trace['observation']),
             '### Questions, options, answers and evaluator-only gold']
    for row in rows:
        q = row['question']
        parts += [f"#### {q['id']}: {q['question']}", fence(q['options'])]
        for arm in ['baseline', 'memory']:
            result = row[arm]
            parts += [f"**{arm}**", fence({**result, 'selected_option_text': q['options'].get(result['answer'])})]
        parts += ['**Evaluator-only gold**', fence(row['truth'])]
    parts += ['### Qwen decisions AFTER answers', fence({'finished': trace['finished'],
              'error': trace.get('error'), 'coverage_review_requested': trace.get('coverage_review_requested')})]
    for r in trace['rounds']:
        parts += [f"#### Tool round {r['round'] + 1}", 'Exact generated output:',
                  fence(r['generation']['text'], 'text'),
                  'Generation metadata:', fence({k: v for k, v in r['generation'].items() if k != 'text'}),
                  'Validity and exact tool result:', fence({'valid': r['valid'], 'tool_result': r['tool_result']}),
                  'Note state before this call:', fence(r['notes_before']),
                  'Note state after this call:', fence(r['notes_after'])]
    added = {k: after[k] for k in after if k not in before}
    deleted = {k: before[k] for k in before if k not in after}
    changed = {k: {'before': before[k], 'after': after[k]} for k in after if k in before and before[k] != after[k]}
    parts += ['### Notes AFTER update (available to the next session)', fence(after),
              '### Added, changed and deleted notes', fence({'added': added, 'changed': changed, 'deleted': deleted}),
              '### Accumulated note size', fence({'before': trace.get('size_before'), 'after': trace.get('size_after')})]
    for key in list(added) + list(changed) + list(deleted):
        diff = '\n'.join(difflib.unified_diff(before.get(key, '').splitlines(), after.get(key, '').splitlines(),
                         fromfile='BEFORE/' + key, tofile='AFTER/' + key, lineterm=''))
        parts += [fence(diff, 'diff')]
    parts += ['### Computed session scores', fence({arm: {'correct': sum(r[arm]['correct'] for r in rows),
                 'questions': len(rows), 'invalid': sum(not r[arm]['valid'] for r in rows)} for arm in ['baseline', 'memory']})]
    return '\n\n'.join(parts) + '\n'


def start_log(output, config):
    path = Path(output) / 'SESSION_LOG.md'
    with path.open('x') as f:
        f.write(render_header(config))


def append_session(output, case, trace, scores):
    with (Path(output) / 'SESSION_LOG.md').open('a') as f:
        f.write(render_session(case, trace, scores))
        f.flush()


def rebuild(output):
    """Rebuild atomically from completed traces; never load a model or call an API."""
    output = Path(output)
    cfg = json.loads((output / 'run_config.json').read_text())
    ep = json.loads((output / 'episode.json').read_text())
    traces = [json.loads(x) for x in (output / 'note_traces.jsonl').read_text().splitlines()]
    scores = [json.loads(x) for x in (output / 'scores.jsonl').read_text().splitlines()]
    cases = {c['session']: c for c in ep['cases']}
    text = render_header(cfg) + ''.join(render_session(cases[t['session']], t, scores) for t in traces)
    tmp = output / 'SESSION_LOG.md.tmp'
    tmp.write_text(text)
    tmp.replace(output / 'SESSION_LOG.md')
    return len(traces)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    a = p.parse_args()
    print(json.dumps({'completed_sessions_rendered': rebuild(a.output), 'log': str(a.output / 'SESSION_LOG.md')}))


if __name__ == '__main__':
    main()
