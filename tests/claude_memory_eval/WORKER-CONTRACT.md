# Contrat minimal du worker d'indexation (Claude, G218-2)

Recette : `tests/claude_memory_eval/test_worker_reference_g214.py` (19 scénarios).
Référence : `reference_worker.py` (fichier de test, **pas** de production).

G235 : la copie `core.indexing.worker:IndexWorker` a été supprimée. Le worker
exécutable est `JournalUpsertWorker`, qualifié par `test_real_worker_contract_g220.py`
et `tests/test_worker_journal.py`. Les 19 scénarios ci-dessous restent une
spécification historique sur doubles ; leur interface n'est pas celle du worker réel.

Pour rejouer la référence historique :

```sh
python -m pytest -q tests/claude_memory_eval/test_worker_reference_g214.py
```

## 1. Construction

```python
Worker(journal, canon, index, rights, *, profile, lock_path, clock,
       grace_seconds=600, crash_at=None, hooks=None,
       descriptor=("embed-test/1", "passage-v1"))
```

| Paramètre | Rôle |
| --- | --- |
| `journal` | `ChangeJournal` (v2) |
| `canon` | lecteur canonique (voir 2) |
| `index` | client d'index (voir 3) |
| `rights(profile, information_id) -> bool` | droits du profil, consultés **juste avant** chaque action |
| `profile` | profil au nom duquel le worker agit |
| `lock_path` | verrou exclusif non bloquant (`flock`) |
| `clock() -> float` | horloge murale, passée à l'aperçu |
| `descriptor` | `(embedding_id, version du découpeur)` attendus |
| `crash_at`, `hooks` | points d'essai : `after_plan`, `before_upsert`, `after_upsert`. Un `hooks[nom]()` est appelé, puis `Crash` est levé si `crash_at == nom`. Ils ne servent qu'aux tests ; ta classe peut les accepter et les ignorer hors test, mais les scénarios de crash en ont besoin |

## 2. Lecteur canonique (`canon`)

- `listing() -> set[str]` : identifiants lisibles.
- `snapshot(ids) -> {id: Canonical | ABSENT}` : un identifiant **illisible
  est absent du dictionnaire** (inconnu), jamais `ABSENT`.
- `read(id) -> Canonical | ABSENT` : lève `CanonUnreadable` si la lecture
  échoue.

## 3. Index (`index`)

- `descriptor() -> (embedding_id, chunker)`.
- `revisions() -> {id: revision}`.
- `upsert(id, revision, sha256)` : idempotent.
- Toutes ces méthodes lèvent `IndexUnavailable`, y compris quand l'écriture
  a eu lieu mais que l'accusé de réception est perdu.
- **Aucune méthode de suppression** n'est exposée à la recette.

## 4. Résultat de `run_once()`

Un objet avec les champs suivants :

- `status` : `DONE`, `BUSY`, `INDEX_UNAVAILABLE`, `INDEX_INCOMPATIBLE`,
  `TRUNCATED` ou `REFUSED` ;
- `applied` : liste de `(kind, id, seq)` ;
- `review` : liste de `(kind, id, seq)` ;
- `proposed_deletions` : liste de `(id, seq)` ;
- `skipped` : liste de `(id, raison)`, avec ces raisons :
  - `"wait"` ;
  - `"canon unreadable"` ;
  - `"forbidden"` ;
  - `"absence not confirmed"` ;
  - `"canon changed since plan"` ;
  - `"canon changed while indexing"` ;
  - `"index read-back failed"`.

## 5. Invariants vérifiés

1. Planifier avec `preview_reconciliation(journal, snapshot, indexed, ...)`
   (lecteur après journal possible depuis `372b093`), puis classer avec
   `worker_preflight.preflight(..., allow_upsert=True)`. Seuls
   `proposals` est exécutable ; `review` est rapporté, jamais appliqué.
2. Pour chaque action exécutable : relire le canon **maintenant**, puis
   vérifier les droits, puis agir.
3. `upsert`, puis relecture de l'index, puis **relecture du canon**, et
   seulement ensuite `indexed(seq)`.
4. Les suppressions ne sont que **proposées**, et seulement si le canon
   relu confirme `ABSENT`.
5. Un modèle ou un découpeur différent donne `INDEX_INCOMPATIBLE`, sans
   aucune écriture.
6. Un journal tronqué ou une horloge en retard sur les intentions donne
   `TRUNCATED` ou `REFUSED`, sans aucun effet.
