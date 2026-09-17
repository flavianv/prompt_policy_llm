#!/usr/bin/env python3
"""Validate/reanalyze saved experiment0.0; fresh inference requires --real-run."""
import argparse
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument('--validate', action='store_true', help='default: offline hashes, data, scores and temporal audit')
    mode.add_argument('--reanalyze', action='store_true', help='offline: additionally write derived metrics and audit to --output')
    mode.add_argument('--real-run', action='store_true', help='explicitly permit paid Luna calls and local GPU inference')
    p.add_argument('--output', type=Path, help='new output directory (required for reanalysis or real run)')
    p.add_argument('--model-path', type=Path, help='verified local Qwen3-1.7B snapshot, required for real run')
    p.add_argument('--credentials', type=Path, help='existing private OpenAI .env; never copied or printed')
    return p


def validate():
    manifest = json.loads((HERE/'manifest.json').read_text())
    for rel, digest in manifest['files_sha256'].items():
        path = REPO/rel
        if not path.is_file() or sha(path) != digest:
            raise ValueError('Checksum mismatch: ' + rel)
    sys.path[:0] = [str(HERE/'vendor/adaptgym/src'), str(REPO/'src')]
    from adaptgym import AdaptGymEnv, DifficultyConfig
    from prompt_policy_llm.adaptgym_pilot import summarize, parse_answers
    root = HERE/'evidence'
    rows = lambda name: [json.loads(line) for line in (root/name).read_text().splitlines()]
    episodes = rows('evaluator_episodes.jsonl')
    for e in episodes:
        generated = asdict(AdaptGymEnv(DifficultyConfig(**e['config'])).generate_episode())
        assert json.loads(json.dumps(generated)) == e, 'Episode regeneration mismatch'
    scores, calls, notes = rows('scores.jsonl'), rows('answer_calls.jsonl'), rows('note_traces.jsonl')
    for score in scores:
        for arm in ('baseline', 'memory'):
            call = next(c for c in calls if c['user_id'] == score['user_id'] and c['session'] == score['session'] and (c['arm'] == arm or c['shared_identical_request']))
            answers, valid = parse_answers(call['generation']['text'], call['payload']['questions'])
            chosen = answers.get(score['question']['id'])
            assert chosen == score[arm+'_answer']
            assert valid == score[arm+'_valid']
            assert (chosen == score['question']['answer']) == score[arm+'_correct']
    for case in json.loads((HERE/'cases.json').read_text()):
        assert case['producer_trace'] == notes[case['source_note_line']-1]
        assert case['score'] == scores[case['score_line']-1]
        for call in case['answer_calls']:
            assert call['record'] == calls[call['line']-1]
    spec = importlib.util.spec_from_file_location('experiment_audit', REPO/'scripts/audit_adaptgym_pilot.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    audit = module.audit(root)
    computed = summarize(rows('scores.jsonl'), rows('note_traces.jsonl'))
    saved = json.loads((root/'metrics.json').read_text())
    for key, value in computed.items():
        assert value == saved[key], 'Saved metric mismatch: ' + key
    assert audit == json.loads((root/'audit.json').read_text()), 'Saved audit mismatch'
    return manifest, computed, audit


def main(argv=None):
    args = parser().parse_args(argv)
    if (args.reanalyze or args.real_run) and (args.output is None or args.output.exists()):
        raise ValueError('Specify a NEW --output directory before any model/API calls')
    manifest, computed, audit = validate()
    print(json.dumps({'experiment': manifest['experiment_id'], 'offline_validation': 'passed',
                      'overall': computed['overall'], 'temporal_checks': audit['checks']}, indent=2))
    if args.reanalyze:
        args.output.mkdir(parents=True)
        (args.output/'recomputed_metrics.json').write_text(json.dumps(computed, indent=2)+'\n')
        (args.output/'audit.json').write_text(json.dumps(audit, indent=2)+'\n')
    if not args.real_run:
        return 0
    if args.model_path is None or args.credentials is None or not args.credentials.is_file():
        raise ValueError('--real-run requires --model-path and an existing --credentials file')
    # Exact weights/tokenizer identity, not merely a model-name assertion.
    model_manifest = json.loads((HERE/'model_manifest.json').read_text())
    for file in model_manifest['files']:
        p = args.model_path/file['path']
        if not p.is_file() or p.stat().st_size != file['size']:
            raise ValueError('Model file absent or size mismatch: '+file['path'])
        if file['lfs']:
            assert sha(p) == file['lfs']['sha256'], 'Model checksum mismatch'
        else:
            blob = p.read_bytes()
            assert hashlib.sha1(b'blob '+str(len(blob)).encode()+b'\0'+blob).hexdigest() == file['blob_id'], 'Model Git blob mismatch'
    import os
    env = dict(os.environ)
    env['PYTHONPATH'] = str(HERE/'vendor/adaptgym/src') + os.pathsep + str(REPO/'src')
    print('Explicit real-run opt-in: starting fixed protocol; API results may differ.', flush=True)
    return subprocess.call([sys.executable, '-m', 'prompt_policy_llm.adaptgym_pilot',
                            '--model-path', str(args.model_path.resolve()),
                            '--credentials', str(args.credentials.resolve()),
                            '--output', str(args.output.resolve())], env=env)


if __name__ == '__main__':
    raise SystemExit(main())
