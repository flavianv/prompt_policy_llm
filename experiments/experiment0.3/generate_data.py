"""Generate disjoint coherent profiles and split-specific rendered sessions."""
import argparse,json,hashlib,sys,time
from copy import deepcopy
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE.parents[1]/'src'))
from prompt_policy_llm.explicit_memory import generate_profile,generate_sessions,export_sessions,dt,iso
from prompt_policy_llm.adaptgym_pilot import load_credentials
from datetime import timedelta
from prompt_policy_llm.profile_contract import validate_profile
TEMPLATES={
 'train':{'reveal':'Please remember {label}: {value}.','change':'As of today, replace my prior record: {label}: {value}.','repeat':'To repeat my existing record, {label}: {value}.','temporary':'Temporarily, {label}: {value}. Until {until} only; then restore the prior preference.'},
 'dev':{'reveal':'A detail about me to keep: {label} is {value}.','change':'My record needs an update effective today: {label} becomes {value}, replacing the old value.','repeat':'This is unchanged: {label} is {value}.','temporary':'For a limited period ending {until}, {label} is {value}. My earlier preference resumes afterward.'},
 'test':{'reveal':'Here is something personal: {label} — {value}.','change':'Going forward from today, {label} — {value}; supersede the earlier value.','repeat':'I still have this recorded: {label} — {value}.','temporary':'Use this exception until {until}: {label} — {value}. At the end revert to what I preferred before.'}}

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--credentials',type=Path,required=True);a=p.parse_args();load_credentials(a.credentials);a.output.mkdir(parents=True,exist_ok=False)
 cfg=json.loads((HERE/'config.json').read_text());base=json.loads((HERE.parent/'experiment0.2/config.json').read_text());fixedbase=json.loads((HERE.parent/'experiment0.2/profile_constraints.json').read_text());records=[];names=set();start=time.perf_counter()
 (a.output/'split_design.json').write_text(json.dumps({'split_users':cfg['split_users'],'templates':TEMPLATES,'seed':cfg['seed'],'purpose':'small infrastructure smoke; not statistically powered'},indent=2))
 index=0
 for split,n in cfg['split_users'].items():
  for j in range(n):
   uid=f'{split}-{j:03d}';root=a.output/uid;root.mkdir();index+=1;fixed=deepcopy(fixedbase);fixed['fixed_values']['profile_id']=uid;fixed['fixed_values']['personal']={'nationality':['Canadian','Japanese','Brazilian','French','Indian','Mexican','German','Italian','Kenyan','Swedish','Spanish','Australian'][index-1]}
   date=(dt('2026-04-01T09:00:00Z')+timedelta(days=index*3));fixed['fixed_values']['reference_date']=date.date().isoformat()
   mats=[['linen'],['cotton','linen'],['wool'],['cotton']][index%4]
   fixed['fixed_paths']['/category_profiles/2/scoped_overrides/0/preferences/materials']=mats
   fixed['fixed_paths']['/category_profiles/5/preferences/patterns']=[] if index%2 else None
   for k in (0,1):
    fixed['fixed_paths'][f'/purchase_intents/{k}/id']=f'{uid}-intent-{k}'
    fixed['fixed_paths'][f'/purchase_intents/{k}/created_at']=iso(date)
    fixed['fixed_paths'][f'/purchase_intents/{k}/deadline']=iso(date+timedelta(days=(20+index if k==0 else 1+index%3)))
   conf=deepcopy(base);conf['seed']=cfg['seed']+index;conf['profile_max_attempts']=3;conf['templates'].update(TEMPLATES[split]);conf['initial_gap_days']=[2+index%4,4+index%3]
   # Make consistency rules explicit to avoid wasting repair calls observed in0.2.
   fixed['fixed_paths']['/general_preferences/0/shopping_effect']='background_only'
   profile=generate_profile(conf,fixed,root/'profile');assert not validate_profile(profile,fixed)
   name=profile['personal']['name'].casefold();assert name not in names,'duplicate identity';names.add(name)
   episode=generate_sessions(profile,conf);sessions=root/'sessions';sessions.mkdir();export_sessions(episode,sessions);(sessions/'episode.json').write_text(json.dumps(episode,indent=2));(root/'session_config.json').write_text(json.dumps(conf,indent=2))
   record={'user':uid,'split':split,'name':profile['personal']['name'],'profile_sha256':hashlib.sha256((root/'profile/profile.json').read_bytes()).hexdigest(),'episode_sha256':hashlib.sha256((sessions/'episode.json').read_bytes()).hexdigest()};records.append(record)
   (a.output/'manifest.json').write_text(json.dumps({'users':records,'complete':len(records)==sum(cfg['split_users'].values()),'elapsed_seconds':time.perf_counter()-start},indent=2));print(json.dumps({'user_ready':record}),flush=True)
if __name__=='__main__':main()
