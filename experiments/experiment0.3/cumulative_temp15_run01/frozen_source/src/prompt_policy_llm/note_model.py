"""Pinned BF16 Qwen3-4B, standard LoRA only; no quantization."""
import hashlib,json
from pathlib import Path

def verify_snapshot(path,manifest_path):
    manifest=json.loads(Path(manifest_path).read_text())
    assert manifest['repo_id']=='Qwen/Qwen3-4B'
    for f in manifest['files']:
        p=Path(path)/f['path'];assert p.is_file() and p.stat().st_size==f['size']
        h=hashlib.sha256() if f['lfs'] else hashlib.sha1()
        if not f['lfs']:h.update(b'blob '+str(f['size']).encode()+b'\0')
        with p.open('rb') as stream:
            for chunk in iter(lambda:stream.read(8*1024*1024),b''):h.update(chunk)
        assert h.hexdigest()==(f['lfs']['sha256'] if f['lfs'] else f['blob_id'])
    return manifest

def load_model(config,adapter_path=None,train=False):
    import torch
    from transformers import AutoModelForCausalLM,AutoTokenizer
    from peft import LoraConfig,get_peft_model,PeftModel
    assert config['model']=='Qwen/Qwen3-4B' and not config['load_in_4bit']
    tokenizer=AutoTokenizer.from_pretrained(config['model_path'],local_files_only=True)
    model=AutoModelForCausalLM.from_pretrained(config['model_path'],local_files_only=True,dtype=torch.bfloat16,attn_implementation='sdpa').to('cuda')
    assert model.config.model_type=='qwen3' and model.config.num_hidden_layers==36
    if adapter_path:model=PeftModel.from_pretrained(model,str(adapter_path),is_trainable=train)
    elif train:
        model=get_peft_model(model,LoraConfig(r=config['lora_rank'],lora_alpha=config['lora_alpha'],lora_dropout=0,target_modules=config['lora_targets'],bias='none',task_type='CAUSAL_LM',init_lora_weights=True))
    if train:
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False});model.enable_input_require_grads()
        assert all('lora_' in n for n,p in model.named_parameters() if p.requires_grad)
    else:
        for p in model.parameters():p.requires_grad_(False)
    model.eval();return model,tokenizer
