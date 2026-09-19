"""Finite, JSON-defined synthetic shopping environment; no executable config."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import random

VERSION = 'experiment0.1'
SCHEMA_VERSION = 'schema-v4'
STATUSES = {'active', 'expired', 'completed', 'cancelled', 'uncertain'}
OPS = {'eq', 'ne', 'in', 'not_in', 'lte', 'gte'}
DEFAULT_SPEC = Path(__file__).resolve().parents[2]/'experiments/experiment0.1/environment.json'


def iso(x):
    return x.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def instant(x):
    if not isinstance(x, str) or not x.endswith('Z'):
        raise ValueError('timestamp requires UTC Z')
    dt = datetime.fromisoformat(x[:-1]+'+00:00')
    if iso(dt) != x:
        raise ValueError('noncanonical timestamp')
    return dt


def strict_json(text):
    def unique(pairs):
        obj = {}
        for k, v in pairs:
            if k in obj:
                raise ValueError('duplicate key')
            obj[k] = v
        return obj
    def reject(_):
        raise ValueError('nonfinite number')
    return json.loads(text, object_pairs_hook=unique, parse_constant=reject)


def matches(value, rule):
    op, wanted = rule['op'], rule['value']
    if op == 'eq': return value == wanted
    if op == 'ne': return value != wanted
    if op == 'in': return value in wanted
    if op == 'not_in': return value not in wanted
    if op == 'lte': return value <= wanted
    if op == 'gte': return value >= wanted
    raise ValueError('unsupported operator')


def lifecycle(intent, now):
    if intent['status'] == 'active' and intent['deadline'] and instant(now) > instant(intent['deadline']):
        return 'expired'
    return intent['status']


def current(history, at):
    return next((r for r in reversed(history) if r['valid_from'] <= at and
                 (r['valid_until'] is None or at < r['valid_until'])), None)


def extend_history(history, value, now, source):
    if history:
        history[-1]['valid_until'] = now
    history.append({'value': deepcopy(value), 'valid_from': now, 'valid_until': None, 'source_ids': [source]})


class SchemaEnvironment:
    def __init__(self, spec=None, categories=None):
        self.spec = deepcopy(spec if spec is not None else strict_json(DEFAULT_SPEC.read_text()))
        self.categories = list(categories if categories is not None else self.spec['generation']['selected_categories'])
        self.validate_spec()
        self.schemas = {k: self.spec['categories'][k] for k in self.categories}

    def validate_spec(self):
        s = self.spec
        if s['schema_version'] != SCHEMA_VERSION or not self.categories or len(set(self.categories)) != len(self.categories):
            raise ValueError('schema version or selection invalid')
        if set(self.categories) - s['categories'].keys() or set(s['operators']) - OPS:
            raise ValueError('unknown category/operator')
        for name, cat in s['categories'].items():
            if not name or not cat['attributes']:
                raise ValueError('empty category')
            for key, field in cat['attributes'].items():
                if key in ('id', 'category', 'deliver_by', 'size', 'sizing_system'):
                    raise ValueError('reserved attribute')
                values = field['values']
                if not values or field['type'] not in ('enum', 'integer', 'number'):
                    raise ValueError('supported fields require finite nonempty domains')
                for value in values:
                    if field['type'] == 'enum' and (not isinstance(value, str) or not value):
                        raise ValueError('enum values must be nonempty strings')
                    if field['type'] == 'integer' and type(value) is not int:
                        raise ValueError('integer domain required')
                    if field['type'] == 'number' and (type(value) not in (int,float) or not float('-inf') < value < float('inf')):
                        raise ValueError('finite numeric domain required')
            if cat['size_systems'] and 'brand' not in cat['attributes']:
                raise ValueError('sized products require brand')
            if any(not values or any(not isinstance(v,str) or not v for v in values) for values in cat['size_systems'].values()):
                raise ValueError('sizes are explicit nonempty strings')
            for layer in ('profile','intent'):
                for mode in ('hard','soft'):
                    for rule in cat[layer][mode]:
                        for value in rule['values']:
                            self.validate_rule(name, dict(field=rule['field'],op=rule['op'],value=value))
        for key, field in s['general_fields'].items():
            if 'derived' in field:
                if field['derived']['operator'] != 'age_years' or field['derived']['source'] not in s['general_fields']:
                    raise ValueError('only age_years derivation supported')
            elif not field['values'] or field['update_policy'] not in ('mutable','correction_only','immutable'):
                raise ValueError('invalid fact schema')
        for key, field in s['general_fields'].items():
            sampler=field.get('sampler')
            if sampler:
                if sampler['operator']!='name_pool' or sampler['source'] not in s['general_fields']:
                    raise ValueError('unsupported fact sampler')
                source=s['general_fields'][sampler['source']]
                if set(sampler['pools'])!=set(source['values']) or any(not pool or any(v not in field['values'] for v in pool) for pool in sampler['pools'].values()):
                    raise ValueError('name pools must cover nationality domain and name values')
        g = s['generation']
        if g['sessions'] < 1 or min(g['gap_days']) <= 0 or min(g['events_per_session']) < 1:
            raise ValueError('chronology/count settings invalid')
        if g['catalog_size'] <= g['cross_category_distractors'] or g['cross_category_distractors'] < 1:
            raise ValueError('catalog size/distractors invalid')
        for t in g['start_dates']: instant(t)
        event_types = {'reveal_fact','update_fact','correct_fact','preference','retract_preference','category_update',
                      'create_intent','complete_intent','cancel_intent','reopen_intent','uncertain_intent',
                      'intent_override','clear_override','distractor'}
        if set(g['event_weights']) - event_types or any(type(v) not in (int,float) or v <= 0 for v in g['event_weights'].values()):
            raise ValueError('invalid event weights')
        for topic in s['preference_topics'].values():
            if not topic['values'] or set(topic['scopes']) - {'global','category'}:
                raise ValueError('invalid preference topic')
            effect = topic['recommendation']
            if effect and (effect['like_operator'] != 'eq' or effect['dislike_operator'] != 'ne' or
                           effect['like_mode'] != 'soft' or effect['dislike_mode'] != 'hard'):
                raise ValueError('preference effects support soft equality / hard exclusion')

    def validate_rule(self, category, rule):
        if not isinstance(rule,dict) or set(rule) != {'field','op','value'} or rule['op'] not in self.spec['operators']:
            raise ValueError('invalid rule')
        fields = self.spec['categories'][category]['attributes']
        if rule['field'] not in fields:
            raise ValueError('rule field not applicable')
        field = fields[rule['field']]; value = rule['value']
        if rule['op'] in ('lte','gte'):
            if field['type'] not in ('number','integer') or type(value) not in (int,float) or not float('-inf') < value < float('inf'):
                raise ValueError('numeric bound required')
        elif rule['op'] in ('in','not_in'):
            if not isinstance(value,list) or not value or any(v not in field['values'] for v in value):
                raise ValueError('set operator requires domain list')
        elif value not in field['values']:
            raise ValueError('rule value outside domain')

    def sample_rules(self, category, layer, rng):
        return {mode:[{'field':r['field'],'op':r['op'],'value':deepcopy(rng.choice(r['values']))}
                      for r in self.schemas[category][layer][mode]] for mode in ('hard','soft')}

    def sample_sizes(self, category, rng):
        schema = self.schemas[category]
        if not schema['size_systems']: return []
        result=[]
        for brand in schema['attributes']['brand']['values']:
            system=rng.choice(list(schema['size_systems']))
            result.append({'brand':brand,'sizing_system':system,'size':rng.choice(schema['size_systems'][system])})
        return result

    def effective(self, state, intent):
        raw=intent['attributes']; cat=raw['category']
        base=state['categories'].get(cat,{}).get('attributes',{}) if raw['recipient']=='self' else {}
        attrs={'category':cat, 'sizes':deepcopy(base.get('sizes',[]) if raw['sizes'] is None else raw['sizes'])}
        for mode in ('hard','soft'):
            # An explicit intent override replaces same-field category rules, never another category.
            overridden={r['field'] for r in raw[mode]} | set(raw['remove_'+mode])
            attrs[mode]=deepcopy([r for r in base.get(mode,[]) if r['field'] not in overridden]+raw[mode])
        relevant=[]
        if raw['recipient']=='self' and raw['use_general_preferences']:
            for pid,p in state['preferences'].items():
                effect=self.spec['preference_topics'][p['topic']]['recommendation']
                if not effect or p['topic'] not in self.schemas[cat].get('preference_topics',[]) or effect['field'] not in self.schemas[cat]['attributes'] or pid in raw['exclude_preferences']:
                    continue
                if p['scope']=='category' and p['category']!=cat: continue
                stance=p['history'][-1]['value']
                if stance=='retracted': continue
                mode='soft' if stance=='like' else 'hard'
                rule={'field':effect['field'],'op':'eq' if stance=='like' else 'ne','value':p['item']}
                # Unknown-to-category brands cannot match; excluding them is harmless.
                attrs[mode].append(rule); relevant.extend(p['history'][-1]['source_ids'])
        attrs['preference_sources']=relevant
        return attrs

    def size_status(self, product, attrs):
        if not self.schemas[attrs['category']]['size_systems']: return 'not_applicable'
        match=next((s for s in attrs['sizes'] if s['brand']==product.get('brand') and
                    s['sizing_system']==product.get('sizing_system')),None)
        if not match: return 'unknown'
        return 'match' if match['size']==product.get('size') else 'mismatch'

    def violations(self, product, attrs, deadline, include_size=True):
        if product.get('category')!=attrs['category']: return ['category']
        bad=[r['field'] for r in attrs['hard'] if not matches(product.get(r['field']),r)]
        if deadline and product['deliver_by']>deadline: bad.append('delivery')
        status=self.size_status(product,attrs)
        if include_size and status in ('unknown','mismatch'): bad.append('size_'+status)
        return sorted(set(bad))

    def preference_score(self, product, attrs):
        return sum(matches(product.get(r['field']),r) for r in attrs['soft'])

    def oracle(self, state, intent, catalog, now):
        status=lifecycle(intent,now); attrs=self.effective(state,intent)
        scores={}; unknown=[]
        if status=='active':
            for p in catalog:
                if not self.violations(p,attrs,intent['deadline']): scores[p['id']]=self.preference_score(p,attrs)
                elif not self.violations(p,attrs,intent['deadline'],False) and self.size_status(p,attrs)=='unknown': unknown.append(p['id'])
        best=max(scores.values()) if scores else None
        if scores:
            choices=[k for k,v in scores.items() if v==best]; decision='tie' if len(choices)>1 else 'ranked_choice'
        elif status!='active': choices,decision=['NONE'],'inactive'
        elif unknown: choices,decision=['ASK_SIZE'],'insufficient_size'
        else: choices,decision=['NONE'],'no_suitable_product'
        sources=list(intent['source_ids'])+attrs.pop('preference_sources')
        if intent['attributes']['recipient']=='self': sources+=state['categories'][attrs['category']]['source_ids']
        return {'kind':'recommendation','intent_status':status,'acceptable_choices':choices,
                'feasible_choices':list(scores),'preference_scores':scores,'best_preference_score':best,
                'decision_type':decision,'effective_attributes':attrs,'deadline':intent['deadline'],
                'support_ids':sorted(set(sources))}

    def random_product(self, cat, now, rng):
        schema=self.schemas[cat]
        p={'category':cat,'deliver_by':iso(instant(now)+timedelta(days=rng.choice([0,1,3,7])))}
        p.update({k:deepcopy(rng.choice(v['values'])) for k,v in schema['attributes'].items()})
        if schema['size_systems']:
            system=rng.choice(list(schema['size_systems'])); p.update(sizing_system=system,size=rng.choice(schema['size_systems'][system]))
        return p

    def best_product(self, attrs, now, rng):
        cat=attrs['category']; schema=self.schemas[cat]; p={'category':cat,'deliver_by':now}
        # Enumerate each finite field independently; rules are unary, with scoped sizing handled below.
        for key,field in schema['attributes'].items():
            values=[v for v in field['values'] if all(matches(v,r) for r in attrs['hard'] if r['field']==key)]
            if not values: return None
            if key=='brand' and schema['size_systems']:
                values=[v for v in values if any(s['brand']==v for s in attrs['sizes'])]
                if not values: return None
            scores={json.dumps(v):sum(matches(v,r) for r in attrs['soft'] if r['field']==key) for v in values}
            best=max(scores.values()); p[key]=deepcopy(rng.choice([v for v in values if scores[json.dumps(v)]==best]))
        if schema['size_systems']:
            s=rng.choice([s for s in attrs['sizes'] if s['brand']==p['brand']]); p.update(sizing_system=s['sizing_system'],size=s['size'])
        return p

    def make_catalog(self, state, intent, now, rng, mode):
        attrs=self.effective(state,intent); cat=attrs['category']; schema=self.schemas[cat]
        best=self.best_product(attrs,now,rng); items=[]
        if best and mode in ('ranked','tie'):
            items=[deepcopy(best) for _ in range(2 if mode=='tie' else 1)]
            # Deliberately include a feasible lower-ranked alternative when one exists.
            for key,field in schema['attributes'].items():
                lower=next((v for v in field['values'] if all(matches(v,r) for r in attrs['hard'] if r['field']==key)
                            and sum(matches(v,r) for r in attrs['soft'] if r['field']==key)<
                                sum(matches(best[key],r) for r in attrs['soft'] if r['field']==key)),None)
                if lower is not None and key!='brand':
                    p=deepcopy(best);p[key]=lower;items.append(p);break
        elif best and mode=='unknown_size' and schema['size_systems']:
            other=next((s for s in schema['size_systems'] if not any(x['brand']==best['brand'] and x['sizing_system']==s for x in attrs['sizes'])),None)
            if other:
                p=deepcopy(best);p.update(sizing_system=other,size=rng.choice(schema['size_systems'][other]));items.append(p)
        other_categories=[c for c in self.categories if c!=cat]
        cross=self.spec['generation']['cross_category_distractors'] if other_categories else 0
        for _ in range(cross): items.append(self.random_product(rng.choice(other_categories),now,rng))
        for _ in range(self.spec['generation']['catalog_size']-len(items)):
            p=self.random_product(cat,now,rng)
            if not self.violations(p,attrs,intent['deadline'],False):
                # Find a schema-valid hard violation; otherwise use a different selected category.
                alternative=next(((r['field'],v) for r in attrs['hard'] for v in schema['attributes'][r['field']]['values'] if not matches(v,r)),None)
                if alternative: p[alternative[0]]=deepcopy(alternative[1])
                elif other_categories: p=self.random_product(rng.choice(other_categories),now,rng)
                elif intent['deadline']: p['deliver_by']=iso(instant(intent['deadline'])+timedelta(seconds=1))
                # If there is no way to violate a rule, the actual oracle (not the requested mode) wins.
            items.append(p)
        rng.shuffle(items)
        for p in items: p['id']='p-'+format(rng.getrandbits(64),'016x');self.validate_product(p)
        return items

    def validate_product(self,p):
        cat=p['category'];schema=self.schemas[cat]
        keys={'id','category','deliver_by'}|set(schema['attributes'])
        if schema['size_systems']:keys|={'size','sizing_system'}
        if set(p)!=keys:raise ValueError('inapplicable product fields')
        instant(p['deliver_by'])
        if any(p[k] not in f['values'] for k,f in schema['attributes'].items()):raise ValueError('product outside domain')
        if schema['size_systems'] and p['size'] not in schema['size_systems'].get(p['sizing_system'],[]):raise ValueError('invalid size/system')

    def generate_episode(self,seed,split='eval'):
        rng=random.Random(f'{SCHEMA_VERSION}:{split}:{seed}');g=self.spec['generation']
        now=instant(rng.choice(g['start_dates']));state={'general':{},'preferences':{},'categories':{},'intents':{}}
        cases=[];all_evidence=[];counter=0
        latent_general={f:deepcopy(rng.choice(d['values'])) for f,d in self.spec['general_fields'].items() if 'derived' not in d}
        for field,definition in self.spec['general_fields'].items():
            sampler=definition.get('sampler')
            if sampler:
                latent_general[field]=rng.choice(sampler['pools'][latent_general[sampler['source']]])
        latent_preferences={}
        for topic,definition in self.spec['preference_topics'].items():
            choices=rng.sample(definition['values'],min(2,len(definition['values'])))
            latent_preferences[topic]={'scope':'global','likes':choices[:1],'dislikes':choices[1:]}
        latent_categories={cat:{'category':cat,'sizes':self.sample_sizes(cat,rng),**self.sample_rules(cat,'profile',rng),'valid_from':iso(now)} for cat in self.categories}
        def sample_value(field,old=None):
            values=self.spec['general_fields'][field]['values'];choices=[v for v in values if v!=old]
            return deepcopy(rng.choice(choices or values))
        for session in range(g['sessions']):
            if session:now+=timedelta(days=rng.choice(g['gap_days']))
            stamp=iso(now);evidence=[]
            def emit(kind,**values):
                eid=f'e{session}-{len(evidence)}'
                text=self.spec['rendering'][kind].format(time=stamp,**values)
                evidence.append({'id':eid,'timestamp':stamp,'text':text});return eid
            def fact(field,kind):
                history=state['general'].setdefault(field,[]);value=sample_value(field,history[-1]['value']) if history else deepcopy(latent_general[field])
                eid=emit(kind,field=field,value=json.dumps(value,sort_keys=True));extend_history(history,value,stamp,eid)
            def category(cat,update=False):
                rules=self.sample_rules(cat,'profile',rng)
                attrs=deepcopy(latent_categories[cat]);attrs['valid_from']=stamp
                if update:
                    attrs=deepcopy(state['categories'][cat]['attributes']);attrs['valid_from']=stamp
                    if attrs['sizes'] and rng.random()<.5:
                        size=rng.choice(attrs['sizes']);values=self.schemas[cat]['size_systems'][size['sizing_system']]
                        size['size']=rng.choice([v for v in values if v!=size['size']] or values)
                    else:
                        mode=rng.choice(['hard','soft']);attrs[mode]=rules[mode]
                eid=emit('category',category=cat,value=json.dumps(attrs,sort_keys=True));state['categories'][cat]={'attributes':attrs,'source_ids':[eid]}
            def preference(retract=False):
                if retract:
                    pid=rng.choice([k for k,p in state['preferences'].items() if p['history'][-1]['value']!='retracted']);p=state['preferences'][pid];stance='retracted'
                else:
                    topic=rng.choice(list(self.spec['preference_topics']));schema=self.spec['preference_topics'][topic]
                    scope=rng.choice(schema['scopes']);cat=rng.choice(self.categories) if scope=='category' else None;item=rng.choice(schema['values'])
                    pid=f'{topic}:{scope}:{cat or "all"}:{item}';p=state['preferences'].setdefault(pid,{'id':pid,'topic':topic,'scope':scope,'category':cat,'item':item,'history':[]})
                    initial=latent_preferences[topic]
                    if not p['history'] and scope=='global' and item in initial['likes']+initial['dislikes']:
                        stance='like' if item in initial['likes'] else 'dislike'
                    else:
                        stance=rng.choice(['like','dislike'])
                    if p['history'] and p['history'][-1]['value']==stance:stance='dislike' if stance=='like' else 'like'
                effect=self.spec['preference_topics'][p['topic']]['recommendation']
                explanation=('For my own applicable purchases, a dislike excludes this brand and a like is a negotiable preference. A retraction removes either effect.' if effect else 'Background preference only; it imposes no shopping requirement.')
                eid=emit('preference',topic=p['topic'],item=p['item'],stance=stance,scope=p['scope'],category=p['category'],effect=explanation)
                extend_history(p['history'],stance,stamp,eid)
            def save_intent(label,p):
                p['attributes']['valid_from']=stamp
                shown={'attributes':p['attributes'],'status':p['status'],'deadline':p['deadline']}
                eid=emit('intent',label=label,value=json.dumps(shown,sort_keys=True));p['source_ids']=[eid]
            def create_intent():
                nonlocal counter
                cat=rng.choice(self.categories)
                if cat not in state['categories']:category(cat)
                gift=rng.random()<g['gift_probability'];rules=self.sample_rules(cat,'intent',rng)
                if gift:
                    base=self.sample_rules(cat,'profile',rng)
                    rules={k:base[k]+rules[k] for k in ('hard','soft')}
                day=rng.choice(g['deadline_days']);deadline=iso(now+timedelta(days=day,hours=8)) if day is not None else None
                label=f'purchase{counter}';counter+=1
                attrs={'label':label,'category':cat,'recipient':'gift' if gift else 'self','sizes':self.sample_sizes(cat,rng) if gift else None,
                       **rules,'remove_hard':[],'remove_soft':[],'use_general_preferences':not gift,'exclude_preferences':[],'valid_from':stamp}
                p={'attributes':attrs,'status':'active','deadline':deadline,'source_ids':[],'base_attributes':deepcopy(attrs)}
                state['intents'][label]=p;save_intent(label,p)
            if session==0:
                fields=[f for f,d in self.spec['general_fields'].items() if 'derived' not in d]
                # Birthday is explicitly revealed; age is computed, never independently randomized.
                age_sources=[d['derived']['source'] for d in self.spec['general_fields'].values() if 'derived' in d]
                initial=list(dict.fromkeys(g.get('initial_required_facts',[])+age_sources+rng.sample(fields,min(g['initial_fact_count'],len(fields)))))
                for field in initial:fact(field,'fact')
                for _ in range(g['initial_preferences']):preference()
                for _ in range(min(g['initial_intents'],g['max_intents'])):create_intent()
            for _ in range(rng.choice(g['events_per_session'])):
                unseen=[f for f,d in self.spec['general_fields'].items() if 'derived' not in d and f not in state['general']]
                mutable=[f for f in state['general'] if self.spec['general_fields'][f]['update_policy']=='mutable']
                correctable=[f for f in state['general'] if self.spec['general_fields'][f]['update_policy']=='correction_only']
                active=[k for k,p in state['intents'].items() if lifecycle(p,stamp)=='active']
                closed=[k for k,p in state['intents'].items() if lifecycle(p,stamp)!='active']
                possible={'reveal_fact':bool(unseen),'update_fact':bool(mutable),'correct_fact':bool(correctable),
                  'preference':True,'retract_preference':any(p['history'][-1]['value']!='retracted' for p in state['preferences'].values()),
                  'category_update':bool(state['categories']),'create_intent':len(state['intents'])<g['max_intents'],
                  'complete_intent':bool(active),'cancel_intent':bool(active),'uncertain_intent':bool(active),
                  'reopen_intent':bool(closed),'intent_override':bool(active),'clear_override':bool(active),'distractor':True}
                options=[k for k in g['event_weights'] if possible[k]];kind=rng.choices(options,weights=[g['event_weights'][k] for k in options])[0]
                if kind=='reveal_fact':fact(rng.choice(unseen),'fact')
                elif kind=='update_fact':fact(rng.choice(mutable),'fact_update')
                elif kind=='correct_fact':fact(rng.choice(correctable),'fact_correction')
                elif kind in ('preference','retract_preference'):preference(kind=='retract_preference')
                elif kind=='category_update':category(rng.choice(list(state['categories'])),True)
                elif kind=='create_intent':create_intent()
                elif kind=='distractor':emit('distractor',text=rng.choice(self.spec['distractors']))
                else:
                    label=rng.choice(closed if kind=='reopen_intent' else active);p=state['intents'][label]
                    if kind=='reopen_intent':p['status']='active';p['deadline']=iso(now+timedelta(days=rng.choice([d for d in g['deadline_days'] if d is not None]),hours=8))
                    elif kind in ('complete_intent','cancel_intent','uncertain_intent'):p['status']={'complete_intent':'completed','cancel_intent':'cancelled','uncertain_intent':'uncertain'}[kind]
                    elif kind=='clear_override':p['attributes']=deepcopy(p['base_attributes'])
                    else:
                        rules=self.sample_rules(p['attributes']['category'],'profile',rng)
                        mode=rng.choice(['hard','soft']);p['attributes'][mode]=rules[mode]
                    save_intent(label,p)
            all_evidence.extend(deepcopy(evidence))
            questions,truth=self.questions(state,stamp,rng)
            known={e['id'] for e in all_evidence}
            assert all(set(t['support_ids'])<=known for t in truth.values())
            cases.append({'session':session,'current_time':stamp,'evidence':evidence,'questions':questions,'truth':truth,'hidden_state':deepcopy(state)})
        return {'version':VERSION,'schema_version':SCHEMA_VERSION,'seed':seed,'split':split,'user_id':f'{split}-{seed}',
                'selected_categories':self.categories,'sampled_user':{'general':latent_general,'general_preferences':latent_preferences,'category_profiles':latent_categories,
                'note':'Hidden initial draw; unrevealed values never drive questions or recommendations. Initial global preference likes/dislikes are hidden until stated; new changes and intents are sampled during sessions.'},'cases':cases}

    def questions(self,state,now,rng):
        cfg=self.spec['generation']['questions'];qs=[];truth={}
        fields=list(state['general'])+[k for k,d in self.spec['general_fields'].items() if 'derived' in d and d['derived']['source'] in state['general']]
        for field in rng.sample(fields,min(cfg['facts'],len(fields))):
            spec=self.spec['general_fields'][field];source=spec.get('derived',{}).get('source',field);history=state['general'][source]
            at=rng.choice(history)['valid_from'] if rng.random()<cfg['historical_probability'] else now
            row=current(history,at);value=deepcopy(row['value'])
            if 'derived' in spec:
                birthday=datetime.fromisoformat(value).date();date=instant(at).date()
                value=date.year-birthday.year-((date.month,date.day)<(birthday.month,birthday.day));values=[value,value-1,value+1,value+2]
            else:values=[value]+[deepcopy(v) for v in spec['values'] if v!=value][:3]
            rng.shuffle(values);options={chr(65+i):v for i,v in enumerate(values)};qid=f'q{len(qs)}'
            qs.append({'id':qid,'kind':'fact','field':field,'at_time':at,'question':f'What was the explicitly supported {field} at {at}?','options':options})
            truth[qid]={'kind':'fact','answer':next(k for k,v in options.items() if v==value),'support_ids':row['source_ids'],'field':field,'at_time':at}
        for pid in rng.sample(list(state['preferences']),min(cfg['preferences'],len(state['preferences']))):
            p=state['preferences'][pid];at=rng.choice(p['history'])['valid_from'] if rng.random()<cfg['historical_probability'] else now;row=current(p['history'],at)
            values=['like','dislike','retracted'];rng.shuffle(values);options={chr(65+i):v for i,v in enumerate(values)};qid=f'q{len(qs)}'
            qs.append({'id':qid,'kind':'preference','topic':p['topic'],'item':p['item'],'scope':p['scope'],'category':p['category'],'at_time':at,'question':'What was the explicitly stated stance at this time and scope?','options':options})
            truth[qid]={'kind':'preference','answer':next(k for k,v in options.items() if v==row['value']),'support_ids':row['source_ids'],'at_time':at}
        labels=list(state['intents']);rng.shuffle(labels)
        for label in labels[:cfg['recommendations']]:
            intent=state['intents'][label];catalog=self.make_catalog(state,intent,now,rng,rng.choice(self.spec['generation']['catalog_modes']));qid=f'q{len(qs)}'
            qs.append({'id':qid,'kind':'recommendation','intent':label,'request':f'Choose for {label} if actionable.','catalog':catalog})
            truth[qid]=self.oracle(state,intent,catalog,now)
        return qs,truth

    def expected_notes(self,state,now):
        notes={}
        def wrap(kind,attrs,sources,status='active',deadline=None):
            return {'kind':kind,'attributes':deepcopy(attrs),'status':status,'deadline':deadline,'source_ids':sorted(set(sources))}
        for field,history in state['general'].items():
            notes['general:'+field]=wrap('general',{'field':field,'history':history},[s for r in history for s in r['source_ids']])
        for pid,p in state['preferences'].items():
            notes['preference:'+pid]=wrap('preference',p,[s for r in p['history'] for s in r['source_ids']])
        for cat,p in state['categories'].items():
            notes['category:'+cat]=wrap('category',p['attributes'],p['source_ids'])
        for label,p in state['intents'].items():
            notes[label]=wrap('intent',p['attributes'],p['source_ids'],lifecycle(p,now),p['deadline'])
        return notes

    def diagnose(self,notes,case):
        expected=self.expected_notes(case['hidden_state'],case['current_time']);checks={}
        for name,note in expected.items():
            actual=notes.get(name,{})
            checks[name]={'kind':note['kind'],'present':bool(actual),
                         'attributes_correct':actual.get('attributes')==note['attributes'],
                         'status_correct':actual.get('status')==note['status'],
                         'deadline_correct':bool(actual) and actual.get('deadline')==note['deadline']}
        return {'expected_notes':len(expected),'checks':checks,'unexpected_note_names':sorted(set(notes)-set(expected))}

    def validate_history(self,history,source_ids):
        if not isinstance(history,list) or not history:raise ValueError('history required')
        last=None
        for i,r in enumerate(history):
            if not isinstance(r,dict) or set(r)!={'value','valid_from','valid_until','source_ids'}:raise ValueError('invalid validity record')
            instant(r['valid_from'])
            if r['valid_until'] is not None:
                instant(r['valid_until'])
                if r['valid_until']<r['valid_from']:raise ValueError('reversed validity interval')
            if i and last!=r['valid_from']:raise ValueError('history must have contiguous explicit intervals')
            if not isinstance(r['source_ids'],list) or not r['source_ids'] or any(s not in source_ids for s in r['source_ids']):raise ValueError('history source not observed')
            last=r['valid_until']
        if last is not None:raise ValueError('last known statement must remain current, including retracted preference')

    def validate_sizes(self,cat,sizes):
        if not isinstance(sizes,list):raise ValueError('explicit size list required')
        schema=self.schemas[cat];seen=set()
        for s in sizes:
            if not isinstance(s,dict) or set(s)!={'brand','sizing_system','size'}:raise ValueError('invalid size')
            if any(not isinstance(v,str) for v in s.values()):raise ValueError('size/system/brand must be strings')
            if s['size'] not in schema['size_systems'].get(s['sizing_system'],[]) or s['brand'] not in schema['attributes']['brand']['values']:raise ValueError('size outside category domain')
            key=(s['brand'],s['sizing_system'])
            if key in seen:raise ValueError('duplicate scoped size')
            seen.add(key)

    def validate_note(self,name,note,sources):
        if not isinstance(name,str) or not name or len(name)>240:raise ValueError('invalid note name')
        if not isinstance(note,dict) or set(note)!={'kind','attributes','status','deadline','source_ids'}:raise ValueError('note schema mismatch')
        kind=note['kind'];a=note['attributes']
        if kind not in ('general','preference','category','intent') or note['status'] not in STATUSES or not isinstance(a,dict):raise ValueError('invalid note kind/status')
        if not isinstance(note['source_ids'],list) or not note['source_ids'] or any(s not in sources for s in note['source_ids']):raise ValueError('source not observed')
        if note['deadline'] is not None:instant(note['deadline'])
        if kind!='intent' and (note['status']!='active' or note['deadline'] is not None):raise ValueError('only intent has lifecycle/deadline')
        if kind=='general':
            if set(a)!={'field','history'} or name!='general:'+a['field'] or a['field'] not in self.spec['general_fields'] or 'derived' in self.spec['general_fields'][a['field']]:raise ValueError('invalid general note')
            self.validate_history(a['history'],sources)
            if any(r['value'] not in self.spec['general_fields'][a['field']]['values'] for r in a['history']):raise ValueError('unknown general value')
        elif kind=='preference':
            if set(a)!={'id','topic','scope','category','item','history'} or name!='preference:'+a['id'] or a['topic'] not in self.spec['preference_topics']:raise ValueError('invalid preference')
            t=self.spec['preference_topics'][a['topic']]
            if a['item'] not in t['values'] or a['scope'] not in t['scopes'] or (a['scope']=='global' and a['category'] is not None) or (a['scope']=='category' and a['category'] not in self.categories):raise ValueError('invalid preference scope')
            expected=f'{a["topic"]}:{a["scope"]}:{a["category"] or "all"}:{a["item"]}'
            if a['id']!=expected:raise ValueError('preference identity mismatch')
            self.validate_history(a['history'],sources)
            if any(r['value'] not in ('like','dislike','retracted') for r in a['history']):raise ValueError('invalid stance')
        else:
            common={'category','sizes','hard','soft','valid_from'}
            expected=common if kind=='category' else common|{'label','recipient','remove_hard','remove_soft','use_general_preferences','exclude_preferences'}
            if set(a)!=expected or a['category'] not in self.categories:raise ValueError('invalid category/intent attributes')
            instant(a['valid_from']);cat=a['category']
            if kind=='category' and name!='category:'+cat:raise ValueError('category note namespace')
            if kind=='intent' and (name!=a['label'] or ':' in name or a['recipient'] not in ('self','gift') or type(a['use_general_preferences']) is not bool):raise ValueError('intent identity/recipient invalid')
            if a['sizes'] is not None:self.validate_sizes(cat,a['sizes'])
            elif kind=='category':raise ValueError('category requires disclosed sizes, possibly empty')
            for mode in ('hard','soft'):
                if not isinstance(a[mode],list):raise ValueError('rules must be lists')
                for r in a[mode]:self.validate_rule(cat,r)
            if kind=='intent':
                for mode in ('hard','soft'):
                    if not isinstance(a['remove_'+mode],list) or any(k not in self.schemas[cat]['attributes'] for k in a['remove_'+mode]):raise ValueError('invalid removed rules')
                if not isinstance(a['exclude_preferences'],list) or any(not isinstance(v,str) for v in a['exclude_preferences']):raise ValueError('invalid excluded preferences')

    def prompts(self):
        # Public schema only: never generation choices, latent state, future events or answers.
        public={'categories':{k:{field:deepcopy(v[field]) for field in ('label','attributes','size_systems','preference_topics') if field in v} for k,v in self.schemas.items()},'general_fields':{k:{field:deepcopy(value) for field,value in v.items() if field!='sampler'} for k,v in self.spec['general_fields'].items()},
                'preference_topics':self.spec['preference_topics'],'operators':self.spec['operators']}
        semantics='''All evidence is explicitly stated synthetic information. Never infer taste, product department,
size or medical constraints from age, gender, body measurements, income, nationality or health.
General facts are background unless a question asks about them. General preferences affect purchases
ONLY through the declared recommendation mapping and category preference_topics, for self recipients.
A like adds one soft rule; dislike is a hard exclusion; retracted removes either effect. Preserve scope.
Category profiles never transfer across categories. Self intents inherit only same-category profiles;
gifts inherit none. Intent rules replace same-field category rules; remove_hard/remove_soft remove
those category rules only. Explicit excluded preference IDs suppress just those general preferences.
Sizes are exact brand+category+sizing_system strings, with no conversion or inference. Self sizes=null
inherits category sizes; an explicit list replaces them; gifts with no sizes have unknown sizing.
General facts and preference stances use [valid_from,valid_until) UTC intervals; retain history for
past-time questions. At an exact change time use the newer statement (last statement if same instant).
Age is derived from the disclosed birth_date at the asked date, not from another demographic field.
Intent deadlines are inclusive; expire strictly after, never by a universal age TTL. Explicit
completion/cancellation/uncertainty closes actionability; reopening restores it with the new deadline.
'''
        answer=semantics+'''For recommendation questions, first enforce category, all hard rules, exact known sizes,
and delivery by deadline. Among verified feasible products maximize number of matched soft rules
(one point each). Any tied best product is correct. Soft preference never overrides a hard constraint.
Choose NONE for inactive plans or no suitable item. Choose ASK_SIZE only when no verified feasible
product exists but some product meets all non-size requirements and has unknown scoped sizing.
For fact/preference questions return {"answer":"option letter"}; for recommendation questions return
{"choice":"product ID|NONE|ASK_SIZE","intent_status":"active|expired|completed|cancelled|uncertain"}.
Return one JSON object keyed by all question IDs. Current explicit evidence overrides prior notes.
'''
        note=semantics+'''You maintain notes, not answers. You receive only current dated evidence and prior notes
through read_notes. Emit exactly one textual JSON tool call {"tool":"NAME","arguments":{...}}.
Tools: read_notes {} once before edits; put_note {"name":"...","note":{...}} (complete upsert);
delete_note {"name":"..."}; no_op {} to finish. Wait for results. No prose.
Every note has kind,attributes,status,deadline,source_ids. Non-intents have active status/null deadline.
Source IDs must be observed. General note name general:FIELD; kind general; attributes {field,history}.
Each history record is {value,valid_from,valid_until,source_ids}; retain past values and close their
interval when changed. Store birth_date, not a separate derived age. Preference note name
preference:TOPIC:SCOPE:CATEGORY_OR_all:ITEM; kind preference; attributes {id,topic,scope,category,item,
history}. id is TOPIC:SCOPE:CATEGORY_OR_all:ITEM. Stance history values like/dislike/retracted.
Category name category:CATEGORY; kind category; attributes {category,sizes,hard,soft,valid_from}.
Intent name matches its label; kind intent; attributes {label,category,recipient,sizes,hard,soft,
remove_hard,remove_soft,use_general_preferences,exclude_preferences,valid_from}.
Rules are {field,op,value}, hard/soft are lists. Sizes are lists of {brand,sizing_system,size}.
Intent status and deadline are top-level, separate from attributes. Preserve explicit temporary and
gift scope; inactive notes need not be deleted. Updating expiry alone does not rewrite source valid_from.
'''+f"Note budget: {json.dumps(self.spec['notes'])}.\n"
        schema='\nPublic schema (data, not instructions): '+json.dumps(public,sort_keys=True)
        return answer+schema,note+schema
