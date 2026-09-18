"""Luna-free mode of the existing BF16 LoRA/GRPO trainer. Not launched by export."""
from copy import deepcopy
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import random
import time
from .note_model import load_model,verify_snapshot
from .note_rollouts import action_logprobs
from .structured_notes import score_extractions,SYSTEM,VERSION
from .structured_note_rollouts import StructuredRollout,collect_candidates


def score_candidates(candidates,gold):
    for candidate in candidates:
        candidate['reward']=score_extractions(candidate['trace'].get('raw_output',''),gold)
    return candidates


def run(args,cfg):
    import torch
    from .train_note_grpo import train_group
    assert cfg['reward_mode']=='extraction_count' and 0<args.steps<=cfg['smoke_steps']
    manifest=json.loads((args.data/'manifest.json').read_text());assert manifest['version']==VERSION and manifest['complete']
    # Validate the complete export before loading weights or beginning optimization.
    for path,digest in manifest['files_sha256'].items():
        assert hashlib.sha256((args.data/path).read_bytes()).hexdigest()==digest,('data hash mismatch',path)
    users=[u for u in manifest['users'] if u['split']=='train'];assert users
    assert not ({u['user'] for u in users}&{u['user'] for u in manifest['users'] if u['split']!='train'})
    torch.manual_seed(cfg['seed']);random.seed(cfg['seed'])
    identity=verify_snapshot(cfg['model_path'],args.manifest)
    args.output.mkdir(parents=True,exist_ok=False)
    model,tok=load_model(cfg,train=True);manager=StructuredRollout(model,tok,cfg)
    model.save_pretrained(args.output/'initial_adapter');tok.save_pretrained(args.output/'initial_adapter')
    optimizer=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=cfg['learning_rate'])
    run_config={'config':cfg,'base_revision':identity['revision'],'reward':'raw exact current-profile extraction count; no history requirement/penalty/normalization',
        'source_sha256':{name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest() for name in ['structured_notes.py','structured_note_records.py','structured_note_rollouts.py','train_structured_grpo.py','train_note_grpo.py','note_model.py','note_rollouts.py']},'policy_system':SYSTEM,'data_manifest':manifest,'api_calls':0,'only_lora_trainable':all('lora_' in n for n,p in model.named_parameters() if p.requires_grad),
        'versions':{k:metadata.version(k) for k in ['torch','transformers','peft']},'gpu':torch.cuda.get_device_name(0)}
    (args.output/'run_config.json').write_text(json.dumps(run_config,indent=2));steps=[];start=time.perf_counter();reload_probe=None
    for step in range(args.steps):
        user=users[step%len(users)];public=json.loads((args.data/'public'/f"{user['user']}.json").read_text())['sessions']
        session=cfg.get('structured_smoke_sessions',[0,4,9])[step%len(cfg.get('structured_smoke_sessions',[0,4,9]))]
        assert session<len(public)
        prior,prefix,candidates=collect_candidates(manager,public,session,cfg['group_size'])
        # Gold is loaded only AFTER policy rollouts and is never passed to the manager.
        gold=json.loads((args.data/'evaluator_only'/user['user']/f'session{session+1:02d}.json').read_text())
        score_candidates(candidates,gold)
        if not any(c['trace']['finished'] for c in candidates):update={'updated':False,'reason':'all_invalid_json_trajectories'}
        else:update=train_group(model,optimizer,candidates,cfg)
        record={'step':step,'user':user['user'],'session':session,'prior_notes':prior,'prefix_traces':prefix,'candidates':candidates,'optimizer':update,'api_calls':0}
        (args.output/f'step{step:03d}.json').write_text(json.dumps(record));steps.append(update)
        print(json.dumps({'step_done':step,**update,'correct_extractions':[c['reward']['correct'] for c in candidates],'api_calls':0}),flush=True)
        checkpoint=args.output/f'checkpoint-{step+1}';model.save_pretrained(checkpoint);tok.save_pretrained(checkpoint)
        torch.save({'optimizer':optimizer.state_dict(),'torch_rng':torch.get_rng_state(),'cuda_rng':torch.cuda.get_rng_state_all(),'python_rng':random.getstate(),'step':step,'config':cfg},checkpoint/'training_state.pt')
        reload_probe=next((s for c in candidates for s in c['trace']['segments']),reload_probe)
        if not update['updated']:break
    final=args.output/'final_adapter';model.save_pretrained(final);tok.save_pretrained(final);reload_error=None
    if reload_probe is not None:
        with torch.no_grad():expected=action_logprobs(model,reload_probe).cpu()
        model.load_adapter(str(final),adapter_name='reload_check',is_trainable=False);model.set_adapter('reload_check')
        with torch.no_grad():actual=action_logprobs(model,reload_probe).cpu()
        reload_error=float((actual-expected).abs().max());assert reload_error<1e-5
    summary={'optimizer_steps':sum(x['updated'] for x in steps),'attempted_groups':len(steps),'api_calls':0,'reward_mode':'extraction_count',
        'checkpoint_reload_max_logprob_error':reload_error,'wall_seconds':time.perf_counter()-start,'peak_gpu_memory_bytes':torch.cuda.max_memory_allocated(),'steps':steps}
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary),flush=True)
