"""Verified contextual recall measurements on disposable synthetic corpora."""
import argparse
from collections import Counter
from dataclasses import asdict,replace
from hashlib import sha256
import json
from pathlib import Path
import platform
import socket
import statistics
import subprocess
import tempfile
from time import perf_counter
from unittest.mock import patch

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.dossiers.projects import ProjectDossiers
from core.information.writes import FilesystemInformationWrites
from core.operations.readiness import check_readiness
from core.retrieval.contextual import ContextualRecall
from core.threads.models import Thread
from core.threads.storage import ThreadStorage

STAMP='2026-10-03T01:00:00Z'
SCOPE={'lab':'alpha'}
SPECS={
 'a-valid':('CONFIRMED',SCOPE,{},'HIGH','MATCH',False),
 'b-review':('UNVERIFIED',SCOPE,{},'LOW','MATCH',True),
 'c-unknown':('CONFIRMED',{}, {},'INTERMEDIATE','UNKNOWN',True),
 'd-conflict':('CONFLICTED',SCOPE,{},'HIGH','UNRESOLVED',True),
 'e-expired':('CONFIRMED',SCOPE,{'valid_until':'2026-10-01T00:00:00Z'},'LOW','EXPIRED',True),
 'f-other':('CONFIRMED',{'lab':'beta'},{},'HIGH','OUT_OF_SCOPE',True),
 'g-refuted':('REFUTED',SCOPE,{},'INTERMEDIATE','MATCH',True),
 'h-superseded':('SUPERSEDED',SCOPE,{},'LOW','MATCH',True),
 'i-pending':('CONFIRMED',SCOPE,{},'HIGH','MATCH',True),
}
CURRENT={f'probe-{key}' for key in ['a-valid','b-review','c-unknown','d-conflict']}


def measured(action):
    counts=Counter();opened=Path.open
    def read(path,mode='r',*args,**kwargs):
        handle=opened(path,mode,*args,**kwargs)
        if 'r' in mode:
            category=('canonical_markdown' if 'persistent' in path.parts and path.suffix=='.md' else
                      'history_json' if 'history' in path.parts and path.suffix=='.json' else
                      'history_markdown' if 'history' in path.parts and path.suffix=='.md' else
                      'dossier' if 'dossiers' in path.parts else 'other')
            counts[category]+=1
        return handle
    started=perf_counter()
    with patch.object(Path,'open',read):result=action()
    return result,dict(seconds=round(perf_counter()-started,6),read_opens=dict(counts))


def file_hashes(root):
    return {str(path.relative_to(root)):sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob('*')) if path.is_file() and path.name!='.write.lock'}


def validate(bundle,expected,originals,*,unknown=False,budget=None,dossier=None):
    actual={item.information_id for item in bundle.items}
    if (actual!=expected if budget is None else len(actual)!=1 or not actual<=expected):
        raise RuntimeError(f'wrong contextual sources: {sorted(actual)} != {sorted(expected)}')
    if budget is not None and (bundle.used_chars>budget or bundle.used_chars!=budget):
        raise RuntimeError('excerpt character budget failed')
    if dossier is not None and bundle.dossier_status!=dossier:
        raise RuntimeError('wrong dossier freshness')
    for item in bundle.items:
        memory=originals[item.information_id];spec=SPECS[item.information_id.removeprefix('probe-')]
        applies='UNKNOWN' if unknown else spec[4]
        review=True if unknown else spec[5]
        if (item.revision!=memory.revision or not memory.content.startswith(item.content)
                or item.epistemic_status!=memory.metadata['epistemic_status']
                or item.availability!=memory.metadata['availability']
                or item.applicability!=applies or item.needs_review!=review
                or item.provenance!=memory.provenance or item.verification!=memory.verification):
            raise RuntimeError('source revision, meaning or review flag differs')
    if bundle.mode=='operational' and actual & {f'probe-{key}' for key in ['e-expired','g-refuted','h-superseded','i-pending']}:
        raise RuntimeError('ineligible source escaped operational filters')


def benchmark(size,history,repeats):
    with tempfile.TemporaryDirectory(prefix='em-recall-') as directory:
        root=Path(directory);backend=FilesystemBackend(root/'memory/persistent',root/'memory/history')
        writer=FilesystemInformationWrites(backend);originals={};commands=[]
        for key,(status,scope,temporal,level,_,_) in SPECS.items():
            memory=Memory('probe-'+key,content='probe measurement '+('value '*20),
                metadata={'epistemic_status':status,'availability':level,'keywords':['probe'],
                          'qualification':{'version':'0.1','nature':'TECHNICAL','qualified_by':'synthetic fixture'},
                          'context':{'scope':scope}},provenance={'source':'synthetic fixture'},
                verification={'evidence':{'supporting':['synthetic reference']}},temporal=temporal)
            originals[memory.information_id]=memory
        for number in range(size-len(SPECS)):
            memory=Memory(f'background-{number:05d}',content=f'ordinary calibration datum {number}',
                          metadata={'epistemic_status':'UNVERIFIED','context':{'scope':SCOPE}})
            originals[memory.information_id]=memory
        for memory in originals.values():
            commands.append(dict(kind='CREATE',memory=asdict(memory),operation_id='seed-'+memory.information_id,
                                 event_id='event-'+memory.information_id,actor='benchmark',timestamp=STAMP))
        started=perf_counter()
        for offset in range(0,size,100):
            if writer.execute_batch(commands[offset:offset+100])['status']!='COMPLETED':raise RuntimeError('seed failed')
        if history=='compact':
            ids=[command['operation_id'] for command in commands]
            for offset in range(0,size,100):
                if writer.compact_batch(ids[offset:offset+100])['status']!='COMPLETED':raise RuntimeError('seed compaction failed')
        backend.delete_request('probe-i-pending','human','Synthetic review',1,'pending')
        storage=ThreadStorage(backend.persistent_root)
        storage.create(Thread('project','Synthetic project','Fixture only',created_at=STAMP,updated_at=STAMP,
                              relations=[{'type':'CONCERNS','target_id':'probe-'+key} for key in ['a-valid','b-review','e-expired']]))
        dossiers=ProjectDossiers(backend,storage,root/'memory/dossiers');dossiers.rebuild('project')
        seed_seconds=round(perf_counter()-started,6)
        reader=ContextualRecall(backend);before=file_hashes(root);rows=[]
        cases=[
          ('operational',{},CURRENT,None,None,False),
          ('historical',{'mode':'historical'},{'probe-'+key for key in SPECS},None,None,False),
          ('high',{'availability':'HIGH'},{'probe-a-valid','probe-d-conflict'},None,None,False),
          ('project-current',{'project_id':'project'},{'probe-a-valid','probe-b-review'},None,'CURRENT',False),
          ('project-historical',{'project_id':'project','mode':'historical'},{'probe-a-valid','probe-b-review','probe-e-expired'},None,'CURRENT',False),
          ('budget',{'max_items':1,'max_chars':7,'max_item_chars':7},CURRENT,7,None,False),
          ('unknown-scope',{'query_scope':{}},CURRENT|{'probe-f-other'},None,None,True),
        ]
        def run_case(name,options,expected,budget,dossier,unknown):
            samples=[];response=None
            for _ in range(repeats):
                kwargs=dict(query_scope=SCOPE,at=STAMP,max_items=9,max_chars=3000);kwargs.update(options)
                result,sample=measured(lambda: reader.recall('probe',**kwargs))
                validate(result,expected,originals,unknown=unknown,budget=budget,dossier=dossier)
                samples.append(sample)
                response=dict(ids=[item.information_id for item in result.items],
                              review_ids=[item.information_id for item in result.items if item.needs_review],
                              used_chars=result.used_chars,excluded_counts=result.excluded_counts,dossier_status=result.dossier_status)
            return dict(case=name,median_seconds=statistics.median(sample['seconds'] for sample in samples),
                        min_seconds=min(sample['seconds'] for sample in samples),max_seconds=max(sample['seconds'] for sample in samples),
                        samples=samples,response=response,expected_verified=True)
        for case in cases:rows.append(run_case(*case))
        if file_hashes(root)!=before:raise RuntimeError('recall altered canonical/history/dossier bytes')
        original=originals['probe-a-valid'];edited=replace(original,content='probe corrected measurement '+('value '*20))
        writer.update(edited,previous_revision=1,operation_id='correction',event_id='corrected',actor='benchmark',timestamp=STAMP)
        originals['probe-a-valid']=replace(edited,revision=2);before=file_hashes(root)
        rows.append(run_case('project-stale',{'project_id':'project'},{'probe-a-valid','probe-b-review'},None,'STALE',False))
        if file_hashes(root)!=before:raise RuntimeError('stale recall silently rebuilt or altered files')
        if any(backend.get(identity)!=memory for identity,memory in originals.items()) or not check_readiness(root)['ready']:
            raise RuntimeError('final canonical or readiness verification failed')
        return dict(records=size,history=history,query_repeats=repeats,seed_seconds=seed_seconds,
                    canonical_verified=size,final_ready=True,read_only_hashes_verified=True,rows=rows)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sizes',type=int,nargs='+',default=[300,1000,3000])
    parser.add_argument('--repeats',type=int,default=3)
    parser.add_argument('--history',nargs='+',choices=['live','compact'],default=['live','compact'])
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv);sizes=sorted(set(args.sizes))
    if sizes[0]<len(SPECS) or args.repeats<1:parser.error('at least nine records and positive query repetitions required')
    sources=[[str(p),sha256(p.read_bytes()).hexdigest()] for p in sorted(Path('core').rglob('*.py'))]
    report=dict(source_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                runtime_core_sha256=sha256(json.dumps(sources,separators=(',',':')).encode()).hexdigest(),
                tool_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),python=platform.python_version(),hostname=socket.gethostname(),
                scope='synthetic warm tempfile filesystem, no real-corpus quality or physical disk latency guarantee',
                temporary_parent=tempfile.gettempdir(),instrumentation='successful file read opens, including Events; excludes setup and final semantic/hash checks',
                repetitions='same warmed corpus per query; separate new corpus for each size/history',workloads=[])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    for history in args.history:
        for size in sizes:
            print(json.dumps(dict(status='START',records=size,history=history)),flush=True)
            row=benchmark(size,history,args.repeats);report['workloads'].append(row)
            args.output.write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps(dict(records=size,history=history,verified=row['canonical_verified'],
                                  cases={case['case']:case['median_seconds'] for case in row['rows']})),flush=True)
    report['completed']=True;args.output.write_text(json.dumps(report,indent=2)+'\n')
    return 0


if __name__=='__main__':raise SystemExit(main())
