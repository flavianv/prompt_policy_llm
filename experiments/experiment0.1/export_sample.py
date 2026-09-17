#!/usr/bin/env python3
"""Export an actual generated user/ten-session sample; no inference."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/'src'))
from prompt_policy_llm.shopping_schema import SchemaEnvironment,strict_json
from prompt_policy_llm.shopping_memory import source_hashes


def export(seed,output,environment=None,categories=None):
    spec=strict_json((environment or HERE/'environment.json').read_text())
    env=SchemaEnvironment(spec,categories);ep=env.generate_episode(seed)
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    (output/'episode.json').write_text(json.dumps(ep,indent=2,ensure_ascii=False)+'\n')
    spoken=['# One generated user: all ten sessions and questions',f'Fixed seed: {seed}. Schema: {ep["schema_version"]}.',
      'This file contains model-visible user statements and questions, with no answer key. These are templated synthetic statements, not a simulated two-speaker conversation. Catalog details are in catalogs.md. Hidden data is kept in separate files.']
    answers=['# Evaluator-only answer key','Do not provide this file to either model.']
    catalogs=['# Model-visible catalogs','Questions refer to these candidates. There are no correctness labels here.']
    for case in ep['cases']:
        index=case['session']+1;date=datetime.fromisoformat(case['current_time'].replace('Z','+00:00')).strftime('%A, %d %B %Y, %H:%M UTC')
        spoken += [f'## Session {index} — {date}']
        for e in case['evidence']:spoken += ['User: '+e['text']]
        spoken += ['### Questions']
        answers += [f'## Session {index}']
        catalogs += [f'## Session {index}']
        for number,q in enumerate(case['questions'],1):
            if q['kind']=='recommendation':
                spoken += [f'{number}. {q["request"]} Give the best product ID, NONE, or ASK_SIZE, and the intent status. See session {index}, question {q["id"]} in catalogs.md.']
                catalogs += [f'### {q["id"]} — {q["intent"]}', '```json',json.dumps(q['catalog'],indent=2),'```']
            else:
                label=q['question']
                if q['kind']=='preference':label+=f' Topic: {q["topic"]}; item: {q["item"]}; scope: {q["scope"]}; category: {q["category"]}; time: {q["at_time"]}.'
                spoken += [f'{number}. {label}']
                spoken += [f'   {key}. {json.dumps(value,ensure_ascii=False)}' for key,value in q['options'].items()]
            t=case['truth'][q['id']]
            if q['kind']=='recommendation':answers += [f'- {q["id"]}: {", ".join(t["acceptable_choices"])}; status {t["intent_status"]}; reason {t["decision_type"]}; evidence {", ".join(t["support_ids"])}.']
            else:answers += [f'- {q["id"]}: {t["answer"]} = {json.dumps(q["options"][t["answer"]],ensure_ascii=False)}; evidence {", ".join(t["support_ids"])}.']
    (output/'sessions_and_questions.md').write_text('\n\n'.join(spoken)+'\n')
    (output/'answer_key.md').write_text('\n\n'.join(answers)+'\n')
    (output/'catalogs.md').write_text('\n\n'.join(catalogs)+'\n')
    (output/'hidden_profile.md').write_text('# Hidden initial sampled user — evaluator only\n\nUnrevealed initial values are not used to grade model answers. See episode.json for per-session revealed truth and validity histories.\n\n```json\n'+json.dumps(ep['sampled_user'],indent=2,ensure_ascii=False)+'\n```\n')
    seen=set()
    for c in ep['cases']:
        seen.update(e['id'] for e in c['evidence'])
        assert all(set(t['support_ids'])<=seen for t in c['truth'].values())
    manifest={'seed':seed,'schema_version':ep['schema_version'],'sessions':len(ep['cases']),
      'questions':sum(len(c['questions']) for c in ep['cases']),'source_hashes':source_hashes(),
      'environment_sha256':hashlib.sha256(json.dumps(spec,sort_keys=True).encode()).hexdigest(),
      'selected_categories':env.categories,'inference_executed':False,'support_check':'passed',
      'files_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir()}}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--seed',type=int,default=17);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--environment',type=Path);p.add_argument('--categories');a=p.parse_args()
    print(json.dumps(export(a.seed,a.output,a.environment,a.categories.split(',') if a.categories else None),indent=2))
