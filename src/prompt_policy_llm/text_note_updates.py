"""Plain-text sparse notes with evaluator-only, one-to-one value matching."""
from copy import deepcopy
import re,unicodedata
from .structured_notes import flatten_profile

SYSTEM='''Maintain notes for one user from the session text and your previous saved notes.
Output only new or changed facts, one per line: a short descriptive key, a colon, and the value. Keys are free-form; there is no required internal schema. A distinctive value may appear alone if no key is needed. Use descriptive keys to preserve category, brand, season, occasion and which attribute changed, especially for unknown values or common sizes.
Do not output JSON, tool calls, code fences, explanations or empty template fields. Keep list values together on one line separated by commas; include the complete current list. Use "unknown" for explicitly unknown and "no preference" for explicitly empty preferences. Never invent missing facts. Ignore chatter and facts about other people. Retain exact names, numbers, units and dates. Separate independent facts onto separate lines, including intent status and deadline. When changing a fact, reuse its previous key so it replaces that note. Unmentioned notes are retained automatically.
Preserve current values as time advances: temporary changes end at their exclusive end time; active purchase intents expire strictly after their deadline unless completed or cancelled. You may retain dated historical facts on separate clearly labeled lines. If nothing changes, output only "No changes."'''


def words(text):
    text=unicodedata.normalize('NFKC',str(text)).casefold()
    aliases={'colours':'colors','colour':'color','colours':'colors','centimeters':'cm','centimetres':'cm','kilograms':'kg','kilogram':'kg','dollars':'usd','dollar':'usd','euros':'eur','euro':'eur'}
    return [aliases.get(w,w) for w in re.findall(r'\d{4}-\d{2}-\d{2}(?:t\d{2}:\d{2}(?::\d{2})?(?:z|[+-]\d{2}:\d{2})?)?|[^\W_]+(?:\.\d+)?',text)]


def parse_lines(raw):
    if not isinstance(raw,str) or len(raw)>200000:raise ValueError('note output size/type')
    entries=[]
    for line in raw.splitlines():
        line=line.strip()
        if not line:continue
        if line.casefold() in {'no changes.','no changes'}:continue
        if line.startswith(('```','{','[','<tool_call>')):raise ValueError('expected plain-text fact lines')
        line=re.sub(r'^[-*]\s+','',line)
        match=re.match(r'^([A-Za-z][^:]*):\s*(.+)$',line)
        key,value=match.groups() if match else ('',line)
        if not value.strip():raise ValueError('empty fact value')
        entries.append({'key':key.strip(),'value':value.strip()})
    if len(entries)>128:raise ValueError('too many update facts')
    return entries


def merge_lines(prior,raw):
    result=deepcopy(prior.get('entries',[]))
    for entry in parse_lines(raw):
        identity=words(entry['key'])
        existing=next((i for i,e in enumerate(result) if identity and words(e['key'])==identity),None)
        if existing is not None:result[existing]=entry
        elif entry not in result:result.append(entry)
    if len(result)>256:raise ValueError('saved note budget')
    return {'entries':result}


def render_notes(notes):
    return '\n'.join((e['key']+': ' if e['key'] else '')+e['value'] for e in notes.get('entries',[])) or '(none)'


def value_signature(value):
    if value is None:return ('unknown',)
    if isinstance(value,list):
        if not value:return ('empty',)
        return ('tokens',tuple(sorted(w for v in value for w in scalar_words(v))))
    return ('tokens',tuple(sorted(scalar_words(value))))


def scalar_words(value):
    if isinstance(value,dict):return [w for v in value.values() for w in scalar_words(v)]
    if isinstance(value,list):return [w for v in value for w in scalar_words(v)]
    if value is None:return ['unknown']
    if isinstance(value,(int,float)) and not isinstance(value,bool):return words(format(value,'g'))
    return words(value)


def predicted_signature(value):
    tokens=words(value)
    if ' '.join(tokens) in {'unknown','explicitly unknown','null','not known'}:return ('unknown',)
    if ' '.join(tokens) in {'no preference','no stated preference','none','empty','no preferences'}:return ('empty',)
    return ('tokens',tuple(sorted(tokens)))


def address_words(address):
    result=[]
    for key,value in address.items():
        if key=='section' and value in {'general','clothing','personal','physical'}:continue
        result.extend(scalar_words(value))
    aliases={'hats':'hat','shirts':'shirt','shoes':'shoe','accessories':'accessory','materials':'material','colors':'color','patterns':'pattern','occasions':'occasion','hobbies':'hobby','languages':'language','status':'state','default':'','birth':'birth','date':'date'}
    return {aliases.get(w,w) for w in result if aliases.get(w,w)}


def key_words(key):
    aliases={'hats':'hat','shirts':'shirt','shoes':'shoe','accessories':'accessory','materials':'material','colors':'color','patterns':'pattern','occasions':'occasion','hobbies':'hobby','languages':'language','status':'state','default':''}
    return {aliases.get(w,w) for w in words(key) if aliases.get(w,w)}


def score_text_notes(notes,gold,valid=True):
    targets=list(flatten_profile(gold['profile']).values());n=len(targets)
    base={'reward':0,'correct':0,'target_count':n,'missing':n,'incorrect':0,'unsupported':0,'schema_valid':valid,'exact_state':False,'correct_fraction':0.,'history_required_for_reward':False,'normalization':'none; fraction is diagnostic only'}
    if not valid:return {**base,'error':'invalid plain-text update'}
    signatures=[value_signature(t['value']) for t in targets]
    used=set();unsupported=0;matches=[]
    for entry in notes.get('entries',[]):
        if {'history','historical','previous','formerly','old'} & key_words(entry['key']):continue
        candidates=[i for i,s in enumerate(signatures) if s==predicted_signature(entry['value'])]
        chosen=None
        # Optional keys suffice for a value unique in the target. Repeated values
        # require a uniquely best contextual match; never assign by target order.
        if len(candidates)==1:
            i=candidates[0];sig=signatures[i]
            common=sig[0] in {'unknown','empty'} or (len(sig[1])==1 and len(sig[1][0])<=3)
            if not common or key_words(entry['key']) & address_words(targets[i]['address']):chosen=i
        elif candidates and entry['key']:
            scores=[(len(key_words(entry['key']) & address_words(targets[i]['address'])),i) for i in candidates]
            best=max(s for s,_ in scores)
            winners=[i for s,i in scores if s==best]
            if best>0 and len(winners)==1:chosen=winners[0]
        if chosen is None:unsupported+=1
        elif chosen not in used:used.add(chosen);matches.append({'note':entry,'address':targets[chosen]['address']})
    correct=len(used)
    return {**base,'reward':correct,'correct':correct,'missing':n-correct,'unsupported':unsupported,'exact_state':correct==n and unsupported==0,'correct_fraction':correct/n if n else 0.,'matches':matches}


def score_candidate(candidate,gold):
    return score_text_notes(candidate['notes'],gold,candidate['trace']['finished'])
