"""Repeat matched frozen/trained evaluations with prespecified additional seeds."""
import json,torch
from pathlib import Path
from prompt_policy_llm.note_model import load_model
from prompt_policy_llm.structured_note_rollouts import StructuredRollout
from prompt_policy_llm.eval_structured_notes import evaluate
base=Path('/home/criteo/qwen17b-work/cumulative-temp15-20260918')
run=base/'all100_01/run';data=base/'experiments/experiment0.3/structured_notes_v1'
cfg=json.loads((run/'run_config.json').read_text())['config']
manifest=json.loads((data/'manifest.json').read_text())
model,tok=load_model(cfg,adapter_path=run/'final_adapter',train=False)
manager=StructuredRollout(model,tok,cfg);rows=[]
for seed in [7320,7321]:
    cfg['evaluation_seed']=seed
    out=base/('repeat_seed_'+str(seed));out.mkdir(exist_ok=False)
    with model.disable_adapter():baseline=evaluate(manager,data,manifest['users'],out/'baseline','frozen_prompted',cfg)
    trained=evaluate(manager,data,manifest['users'],out/'trained','trained_adapter',cfg)
    result={'seed':seed,'baseline':baseline,'trained':trained,'primary_delta':trained['primary_mean_normalized_correct']-baseline['primary_mean_normalized_correct'],'in_sample':True}
    (out/'comparison.json').write_text(json.dumps(result,indent=2));rows.append(result)
    print(json.dumps({'repeat_complete':seed,'primary_delta':result['primary_delta']}),flush=True)
(base/'repeat_comparisons.json').write_text(json.dumps(rows,indent=2))
