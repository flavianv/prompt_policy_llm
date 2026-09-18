"""Partial original-profile notes and raw correct-current-extraction reward.

The optional history sidecar supports temporal memory but never gates current-fact
credit. Gold construction is evaluator-only and consumes a revealed prefix.
"""
from copy import deepcopy
import json
from .structured_note_records import (canonical, _timestamp, _value, _address, FIELDS,
    CATEGORIES, PREFERENCES, gold_notes as _gold_records)
from .explicit_memory import observation

VERSION='partial-profile-notes-v1'
TOP={'personal','residence','professional','languages','interests','physical','general_preferences','category_profiles','purchase_intents'}
SCHEMA={
 '$schema':'https://json-schema.org/draft/2020-12/schema', 'title':VERSION,
 'type':'object','additionalProperties':False,'required':['version','as_of','profile'],
 'properties':{'version':{'const':VERSION},'as_of':{'type':'string','format':'date-time'},
   'profile':{'type':'object','additionalProperties':False,'properties':{
     'personal':{'type':'object'},'residence':{'type':['object','null']},'professional':{'type':'object'},
     'languages':{'type':['array','null']},'interests':{'type':'object'},'physical':{'type':'object'},
     'general_preferences':{'type':'array'},'category_profiles':{'type':'array'},'purchase_intents':{'type':'array'}}},
   'history':{'type':'array','maxItems':128}},
 'x-runtime-validation':'validate_document/flatten_profile are mandatory alongside this envelope schema. They enforce original field names/types, identity/scope keys, uniqueness, complete compound values, strict JSON and optional history chronology.'}
ADDRESS_GUIDE={
 'profile':'Original field names and value types; absent means unrevealed, null means explicitly unknown, [] means explicitly empty.',
 'atomic_units':'One scalar profile field, one complete compound value (height/weight, income, residence, education, default_size, budget), one entire typed preference/hobby/language collection, or one brand size; intent status and deadline count separately.',
 'identity_fields':'category; brand+sizing_system; scoped context; preference topic+item+scope+category; intent id+category+recipient identify records and give no standalone points.',
 'history':'Optional list of {address, events:[{at,until,value}]}; never part of the primary current-field reward.'}
SYSTEM='''Emit a sparse update to the user profile using current_session and your OWN previous_notes only.
Return one strict JSON object: {"profile":{only new or changed fields},"history":[optional changed history records]}. No tools, prose or code fences. The runtime merges your update into previous_notes and supplies version and as_of. Do not repeat unchanged fields. An empty update is {"profile":{}}.
Use original profile field names/types. Fill only explicitly revealed fields; omit unrevealed fields instead of adding null defaults. null means explicitly unknown; [] means explicitly no preference. Do not infer age, sizes, brands, demographic preferences or hidden profile metadata.
All sections below belong INSIDE profile, including purchase_intents. The only output root keys are profile and optional history. Omit every unmentioned field; never fill a template with null defaults.
Allowed profile sections:
personal: name,gender,birth_date,race,nationality,marital_status (text/null).
residence: {city,region,country,timezone} or null.
professional: occupation (text/null), income {amount,currency,period} or null, education {level,field} or null.
languages: [{language,proficiency}] or null. interests: {hobbies:[text] or null}.
physical: height/weight {value,unit} or null; build,hair_color,eye_color (text/null).
category_profiles: an ARRAY of objects (never an object keyed by category), one object per category with category, optional default_size {size,sizing_system} or null, sizes [{brand,sizing_system,size}], preferences {brands,materials,colors,patterns,cuts,fits,occasions,styles,widths}, scoped_overrides [{context:{subtype,season,occasion},preferences:{...}}]. Preference values are complete string lists or null; widths applies only to shoes. Include only stated scope dimensions (null allowed for unused context dimensions). Keep scoped values distinct from category defaults; never convert sizes.
general_preferences: [{topic,item,scope:"global" or "category",category:null or category,stance:"like"/"dislike"/"retracted"/null}]. Identity keys give context, not extra facts.
purchase_intents: [{id,category,recipient:"self"/"gift",status,deadline,budget:{amount,currency}}], omitting unrevealed fields. A budget-only record needs just id and budget; when status/deadline are known include their stated category and recipient. Status may be active,expired,completed,cancelled,uncertain or null; deadline is ISO timestamp/null.
Each record/address has one current value. Duplicate identities or alternative guesses are invalid. Lists are complete typed collections, not a bag of possible answers. Unmentioned fields are retained automatically. Emit changed values on explicit changes or time transitions. Emit each changed list or compound value in full; null sets an explicitly unknown value and [] sets an explicitly empty preference, neither deletes a field. Ignore filler, other-person facts and product descriptions. Repetition does not create a new fact.
Temporary changes expire at their exact exclusive until timestamp and then restore the prior applicable value. Intent deadlines are inclusive: active expires strictly after deadline unless completed/cancelled. Dates remain exactly as supplied. For faithful later restoration you may retain an optional history sidecar: [{"address":{...},"events":[{"at":timestamp,"until":timestamp or null,"value":original value}]}]. Address uses section personal/general/physical/clothing/preference/intent and field; clothing also category+context, brand_size also brand+sizing_system; preference also topic+item+scope+category; intent also intent_id and, for field state, category+recipient. Intent state history values have status+deadline. Preserve old changes when retaining history; confirmations are not changes. History accuracy is measured separately and does NOT gate correct current-field credit.
Initial previous_notes may have as_of:null and profile:{}; it is an empty memory, not gold.
Synthetic format illustration only (never copy these facts): if the only statements were "my name is Jordan Example" and "my preferred shirt colors are teal", an output shape would be:
{"profile":{"personal":{"name":"Jordan Example"},"category_profiles":[{"category":"shirts","preferences":{"colors":["teal"]}}]}}
This example has no gender, residence, budget, history or other absent fields. For scoped materials use a category entry shaped as {"category":"pants","scoped_overrides":[{"context":{"season":"winter"},"preferences":{"materials":["wool"]}}]}; for an explicitly unknown size use {"category":"hats","default_size":null}. These are syntax illustrations, not user facts.
Before ending, ensure arrays use square brackets, all sections are nested inside profile, and each opened brace has exactly one closing brace.
'''


def _dict(value,allowed):
 if not isinstance(value,dict) or set(value)-allowed:raise ValueError('unknown profile fields or object type')


def _identity(row,keys):
 if not keys<=set(row):raise ValueError('missing identity/scope keys')


def flatten_profile(profile):
 """Extract only present original fields, rejecting ambiguous identity/alternative outputs."""
 _dict(profile,TOP);facts={}
 def put(address,value):
  _address(address);_value(address,value);key=canonical(address)
  if key in facts:raise ValueError('duplicate scoped field')
  facts[key]={'address':address,'value':deepcopy(value)}
 for section in ['personal','physical']:
  if section in profile:
   _dict(profile[section],FIELDS[section])
   for field,value in profile[section].items():put({'section':section,'field':field},value)
 for field in ['residence','languages']:
  if field in profile:put({'section':'general','field':field},profile[field])
 if 'professional' in profile:
  _dict(profile['professional'],{'occupation','income','education'})
  for field,value in profile['professional'].items():put({'section':'general','field':field},value)
 if 'interests' in profile:
  _dict(profile['interests'],{'hobbies'})
  if 'hobbies' in profile['interests']:put({'section':'general','field':'hobbies'},profile['interests']['hobbies'])
 def rows(field):
  value=profile.get(field,[])
  if not isinstance(value,list) or len(value)>128:raise ValueError('profile list type/budget')
  return value
 categories=set()
 for cat in rows('category_profiles'):
  _dict(cat,{'category','default_size','sizes','preferences','scoped_overrides'});_identity(cat,{'category'})
  category=cat['category']
  if category not in CATEGORIES or category in categories:raise ValueError('duplicate/unknown category')
  categories.add(category)
  def clothing(field,value,context=None,**extra):put({'section':'clothing','field':field,'category':category,'context':context or {},**extra},value)
  if 'default_size' in cat:clothing('default_size',cat['default_size'])
  prefs=cat.get('preferences',{});_dict(prefs,PREFERENCES)
  for field,value in prefs.items():clothing(field,value)
  sizes=cat.get('sizes',[])
  if not isinstance(sizes,list):raise ValueError('sizes list')
  seen_sizes=set()
  for size in sizes:
   _dict(size,{'brand','sizing_system','size'});_identity(size,{'brand','sizing_system','size'})
   identity=canonical({k:size[k] for k in ['brand','sizing_system']})
   if identity in seen_sizes:raise ValueError('duplicate brand size')
   seen_sizes.add(identity);clothing('brand_size',size['size'],brand=size['brand'],sizing_system=size['sizing_system'])
  overrides=cat.get('scoped_overrides',[])
  if not isinstance(overrides,list):raise ValueError('overrides list')
  contexts=set()
  for override in overrides:
   _dict(override,{'context','preferences'});_identity(override,{'context','preferences'})
   _dict(override['context'],{'subtype','season','occasion'})
   context={k:v for k,v in override['context'].items() if v is not None}
   if not context or canonical(context) in contexts:raise ValueError('empty/duplicate scoped context')
   contexts.add(canonical(context));_dict(override['preferences'],PREFERENCES)
   for field,value in override['preferences'].items():clothing(field,value,context)
 preferences=set()
 for pref in rows('general_preferences'):
  _dict(pref,{'topic','item','scope','category','stance'});_identity(pref,{'topic','item','scope','category','stance'})
  address={'section':'preference','field':'stance',**{k:pref[k] for k in ['topic','item','scope','category']}}
  key=canonical(address)
  if key in preferences:raise ValueError('duplicate preference')
  preferences.add(key);put(address,pref['stance'])
 intents=set()
 for intent in rows('purchase_intents'):
  _dict(intent,{'id','category','recipient','status','deadline','budget'});_identity(intent,{'id'})
  if not isinstance(intent['id'],str) or not intent['id'] or intent['id'] in intents:raise ValueError('duplicate/invalid intent id')
  intents.add(intent['id'])
  if 'budget' in intent:put({'section':'intent','field':'budget','intent_id':intent['id']},intent['budget'])
  if 'status' in intent or 'deadline' in intent:
   _identity(intent,{'category','recipient'})
   address={'section':'intent','field':'state','intent_id':intent['id'],'category':intent['category'],'recipient':intent['recipient']}
   _address(address)
   if 'status' in intent and intent['status'] is not None and intent['status'] not in ['active','expired','completed','cancelled','uncertain']:raise ValueError('intent status')
   if 'deadline' in intent and intent['deadline'] is not None:_timestamp(intent['deadline'])
   for field in ['status','deadline']:
    if field in intent:
     a={**address,'field':field};key=canonical(a)
     facts[key]={'address':a,'value':deepcopy(intent[field])}
  elif set(intent)-{'id','budget'}:raise ValueError('intent context without state')
 if len(facts)>128:raise ValueError('fact budget')
 return facts


def _profile_from_records(records):
 profile={}
 def item(collection,identity):
  rows=profile.setdefault(collection,[])
  for row in rows:
   if all(row.get(k)==v for k,v in identity.items()):return row
  row=deepcopy(identity);rows.append(row);return row
 for record in records:
  a=record['address'];value=deepcopy(record['value']);s=a['section'];f=a['field']
  if s in {'personal','physical'}:profile.setdefault(s,{})[f]=value
  elif s=='general':
   if f in {'residence','languages'}:profile[f]=value
   else:profile.setdefault('interests' if f=='hobbies' else 'professional',{})[f]=value
  elif s=='clothing':
   cat=item('category_profiles',{'category':a['category']})
   if f=='default_size':cat[f]=value
   elif f=='brand_size':cat.setdefault('sizes',[]).append({'brand':a['brand'],'sizing_system':a['sizing_system'],'size':value})
   elif a['context']:
    overrides=cat.setdefault('scoped_overrides',[]);context={k:a['context'].get(k) for k in ['subtype','season','occasion']}
    override=next((o for o in overrides if o['context']==context),None)
    if override is None:override={'context':context,'preferences':{}};overrides.append(override)
    override['preferences'][f]=value
   else:cat.setdefault('preferences',{})[f]=value
  elif s=='preference':item('general_preferences',{k:a[k] for k in ['topic','item','scope','category']})['stance']=value
  elif s=='intent':
   intent=item('purchase_intents',{'id':a['intent_id']})
   if f=='state':intent.update(category=a['category'],recipient=a['recipient'],**value)
   else:
    intent[f]=value
    if f in {'status','deadline'}:intent.update(category=a['category'],recipient=a['recipient'])
 return profile


def validate_document(document,as_of=None):
 if not isinstance(document,dict) or set(document)-{'version','as_of','profile','history'} or not {'version','as_of','profile'}<=set(document) or document['version']!=VERSION:raise ValueError('note envelope')
 now=_timestamp(document['as_of'])
 if as_of is not None and document['as_of']!=as_of:raise ValueError('wrong as_of')
 flatten_profile(document['profile'])
 history=document.get('history',[])
 if not isinstance(history,list) or len(history)>128:raise ValueError('history budget/type')
 seen=set()
 for record in history:
  _dict(record,{'address','events'});_identity(record,{'address','events'});_address(record['address']);key=canonical(record['address'])
  if key in seen:raise ValueError('duplicate history address')
  seen.add(key);events=record['events']
  if not isinstance(events,list) or not 1<=len(events)<=128:raise ValueError('history events')
  previous=None
  for e in events:
   _dict(e,{'at','until','value'});_identity(e,{'at','until','value'});at=_timestamp(e['at'])
   if at>now or (previous is not None and at<=previous):raise ValueError('history chronology')
   if e['until'] is not None and _timestamp(e['until'])<=at:raise ValueError('history expiry')
   _value(record['address'],e['value']);previous=at
 return document


def parse_document(raw,as_of=None):
 def pairs(items):
  result={}
  for key,value in items:
   if key in result:raise ValueError('duplicate JSON key')
   result[key]=value
  return result
 def constant(x):raise ValueError('nonfinite JSON constant')
 if not isinstance(raw,str) or len(raw)>200000:raise ValueError('JSON size/type')
 return validate_document(json.loads(raw,object_pairs_hook=pairs,parse_constant=constant),as_of)


def apply_profile_update(raw, prior, as_of):
 """Validate a sparse model delta, then merge exact scoped fields without gold."""
 # Reuse the strict duplicate-key parser before validating the output envelope.
 envelope=parse_document('{"version":'+json.dumps(VERSION)+',"as_of":'+json.dumps(as_of)+',"profile":{},"history":[]}',as_of)
 def pairs(items):
  result={}
  for key,value in items:
   if key in result:raise ValueError('duplicate JSON key')
   result[key]=value
  return result
 if not isinstance(raw,str) or len(raw)>200000:raise ValueError('JSON size/type')
 delta=json.loads(raw,object_pairs_hook=pairs)
 _dict(delta,{'profile','history'})
 if 'profile' not in delta:raise ValueError('missing profile update')
 envelope.update(delta);validate_document(envelope,as_of)
 facts=flatten_profile(prior['profile']);facts.update(flatten_profile(delta['profile']))
 result={'version':VERSION,'as_of':as_of,'profile':_profile_from_records(facts.values())}
 history={canonical(r['address']):deepcopy(r) for r in prior.get('history',[])}
 history.update({canonical(r['address']):deepcopy(r) for r in delta.get('history',[])})
 if history:result['history']=list(history.values())
 return validate_document(result,as_of)


def score_candidate(candidate,gold):
 trace=candidate['trace']
 # Invalid actions still earn zero; a retained old state cannot rescue them.
 raw=json.dumps(candidate['notes']) if trace['finished'] else ''
 return score_extractions(raw,gold)


def gold_notes(profile,prefix):
 records=_gold_records(profile,prefix)
 result={'version':VERSION,'as_of':records['as_of'],'profile':_profile_from_records(records['facts']),
  'history':[{'address':r['address'],'events':r['history']} for r in records['facts']]}
 return validate_document(result,result['as_of'])


def empty_notes():return {'version':VERSION,'as_of':None,'profile':{}}


def policy_payload(case,prior):return {'current_session':observation(case),'previous_notes':deepcopy(prior)}


def score_extractions(raw,gold):
 validate_document(gold);targets=flatten_profile(gold['profile'])
 result={'reward':0,'correct':0,'target_count':len(targets),'missing':len(targets),'incorrect':0,'unsupported':0,
  'schema_valid':False,'exact_state':False,'correct_fraction':0.,'history_required_for_reward':False,'normalization':'none; fraction is diagnostic only'}
 try:document=parse_document(raw,gold['as_of'])
 except (ValueError,TypeError,KeyError,OverflowError,RecursionError) as exc:return {**result,'error':str(exc)}
 predictions=flatten_profile(document['profile']);correct=[];incorrect=[];unsupported=[]
 for key,fact in predictions.items():
  if key not in targets:unsupported.append(fact['address'])
  elif canonical(fact['value'])==canonical(targets[key]['value']):correct.append(fact['address'])
  else:incorrect.append(fact['address'])
 missing=[f['address'] for k,f in targets.items() if k not in predictions]
 expected_history={canonical(r['address']):r for r in gold.get('history',[])}
 predicted_history={canonical(r['address']):r for r in document.get('history',[])}
 history_correct=sum(k in expected_history and canonical(v)==canonical(expected_history[k]) for k,v in predicted_history.items())
 count=len(correct)
 return {**result,'reward':count,'correct':count,'missing':len(missing),'incorrect':len(incorrect),'unsupported':len(unsupported),
  'schema_valid':True,'correct_fraction':count/len(targets) if targets else 0.,'exact_state':count==len(targets) and not unsupported,
  'correct_addresses':correct,'missing_addresses':missing,'incorrect_addresses':incorrect,'unsupported_addresses':unsupported,
  'history_diagnostic':{'correct':history_correct,'expected':len(expected_history),'predicted':len(predicted_history),'exact':canonical(document.get('history',[]))==canonical(gold.get('history',[]))}}
