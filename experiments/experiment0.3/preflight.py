"""Verify BF16 Qwen3-4B LoRA forward/backward and frozen base."""
import json,sys,importlib.metadata as md
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE.parents[1]/'src'))
import torch
from prompt_policy_llm.note_model import verify_snapshot,load_model
from prompt_policy_llm.explicit_note_coverage import SYSTEM
from prompt_policy_llm.explicit_note_tools import TOOLS
from prompt_policy_llm.note_rollouts import action_logprobs,loss_mask
cfg=json.loads((HERE/'config.json').read_text());identity=verify_snapshot(cfg['model_path'],HERE/'model_manifest.json');m,tok=load_model(cfg,train=True)
train=[(n,p) for n,p in m.named_parameters() if p.requires_grad];assert train and all('lora_' in n for n,p in train)
prompt=tok.apply_chat_template([{'role':'system','content':SYSTEM},{'role':'user','content':'Current time 2026-01-01. My name is Robin.'}],tools=TOOLS,tokenize=False,add_generation_prompt=True,enable_thinking=False)
seg={'prompt_ids':tok(prompt,add_special_tokens=False).input_ids,'completion_ids':tok('<tool_call>{"name":"read_notes","arguments":{}}</tool_call>'+tok.eos_token,add_special_tokens=False).input_ids}
assert sum(loss_mask(seg))==len(seg['completion_ids'])
m.train();loss=-action_logprobs(m,seg).mean();loss.backward();assert torch.isfinite(loss)
grad=sum(p.grad.float().abs().sum().item() for _,p in train if p.grad is not None);assert grad>0
result={'passed':True,'identity':{'repo_id':identity['repo_id'],'revision':identity['revision']},'gpu':torch.cuda.get_device_name(0),'versions':{x:md.version(x) for x in ['torch','transformers','trl','peft','accelerate','openai']},'loaded_in_4bit':False,'trainable_parameters':sum(p.numel() for _,p in train),'only_lora_trainable':True,'loss':loss.item(),'gradient_l1':grad,'max_memory_allocated':torch.cuda.max_memory_allocated(),'template_has_tools':'<tools>' in prompt,'config':cfg}
(HERE/'preflight_result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
