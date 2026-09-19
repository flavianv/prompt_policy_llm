"""Generate two fresh, schema-validated users; never trains or evaluates a model."""
import argparse,hashlib,json,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from copy import deepcopy
from pathlib import Path
from prompt_policy_llm import profile_contract
from prompt_policy_llm.explicit_memory import generate_profile,generate_sessions,export_sessions
from prompt_policy_llm.adaptgym_pilot import load_credentials


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--credentials',type=Path,required=True);a=p.parse_args()
    load_credentials(a.credentials);profile_contract.ROOT=a.root/'profile_contract_snapshot'
    cfg=json.loads((a.root/'generation_config.json').read_text());cfg['profile_max_attempts']=3
    fixed=json.loads((a.root/'profile_constraints.json').read_text())
    out=a.root/'dataset';out.mkdir(exist_ok=False);start=time.perf_counter();records=[];failures=[]
    identities=[('user11','Nora Lindholm','Swedish','female'),('user12','Omar Haddad','Tunisian','male')]
    def work(item):
        uid,name,nationality,gender=item;directory=out/uid;directory.mkdir();c=deepcopy(cfg);c['seed']=20260918+int(uid[4:])
        constraints=deepcopy(fixed);constraints['fixed_values'].update(profile_id=uid,personal={'name':name,'nationality':nationality,'gender':gender})
        profile=generate_profile(c,constraints,directory/'profile');assert not profile_contract.validate_profile(profile,constraints)
        episode=generate_sessions(profile,c);sessions=directory/'sessions';sessions.mkdir();export_sessions(episode,sessions)
        (sessions/'episode.json').write_text(json.dumps(episode,indent=2,ensure_ascii=False)+'\n');(directory/'session_config.json').write_text(json.dumps(c,indent=2)+'\n')
        return {'user':uid,'name':name,'sessions':len(episode['cases']),'seed':c['seed'],'profile_reused':False,'split':'test'}
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(work,item):item[0] for item in identities}
        for future in as_completed(futures):
            try:records.append(future.result());print(json.dumps({'generated':records[-1]}),flush=True)
            except Exception as e:failures.append({'user':futures[future],'error_type':type(e).__name__});print(json.dumps({'failed':failures[-1]}),flush=True)
    manifest={'version':'v0','users':sorted(records,key=lambda x:x['user']),'total_sessions':sum(x['sessions'] for x in records),'failures':failures,'complete':len(records)==2,'elapsed_seconds':time.perf_counter()-start,'generation':'fresh Luna profiles; unchanged seeded session templates; no model training','split_limitations':'Unseen users and session seeds, but shared schema, templates and fixed temporal probes with training.','files_sha256':{str(f.relative_to(out)):hashlib.sha256(f.read_bytes()).hexdigest() for f in out.rglob('*') if f.is_file()}}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps({'complete':manifest['complete'],'users':len(records),'sessions':manifest['total_sessions']}),flush=True)
    if failures:raise SystemExit(1)

if __name__=='__main__':main()
