"""Internal canonical oracle records and typed-value validation; public notes use original profile JSON."""
from copy import deepcopy
from datetime import datetime
import json
import math
from .explicit_memory import profile_facts, resolve_events, observation

VERSION = 'structured-notes-v1'
SECTIONS = {'personal', 'general', 'physical', 'clothing', 'preference', 'intent'}
CATEGORIES = {'shirts', 'outerwear', 'pants', 'shoes', 'hats', 'accessories'}
PREFERENCES = {'brands', 'materials', 'colors', 'patterns', 'cuts', 'fits', 'occasions', 'styles', 'widths'}
FIELDS = {
    'personal': {'name', 'gender', 'birth_date', 'race', 'nationality', 'marital_status'},
    'general': {'residence', 'occupation', 'income', 'education', 'languages', 'hobbies'},
    'physical': {'height', 'weight', 'build', 'hair_color', 'eye_color'},
    'clothing': PREFERENCES | {'default_size', 'brand_size'},
    'preference': {'stance'}, 'intent': {'state', 'budget'},
}
def canonical(value):
    """Typed objects; lists are unordered exact collections, never subsets."""
    if value is None: return ('null',)
    if type(value) is bool: return ('bool', value)
    if type(value) in (int, float):
        if not math.isfinite(value): raise ValueError('nonfinite number')
        return ('number', value)
    if isinstance(value, str): return ('string', value)
    if isinstance(value, list): return ('list', tuple(sorted((canonical(v) for v in value), key=repr)))
    if isinstance(value, dict): return ('object', tuple(sorted((k, canonical(v)) for k,v in value.items())))
    raise ValueError('unsupported value type')


def _timestamp(value):
    if not isinstance(value, str): raise ValueError('timestamp must be string')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None: raise ValueError('timestamp needs timezone')
    return result


def _unique_collections(value):
    if isinstance(value, list):
        members = [canonical(x) for x in value]
        if len(members) != len(set(members)): raise ValueError('duplicate collection member')
        for x in value: _unique_collections(x)
    elif isinstance(value, dict):
        for x in value.values(): _unique_collections(x)
    else: canonical(value)


def _address(a):
    if not isinstance(a, dict) or a.get('section') not in SECTIONS: raise ValueError('address section')
    section, field = a['section'], a.get('field')
    if field not in FIELDS[section]: raise ValueError('address field')
    expected = {'section', 'field'}
    if section == 'clothing':
        expected |= {'category', 'context'}
        if a.get('category') not in CATEGORIES: raise ValueError('category')
        context = a.get('context')
        if not isinstance(context, dict) or set(context)-{'subtype','season','occasion'} or any(not isinstance(x,str) or not x for x in context.values()): raise ValueError('context')
        if field == 'widths' and a['category'] != 'shoes': raise ValueError('widths only for shoes')
        if field == 'brand_size':
            expected |= {'brand', 'sizing_system'}
            if not isinstance(a.get('brand'),str) or not a['brand']: raise ValueError('brand')
            if a.get('sizing_system') is not None and not isinstance(a['sizing_system'],str): raise ValueError('sizing system')
    elif section == 'preference':
        expected |= {'topic','item','scope','category'}
        if not all(isinstance(a.get(k),str) and a[k] for k in ['topic','item']): raise ValueError('preference identity')
        if a.get('scope') not in {'global','category'}: raise ValueError('preference scope')
        if (a['scope']=='global' and a.get('category') is not None) or (a['scope']=='category' and a.get('category') not in CATEGORIES): raise ValueError('preference category')
    elif section == 'intent':
        expected.add('intent_id')
        if not isinstance(a.get('intent_id'),str) or not a['intent_id']: raise ValueError('intent id')
        if field == 'state':
            expected |= {'category','recipient'}
            if a.get('category') not in CATEGORIES or a.get('recipient') not in {'self','gift'}: raise ValueError('intent scope')
    if set(a) != expected: raise ValueError('address fields')


def _value(address, value):
    _unique_collections(value)
    section, field = address['section'], address['field']
    if value is None: return
    if (section == 'clothing' and field in PREFERENCES) or (section=='general' and field=='hobbies'):
        if not isinstance(value,list) or any(not isinstance(x,str) for x in value): raise ValueError('typed preference list')
    elif section=='intent' and field=='state':
        if not isinstance(value,dict) or set(value)!={'status','deadline'} or value['status'] not in {'active','expired','completed','cancelled','uncertain'}: raise ValueError('intent value')
        if value['deadline'] is not None: _timestamp(value['deadline'])
    elif section=='preference':
        if value not in ['like','dislike','retracted']: raise ValueError('stance')
    elif section=='clothing' and field=='default_size':
        if not isinstance(value,dict) or set(value)!={'size','sizing_system'} or any(x is not None and not isinstance(x,str) for x in value.values()): raise ValueError('default size')
    elif section=='clothing' and field=='brand_size':
        if not isinstance(value,str): raise ValueError('brand size must be string')
    elif section=='physical' and field in {'height','weight'}:
        if not isinstance(value,dict) or set(value)!={'value','unit'} or type(value['value']) not in (int,float) or not isinstance(value['unit'],str): raise ValueError('measurement')
    elif (section=='intent' and field=='budget') or (section=='general' and field=='income'):
        fields={'amount','currency'} | ({'period'} if field=='income' else set())
        if not isinstance(value,dict) or set(value)!=fields or type(value['amount']) not in (int,float) or any(not isinstance(value[k],str) for k in fields-{'amount'}): raise ValueError('money')
    elif section=='general' and field=='languages':
        if not isinstance(value,list) or any(not isinstance(v,dict) or set(v)!={'language','proficiency'} or any(not isinstance(x,str) for x in v.values()) for v in value): raise ValueError('languages')
    elif section=='general' and field in {'residence','education'}:
        expected={'city','region','country','timezone'} if field=='residence' else {'level','field'}
        if not isinstance(value,dict) or set(value)!=expected or any(v is not None and not isinstance(v,str) for v in value.values()): raise ValueError('structured general value')
    elif not isinstance(value,str): raise ValueError('scalar text value')


def validate_document(document, as_of=None):
    if not isinstance(document,dict) or set(document)!={'version','as_of','facts'} or document['version']!=VERSION: raise ValueError('note envelope')
    now=_timestamp(document['as_of'])
    if as_of is not None and document['as_of']!=as_of: raise ValueError('wrong as_of')
    if not isinstance(document['facts'],list) or len(document['facts'])>128: raise ValueError('facts budget/type')
    seen=set()
    for fact in document['facts']:
        if not isinstance(fact,dict) or set(fact)!={'address','value','history'}: raise ValueError('fact fields')
        a=fact['address']; _address(a); key=canonical(a)
        if key in seen: raise ValueError('duplicate scoped address')
        seen.add(key); _value(a,fact['value'])
        history=fact['history']
        if not isinstance(history,list) or not 1<=len(history)<=128: raise ValueError('history')
        previous=None
        for event in history:
            if not isinstance(event,dict) or set(event)!={'at','until','value'}: raise ValueError('history fields')
            at=_timestamp(event['at'])
            if at>now or (previous is not None and at<=previous): raise ValueError('history chronology')
            if event['until'] is not None and _timestamp(event['until'])<=at: raise ValueError('expiry before start')
            _value(a,event['value']); previous=at
    return document


def parse_document(raw, as_of=None):
    def pairs(items):
        result={}
        for key,value in items:
            if key in result: raise ValueError('duplicate JSON key')
            result[key]=value
        return result
    def constant(x): raise ValueError('nonfinite JSON constant')
    if not isinstance(raw,str) or len(raw)>200000: raise ValueError('JSON size/type')
    return validate_document(json.loads(raw,object_pairs_hook=pairs,parse_constant=constant),as_of)


def address_for(profile,key):
    parts=key.split(':');section=parts[0]
    if section in {'personal','general','physical'}: return {'section':section,'field':parts[1]}
    if section=='preference':
        p=profile['general_preferences'][int(parts[1])]
        return {'section':'preference','field':'stance',**{k:p[k] for k in ['topic','item','scope','category']}}
    if section=='intent':
        result={'section':'intent','field':parts[2],'intent_id':parts[1]}
        if parts[2]=='state':
            p=next(p for p in profile['purchase_intents'] if p['id']==parts[1])
            result.update(category=p['category'],recipient=p['recipient'])
        return result
    if section=='clothing':
        result={'section':'clothing','category':parts[1],'field':parts[-1],'context':{}}
        if parts[2].startswith('scope'):
            cat=next(c for c in profile['category_profiles'] if c['category']==parts[1])
            result['context']={k:v for k,v in cat['scoped_overrides'][int(parts[2][5:])]['context'].items() if v is not None}
        elif parts[2]=='brand_size':
            result.update(field='brand_size',brand=':'.join(parts[3:-1]),sizing_system=None if parts[-1]=='None' else parts[-1])
        return result
    raise ValueError('unknown source key')


def gold_notes(profile, prefix):
    """Recompute from prefix events only, never from hidden profile values or future cases."""
    if not prefix: raise ValueError('empty prefix')
    now=prefix[-1]['current_time']; histories={}; bank=profile_facts(profile)
    for case in prefix:
        if case['current_time']>now: raise ValueError('future case in prefix')
        for event in case['events']:
            if event.get('key') and event['kind']!='repeat':
                if event['timestamp']>now: raise ValueError('future event')
                histories.setdefault(event['key'],[]).append(event)
    facts=[]
    for key,history in histories.items():
        current,_=resolve_events(history,now,bank[key]['kind'])
        if bank[key]['kind']=='intent':
            event=next(e for e in reversed(history) if e['timestamp']<=now and (e['until'] is None or now<e['until']))
            current={'status':current,'deadline':event['value']['deadline']}
        facts.append({'address':address_for(profile,key),'value':deepcopy(current),
                      'history':[{'at':e['timestamp'],'until':e['until'],'value':deepcopy(e['value'])} for e in history]})
    result={'version':VERSION,'as_of':now,'facts':sorted(facts,key=lambda f:repr(canonical(f['address'])))}
    return validate_document(result,now)

