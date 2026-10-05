import json
import tempfile
from pathlib import Path
from core.sources.chatgpt_import import import_exports, plan_conversation
from core.backend.filesystem import FilesystemBackend
from core.retrieval.contextual import ContextualRecall
from core.operations.readiness import check_readiness

def conv(cid='c1', text='Ne pas acheter la V100 cette semaine.'):
    return dict(id=cid, create_time=1700000000, title='Synthetic audit', current_node='a', mapping={
        'a': dict(parent=None, message=dict(id='a', author={'role':'user'}, create_time=1700000000,
            content={'content_type':'text','parts':[text]}))})

def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file() and p.name != '.write.lock'}

with tempfile.TemporaryDirectory(prefix='eme-probe-') as tmp:
    base=Path(tmp); root=base/'corpus'
    a=base/'a.json'; b=base/'b.json'
    a.write_text(json.dumps([conv()]))
    b.write_text(json.dumps([conv('c2','Nouveau projet robot.'),conv()]))
    import_exports(root,[a]); before=snapshot(root)
    try:
        result=import_exports(root,[b])
    except Exception as exc:
        result={'error':type(exc).__name__,'reason':str(exc)}
    print('overlapping_export',json.dumps(dict(result=result,archives=len(list((root/'memory/persistent').glob('*.md'))),changed=before!=snapshot(root),ready=check_readiness(root)['ready'])))
    after=snapshot(root)
    try:
        result=import_exports(root,[b])
    except Exception as exc:
        result={'error':type(exc).__name__,'reason':str(exc)}
    print('overlapping_export_retry',json.dumps(dict(result=result,unchanged=after==snapshot(root))))
    backend=FilesystemBackend(root/'memory/persistent',root/'memory/history')
    items=ContextualRecall(backend).recall('V100').items
    print('negation_excerpt',json.dumps([dict(content=i.content,reference=i.excerpt_reference,needs_review=i.needs_review) for i in items],ensure_ascii=False))
    for label,parts in [('string','Bonjour'),('dict',{'texte':'Bonjour'})]:
        broken=conv();broken['mapping']['a']['message']['content']['parts']=parts
        try:
            memory,_=plan_conversation(broken,'hash')
            result={'imported':json.loads(memory.content)['messages'][0]['content']}
        except Exception as exc:
            result={'error':type(exc).__name__}
        print('malformed_parts_'+label,json.dumps(result))
