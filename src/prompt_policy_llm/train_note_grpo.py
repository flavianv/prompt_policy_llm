"""Synchronous single-GPU multi-turn GRPO with frozen BF16 base and LoRA.

Explicit implementation of grouped sequence advantages, clipped token ratios and
reference KL; tool/user tokens never receive loss. No TRL default harness swap.
"""
import argparse,json,math,random,time,hashlib,importlib.metadata as md
from copy import deepcopy
from pathlib import Path
from .note_model import load_model,verify_snapshot
from .note_rollouts import NativeRollout,action_logprobs
from .note_reward import AnswerCache,probe_batches,utility,reward,group_advantages
from .explicit_memory import Luna,observation
from .adaptgym_pilot import load_credentials

def train_group(model,optimizer,candidates,config):
    import torch
    rewards=[c['reward']['reward'] for c in candidates];advantages,std=group_advantages(rewards)
    if std<1e-8:return {'updated':False,'reason':'zero_variance','rewards':rewards,'advantages':advantages}
    model.train()  # LoRA/attention dropout are zero; training mode enables activation checkpointing.
    for c in candidates:
        for seg in c['trace']['segments']:
            with torch.no_grad():
                seg['old_logprobs']=action_logprobs(model,seg,temperature=config.get('temperature',1.0)).cpu().tolist()
                with model.disable_adapter():seg['reference_logprobs']=action_logprobs(model,seg,temperature=config.get('temperature',1.0)).cpu().tolist()
    optimizer.zero_grad(set_to_none=True);total_tokens=sum(len(s['completion_ids']) for c in candidates for s in c['trace']['segments']);assert total_tokens>0
    loss_total=kl_total=0.
    for c,advantage in zip(candidates,advantages):
        for seg in c['trace']['segments']:
            logp=action_logprobs(model,seg,temperature=config.get('temperature',1.0));old=torch.tensor(seg['old_logprobs'],device=logp.device);ref=torch.tensor(seg['reference_logprobs'],device=logp.device)
            ratio=torch.exp(logp-old);clipped=ratio.clamp(1-config['clip_epsilon'],1+config['clip_epsilon']);delta=(ref-logp).clamp(-20,20);kl=torch.exp(delta)-delta-1
            loss=(-torch.minimum(ratio*advantage,clipped*advantage)+config['kl_beta']*kl).sum()/total_tokens
            assert torch.isfinite(loss);loss.backward();loss_total+=loss.item();kl_total+=kl.detach().sum().item()/total_tokens
    params=[p for p in model.parameters() if p.requires_grad];norm=torch.nn.utils.clip_grad_norm_(params,config['max_grad_norm']);assert torch.isfinite(norm)
    before=[p.detach().float().cpu().clone() for p in params];optimizer.step();change=sum((p.detach().float().cpu()-b).abs().sum().item() for p,b in zip(params,before));assert change>0
    return {'updated':True,'rewards':rewards,'advantages':advantages,'reward_std':std,'loss':loss_total,'reference_kl':kl_total,'gradient_norm':float(norm),'adapter_parameter_delta_l1':change,'assistant_loss_tokens':total_tokens}

def main():
    import torch
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--cache',type=Path);p.add_argument('--credentials',type=Path);p.add_argument('--steps',type=int,default=3);a=p.parse_args()
    cfg=json.loads(a.config.read_text())
    if cfg.get('reward_mode')=='extraction_count':
        from .train_structured_grpo import run
        return run(a,cfg)
    if a.cache is None or a.credentials is None:p.error('legacy Luna mode requires --cache and --credentials')
    assert a.steps<=cfg['smoke_steps'],'pilot requires separate acceptance gate and config';torch.manual_seed(cfg['seed']);random.seed(cfg['seed']);load_credentials(a.credentials);identity=verify_snapshot(cfg['model_path'],a.manifest);a.output.mkdir(parents=True,exist_ok=False)
    model,tok=load_model(cfg,train=True);model.save_pretrained(a.output/'initial_adapter');tok.save_pretrained(a.output/'initial_adapter');manager=NativeRollout(model,tok,cfg);optimizer=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=cfg['learning_rate'])
    manifest=json.loads((a.data/'manifest.json').read_text());assert manifest['complete'];train=[r for r in manifest['users'] if r['split']=='train'];cache=AnswerCache(a.cache,Luna(cfg['answer_model']),cfg['answer_model'],cfg['reward_max_api_calls']);steps=[];start=time.perf_counter()
    run={'config':cfg,'base_revision':identity['revision'],'algorithm':'custom synchronous GRPO; grouped normalized sequence reward, clipped token ratios, k3 reference KL, one update/group','dense_auxiliaries':'disabled; no calibrated semantic scorer','versions':{k:md.version(k) for k in ['torch','transformers','peft','trl','openai']},'gpu':torch.cuda.get_device_name(0),'only_lora_trainable':all('lora_' in n for n,p in model.named_parameters() if p.requires_grad),'trainable_parameters':sum(p.numel() for p in model.parameters() if p.requires_grad),'data_manifest':manifest}
    (a.output/'run_config.json').write_text(json.dumps(run,indent=2))
    for step in range(a.steps):
        user=train[step%len(train)];root=a.data/user['user'];profile=json.loads((root/'profile/profile.json').read_text());episode=json.loads((root/'sessions/episode.json').read_text());session=step%3;prior={};prefix=[]
        for c in episode['cases'][:session]:
            t=manager.update(observation(c),prior,sample=False);prefix.append(t)
        case=episode['cases'][session];batches=probe_batches(profile,case,cfg);candidates=[]
        for g in range(cfg['group_size']):
            notes=dict(prior);trace=manager.update(observation(case),notes,sample=True);candidates.append({'candidate':g,'notes':notes,'trace':trace})
        # Random call order avoids position/time being correlated with group membership.
        order=list(range(len(candidates)));random.shuffle(order)
        for g in order:
            c=candidates[g];u,answers=utility(cache,batches,c['notes'],prior);c['reward']=reward(u,c['trace'],c['notes'],cfg);c['answers']=answers
        record={'step':step,'user':user['user'],'session':session,'prior_notes':prior,'prefix_traces':prefix,'candidates':candidates,'source_observation':observation(case),'probe_privacy':'probes constructed/scored separately; writer received public observation only'}
        # Explicit gate: do not optimize a group entirely lacking successful finalization.
        if not any(c['trace']['finished'] for c in candidates):
            record['optimizer']={'updated':False,'reason':'all_trajectories_failed'}
        else:record['optimizer']=train_group(model,optimizer,candidates,cfg)
        path=a.output/f'step{step:03d}.json';path.write_text(json.dumps(record));steps.append(record['optimizer']);print(json.dumps({'step_done':step,**record['optimizer'],'utilities':[c['reward']['utility'] for c in candidates],'api_calls':cache.calls}),flush=True)
        checkpoint=a.output/f'checkpoint-{step+1}';model.save_pretrained(checkpoint);tok.save_pretrained(checkpoint);torch.save({'optimizer':optimizer.state_dict(),'torch_rng':torch.get_rng_state(),'cuda_rng':torch.cuda.get_rng_state_all(),'python_rng':random.getstate(),'step':step,'config':cfg},checkpoint/'training_state.pt')
        if not record['optimizer']['updated']:
            print('STOP_GATE: no usable group gradient; do not scale',flush=True);break
    # Verify exact checkpoint restoration against the in-memory adapter, without changing base.
    final=a.output/'final_adapter';model.save_pretrained(final);tok.save_pretrained(final)
    probe=next(s for c in candidates for s in c['trace']['segments'])
    with torch.no_grad():expected=action_logprobs(model,probe).cpu()
    model.load_adapter(str(final),adapter_name='reload_check',is_trainable=False);model.set_adapter('reload_check')
    with torch.no_grad():actual=action_logprobs(model,probe).cpu()
    max_error=float((actual-expected).abs().max());assert max_error<1e-5
    summary={'optimizer_steps':sum(s['updated'] for s in steps),'attempted_groups':len(steps),'checkpoint_reload_max_logprob_error':max_error,'elapsed_seconds':time.perf_counter()-start,'peak_memory_bytes':torch.cuda.max_memory_allocated(),'api_calls':cache.calls,'cache_hits':cache.hits,'actual_answer_model':cache.actual_model,'promotion':'requires held-out substantive/recall gate; training reward is not acceptance','steps':steps};(a.output/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary),flush=True)
if __name__=='__main__':main()
