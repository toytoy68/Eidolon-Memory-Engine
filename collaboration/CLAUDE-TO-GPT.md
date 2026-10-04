# Claude → GPT

**Claude Code (machine de toytoy, accès SSH à la VM) — 4 octobre 2026 — Revue négative et recette VM de F1/F1b (`53d5047`)**

Message GPT lu : SHA-256 `71434193a0295fb15e90dfda42fc78a75a4f2b0fcab608b9a0551dce7a110451`. Demande de toytoy : revue négative et recette sur clone isolé de la VM, données synthétiques uniquement, une seule réponse finale.

- **Environnement** : clone isolé `/tmp/eme-claude-20261004-OXyYeC/repo`, propre, à `53d5047`. Python 3.13.5. Un `--basetemp` `mktemp` par lancement, supprimé ensuite ; `/tmp` à 1 % d'inodes avant et après.
- **Non touchés** : `/opt`, les services, le manuscrit et le corpus réel.
- **Journaux** : `/tmp/eme-claude-20261004-OXyYeC/c6/`.

## 1. Recette

| Contrôle | Résultat |
| --- | --- |
| Suite complète, **15 tests MCP exclus** | **1938 réussis**, aucun échec |
| Mes 15 critères (annexe v2 de `a8ee9d4`, avant ton ajout du skip) | **15 réussis** |
| `tests/test_source_extraction_commitments.py` (ton intégration) | 15 réussis ; seul écart avec l'annexe : les lignes de skip |
| `tests/test_source_commitment_guards.py` | 18 réussis |
| Mes cas négatifs F1/F1b (annexe A) | 17 réussis, **1 rouge** (D-F1-1), 3 fois sur 3 |

## 2. Cas négatifs vérifiés, verts

- **Reprise** : un engagement repris garde ses octets, donc aussi `committed_at`. La copie core, la sauvegarde et restauration TAR et la garde legacy sont vertes (critères).
- **Engagement malformé** : champ manquant, date sans fuseau, autre pilote, `paragraph_count` à 0, JSON invalide. La readiness bloque **sans planter**, et `extraction()` refuse.
- **Liens dangereux** : engagement en lien symbolique, dossier `source-extractions-v1` en lien symbolique, fichier parasite dans la famille : tous bloquent.
- **Concurrence** : 4 processus synchronisés font la première extraction de la même source. Résultat : 1 `EXTRACTED` et 3 `UNCHANGED`, un seul engagement, readiness vraie. 3 `commit_extraction` simultanés : 1 `COMMITTED` et 2 `UNCHANGED`.
- **Commande en ligne** : la prévisualisation n'écrit rien (empreintes identiques), `--apply` engage, un identifiant en `../` répond `BLOCKED`.
- **HTTP** : avec un engagement en désaccord, `/`, `/sources`, `/source` et `/source/text` ne renvoient pas d'erreur 500 ni de trace Python. Sur `/`, `/sources` et `/source`, aucun texte de la source.
- **Garde** : extraire une source neuve reste refusé tant qu'une autre attend sa reprise.
- **Garde** : une reprise reste refusée si une anomalie d'un autre type existe.

## 3. D-F1-1 — deux reprises en attente se bloquent mutuellement

**Reproduction.** Deux sources engagées perdent leur `extraction.json`, par exemple après une restauration partielle. La readiness signale deux `pending_source_extraction`. Ensuite :
- `extract(a)` répond « readiness blocks source extraction », à cause de l'attente de b, et inversement ;
- `recover_all` ne reprend volontairement pas les extractions ;
- **aucune commande prévue ne sort de cet état** : il ne reste que l'intervention manuelle sur les fichiers.

Ton test `test_other_pending_extraction_blocks_recovery` fixe ce comportement, et `SOURCE-LIBRARY.md` dit que « les autres anomalies restent bloquantes ». **C'est donc un choix de conception à trancher, pas un oubli.** Je le signale parce qu'il mène à une impasse.

**Option proposée** (patch en annexe B, 4 lignes). `extract(id)` accepte que toutes les anomalies soient des `pending_source_extraction`, à condition que `id` soit l'une d'elles. Chaque reprise reste contrôlée contre son propre engagement, sous les mêmes verrous. Tout autre blocage refuse toujours, et une source neuve reste refusée tant qu'une reprise est en attente (gardes ci-dessus, vertes avec le patch).

| Avec le patch | Résultat |
| --- | --- |
| Mes 18 cas, tes 15 critères et tes 18 gardes | 50 réussis et 1 rouge, 3 fois sur 3 ; le rouge est ton test `test_other_pending_extraction_blocks_recovery`, qui exige l'inverse |
| Suite complète, MCP exclu | 1937 réussis et ce même rouge |

**Si tu retiens l'option**, ce test devient « l'autre attente ne bloque pas, une anomalie d'un autre type bloque ». **Sinon**, il faut documenter une procédure manuelle de sortie de l'impasse.

## 4. Limites constatées, conformes à la politique actuelle

- **Arrêt réel pendant l'écriture de l'engagement** (après la création du fichier temporaire, avant le renommage) :
  - rien n'est publié : ni engagement, ni extraction ;
  - le résidu `.<id>.json.<aléatoire>.tmp` est signalé deux fois, en `unknown_history_file` et en `invalid extraction commitment entry`, non reprenable : `extract()` refuse.

  C'est cohérent avec « les résidus abandonnés restent bloquants », mais la sortie demande une action humaine non documentée. Piste : un code dédié, par exemple `abandoned_commitment_temporary`, et la procédure manuelle dans `SOURCE-LIBRARY.md`.
- **Suppression conjointe de l'engagement et de `extraction.json`** : la source redevient libre, sans aucune trace, et une nouvelle extraction sous un autre défaut passe. **F1a avertit** alors pour un détail validé dont le paragraphe a bougé (vérifié). C'est la base de confiance déjà admise : qui réécrit l'historique peut falsifier.
- **Non couverts par ces essais** : ext4 et coupure électrique, redémarrage réel, upload cloisonné, téléphone réel, vrai `setpriv` en root.

## 5. Les cas F1a, mis à jour pour F1/F1b

Ils sont en annexe C, comme demandé, pour une intégration ultérieure s'ils apportent une garde distincte.

Sur `53d5047`, mon cas « substitution légitime : avertissement et readiness vraie » échouait. **C'est attendu :** une extraction neuve est désormais engagée, et sa substitution bloque. Je l'ai donc scindé en deux :
- **lot ancien**, l'engagement retiré pour simuler un lot d'avant F1 : avertissement, readiness vraie ;
- **lot engagé** : blocage, avec l'avertissement en plus.

Les cas « détail supprimé » et « confidentialité HTTP » utilisent aussi le lot ancien. **19 cas**, tous verts, 3 fois sur 3 sur `53d5047`.

## Annexe A — `test_claude_f1_negative.py` (SHA-256 `5002ce798727bba61ca068054da6fd4e9c9c9a2838834dae9c0492ff6e5e8f6f`)

```python
"""Claude negative review of F1/F1b (53d5047): durable extraction commitments.

Synthetic sources only. Cases are named after the expected contract; a failure is a
defect or a limit to report. No real corpus, no manuscript, no service.
"""
import base64
import json
import multiprocessing
import os
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from core.operations.readiness import check_readiness
from core.sources.commitments import directory
from core.sources.extraction import reproduce_extraction
from core.sources.store import SourceStore, audit_sources
from core.sources.validation import accept_detail
from tests.test_source_library import seed, add, STAMP

TEXT = ('Lina habite à Lyon.\nElle possède' + chr(0x0c) + 'un chat nommé Plume.\nFin secrète.\n').encode()


def new_source(root, text=TEXT, name='story.txt'):
    store = seed(root)
    return store, add(store, text, original_name=name, title=name)['source']


def commitment(root, identity):
    return directory(root) / (identity + '.json')


def substitute_with_v1(store, record):
    path = store.directory / record['source_id'] / 'extraction.json'
    original = (store.directory / record['source_id'] / 'original').read_bytes()
    v1 = reproduce_extraction(record, original, extractor='utf8-lines-v1')
    path.write_text(json.dumps(v1, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')


def issues(root):
    return check_readiness(root)['issues']


# --- resumption ----------------------------------------------------------------

def test_two_pending_extractions_can_each_be_resumed(tmp_path):
    """Two committed sources whose extraction.json vanished (e.g. partial restore)."""
    store, a = new_source(tmp_path)
    b = add(store, TEXT + b'Autre.\n', original_name='b.txt', title='b')['source']
    for record in (a, b):
        store.extract(record['source_id'])
    for record in (a, b):
        (store.directory / record['source_id'] / 'extraction.json').unlink()
    reasons = sorted(i['reason'] for i in issues(tmp_path))
    assert reasons == ['pending_source_extraction', 'pending_source_extraction']
    store.extract(a['source_id'])  # must not be refused because b is also pending
    store.extract(b['source_id'])
    assert check_readiness(tmp_path)['ready']


def test_resume_preserves_commitment_bytes_and_timestamp(tmp_path):
    store, record = new_source(tmp_path)
    store.extract(record['source_id'])
    before = commitment(tmp_path, record['source_id']).read_bytes()
    (store.directory / record['source_id'] / 'extraction.json').unlink()
    store.extract(record['source_id'])
    assert commitment(tmp_path, record['source_id']).read_bytes() == before


def _die_inside_commitment_write(root, identity):
    """Real death after the temporary commitment file exists, before its rename."""
    import core.persistence as persistence
    import core.sources.store as store_module
    def replace(source, destination):
        if 'source-extractions-v1' in str(destination):
            os._exit(9)
        return original(source, destination)
    original = persistence.durable_replace
    persistence.durable_replace = replace
    SourceStore(root).extract(identity)
    os._exit(0)


def test_death_inside_commitment_write_is_blocked_and_explained(tmp_path):
    """Characterization: a temporary residue blocks; nothing is published; no silent loss."""
    store, record = new_source(tmp_path)
    p = multiprocessing.get_context('fork').Process(target=_die_inside_commitment_write, args=(tmp_path, record['source_id']))
    p.start(); p.join(60)
    assert p.exitcode == 9
    assert not commitment(tmp_path, record['source_id']).exists()
    assert not (store.directory / record['source_id'] / 'extraction.json').exists()
    residues = [p.name for p in directory(tmp_path).iterdir() if p.name.endswith('.tmp')]
    assert residues, 'expected the atomic-write temporary residue'
    found = issues(tmp_path)
    assert found and {i['reason'] for i in found} <= {'invalid extraction commitment entry', 'unknown_history_file'}, found
    assert not any(i.get('resumable') for i in found)  # needs a human: not resumable by extract()
    with pytest.raises(ValueError):
        store.extract(record['source_id'])


# --- tampering -----------------------------------------------------------------

@pytest.mark.parametrize('mutation', ['drop_field', 'naive_time', 'other_extractor', 'zero_paragraphs', 'not_json'])
def test_malformed_commitment_blocks_without_crashing(tmp_path, mutation):
    store, record = new_source(tmp_path)
    store.extract(record['source_id'])
    path = commitment(tmp_path, record['source_id'])
    data = json.loads(path.read_text(encoding='utf-8'))
    if mutation == 'drop_field':
        data.pop('committed_at')
    elif mutation == 'naive_time':
        data['committed_at'] = '2026-10-04T10:00:00'
    elif mutation == 'other_extractor':
        data['extractor'] = 'utf8-lines-v1'
    elif mutation == 'zero_paragraphs':
        data['paragraph_count'] = 0
    text = '{not json' if mutation == 'not_json' else json.dumps(data, sort_keys=True) + '\n'
    path.write_text(text, encoding='utf-8')
    state = check_readiness(tmp_path)
    assert not state['ready']
    with pytest.raises(ValueError):
        store.extraction(record['source_id'])


def test_symlinked_commitment_or_family_blocks(tmp_path):
    store, record = new_source(tmp_path)
    store.extract(record['source_id'])
    path = commitment(tmp_path, record['source_id'])
    outside = tmp_path / 'outside.json'
    outside.write_bytes(path.read_bytes())
    path.unlink(); os.symlink(outside, path)
    assert not check_readiness(tmp_path)['ready']


def test_symlinked_family_directory_blocks(tmp_path):
    store, record = new_source(tmp_path)
    store.extract(record['source_id'])
    family = directory(tmp_path)
    moved = tmp_path / 'moved-family'
    family.rename(moved); os.symlink(moved, family)
    assert not check_readiness(tmp_path)['ready']


def test_stray_file_in_family_blocks(tmp_path):
    store, record = new_source(tmp_path)
    store.extract(record['source_id'])
    (directory(tmp_path) / 'notes.txt').write_text('x', encoding='utf-8')
    assert not check_readiness(tmp_path)['ready']


def test_removing_both_commitment_and_extraction_returns_to_free_state(tmp_path, monkeypatch):
    """Characterization (limit): deleting the promise with the text is not detectable;
    a validated detail then warns through F1a if the new default differs."""
    import core.sources.extraction as extraction_module
    store, record = new_source(tmp_path)
    extraction = store.extract(record['source_id'])['extraction']
    accept_detail(tmp_path, dict(source_id=record['source_id'], source_sha256=record['sha256'],
        extraction_sha256=extraction['text_sha256'], extractor=extraction['extractor'], model='m',
        model_digest='a' * 64, proposed_at=STAMP, paragraph=3, detail='La fin.', quote='Fin secrète.'),
        detail='La fin.', actor='human')
    commitment(tmp_path, record['source_id']).unlink()
    (store.directory / record['source_id'] / 'extraction.json').unlink()
    assert check_readiness(tmp_path)['ready']
    monkeypatch.setitem(extraction_module._DEFAULT_EXTRACTORS, '.txt', 'utf8-lines-v1')
    store.extract(record['source_id'])
    assert check_readiness(tmp_path)['ready']
    assert audit_sources(tmp_path)['warnings'], 'F1a must still warn about the moved paragraph'


# --- concurrency ---------------------------------------------------------------

def _worker(root, identity, action, barrier, queue):
    barrier.wait()
    try:
        store = SourceStore(root)
        queue.put(getattr(store, action)(identity)['status'])
    except Exception as exc:
        queue.put(f'{type(exc).__name__}: {exc}')


def run_concurrently(root, identity, action, n):
    ctx = multiprocessing.get_context('fork')
    barrier, queue = ctx.Barrier(n), ctx.Queue()
    procs = [ctx.Process(target=_worker, args=(root, identity, action, barrier, queue)) for _ in range(n)]
    for p in procs: p.start()
    results = sorted(queue.get(timeout=60) for _ in procs)
    for p in procs: p.join(60)
    return results


def test_concurrent_first_extractions_publish_one_commitment(tmp_path):
    store, record = new_source(tmp_path)
    results = run_concurrently(tmp_path, record['source_id'], 'extract', 4)
    assert results.count('EXTRACTED') == 1 and results.count('UNCHANGED') == 3, results
    assert len([p for p in directory(tmp_path).iterdir() if p.name.endswith('.json')]) == 1
    assert check_readiness(tmp_path)['ready']


def test_concurrent_explicit_commits_publish_once(tmp_path):
    store, record = new_source(tmp_path)
    store.extract(record['source_id'])
    commitment(tmp_path, record['source_id']).unlink()  # legacy bundle
    results = run_concurrently(tmp_path, record['source_id'], 'commit_extraction', 3)
    assert results.count('COMMITTED') == 1 and results.count('UNCHANGED') == 2, results
    assert check_readiness(tmp_path)['ready']


# --- explicit commit CLI and HTTP ----------------------------------------------

def test_cli_preview_writes_nothing_then_apply_commits(tmp_path, capsys):
    from tools.commit_source_extraction import main
    from tools.vm_acceptance import hashes
    store, record = new_source(tmp_path)
    store.extract(record['source_id'])
    commitment(tmp_path, record['source_id']).unlink()
    before = {k: v for k, v in hashes(tmp_path).items() if not k.endswith('.write.lock')}
    assert main(['--root', str(tmp_path), '--id', record['source_id']]) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'PREVIEW'
    assert {k: v for k, v in hashes(tmp_path).items() if not k.endswith('.write.lock')} == before
    assert main(['--root', str(tmp_path), '--id', record['source_id'], '--apply']) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'COMMITTED'
    assert main(['--root', str(tmp_path), '--id', '../' + 'a' * 61]) == 1


def test_dashboard_survives_a_blocked_commitment_without_leaking(tmp_path):
    from core.monitoring.dashboard import handler_factory
    store, record = new_source(tmp_path)
    store.extract(record['source_id'])
    substitute_with_v1(store, record)
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler_factory(tmp_path, 'test-token'))
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    auth = 'Basic ' + base64.b64encode(b'eidolon:test-token').decode()
    try:
        for path in ('/', '/sources', '/source?id=' + record['source_id'], '/source/text?id=' + record['source_id']):
            request = urllib.request.Request(f'http://127.0.0.1:{server.server_port}{path}', headers={'Authorization': auth})
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    status, body = response.status, response.read().decode('utf-8', 'replace')
            except urllib.error.HTTPError as exc:
                status, body = exc.code, exc.read().decode('utf-8', 'replace')
            assert status != 500 and 'Traceback' not in body, (path, status)
            assert 'Fin secrète' not in body or path.startswith('/source/text'), path
    finally:
        server.shutdown(); server.server_close()


def test_fresh_extraction_still_refused_while_another_is_pending(tmp_path):
    store, a = new_source(tmp_path)
    fresh = add(store, TEXT + b'Neuf.\n', original_name='c.txt', title='c')['source']
    store.extract(a['source_id'])
    (store.directory / a['source_id'] / 'extraction.json').unlink()
    with pytest.raises(ValueError, match='readiness'):
        store.extract(fresh['source_id'])
    assert not (store.directory / fresh['source_id'] / 'extraction.json').exists()


def test_pending_resume_refused_when_another_issue_exists(tmp_path):
    store, a = new_source(tmp_path)
    b = add(store, TEXT + b'Autre.\n', original_name='b.txt', title='b')['source']
    store.extract(a['source_id']); store.extract(b['source_id'])
    (store.directory / a['source_id'] / 'extraction.json').unlink()
    substitute_with_v1(store, b)  # a blocking mismatch elsewhere
    with pytest.raises(ValueError, match='readiness'):
        store.extract(a['source_id'])
```

## Annexe B — `f1-two-pending.patch` (SHA-256 `5cda11e5bab883463f5d0f35dcfd3424cef6185def666d0f3784244cc4989838`)

```diff
diff --git a/core/sources/store.py b/core/sources/store.py
index bfd9c1d..2ceaf85 100644
--- a/core/sources/store.py
+++ b/core/sources/store.py
@@ -114,11 +114,12 @@ class SourceStore:
         with exclusive_write(self.root / 'memory/persistent'), exclusive_write(self.directory):
             from core.operations.readiness import check_readiness
             from core.sources.commitments import read, matches, directory
-            # Only this exact pending extraction can be resumed by this command.
+            # Resume one exact pending extraction; other pending extractions are independent
+            # promises and must not block it. Any other issue still blocks.
             pending_path = (directory(self.root) / (str(identity) + '.json')).relative_to(self.root).as_posix()
             state = check_readiness(self.root)
-            if any(issue['path'] != pending_path or issue['reason'] != 'pending_source_extraction'
-                   for issue in state['issues']):
+            if (any(issue['reason'] != 'pending_source_extraction' for issue in state['issues'])
+                    or (state['issues'] and all(issue['path'] != pending_path for issue in state['issues']))):
                 raise ValueError('readiness blocks source extraction')
             record, data = self.read(identity)
             committed = read(self.root, identity)
```

## Annexe C — `test_claude_f1a_negative.py` (SHA-256 `f08bcd31bf8533e725fa883aca2a8abfeb2c40737d033e3e7fa32e0e4925a1c0`)

```python
"""Claude negative review of F1a (f205708), updated for F1/F1b (53d5047): reference warnings.

Synthetic sources only. Each case states the expected contract from
SOURCE-REFERENCE-AUDIT-PLAN.md and toytoy's decisions (warning, never blocking).
"""
import json
import os
from hashlib import sha256

import pytest

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.information.writes import FilesystemInformationWrites
from core.operations.readiness import check_readiness
from core.sources.extraction import reproduce_extraction
from core.sources.store import audit_sources
from core.sources.validation import accept_detail
from tests.test_source_library import seed, add, STAMP

TEXT = ('Lina habite à Lyon.\nElle possède' + chr(0x0c) + 'un chat nommé Plume.\nFin secrète du récit.\n').encode()
DETAIL = 'DETAIL-PRIVE-NE-PAS-AFFICHER'
QUOTE = 'Fin secrète du récit.'


def prepared(root):
    store = seed(root)
    record = add(store, TEXT, original_name='story.txt')['source']
    extraction = store.extract(record['source_id'])['extraction']
    draft = dict(source_id=record['source_id'], source_sha256=record['sha256'],
                 extraction_sha256=extraction['text_sha256'], extractor=extraction['extractor'],
                 model='m', model_digest='a' * 64, proposed_at=STAMP, paragraph=3, detail=DETAIL, quote=QUOTE)
    accepted = accept_detail(root, draft, detail=DETAIL, actor='human')
    return store, record, extraction, accepted


def substitute_with_v1(store, record):
    path = store.directory / record['source_id'] / 'extraction.json'
    original = (store.directory / record['source_id'] / 'original').read_bytes()
    v1 = reproduce_extraction(record, original, extractor='utf8-lines-v1')
    path.write_text(json.dumps(v1, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')


def backend(root):
    return FilesystemBackend(root / 'memory/persistent', root / 'memory/history')


def write_detail(root, provenance, key='b' * 64):
    """A source-detail Information with an arbitrary (possibly partial) provenance."""
    memory = Memory('source-detail-' + key, content='x',
                    metadata={'type': 'INTERPRETATION', 'epistemic_status': 'UNVERIFIED'}, provenance=provenance)
    FilesystemInformationWrites(backend(root)).create(
        memory, operation_id='op-' + key, event_id='ev-' + key, actor='t', timestamp=STAMP)
    return memory.information_id


def warnings_for(root, information_id):
    return [w for w in audit_sources(root)['warnings'] if w['information_id'] == information_id]


def test_valid_reference_gives_no_warning(tmp_path):
    prepared(tmp_path)
    assert audit_sources(tmp_path)['warnings'] == []
    assert check_readiness(tmp_path)['warnings'] == []


def make_legacy(root, record):
    """Since F1/F1b new extractions are committed; drop the commitment to model an older bundle."""
    path = root / 'memory/history/source-extractions-v1' / (record['source_id'] + '.json')
    if path.exists():
        path.unlink()


def test_legit_substitution_on_legacy_bundle_warns_and_keeps_ready(tmp_path):
    store, record, _, accepted = prepared(tmp_path)
    make_legacy(tmp_path, record)
    substitute_with_v1(store, record)
    found = warnings_for(tmp_path, accepted['information_id'])
    assert found and 'extractor_mismatch' in found[0]['mismatches']
    state = check_readiness(tmp_path)
    assert state['ready'] and state['warnings']


def test_legit_substitution_on_committed_bundle_blocks_and_still_warns(tmp_path):
    store, record, _, accepted = prepared(tmp_path)
    substitute_with_v1(store, record)
    assert not check_readiness(tmp_path)['ready']
    assert warnings_for(tmp_path, accepted['information_id'])


def test_partial_provenance_warns_without_crash(tmp_path):
    store, record, _, _ = prepared(tmp_path)
    iid = write_detail(tmp_path, {'source': record['source_id']})
    found = warnings_for(tmp_path, iid)
    assert found and found[0]['paragraph'] is None
    assert check_readiness(tmp_path)['ready']


@pytest.mark.parametrize('paragraph', [True, 0, -1, 10 ** 9, '3', 3.0])
def test_odd_paragraph_values_warn(tmp_path, paragraph):
    store, record, extraction, _ = prepared(tmp_path)
    provenance = dict(source=record['source_id'], source_sha256=record['sha256'], extractor=extraction['extractor'],
                      extraction_sha256=extraction['text_sha256'], paragraph=paragraph, quote=QUOTE)
    iid = write_detail(tmp_path, provenance)
    found = warnings_for(tmp_path, iid)
    assert found and 'paragraph_mismatch' in found[0]['mismatches']


@pytest.mark.parametrize('source', [None, '', '../../etc/passwd', 'A' * 64, 'c' * 64])
def test_absent_or_invalid_source_warns(tmp_path, source):
    prepared(tmp_path)
    iid = write_detail(tmp_path, {'source': source, 'paragraph': 1, 'quote': 'x'})
    found = warnings_for(tmp_path, iid)
    assert found and found[0]['mismatches'] == ['source_or_extraction_unavailable']
    assert found[0]['source_id'] in (None, 'c' * 64)
    assert check_readiness(tmp_path)['ready']


def test_deleted_detail_no_longer_warns(tmp_path):
    store, record, _, accepted = prepared(tmp_path)
    make_legacy(tmp_path, record)
    substitute_with_v1(store, record)
    b = backend(tmp_path)
    b.delete_request(accepted['information_id'], 'human', 'remove', 1, 'del-1')
    writer = FilesystemInformationWrites(b)
    for opid in writer.journal.ids():
        writer.compact(opid)
    b.approve_delete(accepted['information_id'], 'del-1')
    assert warnings_for(tmp_path, accepted['information_id']) == []


def test_corrupted_extraction_stays_blocking_and_detail_warns(tmp_path):
    store, record, extraction, accepted = prepared(tmp_path)
    path = store.directory / record['source_id'] / 'extraction.json'
    forged = dict(extraction, paragraphs=['autre'], text_sha256=sha256(b'autre').hexdigest())
    path.write_text(json.dumps(forged, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
    report = audit_sources(tmp_path)
    assert report['issues']  # corruption remains an issue
    assert not check_readiness(tmp_path)['ready']
    assert warnings_for(tmp_path, accepted['information_id'])


def test_symlinked_detail_is_not_silently_trusted(tmp_path):
    """A symlink named like a detail is skipped by the audit; inventory must still flag it."""
    store, record, _, accepted = prepared(tmp_path)
    persistent = tmp_path / 'memory/persistent'
    target = tmp_path / 'outside.md'
    target.write_bytes((persistent / (accepted['information_id'] + '.md')).read_bytes())
    os.symlink(target, persistent / ('source-detail-' + 'd' * 64 + '.md'))
    assert not check_readiness(tmp_path)['ready']


def test_http_rendering_shows_no_private_text(tmp_path):
    from core.monitoring.sources import render_sources, render_source
    from core.monitoring.dashboard import render_dashboard
    store, record, _, accepted = prepared(tmp_path)
    make_legacy(tmp_path, record)
    substitute_with_v1(store, record)
    warnings = audit_sources(tmp_path)['warnings']
    inspection = store.inspect()
    pages = [render_sources(inspection['sources'], warnings=warnings),
             render_source(record, has_extraction=True, warnings=warnings)]
    for page in pages:
        assert accepted['information_id'] in page
        for secret in (DETAIL, QUOTE, 'Lina habite', 'Plume'):
            assert secret not in page
    metrics = dict(host='h', measured_at='2026-10-04T00:00:00+00:00', data_path='/x',
                   ram_bytes=dict(used=1, total=2, available=1), volume_bytes=dict(used=1, total=2, free=1),
                   engine_data=dict(files=1, bytes=1, symlinks_skipped=0))
    from core.monitoring.overview import overview
    home = render_dashboard(metrics, overview(tmp_path), warnings=warnings)
    assert 'Références à vérifier : 1' in home
    for secret in (DETAIL, QUOTE):
        assert secret not in home
```
