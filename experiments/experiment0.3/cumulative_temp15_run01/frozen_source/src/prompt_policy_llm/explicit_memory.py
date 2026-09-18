"""Explicit-state checkpoint: one generated profile, revealed sessions, paired recall."""
import argparse
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import random
import time

from .profile_contract import ROOT as PROFILE_ROOT,render_prompt,validate_profile
from .adaptgym_pilot import strict_json,load_credentials

ROOT=Path(__file__).resolve().parents[2]/'experiments/experiment0.2'


def iso(dt):return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
def dt(text):return datetime.fromisoformat(text.replace('Z','+00:00'))


class Luna:
    def __init__(self,model):
        from openai import OpenAI
        self.client=OpenAI(timeout=180,max_retries=0);self.model=model

    def generate(self,system,payload,max_tokens):
        from .backend import extract_response_text,estimate_luna_cost
        start=time.perf_counter();r=self.client.responses.create(model=self.model,store=False,
          reasoning={'effort':'low'},max_output_tokens=max_tokens,
          input=[{'role':'system','content':system},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}])
        return {'text':extract_response_text(r),'model':r.model,'response_id':r.id,'status':r.status,
                'input_tokens':r.usage.input_tokens,'output_tokens':r.usage.output_tokens,
                'estimated_cost_usd':estimate_luna_cost(r.usage.input_tokens,r.usage.output_tokens),'latency_s':time.perf_counter()-start}


def generate_profile(config,constraints,output):
    output.mkdir(parents=True,exist_ok=False);model=Luna(config['profile_model'])
    (output/'fixed_constraints.json').write_text(json.dumps(constraints,indent=2))
    (output/'generation_parameters.json').write_text(json.dumps({'requested_model':config['profile_model'],'reasoning_effort':'low','max_output_tokens':config['profile_max_output_tokens'],'max_attempts':config['profile_max_attempts'],'store':False,'max_retries':0},indent=2))
    system=render_prompt(constraints);payload={'task':'Generate one coherent profile; all fixed constraints are binding.'}
    (output/'profile_prompt.txt').write_text(system);errors=[]
    for attempt in range(config['profile_max_attempts']):
        result=model.generate(system,payload,config['profile_max_output_tokens'])
        (output/f'profile_attempt_{attempt}.json').write_text(json.dumps({'payload':payload,'generation':result},indent=2))
        try:
            response=strict_json(result['text'])
            if result['status']!='completed' or response.get('status')!='ok':raise ValueError('profile response not completed/ok')
            profile=response['profile'];errors=validate_profile(profile,constraints)
        except (ValueError,TypeError,KeyError):errors=['Return a complete schema-valid JSON success envelope, without prose.']
        if not errors:
            (output/'profile.json').write_text(json.dumps(profile,indent=2,ensure_ascii=False)+'\n')
            (output/'profile_readable.md').write_text('# Actual Luna-generated initial profile\n\nModel: '+result['model']+'\n\n'+readable_profile(profile)+'\n')
            (output/'profile_validation.json').write_text(json.dumps({'valid':True,'attempts':attempt+1,'actual_model':result['model'],'illustrative':False},indent=2))
            print(json.dumps({'profile_ready':True,'name':profile['personal']['name'],'model':result['model'],'attempts':attempt+1}),flush=True)
            return profile
        payload={'task':'Repair the profile. Preserve every fixed constraint. Return only the required JSON envelope.','validation_errors':errors,'previous_response':result['text']}
    (output/'profile_validation.json').write_text(json.dumps({'valid':False,'errors':errors},indent=2))
    raise ValueError('bounded profile generation failed validation')


def readable_profile(p):
    lines=[]
    def visit(value,heading):
        if isinstance(value,dict):
            for k,v in value.items():visit(v,heading+' / '+k if heading else k)
        elif isinstance(value,list):
            if all(not isinstance(v,(dict,list)) for v in value):lines.append(f'- {heading}: '+(', '.join(map(str,value)) or 'explicitly no stated preference'))
            else:
                for i,v in enumerate(value):visit(v,heading+f' [{i+1}]')
        else:lines.append(f'- {heading}: '+('explicitly unknown' if value is None else str(value)))
    visit(p,'');return '\n'.join(lines)


def describe(value):
    if value is None:return 'explicitly unknown'
    if isinstance(value,list):return 'no stated preference' if not value else ', '.join(describe(x) for x in value)
    if isinstance(value,dict):
        if set(value)>={'value','unit'}:return f"{value['value']} {value['unit']}"
        if set(value)>={'amount','currency'}:return f"{value['amount']} {value['currency']}"+(f" per {value['period']}" if 'period' in value else '')
        if set(value)>={'size','sizing_system'}:return 'size '+describe(value['size'])+' in '+describe(value['sizing_system'])
        if set(value)>={'status','deadline'}:return value['status']+'; deadline '+(value['deadline'] or 'none (open until changed)')
        return '; '.join(k.replace('_',' ')+' '+describe(v) for k,v in value.items())
    return str(value)


def profile_facts(profile):
    facts={}
    def put(key,label,value,kind='fact'):
        facts[key]={'key':key,'label':label,'value':deepcopy(value),'kind':kind}
    for key,value in profile['personal'].items():
        if key!='age':put('personal:'+key,'my '+key.replace('_',' '),value)
    put('general:residence','my residence',profile['residence'])
    put('general:occupation','my occupation',profile['professional']['occupation'])
    put('general:income','my income',profile['professional']['income'])
    put('general:education','my education',profile['professional']['education'])
    put('general:languages','the languages I speak',profile['languages'])
    put('general:hobbies','my hobbies',profile['interests']['hobbies'],'list')
    for key,value in profile['physical'].items():put('physical:'+key,'my '+key.replace('_',' '),value)
    for i,p in enumerate(profile['general_preferences']):
        scope='globally' if p['scope']=='global' else 'for '+str(p['category'])
        put(f'preference:{i}',f'my stance toward {p["item"]} ({p["topic"]}, {scope})',p['stance'],'stance')
    for c in profile['category_profiles']:
        prefix='clothing:'+c['category']
        put(prefix+':default_size','my default size for '+c['category'],c['default_size'],'size')
        for s in c['sizes']:
            put(prefix+':brand_size:'+s['brand']+':'+str(s['sizing_system']),f'my {s["brand"]} {c["category"]} size in {s["sizing_system"]}',s['size'],'brand_size')
        for key,value in c['preferences'].items():put(prefix+':'+key,f'my preferred {key} for {c["category"]}',value,'list')
        for i,o in enumerate(c['scoped_overrides']):
            context=', '.join(str(v) for v in o['context'].values() if v is not None)
            for key,value in o['preferences'].items():put(prefix+f':scope{i}:'+key,f'my preferred {key} for {c["category"]} in context {context}',value,'list')
    for p in profile['purchase_intents']:
        put('intent:'+p['id']+':state',f'the state of purchase intent {p["id"]} ({p["category"]}, recipient {p["recipient"]})',{'status':p['status'],'deadline':p['deadline']},'intent')
        put('intent:'+p['id']+':budget','the budget for purchase intent '+p['id'],p['budget'],'budget')
    return facts


def resolve_events(history,at_time,kind):
    eligible=[e for e in history if e['timestamp']<=at_time and (e['until'] is None or at_time<e['until'])]
    if not eligible:raise ValueError('cannot ask about unrevealed state')
    event=eligible[-1];value=deepcopy(event['value'])
    if kind=='intent':
        if value['status']=='active' and value['deadline'] and at_time>value['deadline']:value['status']='expired'
        value=value['status']
    return value,[e['id'] for e in history if e['timestamp']<=at_time]


def changed_value(fact,current,rng):
    kind=fact['kind']
    if kind=='stance':return rng.choice([v for v in ['like','dislike','retracted'] if v!=current])
    if kind=='list':
        label=fact['label'];pool=(['hiking','reading','chess'] if fact['key']=='general:hobbies' else ['narrow','regular','wide'] if 'widths' in label else ['navy','green','red'] if 'colors' in label else ['linen','cotton','wool'] if 'materials' in label else
          ['plain','striped','floral'] if 'patterns' in label else ['regular','relaxed','slim'] if 'fits' in label or 'cuts' in label else
          ['Aster','Boreal','Cedar'] if 'brands' in label else ['casual','formal'])
        choices=[[],None,[rng.choice(pool)],[pool[0],pool[1]]];return deepcopy(rng.choice([v for v in choices if v!=current]))
    if isinstance(current,dict) and 'value' in current and fact['key']=='physical:weight':
        result=deepcopy(current);result['value']+=rng.choice([-2,2]);return result
    if kind=='budget' and isinstance(current,dict):
        result=deepcopy(current);result['amount']=max(0,result['amount']+rng.choice([-20,20]));return result
    if kind=='brand_size':
        if isinstance(current,str) and current.isdigit():return str(int(current)+1)
        if isinstance(current,str) and 'x' in current and all(v.isdigit() for v in current.split('x')):
            waist,length=current.split('x');return str(int(waist)+2)+'x'+length
        return {'M':'L','L':'M','XL':'L','S':'M'}.get(current,current)
    return current


def answer_candidates(fact,value,rng):
    kind,key=fact['kind'],fact['key']
    if kind=='intent':return ['active','expired','completed','cancelled','uncertain']
    if kind=='stance':return ['like','dislike','retracted',None]
    if kind=='list':
        choices=[None,[]]
        for _ in range(12):choices.append(changed_value(fact,value,rng))
        rng.shuffle(choices);return choices
    if isinstance(value,dict):
        choices=[]
        for delta in (-4,2,6):
            v=deepcopy(value)
            if 'value' in v and type(v['value']) in (int,float):v['value']=max(1,v['value']+delta)
            elif 'amount' in v:v['amount']=max(0,v['amount']+delta*10)
            elif 'size' in v:
                size=v['size'];v['size']=str(int(size)+delta) if isinstance(size,str) and size.isdigit() else ['S','L','XL'][len(choices)]
            elif 'city' in v:
                v={'city':['Lyon','Berlin','Rome'][len(choices)],'region':None,'country':['France','Germany','Italy'][len(choices)],'timezone':['Europe/Paris','Europe/Berlin','Europe/Rome'][len(choices)]}
            elif 'level' in v:v['level']=['secondary','bachelor','doctorate'][len(choices)]
            else:v={k:('intermediate' if k=='proficiency' else x) for k,x in v.items()}
            choices.append(v)
        return choices+[None]
    if kind=='size' and value is None:return [{'sizing_system':'CM','size':str(n)} for n in (56,58,60)]
    pools={'personal:gender':['male','female'], 'personal:name':['Alex Martin','Sofia Rossi','Sam Weber'],
      'personal:race':['Asian','Black','White','Mixed'],'personal:nationality':['French','German','Italian','Nigerian'],
      'personal:marital_status':['single','married','divorced','partnered'],
      'general:occupation':['Teacher','Architect','Data analyst','Nurse'],
      'physical:hair_color':['black','brown','blond','red'],'physical:eye_color':['brown','blue','green','hazel'],
      'physical:build':['slim','average','broad','athletic']}
    if key in pools:return pools[key]
    if key=='personal:birth_date':return [(datetime.fromisoformat(value)+timedelta(days=d)).date().isoformat() for d in (-366,365,730)]
    if kind=='brand_size':
        if isinstance(value,str) and value.isdigit():return [str(int(value)+d) for d in (-1,1,2)]
        return ['S','M','L','XL',None]
    return [None,'not specified','explicitly withdrawn']


def generate_sessions(profile,config):
    errors=validate_profile(profile)
    if errors:raise ValueError('invalid initial profile: '+ '; '.join(errors))
    rng=random.Random(config['seed']);facts=profile_facts(profile);history={};cases=[]
    now=dt(profile['reference_date']+'T09:00:00Z');seen=set()
    anchors=['personal:name','clothing:pants:scope0:materials','clothing:hats:default_size','clothing:accessories:patterns']
    anchors += [k for k,f in facts.items() if f['kind']=='intent'][:2]
    for session in range(config['sessions']):
        if session:now+=timedelta(days=config.get('initial_gap_days',[5,5])[session-1] if session<=2 else rng.choice(config['session_gap_days']))
        events=[];informative=[]
        def add(key,value,kind='reveal',until=None):
            timestamp=iso(now+timedelta(seconds=len(events)));eid=f'e{session}-{len(events)}';f=facts[key]
            text=config['templates'][kind].format(label=f['label'],value=describe(value),until=until)
            e={'id':eid,'timestamp':timestamp,'text':text,'key':key,'value':deepcopy(value),'until':until,'kind':kind}
            events.append(e)
            if kind!='repeat':history.setdefault(key,[]).append(e);informative.append(key)
        if session==0:
            selected=[k for k in anchors if k in facts]
            extras=[k for k in facts if k not in selected];rng.shuffle(extras)
            for key in (selected+extras)[:7]:add(key,facts[key]['value'])
        else:
            keys=list(history);mutable=[k for k in keys if facts[k]['kind'] in ('list','stance','budget','brand_size') or k=='physical:weight']
            if session==1 and mutable:
                key=next((k for k in mutable if ':scope' in k and 'materials' in k),mutable[0]);old,_=resolve_events(history[key],iso(now),facts[key]['kind'])
                add(key,changed_value(facts[key],old,rng),'temporary',iso(now+timedelta(days=3)))
            elif session in (3,5,7) and mutable:
                key=rng.choice(mutable);old,_=resolve_events(history[key],iso(now),facts[key]['kind']);add(key,changed_value(facts[key],old,rng),'change')
            elif session in (4,8):
                intent_keys=[k for k in keys if facts[k]['kind']=='intent']
                if intent_keys:
                    key=rng.choice(intent_keys);value=deepcopy(history[key][-1]['value']);value['status']=rng.choice(['completed','cancelled']) if session==4 else 'active'
                    if session==8:value['deadline']=iso(now+timedelta(days=30))
                    add(key,value,'change')
            for _ in range(rng.choice(config['informative_events_per_session'])):
                fresh=[k for k in facts if k not in history]
                if fresh:
                    key=rng.choice(fresh);add(key,facts[key]['value'])
        target=max(len(events)+1,rng.randint(*config['total_statements_range']))
        # At least one pure unrelated filler per session, alongside other configured families/repetition.
        while len(events)<target:
            family='filler' if len(events)==len(informative) else rng.choice(list(config['distractors'])+['repeat'])
            if family=='repeat' and history:
                key=rng.choice(list(history));value,_=resolve_events(history[key],iso(now+timedelta(seconds=len(events))),facts[key]['kind'])
                if facts[key]['kind']=='intent':
                    status=value;value=deepcopy(history[key][-1]['value']);value['status']=status
                add(key,value,'repeat');continue
            timestamp=iso(now+timedelta(seconds=len(events)));text=rng.choice(config['distractors'][family])
            events.append({'id':f'e{session}-{len(events)}','timestamp':timestamp,'text':text,'kind':family,'key':None})
        current_time=iso(now+timedelta(minutes=1));seen.update(e['id'] for e in events)
        old_keys=[k for k in history if any(not e['id'].startswith(f'e{session}-') for e in history[k])]
        picks=[rng.choice(old_keys or list(history))]
        # Explicit temporal probes in the small smoke; other picks remain seeded.
        if session==1:
            expired=[k for k in history if facts[k]['kind']=='intent' and resolve_events(history[k],current_time,'intent')[0]=='expired']
            if expired:picks[0]=expired[0]
        if session==2:
            temporary=[k for k in history if any(e['until'] for e in history[k])]
            if temporary:picks[0]=temporary[0]
        while len(picks)<config['questions_per_session']:
            remaining=[k for k in history if k not in picks];picks.append(rng.choice(remaining or list(history)))
        if session==2 and len(picks)>1:
            future=[k for k in history if facts[k]['kind']=='intent' and resolve_events(history[k],current_time,'intent')[0]=='active' and k!=picks[0]]
            if future:picks[1]=future[0]
        questions=[];truth={}
        for i,key in enumerate(picks):
            prior=[e for e in history[key] if not e['id'].startswith(f'e{session}-')]
            historical=bool(prior) and rng.random()<config['historical_question_probability'] and not (session==2 or (i==0 and session==1))
            at=rng.choice(prior)['timestamp'] if historical else current_time
            value,sources=resolve_events(history[key],at,facts[key]['kind'])
            alternatives=[value]
            candidates=answer_candidates(facts[key],value,rng)
            def canonical(v):
                return json.dumps(sorted(v,key=lambda x:json.dumps(x,sort_keys=True)) if isinstance(v,list) else v,sort_keys=True)
            for candidate in candidates:
                if canonical(candidate) not in [canonical(v) for v in alternatives] and describe(candidate) not in [describe(v) for v in alternatives]:alternatives.append(candidate)
                if len(alternatives)==4:break
            rng.shuffle(alternatives);options={chr(65+j):describe(v) for j,v in enumerate(alternatives)};qid=f'q{i}'
            question=config['templates']['historical_question' if historical else 'current_question'].format(label=facts[key]['label'],time=at)
            questions.append({'id':qid,'question':question,'options':options})
            truth[qid]={'answer':next(k for k,v in options.items() if v==describe(value)),'value':value,'key':key,'kind':facts[key]['kind'],
                        'historical':historical,'at_time':at,'support_ids':sources,'earlier_session_required':bool(prior) and (historical or not any(e.get('key')==key and e['kind'] in ('reveal','change','repeat') for e in events))}
            assert set(sources)<=seen
        cases.append({'session':session,'current_time':current_time,'events':events,'questions':questions,'truth':truth,'revealed_state':{k:{'value':resolve_events(h,current_time,facts[k]['kind'])[0],'history':deepcopy(h)} for k,h in history.items()}})
    return {'checkpoint':config['checkpoint'],'seed':config['seed'],'profile_id':profile['profile_id'],'cases':cases}


ANSWER_SYSTEM='''Answer only from the current dated session and prior notes, if provided.
Track explicit facts, lists and scope: defaults do not imply brand sizes; summer-pants materials
are not all-pants materials. Unknown, an explicit empty preference list, and unrevealed information
are different. Current explicit changes replace old facts from their stated time; retain history
for historical questions. Temporary overrides expire at their stated end, restoring prior facts.
Intent deadlines are inclusive: expire strictly afterwards, unless completed/cancelled earlier.
Ignore unrelated chatter, other people's preferences and product descriptions as user facts.
No demographic inference, preference learning, recommendation or utility calculation. Return only
JSON mapping every question ID to its option letter. Make the best supported choice if notes lack evidence.'''
NOTE_SYSTEM='''Maintain explicit notes for one user from the dated statements you receive.
Preserve dates, history, unknown values, explicitly empty/multiple preference lists, category,
brand/system and subtype/season/occasion scope. Do not invent sizes or convert between brands.
Changes apply from the stated date; temporary overrides end at their deadline then restore prior
preferences. Intent expiry is distinct from completed/cancelled, and old open/future intents persist.
Save facts needed across sessions, including general facts and explicit dislikes/retractions.
Ignore unrelated filler, other-person statements and product descriptions; repetition does not change state.
Call exactly one strict JSON tool {"tool":"NAME","arguments":{...}} per response.
read_notes {} once before editing; put_note {"name":"short stable topic","text":"concise facts, dates and history"};
delete_note {"name":"existing topic"}; no_op {} to finish. Upsert complete notes. Cite evidence IDs where useful.
No questions, product choices or rewards are available. Do not pretend to know future sessions.'''


def note_call(raw,notes,read,config):
    body=strict_json(raw)
    if not isinstance(body,dict) or set(body)!={'tool','arguments'} or not isinstance(body['arguments'],dict):raise ValueError('tool schema')
    tool,args=body['tool'],body['arguments'];pending=dict(notes)
    if tool=='read_notes':
        if read or args:raise ValueError('read once')
        return {'notes':dict(notes)},True,False
    if not read:raise ValueError('read before editing/finish')
    if tool=='put_note' and set(args)=={'name','text'}:
        if not isinstance(args['name'],str) or not 0<len(args['name'])<=96 or not isinstance(args['text'],str) or not 0<len(args['text'])<=5000:raise ValueError('note shape')
        pending[args['name']]=args['text']
    elif tool=='delete_note' and set(args)=={'name'} and args['name'] in pending:del pending[args['name']]
    elif tool=='no_op' and not args:return {'ok':True},True,True
    else:raise ValueError('unknown tool')
    if len(pending)>config['note_max_count'] or sum(len(t.split()) for t in pending.values())>config['note_max_words']:raise ValueError('note budget')
    notes.clear();notes.update(pending);return {'ok':True},True,False


class NoteManager:
    def __init__(self,generator,config):self.generator,self.config=generator,config
    def update(self,observation,notes):
        messages=[{'role':'system','content':NOTE_SYSTEM},{'role':'user','content':json.dumps(observation)}];rounds=[];read=done=False
        for i in range(self.config['note_max_rounds']):
            try:generation=self.generator.generate(deepcopy(messages))
            except Exception as exc:return {'rounds':rounds,'finished':False,'error_type':type(exc).__name__}
            before=dict(notes)
            try:result,read,done=note_call(generation['text'],notes,read,self.config);valid=True
            except (ValueError,TypeError,KeyError):result,valid={'error':'Invalid call; check exact tool schema/read-first/budget.'},False
            rounds.append({'round':i,'messages':deepcopy(messages),'generation':generation,'valid':valid,'tool_result':result,'notes_before':before,'notes_after':dict(notes)})
            messages.extend([{'role':'assistant','content':generation['text']},{'role':'user','content':'Tool result: '+json.dumps(result)}])
            if done:break
        return {'rounds':rounds,'finished':done}


def observation(case):
    return {'current_time':case['current_time'],'statements':[{k:e[k] for k in ('id','timestamp','text')} for e in case['events']]}


def export_sessions(episode,output):
    text=['# Ten explicit-state sessions and questions','Natural-language user statements; no simulated assistant replies. Answer keys are separate.'];answers=['# Evaluator-only answers']
    for c in episode['cases']:
        text.append(f'## Session {c["session"]+1} — '+dt(c['current_time']).strftime('%d %B %Y, %H:%M UTC'))
        text.extend('User: '+e['text'] for e in c['events']);text.append('### Questions')
        answers.append(f'## Session {c["session"]+1}')
        for q in c['questions']:
            text.append(q['question']);text.extend(k+'. '+v for k,v in q['options'].items())
            t=c['truth'][q['id']];answers.append(f'{q["id"]}: {t["answer"]} — {describe(t["value"])}. Evidence: {", ".join(t["support_ids"])}.')
    (output/'sessions_and_questions.md').write_text('\n\n'.join(text)+'\n');(output/'answer_key.md').write_text('\n\n'.join(answers)+'\n')


def evaluate(episode,answerer,manager,output,config,mode):
    output.mkdir(parents=True,exist_ok=False);export_sessions(episode,output)
    (output/'episode.json').write_text(json.dumps(episode,indent=2));(output/'run_config.json').write_text(json.dumps({'config':config,'mode':mode,'answer_system':ANSWER_SYSTEM,'note_system':NOTE_SYSTEM,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},indent=2))
    notes={};scores=[];calls=[];traces=[]
    def save(file,obj):
        with (output/file).open('a') as f:f.write(json.dumps(obj)+'\n')
    for case in episode['cases']:
        prior=dict(notes);obs=observation(case);payloads={arm:{**deepcopy(obs),'prior_notes':dict(prior) if arm=='memory' else {},'questions':deepcopy(case['questions'])} for arm in ('baseline','memory')}
        order=['baseline','memory'];random.Random(config['seed']+case['session']).shuffle(order);outputs={}
        for arm in order:
            try:result=answerer.generate(ANSWER_SYSTEM,payloads[arm],config['answer_max_output_tokens'])
            except Exception as exc:result={'text':'','status':'error','error_type':type(exc).__name__}
            try:
                parsed=strict_json(result['text']);valid=result['status'] in ('completed','mock') and isinstance(parsed,dict) and set(parsed)=={q['id'] for q in case['questions']} and all(parsed[q['id']] in q['options'] for q in case['questions'])
            except (ValueError,TypeError,KeyError):parsed,valid={},False
            outputs[arm]=(parsed if valid else {},valid)
            row={'session':case['session'],'arm':arm,'payload':payloads[arm],'generation':result};calls.append(row);save('answer_calls.jsonl',row)
        for q in case['questions']:
            t=case['truth'][q['id']];row={'session':case['session'],'question':q,'truth':t,'prior_notes':prior}
            for arm,(parsed,valid) in outputs.items():row[arm]={'answer':parsed.get(q['id']),'valid':valid,'correct':valid and parsed.get(q['id'])==t['answer']}
            scores.append(row);save('scores.jsonl',row)
        trace=manager.update(obs,notes);trace.update(session=case['session'],observation=obs,notes_before=prior,notes_after=dict(notes));traces.append(trace);save('note_traces.jsonl',trace)
        print(json.dumps({'session_done':case['session']+1,'note_count':len(notes),'note_finished':trace['finished']}),flush=True)
    def summarize(rows):
        n=len(rows);return {'questions':n,**{a:{'correct':sum(r[a]['correct'] for r in rows),'accuracy':sum(r[a]['correct'] for r in rows)/n if n else None,'invalid':sum(not r[a]['valid'] for r in rows)} for a in ('baseline','memory')}}
    rounds=[r for t in traces for r in t['rounds']]
    metrics={'mode':mode,'overall':summarize(scores),'historical':summarize([r for r in scores if r['truth']['historical']]),'earlier_session_evidence':summarize([r for r in scores if r['truth']['earlier_session_required']]),
      'memory_only_wins':sum(r['memory']['correct'] and not r['baseline']['correct'] for r in scores),'baseline_only_wins':sum(r['baseline']['correct'] and not r['memory']['correct'] for r in scores),
      'answer_calls':len(calls),'actual_answer_models':sorted({c['generation'].get('model','mock' if mode=='mock' else 'unknown') for c in calls}),
      'note_sessions_finished':sum(t['finished'] for t in traces),'note_rounds':len(rounds),'note_invalid_rounds':sum(not r['valid'] for r in rounds),'note_output_caps':sum(r['generation'].get('hit_output_cap',False) for r in rounds),
      'answer_usage':{k:sum(c['generation'].get(k,0) for c in calls) for k in ('input_tokens','output_tokens','estimated_cost_usd','latency_s')}}
    (output/'metrics.json').write_text(json.dumps(metrics,indent=2));return metrics


def verify_qwen(path):
    manifest=json.loads((ROOT/'model_manifest.json').read_text())
    for item in manifest['files']:
        f=path/item['path']
        if not f.is_file() or f.stat().st_size!=item['size']:raise ValueError('Qwen snapshot file mismatch')
        if item['lfs']:
            h=hashlib.sha256()
            with f.open('rb') as stream:
                for chunk in iter(lambda:stream.read(8*1024*1024),b''):h.update(chunk)
            expected=item['lfs']['sha256']
        else:
            blob=f.read_bytes();h=hashlib.sha1(b'blob '+str(len(blob)).encode()+b'\0'+blob);expected=item['blob_id']
        if h.hexdigest()!=expected:raise ValueError('Qwen snapshot checksum mismatch')
    return {'model':manifest['repo_id'],'revision':manifest['revision'],'verified_files':len(manifest['files'])}


def run_phase(args,config):
    profile=json.loads(args.profile.read_text()) if args.profile else json.loads((PROFILE_ROOT/'example_profile.json').read_text())
    episode=generate_sessions(profile,config)
    if args.phase=='evaluate':
        if not args.profile or not args.model_path:raise ValueError('live evaluation requires a validated profile and Qwen path')
        from .adaptgym_pilot import QwenNotes
        class Generator(QwenNotes):
            def generate(self,messages):
                prompt=self.tokenizer.apply_chat_template(messages,tokenize=False,add_generation_prompt=True,enable_thinking=False)
                batch=self.tokenizer(prompt,return_tensors='pt').to('cuda');cap=config['note_max_output_tokens']
                if batch.input_ids.shape[1]+cap>self.model.config.max_position_embeddings:raise ValueError('context limit')
                self.torch.cuda.synchronize();start=time.perf_counter()
                with self.torch.inference_mode():result=self.model.generate(**batch,max_new_tokens=cap,do_sample=False,pad_token_id=self.tokenizer.eos_token_id)
                self.torch.cuda.synchronize();tokens=result[0,batch.input_ids.shape[1]:]
                return {'text':self.tokenizer.decode(tokens,skip_special_tokens=True),'input_tokens':batch.input_ids.shape[1],'output_tokens':len(tokens),'latency_s':time.perf_counter()-start,'hit_output_cap':len(tokens)>=cap}
        identity=verify_qwen(args.model_path)
        generator=Generator(str(args.model_path));answerer=Luna(config['answer_model'])
        import torch,transformers,openai
        config['runtime']={'qwen_identity':identity,'model_path':str(args.model_path),'torch':torch.__version__,'transformers':transformers.__version__,'openai':openai.__version__,'gpu':torch.cuda.get_device_name(0),'qwen_thinking':False,'qwen_do_sample':False,'precision':'bfloat16','weight_training':False}
    else:
        class Generator:
            def generate(self,messages):return {'text':json.dumps({'tool':'read_notes' if len(messages)==2 else 'no_op','arguments':{}})}
        class Answerer:
            def generate(self,system,payload,max_tokens):return {'text':json.dumps({q['id']:next(iter(q['options'])) for q in payload['questions']}),'status':'mock'}
        generator,answerer=Generator(),Answerer()
    metrics=evaluate(episode,answerer,NoteManager(generator,config),args.output,config,'live' if args.phase=='evaluate' else 'mock')
    print(json.dumps(metrics,indent=2),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--phase',choices=['profile','evaluate','mock'],required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--profile',type=Path);parser.add_argument('--credentials',type=Path)
    parser.add_argument('--model-path',type=Path);args=parser.parse_args();config=json.loads((ROOT/'config.json').read_text())
    if args.phase!='mock':
        if not args.credentials:parser.error('live phases need configured credentials')
        load_credentials(args.credentials)
    if args.phase=='profile':generate_profile(config,json.loads((ROOT/'profile_constraints.json').read_text()),args.output)
    else:run_phase(args,config)


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps({'error_type':type(exc).__name__,'status_code':getattr(exc,'status_code',None)}),flush=True)
        raise SystemExit(1)
