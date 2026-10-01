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
  rapprochement global reprenable, sources/révisions et notes humaines conservées.
- [Écritures Information et compaction v1](docs/INFORMATION-WRITES.md) : API, CLI,
  reprise et audit ; livré en local, essais VM encore requis.
- [Contrat fonctionnel mémoire 0.1](schemas/memory-policy-v0.1.md) :
  correspondance Information/Memory et [planificateur contextuel v0.1](docs/MEMORY-ROUTING.md)
  testés ; dossiers actualisés dans le parcours qualifié, déclencheurs encore à implémenter.
- [Audit transversal du 01/10](docs/AUDIT-2026-10-01.md) et [TODO active](TODO-LIST.md)
- [Architecture et frontières des écrivains](docs/ARCHITECTURE.md)
- [Inventaire et précontrôle de migration](docs/MIGRATION.md)
- [Déploiement et sauvegarde](docs/DEPLOYMENT.md)
- [Reprise des opérations Thread](docs/THREAD_RECOVERY.md) et
  [cycle de vie/suppressions Information](docs/LIFECYCLE.md)
- [Première interface d'assemblage de contexte](docs/RETRIEVAL.md)
- [Manifeste de source pour un index dérivé](docs/INDEXING.md)
- [Catalogue reconstructible](docs/INFORMATION-CATALOGUE.md) : découverte par
  métadonnées, filtres projet/disponibilité et refus d'une projection périmée.
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

Dernière vérification après le catalogue et la réduction des scans du 01/10/2026 :
**883 tests réussis, 5 échecs d’environnement en 51,84 s**, Python 3.12.14, pytest 9.1.1.
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

- Définir l’import opérationnel des sources mixtes. Le convertisseur refuse
  désormais leurs reçus/journaux avant toute écriture dans la destination ;
  il ne les archive plus silencieusement en perdant leurs contraintes actives.
- Étendre l’exécution des plans : le parcours qualifié STORE/UPDATE vers un
  projet existant et son dossier est livré avec reprise et rejeu ; voir
  [ROUTING-EXECUTION.md](docs/ROUTING-EXECUTION.md). Les commandes Thread
  restent décrites dans [THREAD-UPDATES.md](docs/THREAD-UPDATES.md).
- Automatiser le rapprochement des dossiers, maintenant disponible à la demande
  hors du parcours qualifié. Le rappel
  applique maintenant contexte/validité/statuts et expose sources et incertitudes ;
  voir [CONTEXTUAL-RECALL.md](docs/CONTEXTUAL-RECALL.md).
- Poursuivre T-049 avant ingestion intensive : les nouvelles écritures font
  désormais un scan au lieu de trois, mais le coût reste linéaire par commande.
  [Mesures reproductibles](docs/JOURNAL-SCAN-COST.md) : 300 créations en 20,42 s
  contre 59,39 s sur le corpus synthétique local. Catalogue livré à la demande ;
  déclencheurs durables et rattrapage automatique restent ouverts.

Le premier parcours Information → projet existant → dossier actualisé → rappel
contextualisé est livré pour les entrées explicitement qualifiées. Les autres
mutations peuvent laisser du retard, signalé au rappel qui utilise le canonique.
`python -B -m core.dossiers.cli --root RACINE reconcile` inspecte toutes les vues
sans écriture ; ajouter `--apply` répare celles qui manquent ou sont périmées,
y compris après suppression, en conservant les notes humaines. Une interruption
se reprend par relance. Disponibilité autonome et échéances restent ouvertes.
Les anciens services legacy constituent une pile distincte.
La [TODO active](TODO-LIST.md) précise les preuves, priorités et limites actuelles ;
les audits datés conservent leurs constats historiques.
