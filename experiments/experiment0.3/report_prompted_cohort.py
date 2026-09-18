"""Render complete, inspectable per-user reports from frozen evaluation artifacts."""
import argparse
import difflib
import hashlib
import json
import re
from pathlib import Path


def render(parts):
    return re.sub(r'(?m)(^\|[^\n]*\|)\n\n(?=\|)', r'\1\n', '\n\n'.join(parts)) + '\n'


def readlines(path):
    return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []


def block(value, lang='json'):
    return '\n```' + lang + '\n' + (value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)) + '\n```\n'


def score(x):
    return f"{x['correct']}/{x.get('questions', '?')}"


def notes(n):
    if not n:
        return '\n**Empty notes: `{}`.**\n'
    return ''.join('\n**' + k + '**\n' + block(v, 'text') for k, v in n.items())


def audit_user(root, uid, ep, traces, rows, cfg):
    from prompt_policy_llm.explicit_memory import observation, note_call, resolve_events
    from prompt_policy_llm.explicit_note_tools import parse_native
    from prompt_policy_llm.note_reward import stable_hash, ANSWER_PROMPT
    from prompt_policy_llm.explicit_note_coverage import CHECK
    errors = []
    previous = {}
    for case, t in zip(ep['cases'], traces):
        assert t['session'] == case['session']
        assert t['notes_before'] == previous
        assert t['observation'] == observation(case)
        assert t['started_at'] <= t['answered_at'] <= t['updated_at']
        current = dict(previous)
        read = done = checked = False
        for r in t['rounds']:
            assert r['notes_before'] == current
            try:
                call = parse_native(r['generation']['text'])
                result, read, done = note_call(json.dumps({'tool': call['name'], 'arguments': call['arguments']}), current, read, cfg['config'])
                valid = True
                if done and not checked:
                    done = False
                    checked = True
                    result = {'ok': True, 'finished': False, 'review_required': CHECK, 'saved_notes': dict(current)}
            except (ValueError, TypeError, KeyError):
                valid = False
            assert r['valid'] == valid and r['notes_after'] == current
            if valid:
                assert r['tool_result'] == result
        assert t['finished'] == done and t['notes_after'] == current
        for row in [x for x in rows if x['session'] == case['session']]:
            q = row['question']
            assert row['truth'] == case['truth'][q['id']]
            truth = row['truth']
            history = case['revealed_state'][truth['key']]['history']
            value, support = resolve_events(history, truth['at_time'], truth['kind'])
            assert value == truth['value'] and support == truth['support_ids']
            for arm, prior in [('baseline', {}), ('memory', previous)]:
                cached = json.loads((root / 'answer_cache' / uid / (row[arm]['cache_key'] + '.json')).read_text())
                req = cached['request']
                assert stable_hash(req) == row[arm]['cache_key']
                assert req['system'] == ANSWER_PROMPT
                assert req['payload'] == {**observation(case), 'prior_notes': prior, 'questions': case['questions']}
                assert row[arm]['correct'] == (row[arm]['valid'] and row[arm]['answer'] == truth['answer'])
            if not previous:
                assert row['baseline']['cache_key'] == row['memory']['cache_key']
                assert row['baseline'] == row['memory']
        previous = current
    assert len(traces) == 10 and len(rows) == 20
    assert hashlib.sha256((root/'frozen/dataset'/uid/'episode.json').read_bytes()).hexdigest() == cfg['episode_sha256']
    for name, digest in cfg['source_sha256'].items():
        assert hashlib.sha256((root/'frozen'/name).read_bytes()).hexdigest() == digest
    return {'passed': True, 'sessions': len(traces), 'questions': len(rows),
            'checks': ['frozen episode/source hashes', 'chronological prior-note continuity', 'answer-before-update timestamps',
                       'strict tool parser/dispatcher replay including coverage review', 'private gold recomputation',
                       'exact answer payload whitelist and cache hashes', 'paired scoring and identical-input equality'],
            'semantic_note_correctness': 'Separate evidence review; protocol replay does not prove factual support.'}


def failure_markdown(rows):
    missed=[r for r in rows if not r['memory']['correct']]
    if not missed:return 'No memory-arm question failures in this user; this does not imply complete/correct notes.'
    parts=[]
    for r in missed:
        q=r['question'];t=r['truth'];a=r['memory']['answer']
        parts.append(f"- Session {r['session']+1}, {q['id']}: {q['question']} Memory chose **{a}: {q['options'].get(a, 'invalid')}**; evaluator gold **{t['answer']}: {q['options'][t['answer']]}**. Baseline correct={r['baseline']['correct']}.")
    return '\n\n'.join(parts)


def quality_markdown(q):
    c=q['final_field_counts']
    lines=[q['method'], f"Final fields: **{c['supported']}/{c['total']} supported**, {c['ambiguous']} ambiguous, {c['incorrect']} incorrect, {c['missing']} missing.",
           '[Complete field-by-field review with source histories](note_quality_review.json).',
           '| Revealed field | Final status | Finding |', '|---|---|---|']
    for f in q['fields']:
        lines.append(f"| `{f['key']}` | {f['status']} | {f['reason']} |")
    lines.append('### Concrete support and failure observations')
    for o in q['observations']:
        lines.append(f"**Session {o['session']} — {o['type']}**: {o['finding']}")
        if o.get('evidence_ids'):lines.append('Evidence: '+', '.join(o['evidence_ids'])+'.')
        if o.get('quote'):lines.append(block(o['quote'],'text'))
    return render(lines)


def main():
    p = argparse.ArgumentParser(); p.add_argument('root', type=Path); p.add_argument('--max-users', type=int, default=10); a = p.parse_args(); root = a.root
    shared = json.loads((root/'shared_run_config.json').read_text())
    prompt = ['# Frozen prompts and settings', 'All users use these exact shared strings and tool schemas. No weight training or adapter. The rendered Qwen prompt for every call is saved in each note_traces.jsonl round.',
              '## Note writer system', block(shared['note_system'], 'text'), '## Coverage review after the first finish call', block(shared['coverage_check'], 'text'),
              '## Native tool schemas', block(shared['tools']), '## Luna answer system', block(shared['answer_system'], 'text'),
              '## Exact settings and source hashes', block(shared)]
    (root/'PROMPTS.md').write_text('\n\n'.join(prompt))
    summaries=[]
    for meta in json.loads((root/'frozen/dataset/manifest.json').read_text())['users'][:a.max_users]:
        uid=meta['user']; d=root/'results'/uid
        if not (d/'metrics.json').exists():continue
        ep=json.loads((d/'episode.json').read_text()); cfg=json.loads((d/'run_config.json').read_text()); m=json.loads((d/'metrics.json').read_text())
        rows=readlines(d/'scores.jsonl'); traces=readlines(d/'note_traces.jsonl')
        audit=audit_user(root,uid,ep,traces,rows,cfg); (d/'audit.json').write_text(json.dumps(audit,indent=2))
        quality_path=d/'note_quality_review.json'
        quality=json.loads(quality_path.read_text()) if quality_path.exists() else None
        lines=[f"# {uid}: {meta['name']} — frozen prompted Qwen3-4B notes", 
               f"All 10 sessions / 20 questions complete. Luna only: **{m['overall']['baseline']['correct']}/20**; Luna with prior Qwen notes: **{m['overall']['memory']['correct']}/20**. Gold labels below are **evaluator-only**, never supplied to the note writer or answerer.",
               '## Protocol and exact prompts',
               'For each session, both Luna arms first receive the current time, full current user statements and questions. The baseline receives `{}` prior notes; the memory arm receives only the notes produced by earlier sessions. Both answers are scored before the current session is sent to Qwen to update notes for the next session. Qwen sees current statements, its system/tools and saved notes returned by read_notes; it never sees questions, gold, hidden profile or future statements. Each session starts a fresh Qwen conversation. Identical answer requests share the exact cached output.',
               '[Exact shared system prompts, coverage prompt, schemas and settings](../../PROMPTS.md). [This user’s run configuration](run_config.json). Full rendered Qwen prompts/messages/token IDs are preserved in [note_traces.jsonl](note_traces.jsonl); exact Luna requests and raw output text are in [answer cache](../../answer_cache/'+uid+'/).',
               f"Qwen/Qwen3-4B revision `{cfg['model_revision']}`; frozen BF16, no adapter, greedy decoding, thinking disabled. Luna actual model: `{m['actual_answer_model']}`, reasoning low. Qwen budget: {cfg['config']['note_max_rounds']} calls/session, {cfg['config']['note_max_output_tokens']} output tokens/call, {cfg['config']['max_context_tokens']} context tokens; notes: {cfg['config']['note_max_count']} entries / {cfg['config']['note_max_words']} whitespace words. Notes token count uses the Qwen tokenizer on json.dumps(notes), with keys/punctuation; words count note values only. There is no separate notes-token limit. Note text max5000 characters and name max96 characters are enforced by the dispatcher.",
               '## Summary', block(m), '[Integrity audit](audit.json): passed. Failures remain in denominators; no failed session is omitted. [Pure computed session log without review narrative](SESSION_LOG.md).',
               '## Note quality review', quality_markdown(quality) if quality else 'Semantic support/omission/hallucination review is pending. Tool success and note growth alone are not factual-quality metrics.',
               '## Observed answer failures', failure_markdown(rows),
               '## Tool-use interpretation', 'Invocation: every first-three-user call parsed and executed successfully (124/124); each of30 sessions reached the second finish call after coverage review. Dependency: replay verified read-before-write, exact state transitions and prior-session continuity. Intent alignment/context: valid calls still omitted facts, lost history and mixed scopes; see the semantic review. Robustness: no output caps or context-limit failures were observed in the reviewed users; tool outages were not injected, so unavailable-tool recovery is untested. Traceability: exact model text, prompts, tool results, token counts, timing and answer cache payloads are saved. No hidden reasoning was requested (thinking disabled).',
               '## Chronological session log',
               '| Session | Luna only | With prior notes | Notes before → after (words / tokens) | Tool rounds / invalid | Finalized |',
               '|---|---:|---:|---|---:|---|']
        for c,t,s in zip(ep['cases'],traces,m['per_session']):
            before=t['size_before'];after=t['size_after']
            lines.append(f"| {c['session']+1} | {s['baseline']['correct']}/{s['questions']} | {s['memory']['correct']}/{s['questions']} | {before['words']} / {before['serialized_tokens']} → {after['words']} / {after['serialized_tokens']} | {len(t['rounds'])} / {sum(not r['valid'] for r in t['rounds'])} | {t['finished']} |")
        for case,t in zip(ep['cases'],traces):
            n=case['session']+1
            lines += [f"## Session {n} — {case['current_time']}",
                      f"Execution UTC: began {t['started_at']}; both answers complete {t['answered_at']}; notes update complete {t['updated_at']}.",
                      '### 1. Prior notes available BEFORE answering', notes(t['notes_before']),
                      'The baseline prior notes were empty. The memory arm received the complete notes above, plus the current evidence below.',
                      '### 2. Current user evidence (full statements)']
            for e in case['events']:
                lines += [f"**{e['id']} — {e['timestamp']}**", block(e['text'],'text')]
            lines += ['### 3. Questions and decisions BEFORE updating notes']
            for r in [x for x in rows if x['session']==case['session']]:
                q=r['question']; lines += [f"**{q['id']}: {q['question']}**", block(q['options'])]
                for arm,label in [('baseline','Luna only'),('memory','Luna with prior notes')]:
                    ans=r[arm]['answer']; selected=q['options'].get(ans,'INVALID / missing')
                    lines += [f"{label}: **{ans} — {selected}**; correct={r[arm]['correct']}; valid={r[arm]['valid']}. [Exact request and output](../../answer_cache/{uid}/{r[arm]['cache_key']}.json)."]
                truth=r['truth']; lines += [f"Evaluator-only gold: **{truth['answer']} — {q['options'][truth['answer']]}**; earlier-session evidence required={truth['earlier_session_required']}; historical={truth['historical']}; evidence IDs={', '.join(truth['support_ids'])}; evaluated time={truth['at_time']}."]
            lines += ['### 4. Qwen tool decisions AFTER answering', f"Finished={t['finished']}; error={t.get('error','none')}. Accepted writes persist even when later calls fail or the session does not finalize."]
            for r in t['rounds']:
                g=r['generation'];lines += [f"#### Tool round {r['round']+1}",f"Valid={r['valid']}; input/output tokens={g['input_tokens']}/{g['output_tokens']}; output cap hit={g['hit_output_cap']}; model latency={g['latency_s']:.3f}s.", 'Exact generated decision:',block(g['text'],'text'),'Exact tool result / error:',block(r['tool_result'])]
            before=t['notes_before'];after=t['notes_after']
            added=[k for k in after if k not in before];deleted=[k for k in before if k not in after];changed=[k for k in after if k in before and before[k]!=after[k]]
            lines += ['### 5. Updated notes for the NEXT session', notes(after), '### 6. Explicit changes and accumulated size',block({'added':added,'changed':changed,'deleted':deleted,'size_before':t['size_before'],'size_after':t['size_after'],'word_budget':cfg['config']['note_max_words'],'entry_budget':cfg['config']['note_max_count']})]
            for key in added+changed+deleted:
                diff='\n'.join(difflib.unified_diff(before.get(key,'').splitlines(),after.get(key,'').splitlines(),fromfile='BEFORE/'+key,tofile='AFTER/'+key,lineterm=''))
                lines += [block(diff,'diff')]
            if not added+changed+deleted:lines += ['No notes added, changed or deleted.']
        lines += ['## Raw reproducibility artifacts', '[Episode with private evaluator state](episode.json), [scores](scores.jsonl), [complete tool traces](note_traces.jsonl), [metrics](metrics.json), [run configuration](run_config.json), [audit](audit.json). The frozen dataset and exact executed sources are retained under ../../frozen/.',
                  '## Comparison limits', 'Earlier Qwen3-1.7B runs used different prompts/interfaces. The original Maya run produced no valid notes and independent Luna draws gave a spurious 8/20 versus10/20 difference on identical inputs. Native-interface repair probes covered only early sessions. This 4B cohort changes model, prompt/interface and cache handling together; it is not an isolated model-size effect or training improvement. No training occurred.']
        (d/'REPORT.md').write_text(render(lines))
        summaries.append({'user':uid,'name':meta['name'],'metrics':m})
    agg={'review_users_requested':a.max_users,'users_complete':len(summaries),'sessions':10*len(summaries),'questions':20*len(summaries),'users':summaries}
    qualities=[json.loads((root/'results'/u['user']/'note_quality_review.json').read_text()) for u in summaries if (root/'results'/u['user']/'note_quality_review.json').exists()]
    agg['note_quality']={k:sum(q['final_field_counts'][k] for q in qualities) for k in ['total','supported','ambiguous','incorrect','missing']}
    agg['note_quality']['users_reviewed']=len(qualities)
    agg['note_quality']['unit']='Unique revealed current-state field in final notes; manual single-reviewer audit, not question accuracy or complete history coverage.'
    stop_path=root/'user_requested_stop.json'
    stop=json.loads(stop_path.read_text()) if stop_path.exists() else None
    if stop:agg['stop_state']=stop
    for category in ['overall','earlier_session_evidence','current_session_evidence','historical']:
        total=sum(u['metrics'][category]['questions'] for u in summaries)
        agg[category]={'questions':total}
        for arm in ['baseline','memory']:
            correct=sum(u['metrics'][category][arm]['correct'] for u in summaries)
            agg[category][arm]={'correct':correct,'accuracy':correct/total if total else None,'invalid':sum(u['metrics'][category][arm]['invalid'] for u in summaries)}
    agg['paired']={k:sum(u['metrics']['paired'][k] for u in summaries) for k in ['memory_only','baseline_only','both_correct','both_wrong']}
    for k in ['note_rounds','invalid_note_rounds','note_sessions_finished','api_calls_this_process','cache_hits','wall_seconds']:
        agg[k]=sum(u['metrics'][k] for u in summaries)
    (root/'aggregate.json').write_text(json.dumps(agg,indent=2))
    index=['# Frozen prompted Qwen3-4B + Luna: partial cohort review',f"Primary requested review: **{len(summaries)}/10 users**, {agg['sessions']}/100 sessions and {agg['questions']}/200 questions. Partial cohort by user request; evaluation stopped. No training or adapters. Reports below contain every completed user’s ten sessions, full statements, notes before/after, both decisions and raw tool calls.",
           '[Exact frozen prompts/settings](PROMPTS.md) · [Aggregate machine-readable results](aggregate.json)',
           '## Computed logs available independently of review',
           '[Maya session log](results/user01/SESSION_LOG.md) · [Evan session log](results/user02/SESSION_LOG.md) · [Aiko session log](results/user03/SESSION_LOG.md). These deterministic logs contain exact prompts/settings, full current statements, prior/updated notes, tool actions/results, choices, answers, evaluator-only gold, scores and note diffs/sizes. They contain no semantic-review narrative. Existing logs were rebuilt from saved JSON; the evaluator now calls the same renderer after each completed session for future runs. This logging-only change was made after the stopped run; the original executed sources remain frozen and hashed under frozen/. No model was rerun.',
           'Rebuild a log from the repository root: `PYTHONPATH=src python3 -m prompt_policy_llm.note_eval_log experiments/experiment0.3/prompted4b_cohort_20260918/results/user01`. Rebuild the review index/reports: `PYTHONPATH=src python3 experiments/experiment0.3/report_prompted_cohort.py experiments/experiment0.3/prompted4b_cohort_20260918 --max-users 3`.',
           '| User | Luna only | With prior notes | Delta correct | Finalized sessions | Invalid tool rounds | Report |','|---|---:|---:|---:|---:|---:|---|']
    for u in summaries:
        m=u['metrics'];b=m['overall']['baseline']['correct'];c=m['overall']['memory']['correct']
        index.append(f"| {u['name']} | {b}/20 | {c}/20 | {c-b:+} | {m['note_sessions_finished']}/10 | {m['invalid_note_rounds']}/{m['note_rounds']} | [{u['user']}](results/{u['user']}/REPORT.md) |")
    
    if stop:
        index+=['## Actual stop state', 'The stop request reduced the review to the first three users. At receipt, users01–04 had already completed and user05 had eight completed sessions: **48 sessions / 96 scored questions actually executed**. The evaluator process group was terminated immediately. Only users01–03 enter the primary results below; extra pre-stop output remains intact in [user04 raw results](results/user04/) and [user05 partial raw results](results/user05/). No subsequent run was launched. [Stop receipt](user_requested_stop.json).']
    index+=['## Note quality: final current-state fields', '| User | Supported | Ambiguous | Incorrect | Missing | Total fields |', '|---|---:|---:|---:|---:|---:|']
    for u,q in zip(summaries,qualities):
        f=q['final_field_counts'];index.append(f"| {u['name']} | {f['supported']} | {f['ambiguous']} | {f['incorrect']} | {f['missing']} | {f['total']} |")
    index+=['These are manual single-reviewer judgments over final revealed fields, separate from question accuracy. The reports document intermediate forgetting, missing history, scope errors and filler. They do not estimate exhaustive hallucination precision/recall.', '## Findings', 'For the requested three users, prior notes raised accuracy from **34/60 (56.7%) to55/60 (91.7%)**, a35-percentage-point increase:22 memory-only wins,1 baseline-only win,33 both-correct and4 both-wrong. Earlier-session questions improved20/46→41/46; historical questions5/11→10/11; current-session questions were14/14 for both arms. These are descriptive results on this fixed synthetic cohort, without statistical generalization.', 'Maya:10/20→19/20; missed completed intent caused the remaining error. Evan:15/20→20/20 despite four missing final fields and ambiguous shirt-pattern history. Aiko:9/20→16/20; temporary restoration was misanswered even when baseline notes existed, languages were omitted, historical hat occasions were overwritten, and shirt brands were later forgotten. The sole paired regression was Aiko session5: baseline selected the correct historical hat occasion, while notes led to the newer value.', 'All124 tool calls were valid and all30 note sessions finalized; no generated call hit its768-token output cap. Nevertheless, final-note field review found46/65 supported,15 missing,2 ambiguous and2 incorrect. This manual current-state audit is separate from complete historical coverage. Examples: Maya changed a deadline by nine minutes and retained three irrelevant statements; Evan dropped a cancelled intent; Aiko deleted several prior facts and misbound an unknown update to the word travel.', 'The first three users took273.08s total evaluation wall time:125.99s Qwen generation and146.60s Luna API wait. Final notes were206,132 and131 words respectively, all one entry and well below the1600-word budget. Aiko shrank145→84 words in session7 while losing facts. The run used serial interleaving; two-phase bounded-concurrent Luna execution is valid for a future run but was not implemented after the stop request.', '## Aggregate',block({k:v for k,v in agg.items() if k!='users'}),'## Interpretation limits','Paired accuracy measures usefulness of prior Qwen notes on these fixed questions. Factual support, omissions and hallucinations require the separate note-quality review; protocol validity alone cannot establish them. This is a small synthetic cohort, and the earlier1.7B runs differ in prompt/interface and caching, so their differences are confounded.']
    (root/'README.md').write_text(render(index))
    print(json.dumps({k:v for k,v in agg.items() if k!='users'},indent=2))


if __name__=='__main__':main()
