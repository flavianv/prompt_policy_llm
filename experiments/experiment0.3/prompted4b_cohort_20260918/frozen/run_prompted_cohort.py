"""Frozen cohort: one model load, isolated user memory, bounded cached Luna calls."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import time

from prompt_policy_llm.adaptgym_pilot import load_credentials
from prompt_policy_llm.eval_note_policy import evaluate_episode
from prompt_policy_llm.explicit_memory import Luna
from prompt_policy_llm.explicit_note_coverage import SYSTEM, CHECK
from prompt_policy_llm.explicit_note_tools import TOOLS
from prompt_policy_llm.note_model import load_model, verify_snapshot
from prompt_policy_llm.note_reward import AnswerCache, ANSWER_PROMPT
from prompt_policy_llm.note_rollouts import NativeRollout


def main():
    p = argparse.ArgumentParser()
    for name in ['root', 'credentials']:
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    root = a.root
    cfg = json.loads((root / 'eval_config.json').read_text())
    load_credentials(a.credentials)
    identity = verify_snapshot(cfg['model_path'], root / 'model_manifest.json')
    import torch
    torch.manual_seed(cfg['seed'])
    model, tokenizer = load_model(cfg)
    manager = NativeRollout(model, tokenizer, cfg)
    assert not any(p.requires_grad for p in model.parameters())
    manifest = json.loads((root / 'dataset/manifest.json').read_text())
    source_hashes = {str(f.relative_to(root)): hashlib.sha256(f.read_bytes()).hexdigest()
                     for f in sorted((root / 'src').rglob('*.py'))}
    source_hashes['run_prompted_cohort.py'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    shared = dict(config=cfg, model_revision=identity['revision'], adapter=None, weight_training=False,
                  note_system=SYSTEM, coverage_check=CHECK, tools=TOOLS, answer_system=ANSWER_PROMPT,
                  cache_policy='identical payloads share exact cached output; no retries',
                  note_decoding=dict(do_sample=False, enable_thinking=False,
                                     max_new_tokens=cfg['note_max_output_tokens'], repetition_penalty=1.,
                                     use_cache=True, temperature=None, top_p=None, top_k=None),
                  answer_settings=dict(reasoning='low', store=False, max_retries=0,
                                       max_output_tokens=cfg['answer_max_output_tokens']),
                  versions={k: metadata.version(k) for k in ['torch', 'transformers', 'peft', 'openai']},
                  gpu=torch.cuda.get_device_name(0), all_weights_frozen=True, source_sha256=source_hashes,
                  started_at=datetime.now(timezone.utc).isoformat())
    (root / 'shared_run_config.json').write_text(json.dumps(shared, indent=2))
    completed = []
    for user in manifest['users']:
        uid = user['user']
        output = root / 'results' / uid
        episode_path = root / 'dataset' / uid / 'episode.json'
        episode = json.loads(episode_path.read_text())
        assert len(episode['cases']) == 10 and sum(len(c['questions']) for c in episode['cases']) == 20
        run_cfg = {**shared, 'user': user, 'episode_sha256': hashlib.sha256(episode_path.read_bytes()).hexdigest(),
                   'cache_directory': str(root / 'answer_cache' / uid)}
        # Completed immutable runs may be reused only with identical inputs/settings/sources.
        if (output / 'metrics.json').exists():
            old = json.loads((output / 'run_config.json').read_text())
            for key in ['config', 'model_revision', 'source_sha256', 'episode_sha256', 'note_system', 'tools', 'answer_system']:
                assert old[key] == run_cfg[key], ('incompatible resume', uid, key)
            completed.append(uid)
            continue
        cache = AnswerCache(root / 'answer_cache' / uid, Luna(cfg['answer_model']), cfg['answer_model'],
                            max_calls=cfg['answer_max_api_calls_per_user'], max_tokens=cfg['answer_max_output_tokens'])
        print(json.dumps({'user_started': uid, 'name': user['name']}), flush=True)
        torch.cuda.reset_peak_memory_stats()
        start = time.perf_counter()
        result = evaluate_episode(episode, manager, cache, output, run_cfg)
        result.update(wall_seconds=time.perf_counter() - start, peak_gpu_memory_bytes=torch.cuda.max_memory_allocated(),
                      completed_at=datetime.now(timezone.utc).isoformat())
        (output / 'metrics.json').write_text(json.dumps(result, indent=2))
        completed.append(uid)
        (root / 'progress.json').write_text(json.dumps({'completed': completed, 'last_metrics': result}, indent=2))
        print(json.dumps({'user_finished': uid, 'metrics': result}), flush=True)
    (root / 'complete.json').write_text(json.dumps({'completed': completed, 'finished_at': datetime.now(timezone.utc).isoformat()}, indent=2))


if __name__ == '__main__':
    main()
