# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tools/check_chatgpt_recall.py
# Description : Read-only recipe for an existing ChatGPT test corpus; never print private passages.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Read-only recipe for an existing ChatGPT test corpus; never print private passages."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter

from core.backend.filesystem import FilesystemBackend
from core.operations.readiness import check_readiness
from core.retrieval.contextual import ContextualRecall
from core.retrieval.ranking import terms


def check(root):
    root=Path(root)
    if not (root/'CHATGPT-TEST-CORPUS').is_file() or not (root/'memory/persistent').is_dir():
        raise ValueError('existing isolated ChatGPT test corpus required')
    def fingerprints():
        return {p.relative_to(root).as_posix():sha256(p.read_bytes()).hexdigest()
                for p in root.rglob('*') if p.is_file() and p.name!='.write.lock'}
    before=fingerprints()
    backend=FilesystemBackend(root/'memory/persistent',root/'memory/history')
    recall=ContextualRecall(backend)
    rows=[]
    for query in ('Eidolon','roman','mémoire robot','Dans les bras','zzzztermeinexistantzzzz'):
        start=perf_counter()
        result=recall.recall(query,max_items=5,max_chars=4000,max_item_chars=800)
        elapsed=perf_counter()-start
        if len(result.items)>5 or result.used_chars>4000:
            raise ValueError('recall budget exceeded')
        coverage=[]
        for item in result.items:
            ref=item.excerpt_reference
            archive=json.loads(backend.get(item.information_id).content)
            if not ref or ref['conversation_id']!=archive['conversation_id']:
                raise ValueError('invalid conversation reference')
            message=next(m for m in archive['messages'] if m['node_id']==ref['node_id'])
            if (message['content'][ref['start']:ref['end']]!=item.content
                    or any(ref[k]!=message.get(k) for k in ('message_id','parent','role','created_at'))):
                raise ValueError('passage differs from canonical message')
            if not item.needs_review or item.epistemic_status!='UNVERIFIED':
                raise ValueError('archive epistemic reserve lost')
            wanted=set(terms(query));found=set(terms(item.content))&wanted
            if not found:
                raise ValueError('excerpt has no whole query term')
            coverage.append(f'{len(found)}/{len(wanted)}')
        if query=='zzzztermeinexistantzzzz' and result.items:
            raise ValueError('unexpected result for negative query')
        rows.append(dict(query=query,seconds=round(elapsed,3),results=len(result.items),term_coverage=coverage))
    if before!=fingerprints():
        raise ValueError('corpus changed during read-only recipe')
    if not check_readiness(root)['ready']:
        raise ValueError('corpus readiness blocked')
    return dict(status='PASS',queries=rows,unchanged=True,references_exact=True,
                semantic_relevance_evaluated=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(check(args.root),ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
