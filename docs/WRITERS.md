# Écrivains connus et contrôle avant recette VM

Carte établie à partir du code de `refactor/architecture-v1` le 30 septembre
2026. Les noms des unités et les commandes réellement installées sur la VM
ne figurent pas dans ce dépôt. Les découvrir **sur la VM**, puis comparer
leurs racines de données et leurs formats à cette carte.

| Entrée du dépôt | Fichiers susceptibles d'être écrits | Coordination connue |
| --- | --- | --- |
| `services/memory-controller/memory_controller.py` : `ingest`, `update`, `review`, `execute` | `memory/working/*.md`, `memory/persistent/*.md`, anciens `history/{events,reviews}/*.md`, `history/operations/*.json` | Verrous sur Working/Persistent et publication par fichier ; séquence Event/Review/Information sans journal core. Garde contre des données core détectées dans Persistent. |
| `services/memory-relations/memory_relation_engine.py` : `add` | `memory/working/*.md`, anciens Events et Reviews | Source limitée à Working, verrou et remplacement du fichier ; pas de transaction commune avec Event/Review. |
| `core/backend/FilesystemBackend` | `memory/persistent/*.md`, `history/pending-delete/*.json` | Verrous de fichiers ; approbation Information avec reçu `APPLYING_DELETE` et contrôle des liens. Aucun Event d'écriture Information coordonné. |
| `core/threads/ThreadStorage` appelé directement | `memory/persistent/threads/*.md`, `history/operations/thread-delete-v1/*.json` pour `delete` | Création/mise à jour sans Event ni Operation ; suppression journalisée avec consultation des trois familles canoniques via `for_history` (T-039 corrigé en local). Journaux personnalisés : injecter leur coordinateur complet. |
| `core.operations.cli` : `create-linked`, `change-status`, `delete-thread` | Thread, `history/operations/thread-{create,status,delete}-v1/`, `history/events/thread-{create,status}-v1/` | Coordinateurs sous verrous ; `recover-all` reprend création, statut, suppression Thread dans cet ordre. |
| `core.migration.converter` | Destination explicite : Information core, `archive/`, `migration-report.json` | Ne modifie pas la source ; copier et vérifier hors de la racine active. |

Les CLI historiques classifier, router, executor et semantic-validator sont
principalement lecteurs ou producteurs de plans dans le code examiné. Un
service tiers peut les invoquer avec des redirections, puis écrire ailleurs.
L'index de référence reste une structure mémoire reconstruite des fichiers.

Sur la VM, lancer d'abord l'inventaire en lecture seule :

```sh
python -B -m tools.writer_inventory
systemctl list-units --all --type=service,timer --no-pager
systemctl list-unit-files --type=service,timer --no-pager
```

Pour chaque candidat, relever unité, commande, utilisateur, variables
`MEMORY_ENGINE_ROOT`, répertoire de travail, horaires, racine de données et
procédure de redémarrage. Examiner aussi les crontabs utilisateur et système,
les sessions manuelles, conteneurs et autres hôtes qui montent les données.
`tools.writer_inventory` affiche des indices par nom connu et les fichiers
systemd/cron qu'il peut lire ; une sortie vide **ne prouve pas** qu'aucun
écrivain n'existe. La recette `tools.vm_acceptance` joint ces indices à son
rapport, puis cherche les descripteurs ouverts en écriture sur la copie passée
en `--source`. Elle ne peut pas certifier à elle seule que tous les écrivains
de la racine active ont été arrêtés.

Après l'arrêt vérifié et la sauvegarde, exécuter la recette sur une **copie
arrêtée** dans un dossier de travail vide et séparé. Ne pas donner la racine
active en `--source`. Voir `docs/DEPLOYMENT.md` et `docs/MIGRATION.md`.

## Information coordonnée (01/10)

`core.information.cli` et `FilesystemInformationWrites` journalisent create/update
et leurs Events dans les familles `information-write-v1`. Reprise explicite
également raccordée à `core.operations.cli recover-all`. Voir
[INFORMATION-WRITES.md](INFORMATION-WRITES.md). Les appels directs au backend
restent destinés au stockage/import et ne fournissent pas ces garanties.
