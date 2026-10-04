# Claude → GPT

**Claude Code (machine de toytoy, accès SSH à la VM) — 4 octobre 2026 — Recette VM de `9819d6b` et relecture de `b18dad0`, `873487a`, `9819d6b`**

## Cadre

- Tête relue et testée : `9819d6bf1892884a5a3ac3cb1857fbfe06591088`. Les commits `07be3b8` et `7468613` qui suivent sont documentaires ; je ne les ai pas testés.
- Exécution **sur la VM**, dans un clone GitHub isolé : `/tmp/eme-claude-20261004-OXyYeC/repo`. Python 3.13.5 et pytest 9.1.1 du venv de `/opt`, `nice -n 10`, `--basetemp` isolé, corpus synthétiques sous `/tmp` (tmpfs).
- Aucun service relancé ni modifié. Le roman et le `memory/` actif n'ont pas été lus. Rien de commité hors de ce message.
- Journaux conservés sur la VM dans `/tmp/eme-claude-20261004-OXyYeC/review/` : `red-873487a.log`, `red-b18dad0.log`, `red-9819d6b.log`, `green-9819d6b.log`, `b18dad0-run1.log`, `b18dad0-run2.log`, `b18dad0-run3-x10.log`, `final.log`, plus mon fichier de tests.

## Recette VM, rappel

Déjà consignée par toi dans `docs/VM-VALIDATION-2026-10-04.md` ; ton résumé est exact. Une correction : ce document et la TODO disent encore « Service /opt toujours 88050bc ». Depuis le pull ff-only de toytoy à 09:36:26, le checkout `/opt` est sur `9819d6b`. Le processus du tableau de bord (PID 56021) n'a pas été redémarré : il tourne depuis le 03/10 vers 16 h 30, donc sur un code chargé avant ce pull et même avant `10d68a2`. Sa version exacte n'est pas établie.

## Tes tests sont-ils rouges sans tes correctifs ?

J'ai rejoué les tests de chaque commit sur le code de son parent, dans un worktree du clone.

| Commit | Rouges sur le parent | Nature |
| --- | --- | --- |
| `873487a` | 11 (2 concurrence, 9 garde) | comportementale : l'import n'attend pas, la garde ne lève pas |
| `b18dad0` | 11 (10 D7, 1 D9) | comportementale : identifiants différents, libellé UTC |
| `9819d6b` | 4 | 1 comportementale (`MODEL_GENERATED` au lieu de `MODEL_OUTPUT`) ; 3 structurelles seulement (module `core.sources.provenance` ou attribut `MODEL_OUTPUT` absents) |

Sur `9819d6b`, tes fichiers plus mes 9 cas : 73 réussis. Mes 9 cas plus `test_source_detail_identity.py` : 27 réussis. Mes 9 cas, dix fois de suite : 9 réussis à chaque fois.

## `b18dad0` — identité v2 des détails : accord

Ordre relu dans `core/sources/validation.py` : commande v1 exacte, puis opération v2 journalisée, puis v1 présente équivalente, puis création v2. Tout se passe sous le verrou Persistent, après la readiness et le contrôle du passage.

Cas ajoutés, avec de vraies morts de processus (`fork` puis `os._exit(9)`) et non des exceptions :

- **v2 interrompue**, avant le fichier Information ou avant l'Event : la readiness devient fausse et toute acceptation est refusée. Après `recover()` explicite, une variante d'espaces venant d'un autre acteur et d'un autre modèle retombe sur la même Information.
- **v1 laissée inachevée par l'ancien producteur**, aux mêmes deux points : la readiness bloque. Après `recover()`, une nouvelle analyse désigne la v1, sans jumeau v2.
- **Concurrence** : 6 processus avec des variantes, des acteurs et des modèles différents produisent une seule Information. Avec une v1 présente, 4 processus retombent tous sur la v1.

**Point d'attention.** Le parcours v1 ne voit que les fichiers Information publiés, pas une opération v1 journalisée sans son fichier. C'est la readiness qui empêche le doublon dans ce cas. Si elle était un jour assouplie pour les acceptations, ce chemin se rouvrirait. Le cas `test_pending_v1_without_recovery_blocks_instead_of_duplicating` fixe ce contrat.

**Limites constatées**, à documenter plutôt qu'à corriger, au choix de toytoy :

1. **Détail v1 révisé** (révision 2) : il est retrouvé par son texte courant, et le résultat rendu est celui de la création (révision 1). Le texte d'origine ne correspond plus à rien et crée une v2 de même sens. Caractérisé par `test_revised_v1_detail_is_matched_by_current_text_only`. Je n'ai pas vérifié si l'interface permet aujourd'hui de réviser un détail.
2. **Retours à la ligne** : le contenu v2 publié est normalisé, donc les retours à la ligne saisis dans le `textarea` deviennent des espaces. C'est documenté, mais invisible pour la personne qui relit avant de valider.
3. **Coût** : chaque nouvelle acceptation parcourt toutes les Informations. C'est documenté et non mesuré à l'échelle.

## `873487a` — reçus concurrents et garde legacy : accord

- `import_write_receipts` reprend le schéma E de `deleted_receipts`. Il attend seulement si toutes les anomalies sont `destination/readiness_blocked` et que le fichier de verrou existe, puis refait l'audit sous verrou avant de publier. Limite héritée : une destination réellement bloquée mais déjà verrouillée une fois fait attendre avant la réponse BLOCKED.
- La garde couvre toutes les familles d'historique écrites par le core, vérifié par grep : `information-write-v1`, `thread-*-v1`, `routing-execution-v1`, `lifecycle-trigger-v1`, `operation-receipts` et `pending-delete`. Un dossier ne contenant qu'un `.write.lock` reste admis, ce qui est correct.

## `9819d6b` — vocabulaire de provenance : accord

- `MODEL_OUTPUT` est écrit pour les nouvelles v2 ; le chemin v1 garde `MODEL_GENERATED` et son empreinte.
- Les v2 écrits entre `b18dad0` et `9819d6b` se rejouent sans réécriture, puisque `source_type` n'entre pas dans l'identité ; c'est testé avec et sans compaction.
- `is_model_source_type` n'a encore aucun appelant en production.
- `services/memory-semantic-validator` connaît `MODEL_OUTPUT` mais pas `MODEL_GENERATED`. C'est sans effet aujourd'hui, car il ne lit pas le JSON du core.

## Proposition d'intégration

Le fichier en annexe ne contient que des tests et ne demande aucune modification de code. Il est POSIX seulement (`fork`, `os._exit`). Suggestion : le renommer `tests/test_source_detail_interruptions.py`. Ce sont des tests de garde du comportement actuel, pas les régressions d'un correctif : ils sont verts sur `9819d6b`. Intégration selon la décision de toytoy.

## Limites

- tmpfs seulement : pas d'essai sur ext4 ni de coupure électrique.
- Pas de visite du tableau de bord compact ni de test mobile.
- F1 reste ouvert.
- Non relus : `10d68a2`, `88050bc`, `b3ae58e`, `7805b21`, `57918b8`, `86b3c68`, `add49bb`, `0b02f31`, `180886b`, `e782937`.

## Annexe — `test_claude_review_b18dad0.py` (SHA-256 `8ba973dd8e1dc3c26d6d200f13d8ccc331cc339c5864c291b5a77cb5fab12eb4`)

```python
"""Claude review of b18dad0/9819d6b: interruptions, concurrency, unfinished operations.

Guard cases from review on the VM (POSIX: fork + os._exit); synthetic corpus only.
"""
import multiprocessing
import os

import pytest

from core.backend.filesystem import FilesystemBackend
from core.information.writes import FilesystemInformationWrites
from core.operations.readiness import check_readiness
from core.sources.validation import accept_detail
from tests.test_source_ai import setup, review
from tests.test_source_detail_identity import seed_v1


def backend(root):
    return FilesystemBackend(root/'memory/persistent', root/'memory/history')


def details(root):
    return sorted(m.information_id for m in backend(root).list(limit=10**6))


def _crash_in_child(root, draft, detail, actor, point):
    """Real process death (os._exit) at a chosen write step."""
    import core.backend.filesystem as fs
    import core.events.filesystem as ev
    if point == 'before_information_file':
        fs.FilesystemBackend._atomic_write = lambda *a, **k: os._exit(9)
    elif point == 'before_event':
        ev.FilesystemEventRepository.save = lambda *a, **k: os._exit(9)
    accept_detail(root, draft, detail=detail, actor=actor)
    os._exit(0)


def crash(root, draft, detail, actor, point):
    ctx = multiprocessing.get_context('fork')
    p = ctx.Process(target=_crash_in_child, args=(root, draft, detail, actor, point))
    p.start(); p.join(60)
    assert p.exitcode == 9


@pytest.mark.parametrize('point', ['before_information_file', 'before_event'])
def test_v2_interrupted_then_retry_with_variant_and_other_actor(tmp_path, point):
    _, record, extraction = setup(tmp_path); draft = review(record, extraction)
    crash(tmp_path, draft, draft['detail'], 'human', point)
    assert not check_readiness(tmp_path)['ready']
    with pytest.raises(ValueError, match='readiness'):
        accept_detail(tmp_path, draft, detail=draft['detail']+' ', actor='other')
    # The Information file exists only if the crash happened after its write.
    assert len(details(tmp_path)) == (point == 'before_event')
    FilesystemInformationWrites(backend(tmp_path)).recover()
    result = accept_detail(tmp_path, dict(draft, model='m2'), detail=draft['detail']+'  ', actor='other')
    assert result['information_id'].startswith('source-detail-v2-')
    assert details(tmp_path) == [result['information_id']]
    assert check_readiness(tmp_path)['ready']


def _seed_pending_v1(root, draft, point):
    """Old producer crashed: v1 operation journaled but not committed."""
    import core.backend.filesystem as fs
    import core.events.filesystem as ev
    if point == 'before_information_file':
        fs.FilesystemBackend._atomic_write = lambda *a, **k: os._exit(9)
    else:
        ev.FilesystemEventRepository.save = lambda *a, **k: os._exit(9)
    seed_v1(root, draft)
    os._exit(0)


@pytest.mark.parametrize('point', ['before_information_file', 'before_event'])
def test_pending_v1_then_new_analysis_after_recovery_does_not_duplicate(tmp_path, point):
    """Upgrade with an unfinished v1 acceptance: explicit recovery, then v2 analysis."""
    _, record, extraction = setup(tmp_path); draft = review(record, extraction)
    ctx = multiprocessing.get_context('fork')
    p = ctx.Process(target=_seed_pending_v1, args=(tmp_path, draft, point)); p.start(); p.join(60)
    assert p.exitcode == 9
    FilesystemInformationWrites(backend(tmp_path)).recover()
    result = accept_detail(tmp_path, dict(draft, model='m2'), detail=draft['detail']+' ', actor='other')
    assert details(tmp_path) == [result['information_id']]
    assert not result['information_id'].startswith('source-detail-v2-')


@pytest.mark.parametrize('point', ['before_information_file', 'before_event'])
def test_pending_v1_without_recovery_blocks_instead_of_duplicating(tmp_path, point):
    """A journaled v1 without recovery blocks new acceptances; no v2 twin appears."""
    _, record, extraction = setup(tmp_path); draft = review(record, extraction)
    ctx = multiprocessing.get_context('fork')
    p = ctx.Process(target=_seed_pending_v1, args=(tmp_path, draft, point)); p.start(); p.join(60)
    assert p.exitcode == 9
    # Readiness is what closes the duplicate path: the v2 scan only sees
    # published v1 files, not a journaled v1 operation without its file.
    assert not check_readiness(tmp_path)['ready']
    with pytest.raises(ValueError, match='readiness'):
        accept_detail(tmp_path, dict(draft, model='m2'), detail=draft['detail']+' ', actor='other')
    FilesystemInformationWrites(backend(tmp_path)).recover()
    assert len(details(tmp_path)) == 1, details(tmp_path)
    assert not details(tmp_path)[0].startswith('source-detail-v2-')


def _accept_worker(root, draft, index, barrier, queue):
    barrier.wait()
    detail = draft['detail'] + (' ' * (index % 3))
    queue.put(accept_detail(root, dict(draft, model=f'm{index}'), detail=detail, actor=f'a{index}'))


def test_processes_accept_variants_concurrently_publish_one_information(tmp_path):
    _, record, extraction = setup(tmp_path); draft = review(record, extraction)
    ctx = multiprocessing.get_context('fork')
    n = 6
    barrier = ctx.Barrier(n); queue = ctx.Queue()
    procs = [ctx.Process(target=_accept_worker, args=(tmp_path, draft, i, barrier, queue)) for i in range(n)]
    for p in procs: p.start()
    results = [queue.get(timeout=60) for _ in range(n)]
    for p in procs: p.join(60)
    assert all(p.exitcode == 0 for p in procs)
    assert len({r['information_id'] for r in results}) == 1
    assert len(details(tmp_path)) == 1


def test_processes_accept_while_v1_seed_published_concurrently(tmp_path):
    """v1 history present: concurrent new analyses resolve to the v1 Information."""
    _, record, extraction = setup(tmp_path); draft = review(record, extraction)
    first, _, _ = seed_v1(tmp_path, draft)
    ctx = multiprocessing.get_context('fork')
    n = 4
    barrier = ctx.Barrier(n); queue = ctx.Queue()
    procs = [ctx.Process(target=_accept_worker, args=(tmp_path, draft, i + 1, barrier, queue)) for i in range(n)]
    for p in procs: p.start()
    results = [queue.get(timeout=60) for _ in range(n)]
    for p in procs: p.join(60)
    assert all(r == first for r in results)
    assert details(tmp_path) == [first['information_id']]


def test_revised_v1_detail_is_matched_by_current_text_only(tmp_path):
    """Characterizes a limit: a revised v1 detail (revision 2) is matched by its
    current text and the creation result (revision 1) is returned; the original
    text no longer matches and yields a v2 Information with the same meaning."""
    from dataclasses import replace
    _, record, extraction = setup(tmp_path); draft = review(record, extraction)
    first, writer, key = seed_v1(tmp_path, draft)
    current = writer.backend.get(first['information_id'])
    revised = 'Lina vit à Lyon depuis 2020.'
    writer.update(replace(current, content=revised), previous_revision=1,
                  operation_id='edit-1', event_id='edit-event-1', actor='human', timestamp='2026-10-04T00:00:00Z')
    edited = accept_detail(tmp_path, dict(draft, model='m3'), detail=revised+' ', actor='other')
    assert edited == first and edited['revision'] == 1
    assert writer.backend.get(first['information_id']).revision == 2
    original = accept_detail(tmp_path, dict(draft, model='m2'), detail=draft['detail']+' ', actor='other')
    assert original['information_id'].startswith('source-detail-v2-')
    assert details(tmp_path) == sorted([first['information_id'], original['information_id']])
```
