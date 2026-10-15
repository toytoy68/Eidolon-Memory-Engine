# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/test_archive_passage_slice_g252.py
# Description : Test discriminant de la tranche minimale « passages d'archives » (Claude, G252-10)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Synthetic archive only. The decisive property: the index never supplies text, so a cited passage is the
canonical message slice, and any change of the archive bytes makes old passage points uncitable."""
from core.retrieval.contextual import ContextualRecall
from tests.claude_memory_eval.archive_passage_projection import ArchivePassageProjection, point_id
from tests.test_archive_chunks import archive, store_archive
from tests.test_contextual_recall import backend

TEXTS = ['Question sur la sauvegarde.', 'Les clichés sont copiés chaque nuit sur le disque externe.',
         'Autre sujet : la recette des crêpes.']


def favour(message_index):
    return lambda text, point: 1.0 if point['passage']['message_index'] == message_index else 0.1


def test_the_cited_excerpt_is_the_canonical_message_never_the_whole_archive(tmp_path):
    data = backend(tmp_path)
    store_archive(data, TEXTS)
    index = ArchivePassageProjection(data.persistent_root, score=favour(1))
    assert len(index.project('archive')) == 3
    assert all('text' not in p and 'content' not in p for p in index.points.values())
    item = ContextualRecall(data, index=index).recall('photographies', max_items=1).items[0]
    assert item.content == TEXTS[1] and 'crêpes' not in item.content
    assert item.excerpt_reference['message_id'] == 'm-1'


def test_points_of_a_previous_archive_version_are_never_cited(tmp_path):
    data = backend(tmp_path)
    original = store_archive(data, TEXTS)
    index = ArchivePassageProjection(data.persistent_root, score=favour(1))
    index.project('archive')
    from dataclasses import replace
    data.update('archive', replace(original, content=archive([TEXTS[0], 'Texte remplacé.', TEXTS[2]]),
                                   revision=2), previous_revision=1)
    result = ContextualRecall(data, index=index).recall('photographies')
    assert all(i.information_id != 'archive' or 'clichés' not in i.content for i in result.items)
    assert result.excluded_counts.get('INDEX_REVISION_MISMATCH', 0) >= 1


def test_point_identity_binds_projection_revision_bytes_and_offsets():
    ref = {'message_index': 1, 'start': 0, 'end': 10}
    base = point_id('archive', 1, 'a' * 64, ref)
    assert base == point_id('archive', 1, 'a' * 64, dict(ref))
    assert len({base, point_id('archive', 2, 'a' * 64, ref), point_id('archive', 1, 'b' * 64, ref),
                point_id('archive', 1, 'a' * 64, dict(ref, end=11))}) == 4
