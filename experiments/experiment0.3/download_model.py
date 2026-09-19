import dataclasses,hashlib,json,subprocess
from pathlib import Path
from huggingface_hub import HfApi
repo='Qwen/Qwen3-4B';dest=Path('/home/criteo/qwen17b-work/qwen3-4b');p=Path(__file__).parent/'model_manifest.json'
if p.exists():
 manifest=json.loads(p.read_text());assert manifest['repo_id']==repo
else:
 info=HfApi().model_info(repo,files_metadata=True)
 manifest={'repo_id':repo,'revision':info.sha,'files':[{'path':f.rfilename,'size':f.size,'blob_id':f.blob_id,'lfs':dataclasses.asdict(f.lfs) if f.lfs else None} for f in info.siblings if f.rfilename.endswith(('.json','.safetensors','.txt','.jinja'))]}
p.write_text(json.dumps(manifest,indent=2));revision=manifest['revision'];print('download_revision',revision,flush=True)
subprocess.run(['/home/criteo/verl-venv/bin/hf','download',repo,*[f['path'] for f in manifest['files']],'--revision',revision,'--local-dir',str(dest)],check=True)
for f in manifest['files']:
 file=dest/f['path'];assert file.stat().st_size==f['size'];h=hashlib.sha256() if f['lfs'] else hashlib.sha1()
 if not f['lfs']:h.update(b'blob '+str(f['size']).encode()+b'\0')
 with file.open('rb') as stream:
  for chunk in iter(lambda:stream.read(8*1024*1024),b''):h.update(chunk)
 assert h.hexdigest()==(f['lfs']['sha256'] if f['lfs'] else f['blob_id'])
print('verified_model_files',len(manifest['files']),flush=True)
