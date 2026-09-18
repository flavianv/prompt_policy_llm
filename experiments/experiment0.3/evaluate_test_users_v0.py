import json
from pathlib import Path
from prompt_policy_llm.note_model import load_model
from prompt_policy_llm.structured_note_rollouts import StructuredRollout
from prompt_policy_llm.eval_structured_notes import evaluate
base=Path('/home/criteo/qwen17b-work/cumulative-temp15-20260918')
root=Path('/home/criteo/qwen17b-work/test-users-v0-20260918')
run=base/'all100_01/run'
data=root/'evaluation_data'
cfg=json.loads((run/'run_config.json').read_text())['config']
cfg.update(evaluation_seed=7322,evaluation_scope='held-out two new users; twenty sessions; no training or tuning',in_sample=False)
users=[u for u in json.loads((data/'manifest.json').read_text())['users'] if u['split']=='test']
assert len(users)==2 and sum(u['sessions'] for u in users)==20
out=root/'heldout_eval';out.mkdir(exist_ok=False)
model,tok=load_model(cfg,adapter_path=run/'final_adapter',train=False)
manager=StructuredRollout(model,tok,cfg)
with model.disable_adapter():baseline=evaluate(manager,data,users,out/'baseline','frozen_prompted',cfg)
trained=evaluate(manager,data,users,out/'trained','trained_adapter',cfg)
result={'baseline':baseline,'trained':trained,'primary_delta':trained['primary_mean_normalized_correct']-baseline['primary_mean_normalized_correct'],'in_sample':False,'training_updates':0,'checkpoint':str(run/'final_adapter')}
(out/'comparison.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result),flush=True)
