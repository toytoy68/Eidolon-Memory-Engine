# Eidolon Memory Engine

Moteur de mémoire en fichiers pour Eidolon. Les Informations et Threads sous
`memory/` sont la source de vérité ; un port d’index reconstructible et sa
référence sans dépendance externe existent. Le connecteur Qdrant reste différé.
La branche `refactor/architecture-v1` est en cours de
développement et n'est pas encore validée sur la VM.

## Point de départ

- [Échanges et reprise Codex/Claude](ECHANGES.md), avec le
  [mode de collaboration asynchrone](docs/COLLABORATION.md).
- [Architecture cible complète, consolidée au 01/10](docs/ARCHITECTURE-CIBLE.md)
  et [conception des écritures Information](docs/DESIGN-INFORMATION-WRITES.md)
- [Dossiers Markdown de projet](docs/PROJECT-DOSSIERS.md) : reconstruction explicite,
  sources/révisions et notes humaines conservées ; actualisation automatique à venir.
- [Écritures Information et compaction v1](docs/INFORMATION-WRITES.md) : API, CLI,
  reprise et audit ; livré en local, essais VM encore requis.
- [Contrat fonctionnel mémoire 0.1](schemas/memory-policy-v0.1.md) :
  correspondance Information/Memory et [planificateur contextuel v0.1](docs/MEMORY-ROUTING.md)
  testés ; actualisation automatique des dossiers et déclencheurs encore à implémenter.
- [Audit transversal du 01/10](docs/AUDIT-2026-10-01.md) et [TODO active](TODO-LIST.md)
- [Architecture et frontières des écrivains](docs/ARCHITECTURE.md)
- [Inventaire et précontrôle de migration](docs/MIGRATION.md)
- [Déploiement et sauvegarde](docs/DEPLOYMENT.md)
- [Reprise des opérations Thread](docs/THREAD_RECOVERY.md) et
  [cycle de vie/suppressions Information](docs/LIFECYCLE.md)
- [Première interface d'assemblage de contexte](docs/RETRIEVAL.md)
- [Manifeste de source pour un index dérivé](docs/INDEXING.md)
- [Mesures synthétiques et procédure de répétition](docs/PERFORMANCE.md)

Après une sauvegarde des données et l'arrêt des écrivains, les outils
`core.migration.inventory`, `core.migration.preflight`,
`core.threads.link_audit` et `core.information.deletion_audit` peuvent examiner
une **copie** en lecture seule. Ils prennent `--root` vers le dossier contenant
`memory/`. Aucune migration automatique n'est fournie.

Pour tester le dépôt sans toucher à la mémoire réelle :

```sh
python -m pip install -r requirements.txt -r requirements-dev.txt
MEMORY_ENGINE_ROOT="$(mktemp -d)" PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider
```

La reprise des journaux Thread et des écritures Information se fait explicitement avec
`python -m core.operations.cli recover-all`, en pointant
`MEMORY_ENGINE_ROOT` vers la racine voulue. Cette commande **écrit** pour
terminer les opérations en attente : consulter la procédure de déploiement et
ne pas la lancer sur la VM sans sauvegarde et arrêt des autres écrivains.
Les nouvelles suppressions Information en `APPLYING_DELETE` ont une reprise
séparée : `python -m core.information.deletion_recovery --root RACINE` réalise
l'audit, et l'option `--apply` reprend les reçus compatibles. Les anciens
reçus ambigus restent à examiner humainement ; aucun de ces chemins n'est
automatisé au démarrage.

État audité au 01/10, code `a779c9d` : 754 tests réussis, cinq échecs dus aux
sockets Manager interdites avant scénario métier. Aucune validation VM.
`recover-all` n'est pas encore une autorisation fiable de démarrage : il omet
les FAILED Thread de son rapport. L'inventaire omet aussi thread-delete-v1 ;
la migration archive les reçus sans restaurer leurs réservations actives.
Voir les constats A-01 à A-03 et T-048/T-021 avant toute mise en service.
