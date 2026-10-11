# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tools/benchmark_independent_recall.py
# Description : Temporary independent synthetic recall benchmark.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""No real corpus, service, or VM router is touched."""
from dataclasses import asdict
from pathlib import Path
import hashlib,json,statistics,subprocess,tempfile,time
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.retrieval.contextual import ContextualRecall

BASE=Path('docs/validation/2026-10-11')
gold=json.loads((BASE/'synthetic-gold.json').read_text())
def hashes(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file() and p.name!='.write.lock'}
rows=[]
with tempfile.TemporaryDirectory(prefix='eidolon-independent-') as directory:
    root=Path(directory); backend=FilesystemBackend(root/'memory/persistent',root/'memory/history'); originals={}
    for topic,text,_ in gold['topics']:
        for suffix,body,status,temporal in [('current',text,'CONFIRMED',{'valid_from':'2026-10-01T00:00:00Z'}),('old',f'{topic} état ancien valeur obsolète.','SUPERSEDED',{'valid_until':'2026-09-30T23:59:59Z'}),('hypothesis',f'{topic} hypothèse non validée.','UNVERIFIED',{}),('future',f'{topic} futur valeur prévue.','CONFIRMED',{'valid_from':'2027-01-01T00:00:00Z'})]:
            identity=topic+'-'+suffix
            m=Memory(identity,content=body,metadata={'epistemic_status':status,'context':{'scope':{'topic':topic}}},temporal=temporal,provenance={'source':identity+'.md','actor':'synthetic-human'},verification={'evidence':{'supporting':[identity+'-evidence']}})
            backend.store(m); originals[identity]=m
    reader=ContextualRecall(backend); before=hashes(root)
    for case in gold['questions']:
        times=[]
        for _ in range(3):
            start=time.perf_counter(); bundle=reader.recall(case['question'],query_scope=case['scope'],at=case['at'],mode=case['mode'],max_items=5);times.append((time.perf_counter()-start)*1000)
        actual=[x.information_id for x in bundle.items];expected=case['relevant_ids'];rank=next((i+1 for i,x in enumerate(actual) if x in expected),None);errors=[]
        for item in bundle.items:
            src=originals[item.information_id]
            if item.provenance!=src.provenance or item.temporal!=src.temporal or item.revision!=src.revision:errors.append('source_mismatch')
            if item.epistemic_status!=src.metadata['epistemic_status']:errors.append('status_changed')
            if item.epistemic_status!='CONFIRMED' and not item.needs_review:errors.append('unsafe_confirmation')
            if case['mode']=='operational' and item.applicability in {'EXPIRED','OUT_OF_SCOPE'}:errors.append('invalid_time_or_scope')
        rows.append(dict(**case,returned=actual,rank=rank,recall_at_5=int(rank is not None) if expected else None,reciprocal_rank=(1/rank if rank else 0) if expected else None,precision_at_5=sum(x in expected for x in actual)/len(actual) if actual else None,abstention_correct=not actual if not expected else None,safety_errors=errors,median_ms=statistics.median(times),samples_ms=times,response=asdict(bundle)))
    unchanged=before==hashes(root)
relevant=[r for r in rows if r['relevant_ids']]
report=dict(scope=gold['scope'],source_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),questions=len(rows),strategy='published lexical_v1 + ContextualRecall policy',unavailable_strategies=['VM factual v2','VM hybrid MiniLM/RRF','VM Cross-Encoder','VM context_router_v3'],canonical_unchanged=unchanged,safety_errors=sum(len(r['safety_errors']) for r in rows),recall_at_5=statistics.mean(r['recall_at_5'] for r in relevant),mrr=statistics.mean(r['reciprocal_rank'] for r in relevant),median_ms=statistics.median(r['median_ms'] for r in rows),rows=rows)
(BASE/'synthetic-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='rows'},ensure_ascii=False,indent=2))
for kind in sorted({r['kind'] for r in rows}):
    group=[r for r in rows if r['kind']==kind];print(kind, 'hits',sum(r['recall_at_5'] or 0 for r in group),'abstentions',sum(r['abstention_correct'] is True for r in group))
raise SystemExit(0 if unchanged and not report['safety_errors'] else 1)
