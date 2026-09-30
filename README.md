# Eidolon Memory Engine

Moteur de mémoire en fichiers pour Eidolon. Les Informations et Threads sous
`memory/` sont la source de vérité prévue ; Qdrant reste un index à définir et
à rendre reconstructible. La branche `refactor/architecture-v1` est en cours de
développement et n'est pas encore validée sur la VM.

## Point de départ

- [Bilan de l'audit](docs/AUDIT-2026-09-29.md) et [todo list](TODO-LIST.md)
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

La reprise des journaux Thread se fait explicitement avec
`python -m core.operations.cli recover-all`, en pointant
`MEMORY_ENGINE_ROOT` vers la racine voulue. Cette commande **écrit** pour
terminer les opérations en attente : consulter la procédure de déploiement et
ne pas la lancer sur la VM sans sauvegarde et arrêt des autres écrivains.
Les nouvelles suppressions Information en `APPLYING_DELETE` ont une reprise
séparée : `python -m core.information.deletion_recovery --root RACINE` réalise
l'audit, et l'option `--apply` reprend les reçus compatibles. Les anciens
reçus ambigus restent à examiner humainement ; aucun de ces chemins n'est
automatisé au démarrage.
