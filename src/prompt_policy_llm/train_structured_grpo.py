"""Luna-free mode of the existing BF16 LoRA/GRPO trainer. Not launched by export."""
from copy import deepcopy
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import random
import time
from .note_model import load_model,verify_snapshot
from .text_note_updates import score_candidate
from .note_rollouts import action_logprobs
from .structured_notes import score_extractions,SYSTEM,VERSION
from .structured_note_rollouts import StructuredRollout,collect_candidates,TEXT_SYSTEM


def score_candidates(candidates,gold):
    for candidate in candidates:
        candidate['reward']=score_candidate(candidate,gold)
    return candidates


def build_schedule(manifest,cfg,steps):
    if cfg.get('structured_run_scope')=='all_existing_users_100_sessions':
        schedule=[(u,i) for u in manifest['users'] for i in range(u['sessions'])]
        assert len(schedule)==100 and steps==100
        return schedule
    users=[u for u in manifest['users'] if u['split']=='train'];assert users
    assert 0<steps<=cfg['smoke_steps']
    sessions=cfg.get('structured_smoke_sessions',[0,4,9])
    return [(users[i%len(users)],sessions[i%len(sessions)]) for i in range(steps)]


def run(args,cfg):
    import torch
    from .train_note_grpo import train_group
    from .structured_notes import empty_notes
    from .structured_note_rollouts import group_from_prior,carry_candidate_zero
    from .eval_structured_notes import evaluate,group_metrics,summarize,append_log
    assert cfg['reward_mode']=='extraction_count'
    manifest=json.loads((args.data/'manifest.json').read_text());assert manifest['version']==VERSION and manifest['complete']
    for path,digest in manifest['files_sha256'].items():
        assert hashlib.sha256((args.data/path).read_bytes()).hexdigest()==digest,('data hash mismatch',path)
    schedule=build_schedule(manifest,cfg,args.steps)
    full=cfg.get('structured_run_scope')=='all_existing_users_100_sessions'
    torch.manual_seed(cfg['seed']);random.seed(cfg['seed'])
    identity=verify_snapshot(cfg['model_path'],args.manifest);args.output.mkdir(parents=True,exist_ok=False)
    model,tok=load_model(cfg,train=True);manager=StructuredRollout(model,tok,cfg)
    assert all('lora_' in n for n,p in model.named_parameters() if p.requires_grad)
    model.save_pretrained(args.output/'initial_adapter');tok.save_pretrained(args.output/'initial_adapter')
    optimizer=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=cfg['learning_rate'])
    source_names=['text_note_updates.py','structured_notes.py','structured_note_records.py','structured_note_rollouts.py','train_structured_grpo.py','train_note_grpo.py','note_model.py','note_rollouts.py','eval_structured_notes.py']
    run_config={'config':cfg,'base_revision':identity['revision'],'reward':'raw one-to-one current-field value matches from plain-text notes; flexible keys; ambiguous values require context; no penalty/normalization',
        'policy_system':TEXT_SYSTEM,'policy_tools':[],'data_manifest':manifest,'api_calls':0,'only_lora_trainable':True,
        'all_sessions_training':full,'training_schedule':[{'user':u['user'],'session':s,'original_split':u['split']} for u,s in schedule],
        'evaluation_design':'four samples/context, fixed candidate0 carry, matched seeds; in-sample only',
        'primary_metric':'mean per-session normalized correct current fields across all4traces',
        'source_sha256':{name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest() for name in source_names},
        'versions':{k:metadata.version(k) for k in ['torch','transformers','peft']},'gpu':torch.cuda.get_device_name(0)}
    (args.output/'run_config.json').write_text(json.dumps(run_config,indent=2));steps=[];records=[];start=time.perf_counter();reload_probe=None
    if full:
        with model.disable_adapter():baseline=evaluate(manager,args.data,manifest['users'],args.output/'baseline','frozen_prompted',cfg)
        torch.manual_seed(cfg['seed']);random.seed(cfg['seed'])
    prior=empty_notes();previous_user=None
    for step,(user,session) in enumerate(schedule):
        uid=user['user'];public=json.loads((args.data/'public'/f'{uid}.json').read_text())['sessions']
        if full:
            if uid!=previous_user:prior=empty_notes()
            prefix=[];candidates=group_from_prior(manager,public[session]['observation'],prior,cfg['group_size'])
        else:prior,prefix,candidates=collect_candidates(manager,public,session,cfg['group_size'])
        gold=json.loads((args.data/'evaluator_only'/uid/f'session{session+1:02d}.json').read_text());score_candidates(candidates,gold)
        carried=carry_candidate_zero(prior,candidates)
        if not any(c['trace']['finished'] for c in candidates):update={'updated':False,'reason':'all_invalid_json_trajectories'}
        else:update=train_group(model,optimizer,candidates,cfg)
        record={'step':step,'user':uid,'session':session,'observation':public[session]['observation'],'prior_notes':deepcopy(prior),
                'prefix_traces':prefix,'candidates':candidates,'carried_notes':carried,'metrics':group_metrics(candidates),'optimizer':update,'api_calls':0}
        (args.output/f'step{step:03d}.json').write_text(json.dumps(record));steps.append(update);records.append(record)
        log=args.output/f'{uid}_TRAINING_LOG.md'
        if not log.exists():log.write_text(f'# Training: {uid}\n\nRaw count reward; fixed candidate0 own-memory carry.\n')
        append_log(log,record)
        with (args.output/'training_metrics.jsonl').open('a') as f:f.write(json.dumps({'step':step,'user':uid,'session':session,'optimizer':update,**record['metrics']})+'\n')
        print(json.dumps({'phase':'training','step_done':step+1,'total_sessions':len(schedule),'user':uid,'session':session+1,**update,'correct_extractions':[c['reward']['correct'] for c in candidates],'api_calls':0}),flush=True)
        prior=carried;previous_user=uid
        reload_probe=next((s for c in candidates for s in c['trace']['segments']),reload_probe)
        if (step+1)%cfg.get('checkpoint_every',25)==0 or step+1==len(schedule):
            checkpoint=args.output/f'checkpoint-{step+1}';model.save_pretrained(checkpoint);tok.save_pretrained(checkpoint)
            torch.save({'optimizer':optimizer.state_dict(),'torch_rng':torch.get_rng_state(),'cuda_rng':torch.cuda.get_rng_state_all(),'python_rng':random.getstate(),'step':step,'config':cfg,'carried_notes':prior,'user':uid},checkpoint/'training_state.pt')
        # Tied/invalid groups are logged, not dropped: every authorized session is processed.
    if full:assert len({(r['user'],r['session']) for r in records})==100
    final=args.output/'final_adapter';model.save_pretrained(final);tok.save_pretrained(final);reload_error=None
    if reload_probe is not None:
        model.eval()
        with torch.no_grad():expected=action_logprobs(model,reload_probe).cpu()
        model.load_adapter(str(final),adapter_name='reload_check',is_trainable=False);model.set_adapter('reload_check')
        with torch.no_grad():actual=action_logprobs(model,reload_probe).cpu()
        reload_error=float((actual-expected).abs().max());assert reload_error<1e-5
    training_summary={'optimizer_steps':sum(x['updated'] for x in steps),'attempted_groups':len(steps),'unique_sessions':len({(r['user'],r['session']) for r in records}),
        'api_calls':0,'reward_mode':'extraction_count','checkpoint_reload_max_logprob_error':reload_error,'training_wall_seconds':time.perf_counter()-start,
        'peak_gpu_memory_bytes':torch.cuda.max_memory_allocated(),'training_metrics':summarize(records),'steps':steps}
    (args.output/'training_summary.json').write_text(json.dumps(training_summary,indent=2))
    if full:
        trained=evaluate(manager,args.data,manifest['users'],args.output/'trained','trained_adapter',cfg)
        comparison={'in_sample':True,'primary':'mean normalized correct current fields across4samples/session','baseline':baseline,'trained':trained,
                    'primary_delta':trained['primary_mean_normalized_correct']-baseline['primary_mean_normalized_correct'],
                    'status':'single matched seed; repeat matched seeds before declaring robust improvement'}
        (args.output/'comparison.json').write_text(json.dumps(comparison,indent=2));print(json.dumps({'comparison':comparison}),flush=True)
    (args.output/'summary.json').write_text(json.dumps(training_summary,indent=2));print(json.dumps(training_summary),flush=True)
