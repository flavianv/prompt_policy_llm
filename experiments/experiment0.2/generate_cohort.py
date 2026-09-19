#!/usr/bin/env python3
"""Bounded nine additional profile API jobs; never launches paired evaluation."""
from concurrent.futures import ThreadPoolExecutor,as_completed
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
import argparse

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/'src'))
from prompt_policy_llm.explicit_memory import generate_profile,generate_sessions,export_sessions
from prompt_policy_llm.adaptgym_pilot import load_credentials
from prompt_policy_llm.profile_contract import validate_profile,ROOT as PROFILE_ROOT


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--first-profile',type=Path,required=True);p.add_argument('--credentials',type=Path,required=True);a=p.parse_args()
    load_credentials(a.credentials);a.output.mkdir(parents=True,exist_ok=False)
    config=json.loads((HERE/'config.json').read_text());base=json.loads((HERE/'profile_constraints.json').read_text())
    started=time.perf_counter();records=[];failures=[]
    shutil.copytree(PROFILE_ROOT,a.output/'profile_contract_snapshot')
    (a.output/'config.json').write_text(json.dumps(config,indent=2))
    def sessions(userdir,user_config):
        profile=json.loads((userdir/'profile/profile.json').read_text());errors=validate_profile(profile)
        if errors:raise ValueError('profile validation failed')
        ep=generate_sessions(profile,user_config);out=userdir/'sessions';out.mkdir();export_sessions(ep,out)
        (out/'episode.json').write_text(json.dumps(ep,indent=2));(userdir/'session_config.json').write_text(json.dumps(user_config,indent=2))
        return {'name':profile['personal']['name'],'sessions':len(ep['cases']),'questions':sum(len(c['questions']) for c in ep['cases']),
                'statements':sum(len(c['events']) for c in ep['cases'])}
    first=a.output/'user01';first.mkdir();shutil.copytree(a.first_profile,first/'profile')
    (first/'profile/fixed_constraints.json').write_text(json.dumps(base,indent=2))
    record={'user':'user01','profile_reused':True,'evaluation_scope':'separate user01 smoke',**sessions(first,config)};records.append(record)
    print(json.dumps({'dataset_user_ready':record}),flush=True)
    nationalities=['Canadian','Japanese','Brazilian','French','Indian','Mexican','German','Italian','Kenyan']
    def work(index,nationality):
        uid=f'user{index:02d}';root=a.output/uid;root.mkdir();cfg=deepcopy(config);cfg['seed']=config['seed']+index-1
        fixed=deepcopy(base);fixed['fixed_values']['profile_id']=uid
        fixed['fixed_values']['personal']={'nationality':nationality,'gender':'male' if index%2==0 else 'female'}
        start=time.perf_counter();generate_profile(cfg,fixed,root/'profile');result=sessions(root,cfg)
        return {'user':uid,'profile_reused':False,'evaluated_elsewhere':False,'generation_and_session_seconds':time.perf_counter()-start,**result}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(work,i,n):f'user{i:02d}' for i,n in enumerate(nationalities,2)}
        for future in as_completed(futures):
            try:
                record=future.result();records.append(record);print(json.dumps({'dataset_user_ready':record}),flush=True)
            except Exception as exc:
                error={'user':futures[future],'error_type':type(exc).__name__};failures.append(error);print(json.dumps({'dataset_user_failed':error}),flush=True)
            (a.output/'progress.json').write_text(json.dumps({'completed':len(records),'target':10,'users':sorted(records,key=lambda x:x['user']),'failures':failures,'elapsed_seconds':time.perf_counter()-started},indent=2))
    manifest={'dataset':'experiment0.2 explicit-state','users':sorted(records,key=lambda x:x['user']),'failures':failures,'elapsed_seconds':time.perf_counter()-started,
      'generation_concurrency':3,'max_new_profiles':9,'max_attempts_per_profile':config['profile_max_attempts'],
      'live_paired_evaluation_scope':'user01 only, separate output; other users generated only',
      'files_sha256':{str(f.relative_to(a.output)):hashlib.sha256(f.read_bytes()).hexdigest() for f in a.output.rglob('*') if f.is_file()}}
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps({'cohort_finished':len(records),'failures':failures,'seconds':manifest['elapsed_seconds']}),flush=True)
    return 1 if failures else 0


if __name__=='__main__':raise SystemExit(main())
