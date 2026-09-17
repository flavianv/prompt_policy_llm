import json,re
from pathlib import Path
p=Path(__file__).resolve().parent
ep=json.loads((p/'episode_hidden_complete.json').read_text())
def val(v):
    if v is None:return 'none'
    if isinstance(v,bool):return 'yes' if v else 'no'
    if isinstance(v,list):return '; '.join(map(val,v)) or 'none'
    if isinstance(v,dict):
        if set(v)=={'field','op','value'}:
            return f"{v['field'].replace('_',' ')} {dict(eq='equals',ne='does not equal',lte='at most',gte='at least',**{'in':'is one of','not_in':'is not one of'})[v['op']]} {val(v['value'])}"
        return '; '.join(k.replace('_',' ')+': '+val(x) for k,x in v.items())
    return str(v)
def readable(s):
    # Decode only JSON fragments already present in the observed evidence.
    decoder=json.JSONDecoder(); out='';i=0
    while i<len(s):
        if s[i] in '{[' or s[i]=='"':
            try:
                v,n=decoder.raw_decode(s[i:]);out+=val(v);i+=n;continue
            except ValueError:pass
        out+=s[i];i+=1
    return out
public={k:v for k,v in ep.items() if k!='cases'}
public['cases']=[{k:v for k,v in c.items() if k not in ('truth','hidden_state')} for c in ep['cases']]
(p/'sessions_exact.json').write_text(json.dumps(public,indent=2))
(p/'hidden_persona.json').write_text(json.dumps([{'session':c['session'],'time':c['current_time'],'state':c['hidden_state']} for c in ep['cases']],indent=2))
(p/'answer_key.json').write_text(json.dumps([{'session':c['session'],'time':c['current_time'],'answers':c['truth']} for c in ep['cases']],indent=2))
intro=['# Ten sessions for synthetic user eval-17','Fixed seed: 17. Experiment 0.1, schema-v3. One user throughout. Session numbers below start at one; source indices start at zero. All times are UTC.','This is a faithful prose rendering of actual procedural generator output, not model-written dialogue. JSON fields in evidence are expanded into readable phrases. All evidence, question options and catalog fields are included. Hidden state and answers are saved separately.','Reading rules: Requirements are hard constraints; preferences are negotiable. Sizes are specific to brand, category and sizing system. Gift purchases do not inherit the user’s own profile. Intent rules replace category rules for the same field. A null intent size list means inherit the self profile; an explicit list replaces it. General preferences apply only when enabled and relevant. Never infer shopping constraints from demographics. Use the latest statement at an exact change time. Deadlines are inclusive. For recommendations, choose the feasible product matching most soft preferences; ties are allowed. Answer NONE if inactive or no product is suitable; ASK_SIZE if only unknown sizing prevents a feasible choice. Also report active, expired, completed, cancelled or uncertain status. Product prices retain generator units; no currency is added.']
lines=list(intro); exact=list(intro[:2]); questions=[]
for c in public['cases']:
    heading=f"## Session {c['session']+1} — {c['current_time']}"
    lines.extend([heading,'### User statements']);exact.extend([heading,'### Exact user statements'])
    for e in c['evidence']:
        lines.append(f"{e['id']}: {readable(e['text'])}");exact.append(f"{e['id']}: {e['text']}")
    qlines=['### Questions']
    for n,q in enumerate(c['questions'],1):
        qlines.append(f"Question {n}, {q['id']}: "+q.get('question',q.get('request','')))
        if q['kind']=='preference':qlines.append('Context: '+ '; '.join(k.replace('_',' ')+': '+val(q[k]) for k in ('topic','item','scope','category','at_time'))+'.')
        if 'options' in q:qlines.append('Options: '+ '; '.join(k+': '+val(v) for k,v in q['options'].items())+'.')
        for n,product in enumerate(q.get('catalog',[]),1):qlines.append(f"Product {n}: "+val(product)+'.')
    lines.extend(qlines);exact.extend(qlines);questions.extend([heading]+[s for s in qlines if not s.startswith('Product ')])
(p/'sessions_read_aloud.md').write_text('\n\n'.join(lines)+'\n')
(p/'sessions_verbatim.md').write_text('\n\n'.join(exact)+'\n')
(p/'questions_read_aloud.md').write_text('\n\n'.join(questions)+'\n')
assert sum(len(c['questions']) for c in public['cases'])==sum(s.startswith('Question ') for s in lines)
assert sum(len(q.get('catalog',[])) for c in public['cases'] for q in c['questions'])==sum(s.startswith('Product ') for s in lines)
print(json.dumps({'path':str(p/'sessions_read_aloud.md'),'sessions':len(public['cases']),'questions':sum(len(c['questions']) for c in public['cases']),'words':len(' '.join(lines).split()),'chronology':[(c['current_time'],len(c['questions'])) for c in public['cases']]},indent=2))
