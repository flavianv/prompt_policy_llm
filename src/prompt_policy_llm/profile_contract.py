"""Offline validation/rendering for the shipped initial-profile JSON Schema.

No model calls; a deliberately small validator for the keywords used by this
contract, not a replacement for arbitrary Draft 2020-12 JSON Schema engines.
"""
import argparse
from datetime import date, datetime
import json
import math
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]/'experiments/experiment0.1/profile_generation'


def equal_exact(a,b):
    if type(a) is not type(b):return False
    if isinstance(a,dict):return a.keys()==b.keys() and all(equal_exact(a[k],b[k]) for k in a)
    if isinstance(a,list):return len(a)==len(b) and all(equal_exact(x,y) for x,y in zip(a,b))
    return a==b


def load_schema():return json.loads((ROOT/'user_profile.schema.json').read_text())
def escape(s):return s.replace('~','~0').replace('/','~1')

def tokens(pointer):
    if pointer=='':return []
    if not pointer.startswith('/') or re.search(r'~(?![01])',pointer):raise ValueError('invalid JSON Pointer')
    return [t.replace('~1','/').replace('~0','~') for t in pointer[1:].split('/')]


def resolve(node,root):
    if '$ref' in node:
        ref=node['$ref']
        if not ref.startswith('#/'):raise ValueError('only local schema refs supported')
        node=root
        for key in tokens(ref[1:]):node=node[key]
    return node


def _validate(value,node,root,path='',partial=False):
    node=resolve(node,root);errors=[]
    types=node.get('type');types=[types] if isinstance(types,str) else types
    def is_type(t):
        return {'object':isinstance(value,dict),'array':isinstance(value,list),'string':isinstance(value,str),
                'integer':type(value) is int,'number':type(value) in (int,float) and math.isfinite(value),
                'boolean':type(value) is bool,'null':value is None}[t]
    if types and not any(is_type(t) for t in types):return [f'{path or "/"}: wrong type, expected {types}']
    if value is None:return errors
    if 'const' in node and value!=node['const']:errors.append(f'{path}: must equal {node["const"]!r}')
    if 'enum' in node and value not in node['enum']:errors.append(f'{path}: unsupported enum value')
    if isinstance(value,dict):
        props=node.get('properties',{})
        if not partial:
            errors += [f'{path}/{escape(k)}: required' for k in node.get('required',[]) if k not in value]
        for k,v in value.items():
            if k not in props:
                if node.get('additionalProperties') is False:errors.append(f'{path}/{escape(k)}: unknown property')
            else:errors+=_validate(v,props[k],root,path+'/'+escape(k),partial)
    elif isinstance(value,list):
        if len(value)<node.get('minItems',0) or len(value)>node.get('maxItems',float('inf')):errors.append(f'{path}: array length')
        for i,v in enumerate(value):errors+=_validate(v,node.get('items',{}),root,path+'/'+str(i),False)
    elif isinstance(value,str):
        if len(value)<node.get('minLength',0):errors.append(f'{path}: empty string')
        if 'pattern' in node and not re.search(node['pattern'],value):errors.append(f'{path}: pattern mismatch')
        try:
            if node.get('format')=='date':
                if date.fromisoformat(value).isoformat()!=value:raise ValueError()
            elif node.get('format')=='date-time':
                if not value.endswith('Z'):raise ValueError()
                parsed=datetime.fromisoformat(value[:-1]+'+00:00')
                if parsed.strftime('%Y-%m-%dT%H:%M:%SZ')!=value:raise ValueError()
        except ValueError:errors.append(f'{path}: invalid {node["format"]} (timestamps must use UTC Z)')
    elif type(value) in (int,float):
        for key,invalid in [('minimum',lambda n:value<n),('maximum',lambda n:value>n),('exclusiveMinimum',lambda n:value<=n)]:
            if key in node and invalid(node[key]):errors.append(f'{path}: violates {key}')
    return errors


def at(value,pointer):
    for t in tokens(pointer):
        if isinstance(value,list):
            if not t.isdigit() or str(int(t))!=t:raise ValueError('array index must be canonical integer')
            value=value[int(t)]
        else:value=value[t]
    return value


def schema_at(schema,pointer):
    node=schema
    for t in tokens(pointer):
        node=resolve(node,schema)
        types=node.get('type',[]);types=[types] if isinstance(types,str) else types
        if 'object' in types:node=node['properties'][t]
        elif 'array' in types:
            if not t.isdigit() or str(int(t))!=t or int(t)>=node.get('maxItems',100000):raise ValueError('invalid index')
            node=node['items']
        else:raise ValueError('path traverses a scalar')
    return resolve(node,schema)


def age_at(birth,reference):
    b=date.fromisoformat(birth);r=date.fromisoformat(reference)
    return r.year-b.year-((r.month,r.day)<(b.month,b.day))


def constraint_rules(constraints,schema=None):
    schema=schema or load_schema();errors=[];rules={}
    if not isinstance(constraints,dict) or set(constraints)-{'fixed_values','fixed_paths'}:return {},['constraints: only fixed_values and fixed_paths are supported']
    fixed=constraints.get('fixed_values',{});paths=constraints.get('fixed_paths',{})
    if not isinstance(fixed,dict) or not isinstance(paths,dict):return {},['constraints: both fields must be objects']
    errors+=_validate(fixed,schema,schema,partial=True)
    def flatten(value,path):
        if isinstance(value,dict):
            for k,v in value.items():flatten(v,path+'/'+escape(k))
        else:rules[path]=value
    flatten(fixed,'')
    for pointer,value in paths.items():
        try:
            node=schema_at(schema,pointer)
            errors+=_validate(value,node,schema,pointer)
            if pointer in rules and not equal_exact(rules[pointer],value):errors.append(f'{pointer}: fixed_values and fixed_paths disagree')
            rules[pointer]=value
        except (KeyError,ValueError,TypeError):errors.append(f'{pointer}: unknown or invalid fixed path')
    entries=list(rules.items())
    for p,v in entries:
        for q,w in entries:
            if p!=q and (p=='' or q.startswith(p+'/')):
                try:
                    if not equal_exact(at(v,q[len(p):]),w):raise ValueError()
                except (KeyError,ValueError,TypeError,IndexError):errors.append(f'{p or "/"}, {q}: overlapping fixed values conflict')
    def known(pointer):
        for p,v in entries:
            if p==pointer:return v
            if p=='' or pointer.startswith(p+'/'):
                try:return at(v,pointer[len(p):])
                except (KeyError,ValueError,TypeError,IndexError):pass
        return None
    birth,reference,age=known('/personal/birth_date'),known('/reference_date'),known('/personal/age')
    if birth is not None and reference is not None:
        try:
            derived=age_at(birth,reference)
            if not 0<=derived<=120 or (age is not None and age!=derived):errors.append('/personal/age, /personal/birth_date, /reference_date: inconsistent age/date constraints')
        except (TypeError,ValueError):pass  # structural validator reports malformed dates
    for pointer,value in entries:
        if pointer.endswith('/hard') and isinstance(value,list) and all(isinstance(r,dict) and set(r)>={'field','op','value'} for r in value):
            errors += [pointer+': '+e for e in hard_rule_conflicts(value)]
    return rules,list(dict.fromkeys(errors))


def hard_rule_conflicts(rules):
    """Unary hard-rule contradictions, without demographic assumptions."""
    fields={r['field'] for r in rules};errors=[]
    for field in fields:
        group=[r for r in rules if r['field']==field]
        allowed=None;lower=float('-inf');upper=float('inf')
        for r in group:
            if r['op'] in ('eq','in'):
                values=[r['value']] if r['op']=='eq' else r['value']
                if not isinstance(values,list):continue
                allowed=values if allowed is None else [v for v in allowed if v in values]
            elif r['op']=='gte' and type(r['value']) in (int,float):lower=max(lower,r['value'])
            elif r['op']=='lte' and type(r['value']) in (int,float):upper=min(upper,r['value'])
        if allowed is not None:
            for r in group:
                if r['op']=='ne':allowed=[v for v in allowed if v!=r['value']]
                elif r['op']=='not_in' and isinstance(r['value'],list):allowed=[v for v in allowed if v not in r['value']]
            if lower!=float('-inf') or upper!=float('inf'):
                allowed=[v for v in allowed if type(v) in (int,float) and lower<=v<=upper]
        if lower>upper or allowed==[]:errors.append('contradictory hard rules for '+field)
    return errors


def validate_profile(profile,constraints=None,schema=None):
    schema=schema or load_schema();errors=_validate(profile,schema,schema)
    if errors:return errors
    if age_at(profile['personal']['birth_date'],profile['reference_date'])!=profile['personal']['age']:
        errors.append('/personal/age: inconsistent with birth_date/reference_date')
    category_keys=[c['category'] for c in profile['category_profiles']]
    if len(category_keys)!=len(set(category_keys)):errors.append('/category_profiles: duplicate category')
    seen=set()
    for i,p in enumerate(profile['general_preferences']):
        key=(p['topic'],p['item'],p['scope'],p['category'])
        if key in seen:errors.append(f'/general_preferences/{i}: duplicate or conflicting scoped preference')
        seen.add(key)
        if (p['scope']=='global' and p['category'] is not None) or (p['scope']=='category' and p['category'] not in category_keys):errors.append(f'/general_preferences/{i}: invalid category scope')
        if (p['stance']=='retracted' and p['shopping_effect']!='background_only') or (p['stance']=='like' and p['shopping_effect']=='hard_exclusion') or (p['stance']=='dislike' and p['shopping_effect']=='soft_preference'):errors.append(f'/general_preferences/{i}: contradictory stance/effect')
    ids=set()
    for i,p in enumerate(profile['purchase_intents']):
        if p['id'] in ids:errors.append(f'/purchase_intents/{i}: duplicate id')
        ids.add(p['id'])
        if p['category'] not in category_keys:errors.append(f'/purchase_intents/{i}/category: category profile missing')
        if p['recipient']=='gift' and p['use_general_preferences']:errors.append(f'/purchase_intents/{i}: gift cannot inherit shopper preferences')
        if p['deadline'] and (p['deadline']<p['created_at'] or (p['status']=='active' and p['deadline'][:10]<profile['reference_date'])):errors.append(f'/purchase_intents/{i}/deadline: inconsistent chronology/status')
    for prefix,p in [(f'/category_profiles/{i}',p) for i,p in enumerate(profile['category_profiles'])]+[(f'/purchase_intents/{i}',p) for i,p in enumerate(profile['purchase_intents'])]:
        seen_sizes=set()
        for s in p['sizes'] or []:
            key=(s['brand'],s['sizing_system'])
            if key in seen_sizes:errors.append(prefix+'/sizes: duplicate/conflicting scoped size')
            seen_sizes.add(key)
        errors += [prefix+': '+e for e in hard_rule_conflicts(p['hard'])]
        for r in p['hard']+p.get('soft',[]):
            if r['op'] in ('in','not_in') and (not isinstance(r['value'],list) or not r['value']):errors.append(prefix+': set rule requires nonempty list')
            if r['op'] in ('lte','gte') and type(r['value']) not in (int,float):errors.append(prefix+': numeric bound required')
    definitions=json.loads((ROOT/'clothing_categories.json').read_text())['categories']
    for i,c in enumerate(profile['category_profiles']):
        if c['category'] not in definitions:
            errors.append(f'/category_profiles/{i}: unknown clothing category');continue
        allowed=set(definitions[c['category']]['preference_attributes'])
        if set(c['preferences'])!=allowed:errors.append(f'/category_profiles/{i}/preferences: include exactly applicable attributes, using null if unknown')
        for j,override in enumerate(c['scoped_overrides']):
            if set(override['preferences'])-allowed:errors.append(f'/category_profiles/{i}/scoped_overrides/{j}: attribute not applicable')
            if not any(v is not None for v in override['context'].values()):errors.append(f'/category_profiles/{i}/scoped_overrides/{j}: context must be specified')
    if constraints is not None:
        rules,conflicts=constraint_rules(constraints,schema);errors+=conflicts
        for pointer,value in rules.items():
            try:
                if not equal_exact(at(profile,pointer),value):errors.append(pointer+': fixed value changed')
            except (KeyError,ValueError,TypeError,IndexError):errors.append(pointer+': fixed path missing')
    return list(dict.fromkeys(errors))


def resolve_clothing_preferences(category,context):
    result=json.loads(json.dumps(category['preferences']))
    matching=[(sum(v is not None for v in o['context'].values()),i,o) for i,o in enumerate(category['scoped_overrides'])
              if all(v is None or context.get(k)==v for k,v in o['context'].items())]
    for _,_,override in sorted(matching):result.update(json.loads(json.dumps(override['preferences'])))
    return result


def render_prompt(constraints,category_schemas=None):
    _,errors=constraint_rules(constraints)
    if errors:raise ValueError('; '.join(errors))
    text=(ROOT/'conditional_profile_prompt.md').read_text()
    for key,value in {'USER_PROFILE_SCHEMA_JSON':load_schema(),'FIXED_CONSTRAINTS_JSON':constraints,'CATEGORY_SCHEMAS_JSON':category_schemas if category_schemas is not None else json.loads((ROOT/'clothing_categories.json').read_text())}.items():
        text=text.replace('{{'+key+'}}',json.dumps(value,indent=2,ensure_ascii=False))
    return text


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--profile',type=Path,default=ROOT/'example_profile.json');p.add_argument('--constraints',type=Path,default=ROOT/'example_constraints.json');p.add_argument('--render-prompt',type=Path)
    args=p.parse_args();constraints=json.loads(args.constraints.read_text());profile=json.loads(args.profile.read_text());errors=validate_profile(profile,constraints)
    if args.render_prompt and not errors:args.render_prompt.write_text(render_prompt(constraints))
    print(json.dumps({'valid':not errors,'errors':errors,'model_generation_executed':False},indent=2))
    raise SystemExit(1 if errors else 0)


if __name__=='__main__':main()
