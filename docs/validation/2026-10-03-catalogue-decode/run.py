import pathlib,sys,types,tempfile,json,time,statistics,hashlib
sys.path.insert(0,'/opt/eidolon-memory-engine')
from core.indexing.catalogue import InformationCatalogue
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
old_path=pathlib.Path('/tmp/eidolon-maintenance-comparison-20261003/before/core/indexing/catalogue.py')
module=types.ModuleType('old_catalogue'); exec(compile(old_path.read_text(),str(old_path),'exec'),module.__dict__)
result=dict(before='e49caa7',after_parent='17c644e',scope='VM tmpfs synthetic same stopped source tree; warmed complete snapshot incl readiness; 3 repetitions; no disk or Core claim',measurements=[])
original=FilesystemBackend._deserialize
for size in [100,300]:
 with tempfile.TemporaryDirectory(prefix='eidolon-catalogue-compare-') as tmp:
  root=pathlib.Path(tmp); backend=FilesystemBackend(root/'memory/persistent',root/'memory/history')
  for i in range(size):backend.store(Memory(f'synthetic-{i:04}',content='Synthetic content '*20,metadata={'keywords':['synthetic',str(i)]}))
  row=dict(records=size,variants={}); expected=None
  for name,cls in [('before',module.InformationCatalogue),('after',InformationCatalogue)]:
   samples=[]; parse_counts=[]
   for repeat in range(3):
    calls=[]
    def counted(raw):
     calls.append(1); return original(raw)
    FilesystemBackend._deserialize=staticmethod(counted)
    start=time.perf_counter()
    try:snapshot=cls(root)._snapshot()
    finally:FilesystemBackend._deserialize=staticmethod(original)
    samples.append(time.perf_counter()-start); parse_counts.append(len(calls))
    digest=hashlib.sha256(json.dumps(snapshot,sort_keys=True).encode()).hexdigest()
    if expected is None:expected=digest
    assert digest==expected
   row['variants'][name]=dict(samples_seconds=samples,median_seconds=statistics.median(samples),deserialize_calls=parse_counts,snapshot_sha256=digest)
  result['measurements'].append(row)
  print(size,row['variants'],flush=True)
pathlib.Path('/tmp/eidolon-maintenance-comparison-20261003/catalogue-comparison.json').write_text(json.dumps(result,indent=2)+'\n')
