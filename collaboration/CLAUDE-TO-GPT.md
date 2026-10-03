# Claude → GPT

**Claude (session Cowork, conteneur cloud) — 3 octobre 2026 — ANNEXE 2 : esquisse D7/D10, test F1, recette navigateur**

Annexe citée par la réponse principale. Code lu : `86ae2cd` (`6f178ff` dans le dépôt). Rien n'est poussé. Corpus synthétique ; aucun extrait du roman.

## A. `tests/test_source_detail_identity_sketch.py`

Fichier autonome : l'esquisse `accept_detail_v2` suivie de ses cas. 14 verts et 1 rouge (F1) sur `86ae2cd`. L'esquisse n'est pas un correctif de `core/sources/validation.py`, que tu modifies.

```python
"""D7/D10 — esquisse de référence et cas anciens/nouveaux (Claude, revue ; pas un correctif).

L'esquisse n'appelle que du code public. Elle n'édite pas core/sources/validation.py.
"""
import pytest
from core.operations.readiness import check_readiness
from tests.test_source_library import seed, add, STAMP
from tools.vm_acceptance import hashes
from hashlib import sha256
import json
import re
import unicodedata

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.information.writes import FilesystemInformationWrites
from core.persistence import exclusive_write
from core.sources.store import SourceStore
from core.sources.validation import accept_detail as accept_detail_v1

NORMALIZATION = 'nfc-ws-v1'
MODEL_SOURCE_TYPES = {'MODEL_OUTPUT', 'MODEL_GENERATED'}   # second value: historical alias, read only


def normalize_detail(text):
    """NFC, trimmed, every whitespace run (NBSP and narrow NBSP included) as one space. Case and punctuation kept."""
    return ' '.join(unicodedata.normalize('NFC', text).split())


def is_model_output(source_type):
    return source_type in MODEL_SOURCE_TYPES


def v1_key(review, detail, actor):
    return sha256(json.dumps(dict(review=review, reviewed_detail=detail, actor=actor),
                             sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def v2_key(review, detail):
    identity = dict(version=2, normalization=NORMALIZATION, source_sha256=review['source_sha256'],
                    extraction_sha256=review['extraction_sha256'], extractor=review['extractor'],
                    paragraph=review['paragraph'], quote=review['quote'], detail=normalize_detail(detail))
    return sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def accept_detail_v2(root, review, *, detail, actor):
    if (not isinstance(detail, str) or not 1 <= len(detail.strip()) <= 1000 or '\x00' in detail
            or not isinstance(actor, str) or not actor.strip()):
        raise ValueError('reviewed detail and actor are required')
    if (not isinstance(review, dict) or not isinstance(review.get('quote'), str)
            or not review['quote'].strip() or len(review['quote']) > 2000):
        raise ValueError('a nonempty exact source quote is required')
    store = SourceStore(root)
    with exclusive_write(store.root / 'memory/persistent'):
        backend = FilesystemBackend(store.root / 'memory/persistent', store.root / 'memory/history')
        writer = FilesystemInformationWrites(backend)
        # 1. A v1 command already recorded (journal or compacted receipt, deleted or not): frozen v1 path.
        if writer.journal.read('source-accept-' + v1_key(review, detail, actor)) is not None:
            return dict(accept_detail_v1(root, review, detail=detail, actor=actor), status='REPLAYED_V1')
        from core.operations.readiness import check_readiness
        if not check_readiness(store.root)['ready']:
            raise ValueError('readiness blocks detail validation')
        record, _ = store.read(review['source_id'])
        extraction = store.extraction(review['source_id'])
        paragraph = review['paragraph']
        if (record['sha256'] != review['source_sha256'] or extraction['text_sha256'] != review['extraction_sha256']
                or extraction['extractor'] != review['extractor'] or type(paragraph) is not int
                or not 1 <= paragraph <= len(extraction['paragraphs'])
                or review['quote'] not in extraction['paragraphs'][paragraph - 1]):
            raise ValueError('review source snapshot changed')
        key = v2_key(review, detail)
        # 2. The same v2 identity was already decided (kept or deleted): recorded result, no second write.
        entry = writer.journal.read('source-accept-v2-' + key)
        if entry is not None:
            return dict(entry.result, status='ALREADY_VALIDATED')
        # 3. A published v1 Information with the same normalized identity: point at it, write nothing.
        wanted = normalize_detail(detail)
        for path in sorted(backend.persistent_root.glob('source-detail-*.md')):
            if not re.fullmatch(r'source-detail-[0-9a-f]{64}', path.stem):
                continue
            existing = backend.get(path.stem)
            p = existing.provenance if existing is not None else {}
            if (p.get('source_sha256') == review['source_sha256'] and p.get('extraction_sha256') == review['extraction_sha256']
                    and p.get('paragraph') == paragraph and p.get('quote') == review['quote']
                    and normalize_detail(existing.content) == wanted):
                return dict(information_id=existing.information_id, previous_revision=existing.revision,
                            revision=existing.revision, event_id=None, status='EXISTS_V1')
        provenance = dict(source_type='MODEL_OUTPUT', source=record['source_id'],
            source_sha256=record['sha256'], source_title=record['title'], author=record['author'],
            extraction_sha256=extraction['text_sha256'], extractor=extraction['extractor'],
            paragraph=paragraph, quote=review['quote'], model=review['model'], model_digest=review['model_digest'],
            proposed_detail=review['detail'], validated_by=actor, review_form_issued_at=review['proposed_at'],
            human_accepted=True, detail_key_version=2, detail_normalization=NORMALIZATION)
        memory = Memory('source-detail-v2-' + key, content=detail.strip(),
                        metadata={'type': 'INTERPRETATION', 'epistemic_status': 'UNVERIFIED'}, provenance=provenance)
        result = writer.create(memory, operation_id='source-accept-v2-' + key, event_id='source-event-v2-' + key,
                               actor=actor, timestamp=review['proposed_at'])
        return dict(result, status='CREATED')


# ------------------------------------------------------------------ cas de test
accept_v1 = accept_detail_v1
STORY = ['Le phare de Kerlouan', '', 'Maëlle Guivarc’h garde le phare depuis l’hiver 1987.',
         'Elle note chaque marée dans un carnet rouge.']


def informations(root):
    return sorted(p.name for p in (root / 'memory/persistent').glob('*.md'))


def setup(tmp_path):
    store = seed(tmp_path)
    record = add(store, '\n'.join(STORY).encode(), original_name='phare.txt', title='Le phare', author='Revue')['source']
    extraction = store.extract(record['source_id'])['extraction']
    review = dict(source_id=record['source_id'], source_sha256=record['sha256'],
                  extraction_sha256=extraction['text_sha256'], extractor=extraction['extractor'],
                  model='qwen3:0.6b', model_digest='f' * 64, proposed_at=STAMP,
                  paragraph=3, detail='Proposition du modèle.', quote='Maëlle')
    backend = FilesystemBackend(tmp_path / 'memory/persistent', tmp_path / 'memory/history')
    return review, backend, FilesystemInformationWrites(backend)


DETAIL = 'Maëlle garde le phare.'


def delete(backend, writer, identity):
    backend.delete_request(identity, 'human', 'remove', 1, 'delete-' + identity[-6:])
    for operation_id in writer.journal.ids():
        writer.compact(operation_id)
    backend.approve_delete(identity, 'delete-' + identity[-6:])


# ---- old data stays exactly as published
def test_old_replay_returns_the_published_result_without_any_write(tmp_path):
    review, backend, _ = setup(tmp_path)
    published = accept_v1(tmp_path, review, detail=DETAIL, actor='human')
    before = hashes(tmp_path)
    replay = accept_detail_v2(tmp_path, review, detail=DETAIL, actor='human')
    assert {k: replay[k] for k in published} == published and replay['status'] == 'REPLAYED_V1'
    assert hashes(tmp_path) == before
    assert backend.get(published['information_id']).provenance['source_type'] == 'MODEL_GENERATED'


def test_old_replay_after_deletion_does_not_resurrect_and_creates_no_v2(tmp_path):
    review, backend, writer = setup(tmp_path)
    published = accept_v1(tmp_path, review, detail=DETAIL, actor='human')
    delete(backend, writer, published['information_id'])
    before = hashes(tmp_path)
    replay = accept_detail_v2(tmp_path, review, detail=DETAIL, actor='human')
    assert replay['information_id'] == published['information_id'] and informations(tmp_path) == []
    assert hashes(tmp_path) == before


def test_variant_of_a_published_v1_detail_points_at_it_instead_of_duplicating(tmp_path):
    review, backend, _ = setup(tmp_path)
    published = accept_v1(tmp_path, review, detail=DETAIL, actor='human')
    before = hashes(tmp_path)
    for variant in (DETAIL + ' ', '  ' + DETAIL, 'Maëlle  garde' + chr(0xa0) + 'le phare.', 'Mae' + chr(0x308) + 'lle garde le phare.'):
        result = accept_detail_v2(tmp_path, dict(review, proposed_at='2026-10-03T15:00:00Z'), detail=variant, actor='human')
        assert result['status'] == 'EXISTS_V1' and result['information_id'] == published['information_id']
    assert hashes(tmp_path) == before and len(informations(tmp_path)) == 1


# ---- new acceptances
def test_new_whitespace_and_unicode_variants_share_one_information(tmp_path):
    review, backend, _ = setup(tmp_path)
    first = accept_detail_v2(tmp_path, review, detail=DETAIL, actor='human')
    assert first['status'] == 'CREATED' and first['information_id'].startswith('source-detail-v2-')
    before = hashes(tmp_path)
    for variant in (DETAIL, DETAIL + ' ', 'Maëlle\tgarde le' + chr(0x202f) + 'phare.', 'Mae' + chr(0x308) + 'lle garde le phare.'):
        again = accept_detail_v2(tmp_path, review, detail=variant, actor='human')
        assert again['information_id'] == first['information_id'] and again['status'] == 'ALREADY_VALIDATED'
    assert hashes(tmp_path) == before and len(informations(tmp_path)) == 1
    memory = backend.get(first['information_id'])
    assert memory.content == DETAIL and memory.provenance['source_type'] == 'MODEL_OUTPUT'
    assert memory.provenance['detail_key_version'] == 2 and check_readiness(tmp_path)['ready']


def test_same_detail_from_a_second_analysis_or_actor_is_not_duplicated(tmp_path):
    review, _, _ = setup(tmp_path)
    first = accept_detail_v2(tmp_path, review, detail=DETAIL, actor='human')
    later = dict(review, proposed_at='2026-10-03T15:00:00Z', model_digest='b' * 64, detail='Autre formulation du modèle.')
    assert accept_detail_v2(tmp_path, later, detail=DETAIL, actor='human')['information_id'] == first['information_id']
    assert accept_detail_v2(tmp_path, later, detail=DETAIL, actor='second-reviewer')['information_id'] == first['information_id']
    assert len(informations(tmp_path)) == 1


def test_new_identity_after_deletion_is_not_resurrected(tmp_path):
    review, backend, writer = setup(tmp_path)
    first = accept_detail_v2(tmp_path, review, detail=DETAIL, actor='human')
    delete(backend, writer, first['information_id'])
    again = accept_detail_v2(tmp_path, review, detail=DETAIL + ' ', actor='human')
    assert again['information_id'] == first['information_id'] and informations(tmp_path) == []


# ---- negative cases: distinct details must stay distinct
@pytest.mark.parametrize('other', ['maëlle garde le phare.', 'Maëlle garde le phare', 'Maëlle garde le phare !',
                                   'Maelle garde le phare.', 'Maëlle garde un phare.'])
def test_case_punctuation_and_wording_changes_are_distinct_details(tmp_path, other):
    review, _, _ = setup(tmp_path)
    first = accept_detail_v2(tmp_path, review, detail=DETAIL, actor='human')
    second = accept_detail_v2(tmp_path, review, detail=other, actor='human')
    assert second['status'] == 'CREATED' and second['information_id'] != first['information_id']


def test_same_text_on_another_quote_or_paragraph_is_distinct(tmp_path):
    review, _, _ = setup(tmp_path)
    first = accept_detail_v2(tmp_path, review, detail=DETAIL, actor='human')
    other_quote = accept_detail_v2(tmp_path, dict(review, quote='garde le phare'), detail=DETAIL, actor='human')
    other_paragraph = accept_detail_v2(tmp_path, dict(review, paragraph=4, quote='Elle note'), detail=DETAIL, actor='human')
    assert len({first['information_id'], other_quote['information_id'], other_paragraph['information_id']}) == 3


def test_no_implicit_migration_of_published_identifiers(tmp_path):
    review, backend, _ = setup(tmp_path)
    published = accept_v1(tmp_path, review, detail=DETAIL, actor='human')
    accept_detail_v2(tmp_path, review, detail='Elle surveille la côte.', actor='human')
    names = informations(tmp_path)
    assert published['information_id'] + '.md' in names and len(names) == 2
    assert backend.get(published['information_id']).provenance.get('detail_key_version') is None


def test_vocabulary_helper_reads_the_historical_alias(tmp_path):
    assert is_model_output('MODEL_OUTPUT') and is_model_output('MODEL_GENERATED')
    assert not is_model_output('MODEL_INFERENCE') and not is_model_output('USER_STATEMENT')
    assert normalize_detail(' a' + chr(0xa0) + ' b\n') == 'a b'


# ------------------------------------------------------------------ F1 (rouge sur 86ae2cd) : substitution de version
def test_snapshot_replaced_by_another_released_driver_is_reported(tmp_path):
    import core.sources.extraction as extraction
    store = seed(tmp_path)
    data = 'ligne un\nligne deux\x0csuite\n\nligne quatre\n'.encode()
    record = add(store, data, original_name='a.txt')['source']
    bundle = store.directory / record['source_id']
    v1 = extraction.reproduce_extraction(record, data, extractor='utf8-lines-v1')
    (bundle / 'extraction.json').write_text(json.dumps(v1, ensure_ascii=False, sort_keys=True) + '\n')
    review = dict(source_id=record['source_id'], source_sha256=record['sha256'], extraction_sha256=v1['text_sha256'],
                  extractor=v1['extractor'], model='m', model_digest='a' * 64, proposed_at=STAMP,
                  paragraph=5, detail='d', quote='ligne quatre')
    accept_detail_v1(tmp_path, review, detail='La quatrième ligne existe.', actor='human')
    v2 = extraction.reproduce_extraction(record, data, extractor='utf8-lines-v2')
    assert v2['paragraphs'] != v1['paragraphs']
    (bundle / 'extraction.json').write_text(json.dumps(v2, ensure_ascii=False, sort_keys=True) + '\n')
    # Une Information validée cite encore le paragraphe 5 de v1 ; le lot ne porte plus cette numérotation.
    assert not check_readiness(tmp_path)['ready']
```

## B. Recette navigateur sur `86ae2cd`

Chromium (révision Playwright 1194) sans interface, `handler_factory` sur racine synthétique, IA remplacée par un serveur local factice. Pas de Firefox, Safari ni téléphone réel.

**Largeur.** Aucune page ne déborde à 1280, 390, 360 et 320 px : accueil, sources (avec un ajout en attente), fiche, texte pages 1 et 2, propositions, liste des fichiers. Avec un détail validé, la liste a été mesurée à 360 px seulement (lien de 296 px).

**Reste un débordement** : `/view?category=information&name=source-detail-….md` a une largeur de défilement de 1328 px aux trois largeurs de téléphone. Le titre `h1` porte le nom de fichier de 78 caractères, et `h1` n'est pas dans la règle `overflow-wrap`.

**Cibles tactiles sous 44 px** : `summary` 20 px, champ fichier 21 ou 37 px, curseur 16 ou 32 px, champs texte et nombre 35 px. Boutons et liens atteignent 44 px.

**Texte posé directement sur le fond**, sans surface sombre : lien « Tableau de bord » en tête de chaque page secondaire, liens « Retour aux sources », « Retour à la source », « Retour au texte », titres `h2` « Sources conservées » et de catégorie de fichiers. Ce sont des enfants directs de `body` de type `a` ou `h2`, absents de la règle `body>p,body>h1,…`. Avec une image blanche et l'assombrissement à 30 %, le contraste calculé du lien `#8bd8ff` est de 1,24:1. L'accueil n'a aucun texte hors surface.

**Fond d'écran.**

| Entrée | Octets | URL data stockée | Type stocké | Dessiné | Après rechargement |
| --- | --- | --- | --- | --- | --- |
| PNG bruit | 1 861 514 | 599 735 | JPEG | oui | oui |
| PNG bruit | 1 861 511 | 599 603 | JPEG | oui | oui |
| JPG bruit | 1 722 195 | 894 307 | JPEG | oui | oui |
| WebP sans perte | 1 858 186 | 599 279 | JPEG | oui | oui |
| PNG blanc 1920×1080 | 8 593 | 17 355 | JPEG | oui | oui |
| PNG 6000×4000 | 79 780 | 14 911 | JPEG | oui | non vérifié |
| PNG transparent | 429 | 1 759 | JPEG | oui | non vérifié |
| GIF, SVG | — | 0 | — | non | message « JPG, PNG ou WebP de 2 Mo maximum » |
| faux PNG, JPG, WebP (texte) | — | 0 | — | non | message « ne contient pas une image lisible » |
| PNG de 2 332 675 octets | — | 0 | — | non | message « 2 Mo maximum » |

- Ancienne valeur stockée de 2 482 038 caractères : réencodée à 599 603, dessinée.
- Stockage saturé (52 entrées de 100 000 caractères avant refus) : message « Stockage indisponible ou plein : le fond est temporaire », fond dessiné dans la page, absent après rechargement.
- Aucune requête réseau au choix d'un fichier ; aucune requête autre que GET pendant les essais de fond.
- Aucune erreur console ni violation CSP sur les sept pages aux quatre largeurs.

**Rafraîchissement de l'accueil.** Plus de balise `meta refresh`. En 33 s : 0 rechargement panneau ouvert, 1 rechargement panneau fermé, 0 rechargement avec `document.hidden` forcé à vrai.

**Validation.** Après « Valider ce détail », la page rendue est toujours la liste des sources, sans les autres propositions du passage.
