"""Paired, session-level AdaptGym evaluation with a frozen Qwen note manager.

Ground truth stays in the evaluator. Every API call is stateless. Only the
explicit note dictionary crosses session boundaries in the memory arm.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import random
import time

from .backend import extract_response_text, estimate_luna_cost

ANSWER_SYSTEM = (
    'Recover the current user preferences from the supplied evidence. '
    'Current explicit statements supersede older notes. Other people, hypothetical '
    'examples, product descriptions, and historical preferences are not current user '
    'preferences. Answer every question, making your best guess if evidence is absent. '
    'Return only a JSON object mapping question IDs to one option letter each, '
    'for example {"q0":"B","q1":"A"}.'
)
NOTE_SYSTEM = """Maintain notes about ONE user's current preferences. Save only explicit
current preferences. Ignore other people, hypotheticals, product descriptions and
historical facts. Update superseded preferences. Do not infer demographic tastes.
You are a note manager, not an answerer. Use at most 12 notes and 120 words total.
Available tools:
- read_notes: arguments {}. Returns all notes. Call once before changes.
- write_note: arguments {"name": category, "text": concise_fact}. Name must be new.
- update_note: arguments {"name": existing_category, "text": replacement_fact}.
- no_op: arguments {}. Finishes this session after changes, or without changes.
Return exactly ONE JSON object with ONE calls array, nothing else.
First response: {"calls":[{"tool":"read_notes","arguments":{}}]}
After the read result, put every write/update AND no_op in the SAME array.
Example for an unrelated user's evidence 'I prefer swimming for exercise':
{"calls":[{"tool":"write_note","arguments":{"name":"exercise","text":"User prefers swimming for exercise."}},{"tool":"no_op","arguments":{}}]}
If notes already contain the fact: {"calls":[{"tool":"no_op","arguments":{}}]}
Use meaningful category names, not placeholders. Never return multiple JSON objects.
"""


def session_cases(episode):
    """Use only prefix truth; never use episode.questions or final_profile."""
    from adaptgym.environment import SLOT_VALUES
    profile, last_seen = {}, {}
    for session in range(episode.config['session_count']):
        observations = [o for o in episode.observations if o.session_index == session]
        # Metadata is used ONLY here for evaluation labels, never rendered as input.
        for obs in observations:
            if obs.metadata.get('is_profile_event'):
                profile[obs.metadata['slot']] = obs.metadata['value']
                last_seen[obs.metadata['slot']] = session
        questions = []
        rng = random.Random(episode.config['seed'] * 1009 + session)
        for i, slot in enumerate(sorted(profile)):
            # Standard MC candidates are evaluator-created and shared exactly.
            decoys = [v for v in SLOT_VALUES[slot] if v != profile[slot]]
            options = [profile[slot], *rng.sample(decoys, 3)]
            rng.shuffle(options)
            choices = {chr(65 + j): value for j, value in enumerate(options)}
            questions.append({'id': f'q{i}', 'slot': slot,
                              'question': f"What is the user's latest preference for {slot}?",
                              'options': choices,
                              'last_true_evidence_session': last_seen[slot],
                              'evidence_delay': session - last_seen[slot],
                              'current_text_mentions_answer': any(profile[slot] in o.text for o in observations),
                              'answer': next(k for k, v in choices.items() if v == profile[slot])})
        yield {'session': session, 'evidence': [o.text for o in observations],
               'questions': questions}


def answer_payload(case, notes):
    return {'current_session': case['evidence'], 'prior_session_notes': dict(notes),
            'questions': [{k: q[k] for k in ('id', 'question', 'options')}
                          for q in case['questions']]}


def parse_answers(text, questions):
    try:
        result = json.loads(text)
    except (ValueError, TypeError):
        return {}, False
    if not isinstance(result, dict):
        return {}, False
    valid = (set(result) == {q['id'] for q in questions} and
             all(isinstance(result.get(q['id']), str) and
                 result[q['id']] in q['options'] for q in questions))
    # Invalid rows count as wrong, never disappear from denominator.
    return (result if valid else {}), valid


def apply_calls(raw, notes, has_read):
    """Strict, transactional tool execution; a rejected batch cannot mutate notes."""
    body = json.loads(raw)
    if not isinstance(body, dict) or set(body) != {'calls'}:
        raise ValueError('expected calls object')
    calls = body['calls']
    if not isinstance(calls, list) or not 1 <= len(calls) <= 8:
        raise ValueError('expected 1..8 calls')
    pending, results, done = dict(notes), [], False
    read = has_read
    for call in calls:
        if done or not isinstance(call, dict) or set(call) != {'tool', 'arguments'}:
            raise ValueError('invalid call or call after no_op')
        tool, args = call['tool'], call['arguments']
        if not isinstance(args, dict):
            raise ValueError('arguments must be object')
        if tool == 'read_notes':
            if args or len(calls) != 1:
                raise ValueError('read_notes must be alone with empty arguments')
            read = True
            results.append({'tool': tool, 'notes': dict(pending)})
        elif tool == 'no_op':
            if args or not read:
                raise ValueError('must read before finishing')
            done = True
            results.append({'tool': tool, 'ok': True})
        elif tool in ('write_note', 'update_note'):
            if not read or set(args) != {'name', 'text'}:
                raise ValueError('read first; name and text required')
            name, text = args['name'], args['text']
            if not isinstance(name, str) or not name.strip() or len(name) > 80:
                raise ValueError('invalid note name')
            if not isinstance(text, str) or not text.strip() or len(text) > 1200:
                raise ValueError('invalid note text')
            if (tool == 'write_note' and name in pending) or (tool == 'update_note' and name not in pending):
                raise ValueError('write requires new name; update requires existing name')
            pending[name] = text
            if len(pending) > 12 or sum(len(x.split()) for x in pending.values()) > 120:
                raise ValueError('note budget exceeded')
            results.append({'tool': tool, 'ok': True})
        else:
            raise ValueError('unknown tool')
    notes.clear()
    notes.update(pending)
    return results, read, done


class QwenNotes:
    def __init__(self, model_path):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path, local_files_only=True, dtype=torch.bfloat16,
            attn_implementation='sdpa').to('cuda').eval()

    def generate(self, messages):
        prompt = self.tokenizer.apply_chat_template(messages, tokenize=False,
                                                   add_generation_prompt=True, enable_thinking=False)
        batch = self.tokenizer(prompt, return_tensors='pt').to('cuda')
        self.torch.cuda.synchronize()
        start = time.perf_counter()
        with self.torch.inference_mode():
            result = self.model.generate(**batch, max_new_tokens=384, do_sample=False,
                                         pad_token_id=self.tokenizer.eos_token_id)
        self.torch.cuda.synchronize()
        tokens = result[0, batch.input_ids.shape[1]:]
        return {'text': self.tokenizer.decode(tokens, skip_special_tokens=True),
                'input_tokens': batch.input_ids.shape[1], 'output_tokens': len(tokens),
                'latency_s': time.perf_counter() - start,
                'hit_output_cap': len(tokens) >= 384}

    def update(self, evidence, notes):
        # New messages every session: no prior chat/KV state retained.
        messages = [{'role': 'system', 'content': NOTE_SYSTEM},
                    {'role': 'user', 'content': json.dumps({'current_session': evidence})}]
        traces, read, done = [], False, False
        for round_index in range(4):
            generation = self.generate(messages)
            before = dict(notes)
            try:
                results, read, done = apply_calls(generation['text'], notes, read)
                valid, error = True, None
            except (ValueError, TypeError, KeyError) as exc:
                results, valid, error = {'error': str(exc)}, False, str(exc)
            traces.append({'round': round_index, 'messages': list(messages),
                           'generation': generation, 'valid': valid, 'error': error,
                           'tool_results': results, 'notes_before': before, 'notes_after': dict(notes)})
            messages.extend([{'role': 'assistant', 'content': generation['text']},
                             {'role': 'user', 'content': 'Tool results: ' + json.dumps(results) +
                              ('\nRead is complete. Now write/update the current preferences from the session, then no_op. Do not read again.' if read else '\nCorrect the tool call and try again.')}])
            if done:
                break
        return {'rounds': traces, 'finished': done}


class LunaAnswers:
    def __init__(self, model='gpt-5.6-luna'):
        from openai import OpenAI
        self.client = OpenAI(timeout=90, max_retries=0)
        self.model = model

    def answer(self, payload):
        start = time.perf_counter()
        response = self.client.responses.create(
            model=self.model, input=[{'role': 'system', 'content': ANSWER_SYSTEM},
                                    {'role': 'user', 'content': json.dumps(payload)}],
            reasoning={'effort': 'low'}, max_output_tokens=1024, store=False)
        usage = response.usage
        return {'text': extract_response_text(response), 'model': response.model,
                'response_id': response.id, 'status': response.status,
                'input_tokens': usage.input_tokens, 'output_tokens': usage.output_tokens,
                'latency_s': time.perf_counter() - start,
                'estimated_cost_usd': estimate_luna_cost(usage.input_tokens, usage.output_tokens)}


def summarize(rows, note_rows):
    def group(items):
        n = len(items)
        return {'questions': n, 'baseline_correct': sum(r['baseline_correct'] for r in items),
                'memory_correct': sum(r['memory_correct'] for r in items),
                'baseline_accuracy': sum(r['baseline_correct'] for r in items)/n if n else 0,
                'memory_accuracy': sum(r['memory_correct'] for r in items)/n if n else 0,
                'memory_only_wins': sum(r['memory_correct'] and not r['baseline_correct'] for r in items),
                'baseline_only_wins': sum(r['baseline_correct'] and not r['memory_correct'] for r in items),
                'both_correct': sum(r['baseline_correct'] and r['memory_correct'] for r in items),
                'both_wrong': sum(not r['baseline_correct'] and not r['memory_correct'] for r in items),
                'baseline_invalid': sum(not r['baseline_valid'] for r in items),
                'memory_invalid': sum(not r['memory_valid'] for r in items)}
    rounds = [r for s in note_rows for r in s['rounds']]
    tools = Counter()
    for r in rounds:
        if r['valid']:
            tools.update(c['tool'] for c in json.loads(r['generation']['text'])['calls'])
    return {'overall': group(rows),
            'by_session': {str(s): group([r for r in rows if r['session'] == s]) for s in sorted({r['session'] for r in rows})},
            'by_evidence_delay': {str(d): group([r for r in rows if r['question']['evidence_delay'] == d]) for d in sorted({r['question']['evidence_delay'] for r in rows})},
            'by_user': {u: group([r for r in rows if r['user_id'] == u]) for u in sorted({r['user_id'] for r in rows})},
            'note_policy': {'sessions': len(note_rows), 'rounds': len(rounds),
                            'valid_rounds': sum(r['valid'] for r in rounds),
                            'output_cap_rounds': sum(r['generation'].get('hit_output_cap', False) for r in rounds),
                            'finished_sessions': sum(s['finished'] for s in note_rows),
                            'executed_tools': dict(tools),
                            'input_tokens': sum(r['generation']['input_tokens'] for r in rounds),
                            'output_tokens': sum(r['generation']['output_tokens'] for r in rounds),
                            'latency_s': sum(r['generation']['latency_s'] for r in rounds)}}


def run(episodes, answerer, manager, output):
    output.mkdir(parents=True, exist_ok=False)
    rows, note_rows, calls = [], [], []
    def append(name, obj):
        with (output/name).open('a') as handle:
            handle.write(json.dumps(obj) + '\n')
    for episode in episodes:
        append('evaluator_episodes.jsonl', asdict(episode))
        notes = {}
        for case in session_cases(episode):
            prior_notes = dict(notes)
            payloads = {'baseline': answer_payload(case, {}), 'memory': answer_payload(case, prior_notes)}
            assert payloads['baseline']['current_session'] == payloads['memory']['current_session']
            assert payloads['baseline']['questions'] == payloads['memory']['questions']
            shared = payloads['baseline'] == payloads['memory']
            outputs = {}
            order = ['baseline', 'memory']
            random.Random(episode.config['seed'] * 17 + case['session']).shuffle(order)
            for arm in order:
                if shared and outputs:
                    outputs[arm] = next(iter(outputs.values()))
                    continue
                generation = answerer.answer(payloads[arm])
                outputs[arm] = generation
                call = {'user_id': episode.user_id, 'session': case['session'], 'arm': arm,
                        'shared_identical_request': shared, 'system': ANSWER_SYSTEM,
                        'payload': payloads[arm], 'generation': generation}
                calls.append(call)
                append('answer_calls.jsonl', call)
            parsed = {a: parse_answers(outputs[a]['text'], case['questions']) for a in order}
            for q in case['questions']:
                row = {'user_id': episode.user_id, 'session': case['session'], 'question': q,
                       'prior_notes': prior_notes, 'shared_identical_request': shared}
                for arm in order:
                    answers, valid = parsed[arm]
                    row.update({f'{arm}_answer': answers.get(q['id']), f'{arm}_valid': valid,
                                f'{arm}_correct': answers.get(q['id']) == q['answer']})
                rows.append(row)
                append('scores.jsonl', row)
            # Crucially: no questions, answer outputs, correctness or truth to manager.
            note_trace = manager.update(list(case['evidence']), notes)
            note_trace.update({'user_id': episode.user_id, 'session': case['session'],
                               'notes_before': prior_notes, 'notes_after': dict(notes)})
            note_rows.append(note_trace)
            append('note_traces.jsonl', note_trace)
            print(json.dumps({'user': episode.user_id, 'session': case['session'],
                              'notes': len(notes), 'update_finished': note_trace['finished']}), flush=True)
    metrics = summarize(rows, note_rows)
    metrics['luna_actual_calls'] = len(calls)
    metrics['luna_status_counts'] = dict(Counter(c['generation'].get('status', 'unknown') for c in calls))
    metrics['luna_usage'] = {k: sum(c['generation'][k] for c in calls)
                            for k in ('input_tokens', 'output_tokens', 'latency_s', 'estimated_cost_usd')}
    metrics['first_session_parity'] = all(r['shared_identical_request'] and
                                        r['baseline_answer'] == r['memory_answer']
                                        for r in rows if r['session'] == 0)
    metrics['cost_note'] = 'Estimated Luna API cost using repository rates, not billing; Qwen hardware cost excluded.'
    (output/'metrics.json').write_text(json.dumps(metrics, indent=2))
    return metrics


def load_credentials(path):
    """Load only OpenAI configuration; never shell-source or log values."""
    from dotenv import dotenv_values
    for key, value in dotenv_values(path).items():
        if key in ('OPENAI_API_KEY', 'OPENAI_BASE_URL', 'OPENAI_ORG_ID', 'OPENAI_PROJECT_ID') and value:
            os.environ[key] = value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-path', default='/home/criteo/qwen17b-work/model')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--credentials', type=Path, default=Path('/home/criteo/reco-rl/app/backend/.env'))
    parser.add_argument('--smoke', action='store_true')
    args = parser.parse_args()
    from adaptgym import AdaptGymEnv, DifficultyConfig
    load_credentials(args.credentials)
    answerer = LunaAnswers()
    # Small authorized access check before GPU load or the pilot.
    access = answerer.answer({'current_session': ['For drink, I prefer green tea.'],
                             'prior_session_notes': {}, 'questions': [{'id': 'q0', 'question': 'Preferred drink?',
                                                                      'options': {'A': 'green tea', 'B': 'coffee'}}]})
    if access['status'] != 'completed' or json.loads(access['text']) != {'q0': 'A'}:
        raise RuntimeError('Luna access smoke failed: ' + access['status'])
    print('Luna access smoke passed', flush=True)
    manager = QwenNotes(args.model_path)
    smoke_notes = {}
    smoke_trace = manager.update(['For drink, I prefer green tea.'], smoke_notes)
    if not smoke_trace['finished'] or not any('green tea' in v.lower() for v in smoke_notes.values()):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.with_suffix('.smoke_failure.json').write_text(json.dumps(smoke_trace, indent=2))
        raise RuntimeError('Qwen tool smoke failed; trace saved')
    print('Qwen GPU/tool smoke passed', flush=True)
    if args.smoke:
        args.output.mkdir(parents=True, exist_ok=False)
        (args.output/'smoke.json').write_text(json.dumps({'luna': access, 'qwen': smoke_trace}, indent=2))
        return
    seeds = [17, 29, 43, 59, 71, 89, 101, 113, 127, 139]
    episodes = [AdaptGymEnv(DifficultyConfig(profile_size=5, session_count=10,
                  distractors_per_session=2, update_rate=0.35, seed=seed)).generate_episode() for seed in seeds]
    start = time.perf_counter()
    metrics = run(episodes, answerer, manager, args.output)
    import torch, transformers, openai
    config = {'seeds': seeds, 'sessions': 10, 'profile_size': 5, 'update_rate': 0.35,
              'distractors_per_session': 2, 'choices_per_question': 4, 'note_budget_words': 120,
              'model_path': args.model_path, 'qwen_revision': '70d244cc86ccca08cf5af4e1e306ecf908b1ad5e',
              'qwen': {'fixed_weights': True, 'thinking': False, 'do_sample': False, 'max_new_tokens': 384,
                       'max_tool_rounds': 4, 'precision': 'bfloat16', 'tool_protocol': 'strict JSON executed by local dispatcher; not native API tool_calls'},
              'luna': {'model': answerer.model, 'reasoning_effort': 'low', 'max_output_tokens': 1024,
                       'temperature': None, 'seed': None, 'store': False, 'max_retries': 0},
              'protocol': 'score each session using prior notes, then update; all notes supplied; identical requests shared',
              'versions': {'torch': torch.__version__, 'transformers': transformers.__version__, 'openai': openai.__version__},
              'gpu': torch.cuda.get_device_name(0), 'wall_time_s': time.perf_counter()-start,
              'qwen_context_limit': manager.model.config.max_position_embeddings,
              'max_observed_qwen_input_tokens': max(r['generation']['input_tokens'] for n in [json.loads(line) for line in (args.output/'note_traces.jsonl').read_text().splitlines()] for r in n['rounds']),
              'max_observed_luna_input_tokens': max(json.loads(line)['generation']['input_tokens'] for line in (args.output/'answer_calls.jsonl').read_text().splitlines()),
              'pilot_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'smoke_luna': access, 'smoke_qwen': smoke_trace}
    (args.output/'run_config.json').write_text(json.dumps(config, indent=2))
    print(json.dumps(metrics, indent=2), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # API errors may contain credential fragments; print only type/status.
        print(json.dumps({'error_type': type(exc).__name__, 'status_code': getattr(exc, 'status_code', None)}), flush=True)
        raise SystemExit(1)
