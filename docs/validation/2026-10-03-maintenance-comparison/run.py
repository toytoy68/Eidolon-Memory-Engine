import sys,json,pathlib,platform,time,hashlib
root=pathlib.Path(sys.argv[1]); sys.path.insert(0,str(root))
from tools.benchmark_maintenance import benchmark
report=dict(base=sys.argv[2],python=platform.python_version(),scope='VM Linux; synthetic disposable corpus on tmpfs; warmed instrumented reads; no physical disk or Core load claim',service_sha256=hashlib.sha256((root/'core/maintenance/service.py').read_bytes()).hexdigest(),workloads=[])
for history in ['live','compact']:
 row=benchmark(int(sys.argv[4]) if len(sys.argv)>4 else 100,5,5,3,history)
 report['workloads'].append(row)
 pathlib.Path(sys.argv[3]).write_text(json.dumps(report,indent=2)+'\n')
 print(history,'idle',row['idle']['median_seconds'],'due',row['due']['seconds'],flush=True)
