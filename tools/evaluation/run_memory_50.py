"""Read-only 50-question Memory Bridge retrieval benchmark.

Uses an explicit local test fixture, no writes to Memory Bridge. Negative cases
are *not* evidence of hallucination merely because candidates are returned.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
from time import monotonic
from urllib.request import Request, urlopen


def validate_fixture(payload):
    if payload.get('schema') != 'eidolon-eval-questions/1':
        raise ValueError('unknown fixture schema')
    cases = payload.get('cases')
    if not isinstance(cases, list) or len(cases) != 50:
        raise ValueError('exactly 50 cases required')
    if len({c['id'] for c in cases}) != 50:
        raise ValueError('duplicate case identifiers')
    if sum(c['expected_id'] is None for c in cases) != 20:
        raise ValueError('expected 20 negative cases')
    for c in cases:
        if not isinstance(c.get('query'), str) or not 1 <= len(c['query']) <= 500:
            raise ValueError('invalid query')
        if c['expected_id'] is not None and not c['expected_id'].startswith('remember-veille-ia-20261022-'):
            raise ValueError('unexpected source')
    return cases


def run(cases, *, url, token, timeout):
    rows = []
    for case in cases:
        start = monotonic()
        payload = {'query':case['query'],'mode':'operational','max_items':5,'max_chars':4000,'max_item_chars':800}
        req = Request(url, data=json.dumps(payload).encode(), headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
        try:
            with urlopen(req,timeout=timeout) as resp:
                if resp.status != 200: raise ValueError('unexpected HTTP status')
                data = json.load(resp)
            if data.get('schema') != 'eidolon-memory-recall/1':raise ValueError('wrong response schema')
            result = data['result'];items = result['items']
            if len(items)>5 or result['used_chars']>4000:raise ValueError('budget exceeded')
            ids=[item['information_id'] for item in items]
            if len(ids)!=len(set(ids)):raise ValueError('duplicate candidate')
            expected=case['expected_id']
            rank=ids.index(expected)+1 if expected in ids else None
            row={'id':case['id'],'category':case['category'],'rank':rank,'candidates':len(ids),
                 'first_score':items[0].get('score') if items else None,
                 'first_id':ids[0] if ids else None,'source_revision_valid':all(item.get('revision',0)>=1 for item in items),
                 'duration_ms':round((monotonic()-start)*1000,1)}
        except Exception as exc:
            row={'id':case['id'],'category':case['category'],'error':type(exc).__name__,'duration_ms':round((monotonic()-start)*1000,1)}
        rows.append(row)
        print(json.dumps(row,ensure_ascii=False),flush=True)
    positives=[x for x in rows if x['category']!='unknown'];negatives=[x for x in rows if x['category']=='unknown']
    durations=[x['duration_ms'] for x in rows]
    return {'schema':'eidolon-memory-50-report/1','cases':len(rows),'positive_top1':sum(x.get('rank')==1 for x in positives),
            'positive_top5':sum(x.get('rank') is not None and x['rank']<=5 for x in positives),
            'negative_with_candidates':sum(x.get('candidates',0)>0 for x in negatives),
            'errors':sum('error' in x for x in rows),'median_ms':median(durations),
            'negative_answerability_validated':False,'threshold_calibrated':False,'rows':rows}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--fixture',required=True,type=Path)
    ap.add_argument('--env-file',required=True,type=Path)
    ap.add_argument('--output',required=True,type=Path)
    ap.add_argument('--url',default='http://127.0.0.1:18765/v1/recall')
    ap.add_argument('--timeout',type=float,default=20)
    args=ap.parse_args()
    if args.url!='http://127.0.0.1:18765/v1/recall':ap.error('only local read-only recall endpoint permitted')
    cases=validate_fixture(json.loads(args.fixture.read_text()))
    values=dict(line.split('=',1) for line in args.env_file.read_text().splitlines() if '=' in line)
    token=values['EIDOLON_MEMORY_BRIDGE_TOKEN'].strip().strip('"\'')
    report=run(cases,url=args.url,token=token,timeout=args.timeout)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('SUMMARY',json.dumps({k:v for k,v in report.items() if k!='rows'}),flush=True)
    if report['errors']:raise SystemExit(2)


if __name__=='__main__':main()
