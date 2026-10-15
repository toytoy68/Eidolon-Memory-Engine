# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_recall_guard_probes_g251.py
# Description : Contre-revue Claude G242-G251 : gardes du rappel sémantique non couvertes par les tests GPT
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Each probe kills a mutant of core/retrieval/indexed.py that survives GPT's 87 recall tests (local mutation,
file restored). Synthetic data, scripted index candidates; nothing leaves the process."""
from dataclasses import replace

from core.indexing.port import IndexHit
from core.indexing.worker_canonical import CanonicalReader
from core.sources.chatgpt_import import ARCHIVE_IMPORTERS
from tests.test_contextual_recall import backend, store
from tests.test_indexed_recall import Candidates, hit, recall


def proven_hit(data, identity, revision=1):
    _, digest = CanonicalReader(data.persistent_root)(identity)
    return IndexHit(identity, 1.0, {'revision': revision, 'policy': 'synthetic', 'canonical_sha256': digest,
                                    'index_freshness': 'UNVERIFIED_INCREMENTAL'})


def test_a_duplicated_candidate_is_returned_once(tmp_path):
    data = backend(tmp_path)
    store(data, 'one')
    result = recall(data, Candidates([hit('one'), hit('one', score=0.5)]))
    assert [i.information_id for i in result.items] == ['one']


def test_an_archive_without_a_passage_reference_is_never_cited_whole(tmp_path):
    data = backend(tmp_path)
    store(data, 'note')
    archive = store(data, 'archive', content='power measurement in a long conversation')
    importer = sorted(ARCHIVE_IMPORTERS)[0]
    data.update('archive', replace(archive, metadata={**archive.metadata, 'archive_kind': 'conversation'},
                                   provenance={**archive.provenance, 'importer': importer}, revision=2),
                previous_revision=1)
    result = recall(data, Candidates([hit('archive', revision=2), hit('note')]))
    assert [i.information_id for i in result.items] == ['note']
    assert result.excluded_counts.get('INDEX_PASSAGE_MISSING') == 1


def test_returned_content_is_the_proven_content_not_an_earlier_read(tmp_path, monkeypatch):
    """ABA between backend.get() and the proof read: get() saw other content at the same revision, the file is back
    to the proven bytes when the proof is read. The proof must cover what is returned, so the candidate is dropped."""
    data = backend(tmp_path)
    original = store(data, 'one')
    candidate = proven_hit(data, 'one')
    real_get = data.get

    def drifting_get(identity):
        memory = real_get(identity)
        return replace(memory, content='unproven text') if identity == 'one' else memory
    monkeypatch.setattr(data, 'get', drifting_get)
    result = recall(data, Candidates([candidate]))
    assert all(i.content != 'unproven text' for i in result.items)
