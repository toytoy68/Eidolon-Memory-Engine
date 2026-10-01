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

## État vérifié et reprise

Dernière vérification du code `25544c7` le 01/10/2026 : **775 tests réussis,
5 échecs d’environnement en 37,17 s**, Python 3.12.14, pytest 9.1.1.
Les cinq tests Manager échouent sur les sockets interdites avant leur scénario
métier et restent à valider sur la VM. Aucun test désélectionné ; aucune
validation VM, donnée réelle ou coupure électrique.

Sur une copie arrêtée, `MEMORY_ENGINE_ROOT` désigne la racine contenant `memory/` :

```sh
python -B -m core.operations.cli readiness
python -B -m core.operations.cli recover-all
```

`readiness` contrôle les journaux et reçus en lecture seule. `recover-all`
**écrit** pour reprendre les opérations connues, y compris les suppressions
Information déjà approuvées en APPLYING_DELETE, puis relit l’état sur disque.
Le code de sortie vaut zéro seulement si `readiness.ready` est vrai.
FAILED, corruption, format inconnu ou divergence bloquent la reprise automatique ;
PENDING_DELETE valide reste une attente et n’est jamais approuvé automatiquement.
Consulter [STARTUP-READINESS.md](docs/STARTUP-READINESS.md) avant utilisation.
Ce contrôle ponctuel exige les écrivains arrêtés ; aucun service de démarrage
n’est encore installé sur la VM.

## Prochaines étapes

- Sécuriser la migration des sources mixtes : les reçus archivés ne réactivent
  pas leurs réservations d’identité. Ne pas activer une destination sur le seul
  critère d’absence de rejets.
- Compléter les commandes de liens/actions Thread et exécuter les plans par
  les services coordonnés.
- Raccorder l’actualisation des dossiers et le rappel au contexte et à la validité.
- Construire le catalogue et les déclencheurs durables ; réduire les scans de
  journaux avant ingestion intensive.

Le planificateur et les dossiers explicites sont livrés, mais le parcours
Information → projet existant → dossier actualisé → rappel contextuel reste
incomplet. Les anciens services legacy constituent une pile distincte.
La [TODO active](TODO-LIST.md) précise les preuves, priorités et limites actuelles ;
les audits datés conservent leurs constats historiques.
