"""Paired frozen-model evaluation of the JSON-defined shopping environment."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import random
import time

from .shopping_schema import (SchemaEnvironment, VERSION, SCHEMA_VERSION, STATUSES,
                              strict_json, instant, iso, lifecycle, DEFAULT_SPEC)


def generate_episode(seed,split='eval'):
    return SchemaEnvironment().generate_episode(seed,split)


def answer_payload(case,notes):
    return deepcopy({'current_time':case['current_time'],'current_session':case['evidence'],
                     'prior_session_notes':notes,'questions':case['questions']})


def note_payload(case):
    return deepcopy({'current_time':case['current_time'],'current_session':case['evidence']})


def parse_answers(text,questions):
    try:
        result=strict_json(text)
        if not isinstance(result,dict) or set(result)!={q['id'] for q in questions}:raise ValueError('question keys')
        for q in questions:
            a=result[q['id']]
            if q['kind']=='recommendation':
                if (not isinstance(a,dict) or set(a)!={'choice','intent_status'} or a['intent_status'] not in STATUSES or
                    a['choice'] not in ['NONE','ASK_SIZE',*[p['id'] for p in q['catalog']]]):raise ValueError('invalid choice')
            elif not isinstance(a,dict) or set(a)!={'answer'} or a['answer'] not in q['options']:raise ValueError('invalid option')
        return result,True
    except (ValueError,TypeError,KeyError):return {},False


def score_answer(answer,truth,question,valid,environment=None):
    env=environment or SchemaEnvironment()
    if question['kind']!='recommendation':
        return {'valid':valid,'correct':valid and answer.get('answer')==truth['answer']}
    choice=answer.get('choice');status=answer.get('intent_status')
    product=next((p for p in question['catalog'] if p['id']==choice),None)
    violations=env.violations(product,truth['effective_attributes'],truth['deadline']) if product else []
    if product and truth['intent_status']!='active':violations.append('inactive_intent')
    feasible=valid and choice in truth['feasible_choices']
    return {'valid':valid,'correct':valid and choice in truth['acceptable_choices'] and status==truth['intent_status'],
            'choice_correct':valid and choice in truth['acceptable_choices'],'status_correct':valid and status==truth['intent_status'],
            'constraint_violations':violations,'feasible_choice':feasible,
            'preference_regret':truth['best_preference_score']-truth['preference_scores'][choice] if feasible else None,
            'missed_feasible_choice':valid and choice in ('NONE','ASK_SIZE') and bool(truth['feasible_choices']),
            'sizing_decision_correct':valid and (choice=='ASK_SIZE')==(truth['acceptable_choices']==['ASK_SIZE'])}


def apply_call(raw,notes,has_read,sources,environment=None):
    env=environment or SchemaEnvironment();body=strict_json(raw)
    if not isinstance(body,dict) or set(body)!={'tool','arguments'} or not isinstance(body['arguments'],dict):raise ValueError('one tool object required')
    tool,args=body['tool'],body['arguments'];pending=deepcopy(notes)
    if tool=='read_notes':
        if args or has_read:raise ValueError('read once')
        return {'notes':deepcopy(notes)},True,False
    if not has_read:raise ValueError('read before edits/finish')
    if tool=='put_note' and set(args)=={'name','note'}:
        env.validate_note(args['name'],args['note'],sources);pending[args['name']]=deepcopy(args['note'])
    elif tool=='delete_note' and set(args)=={'name'}:
        if not isinstance(args['name'],str) or args['name'] not in pending:raise ValueError('existing note required')
        del pending[args['name']]
    elif tool=='no_op' and not args:return {'ok':True},True,True
    else:raise ValueError('unknown tool/arguments')
    limits=env.spec['notes'];serialized=json.dumps(pending)
    if len(pending)>limits['max_notes'] or len(serialized.split())>limits['max_words'] or len(serialized)>limits['max_characters']:raise ValueError('note budget')
    notes.clear();notes.update(pending)
    # Read once, then acknowledge edits without repeatedly echoing the entire growing memory.
    return {'ok':True,'name':args['name']},True,False


ERROR_RESULT={'error':'Invalid call: check schema, observed sources, read-first and budget.'}


class PromptedNotes:
    def __init__(self,generator,max_rounds=None,environment=None):
        self.environment=environment or SchemaEnvironment();self.generator=generator
        self.max_rounds=max_rounds or self.environment.spec['notes']['max_rounds']
        self.system=self.environment.prompts()[1]

    def update(self,observation,notes):
        sources={e['id'] for e in observation['current_session']}|{s for n in notes.values() for s in n['source_ids']}
        messages=[{'role':'system','content':self.system},{'role':'user','content':json.dumps(observation)}]
        rounds=[];read=done=False
        for index in range(self.max_rounds):
            try:generation=self.generator.generate(deepcopy(messages))
            except Exception as exc:return {'rounds':rounds,'finished':False,'error_type':type(exc).__name__}
            before=deepcopy(notes)
            try:result,read,done=apply_call(generation['text'],notes,read,sources,self.environment);valid=True
            except (ValueError,TypeError,KeyError):result,valid=deepcopy(ERROR_RESULT),False
            rounds.append({'round':index,'messages':deepcopy(messages),'generation':generation,'valid':valid,
                           'tool_result':result,'notes_before':before,'notes_after':deepcopy(notes)})
            messages += [{'role':'assistant','content':generation['text']},{'role':'user','content':'Tool result: '+json.dumps(result)}]
            if done:break
        return {'rounds':rounds,'finished':done}


class LiveAnswers:
    def __init__(self,model,environment=None):
        from openai import OpenAI
        self.client=OpenAI(timeout=90,max_retries=0);self.model=model
        self.system=(environment or SchemaEnvironment()).prompts()[0]

    def answer(self,payload):
        from .backend import extract_response_text,estimate_luna_cost
        start=time.perf_counter()
        response=self.client.responses.create(model=self.model,input=[{'role':'system','content':self.system},
            {'role':'user','content':json.dumps(payload)}],reasoning={'effort':'low'},max_output_tokens=1536,store=False)
        return {'text':extract_response_text(response),'status':response.status,'model':response.model,'response_id':response.id,
                'input_tokens':response.usage.input_tokens,'output_tokens':response.usage.output_tokens,
                'latency_s':time.perf_counter()-start,'estimated_cost_usd':estimate_luna_cost(response.usage.input_tokens,response.usage.output_tokens)}


class MockAnswers:
    def answer(self,payload):
        answers={q['id']:({'choice':'NONE','intent_status':'uncertain'} if q['kind']=='recommendation' else
                          {'answer':next(iter(q['options']))}) for q in payload['questions']}
        return {'text':json.dumps(answers),'status':'mock','input_tokens':0,'output_tokens':0,'latency_s':0,'estimated_cost_usd':0}


class MockGenerator:
    def generate(self,messages):
        return {'text':json.dumps({'tool':'read_notes' if len(messages)==2 else 'no_op','arguments':{}}),
                'input_tokens':0,'output_tokens':0,'latency_s':0,'hit_output_cap':False}


def source_hashes():
    return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),Path(__file__).with_name('shopping_schema.py')]}


def run(episodes,answerer,manager,output,config,mode='mock',environment=None):
    env=environment or SchemaEnvironment();output=Path(output);output.mkdir(parents=True,exist_ok=False)
    a_system,n_system=env.prompts()
    (output/'run_config.json').write_text(json.dumps({'version':VERSION,'schema_version':SCHEMA_VERSION,'mode':mode,
        'config':config,'environment':env.spec,'selected_categories':env.categories,'source_sha256':source_hashes(),
        'answer_system':a_system,'note_system':n_system,'weight_training':False},indent=2))
    def append(name,obj):
        with (output/name).open('a') as f:f.write(json.dumps(obj)+'\n')
    scores=[];traces=[];calls=[]
    for episode in episodes:
        append('evaluator_episodes.jsonl',episode);notes={}
        for case in episode['cases']:
            prior=deepcopy(notes);payloads={'baseline':answer_payload(case,{}),'memory':answer_payload(case,prior)}
            a,b=deepcopy(payloads['baseline']),deepcopy(payloads['memory']);a.pop('prior_session_notes');b.pop('prior_session_notes');assert a==b
            order=['baseline','memory'];random.Random(f"{episode['seed']}:{case['session']}").shuffle(order);parsed={}
            for arm in order:
                try:generation=answerer.answer(deepcopy(payloads[arm]))
                except Exception as exc:generation={'text':'','status':'error','error_type':type(exc).__name__}
                parsed[arm]=parse_answers(generation.get('text',''),case['questions']) if generation.get('status') in ('mock','completed') else ({},False)
                call={'user_id':episode['user_id'],'session':case['session'],'arm':arm,'payload':payloads[arm],'generation':generation}
                calls.append(call);append('answer_calls.jsonl',call)
            for q in case['questions']:
                row={'user_id':episode['user_id'],'session':case['session'],'question_id':q['id'],'truth':case['truth'][q['id']]}
                for arm,(answers,valid) in parsed.items():
                    answer=answers.get(q['id'],{});row[arm]={'answer':answer,**score_answer(answer,row['truth'],q,valid,env)}
                scores.append(row);append('scores.jsonl',row)
            observation=note_payload(case)
            trace=manager.update(deepcopy(observation),notes)
            trace.update({'user_id':episode['user_id'],'session':case['session'],'observation':observation,
                          'notes_before':prior,'notes_after':deepcopy(notes),'diagnostics':env.diagnose(notes,case)})
            traces.append(trace);append('note_traces.jsonl',trace)
    metrics=summarize(scores,traces,calls,mode)
    (output/'metrics.json').write_text(json.dumps(metrics,indent=2));return metrics


def summarize(scores,traces,calls,mode):
    def group(rows):
        out={'questions':len(rows)}
        recs=[r for r in rows if r['truth']['kind']=='recommendation']
        for arm in ('baseline','memory'):
            correct=sum(r[arm]['correct'] for r in rows);valid=sum(r[arm]['valid'] for r in rows)
            out[arm]={'correct':correct,'valid':valid,'accuracy':correct/len(rows) if rows else None,'valid_only_accuracy':correct/valid if valid else None,
              'recommendation_questions':len(recs),'choice_correct':sum(r[arm]['choice_correct'] for r in recs),
              'status_correct':sum(r[arm]['status_correct'] for r in recs),
              'constraint_violating_choices':sum(bool(r[arm]['constraint_violations']) for r in recs),
              'missed_feasible_choices':sum(r[arm]['missed_feasible_choice'] for r in recs),
              'suboptimal_feasible_choices':sum(r[arm]['feasible_choice'] and not r[arm]['choice_correct'] for r in recs),
              'preference_regret_on_feasible':sum(r[arm]['preference_regret'] or 0 for r in recs),
              'sizing_decisions_correct':sum(r[arm]['sizing_decision_correct'] for r in recs)}
        out['memory_only_wins']=sum(r['memory']['correct'] and not r['baseline']['correct'] for r in rows)
        out['baseline_only_wins']=sum(r['baseline']['correct'] and not r['memory']['correct'] for r in rows)
        return out
    rounds=[r for t in traces for r in t['rounds']]
    return {'version':VERSION,'schema_version':SCHEMA_VERSION,'mode':mode,'is_model_quality_result':mode=='live',
      'overall':group(scores),'by_kind':{k:group([r for r in scores if r['truth']['kind']==k]) for k in ('fact','preference','recommendation')},
      'by_decision_type':{k:group([r for r in scores if r['truth'].get('decision_type')==k]) for k in sorted({r['truth']['decision_type'] for r in scores if 'decision_type' in r['truth']})},
      'by_category':{k:group([r for r in scores if r['truth'].get('effective_attributes',{}).get('category')==k]) for k in sorted({r['truth']['effective_attributes']['category'] for r in scores if 'effective_attributes' in r['truth']})},
      'answer_calls':len(calls),'note_sessions':len(traces),'note_finished_sessions':sum(t['finished'] for t in traces),
      'note_tool_rounds':len(rounds),'note_invalid_rounds':sum(not r['valid'] for r in rounds),
      'note_output_cap_rounds':sum(r['generation'].get('hit_output_cap',False) for r in rounds),
      'note_diagnostics':{kind:{'expected':sum(c['kind']==kind for t in traces for c in t['diagnostics']['checks'].values()),
          **dict(Counter(k for t in traces for c in t['diagnostics']['checks'].values() if c['kind']==kind for k,v in c.items() if k!='kind' and v))}
          for kind in ('general','preference','category','intent')},
      'luna_usage':{k:sum(c['generation'].get(k,0) for c in calls) for k in ('input_tokens','output_tokens','latency_s','estimated_cost_usd')},
      'cost_note':'Mock scores are not model results. Live cost uses repository rates, excluding Qwen hardware.'}


def audit_run(output):
    output=Path(output)
    def rows(name):return [strict_json(x) for x in (output/name).read_text().splitlines()]
    manifest=strict_json((output/'run_config.json').read_text());assert manifest['source_sha256']==source_hashes(),'source hash mismatch'
    env=SchemaEnvironment(manifest['environment'],manifest['selected_categories']);assert tuple(env.prompts())==(manifest['answer_system'],manifest['note_system'])
    episodes=rows('evaluator_episodes.jsonl');assert episodes==[env.generate_episode(s,manifest['config']['split']) for s in manifest['config']['seeds']]
    calls,traces,scores=rows('answer_calls.jsonl'),rows('note_traces.jsonl'),rows('scores.jsonl');ci=ti=si=0
    for ep in episodes:
        notes={};seen={}
        for case in ep['cases']:
            seen.update({e['id']:e['timestamp'] for e in case['evidence']})
            assert all(all(s in seen and seen[s]<=case['current_time'] for s in t['support_ids']) for t in case['truth'].values())
            pair=calls[ci:ci+2];ci+=2;assert len(pair)==2 and {c['arm'] for c in pair}=={'baseline','memory'};parsed={}
            for c in pair:
                assert (c['user_id'],c['session'])==(ep['user_id'],case['session'])
                assert c['payload']==answer_payload(case,notes if c['arm']=='memory' else {})
                gen=c['generation'];parsed[c['arm']]=parse_answers(gen['text'],case['questions']) if gen['status'] in ('mock','completed') else ({},False)
            for q in case['questions']:
                row=scores[si];si+=1;assert (row['user_id'],row['session'],row['question_id'])==(ep['user_id'],case['session'],q['id'])
                assert row['truth']==case['truth'][q['id']]
                for arm,(answers,valid) in parsed.items():
                    answer=answers.get(q['id'],{});assert row[arm]=={'answer':answer,**score_answer(answer,row['truth'],q,valid,env)}
            trace=traces[ti];ti+=1;assert (trace['user_id'],trace['session'])==(ep['user_id'],case['session'])
            assert trace['observation']==note_payload(case) and trace['notes_before']==notes
            sources={e['id'] for e in case['evidence']}|{s for n in notes.values() for s in n['source_ids']};read=done=False
            messages=[{'role':'system','content':env.prompts()[1]},{'role':'user','content':json.dumps(note_payload(case))}]
            for r in trace['rounds']:
                assert not done and r['messages']==messages and r['notes_before']==notes
                try:result,read,done=apply_call(r['generation']['text'],notes,read,sources,env);valid=True
                except (ValueError,TypeError,KeyError):result,valid=deepcopy(ERROR_RESULT),False
                assert r['valid']==valid and r['tool_result']==result and r['notes_after']==notes
                messages += [{'role':'assistant','content':r['generation']['text']},{'role':'user','content':'Tool result: '+json.dumps(result)}]
            assert trace['notes_after']==notes and trace['finished']==done and trace['diagnostics']==env.diagnose(notes,case)
    assert (ci,ti,si)==(len(calls),len(traces),len(scores))
    assert strict_json((output/'metrics.json').read_text())==summarize(scores,traces,calls,manifest['mode'])
    return {'valid':True,'schema_version':SCHEMA_VERSION,'mode':manifest['mode'],'users':len(episodes),'sessions':len(traces),
            'paired_questions':len(scores),'independent_answer_calls':len(calls),'selected_categories':env.categories}


def verify_model_snapshot(model_path,manifest_path):
    manifest=strict_json(Path(manifest_path).read_text())
    for item in manifest['files']:
        path=Path(model_path)/item['path']
        if not path.is_file() or path.stat().st_size!=item['size']:raise ValueError('model file absent/size mismatch: '+item['path'])
        if item['lfs']:
            digest=hashlib.sha256()
            with path.open('rb') as stream:
                for chunk in iter(lambda:stream.read(8*1024*1024),b''):digest.update(chunk)
            expected=item['lfs']['sha256']
        else:
            data=path.read_bytes();digest=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data);expected=item['blob_id']
        if digest.hexdigest()!=expected:raise ValueError('model checksum mismatch')
    return {'repo_id':manifest['repo_id'],'revision':manifest['revision'],'verified_files':len(manifest['files'])}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--environment',type=Path);parser.add_argument('--categories',help='Comma-separated category keys selected at load')
    parser.add_argument('--real-run',action='store_true');parser.add_argument('--model-path',type=Path);parser.add_argument('--credentials',type=Path)
    args=parser.parse_args();config=strict_json(args.config.read_text())
    if args.output.exists():parser.error('choose a new output directory')
    if config['version']!=VERSION or config['schema_version']!=SCHEMA_VERSION or len(set(config['seeds']))!=len(config['seeds']):raise ValueError('invalid config')
    spec=strict_json((args.environment or args.config.parent/config['environment_file']).read_text())
    env=SchemaEnvironment(spec,args.categories.split(',') if args.categories else None)
    episodes=[env.generate_episode(s,config['split']) for s in config['seeds']]
    if args.real_run:
        if not args.model_path or not args.credentials:parser.error('live run requires model path and credentials')
        from .adaptgym_pilot import QwenNotes,load_credentials
        identity=verify_model_snapshot(args.model_path,args.config.parent/'model_manifest.json')
        if identity['revision']!=config['qwen_revision'] or identity['repo_id']!=config['qwen_model']:raise ValueError('model identity mismatch')
        if config['qwen_max_new_tokens']!=384 or config['qwen_thinking'] or config['qwen_do_sample'] or not config['qwen_fixed_weights'] or config['training']!='none':raise ValueError('frozen Qwen config mismatch')
        class BoundedQwen(QwenNotes):
            def generate(self,messages):
                prompt=self.tokenizer.apply_chat_template(messages,tokenize=False,add_generation_prompt=True,enable_thinking=False)
                if len(self.tokenizer.encode(prompt))+384>self.model.config.max_position_embeddings:raise ValueError('Qwen context budget exceeded')
                return super().generate(messages)
        load_credentials(args.credentials);generator=BoundedQwen(str(args.model_path));answerer=LiveAnswers(config['luna_model'],env)
        import torch,transformers,openai
        config['runtime']={'model_path':str(args.model_path.resolve()),'model_identity':identity,'torch':torch.__version__,
            'transformers':transformers.__version__,'openai':openai.__version__,'gpu':torch.cuda.get_device_name(0)}
    else:generator,answerer=MockGenerator(),MockAnswers()
    result=run(episodes,answerer,PromptedNotes(generator,environment=env),args.output,config,'live' if args.real_run else 'mock',env)
    print(json.dumps({k:result[k] for k in ('version','schema_version','mode','is_model_quality_result','overall','answer_calls','note_sessions')},indent=2))


if __name__=='__main__':main()
