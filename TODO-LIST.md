# Eidolon Memory Engine — feuille de route

Dernière mise à jour : 2026-09-28. Branche suivie : `refactor/architecture-v1`.
Cette arborescence décrit une **cible supposée**, pas une architecture figée. Les
emplacements marqués `prévu` sont des propositions à confirmer avant création.
Le dépôt Git versionne le code et les schémas ; les mémoires réelles, secrets,
sauvegardes et index reconstruisibles restent hors Git.

## Convention de suivi

- **【FAIT】** : changement présent dans Git et vérifié par des tests adaptés ;
  cela ne signifie pas qu'il est installé sur la VM.
- **【À FAIRE】** : prochaine action identifiée, non terminée.
- **【À VALIDER】** : décision d'architecture ou vérification sur données/VM réelles.
- **【BLOQUÉ】** : action impossible avant la condition indiquée.

Lorsqu'une tâche est terminée, remplacer son statut par **【FAIT】**, ajouter le
commit ou la preuve du test et la date. Garder la tâche dans le fichier afin de
conserver l'historique. Ajouter toute nouvelle tâche avec un identifiant stable ;
ne pas interpréter la présence d'un dossier comme une preuve d'intégration.

## Arborescence cible supposée

```text
Eidolon-Memory-Engine/
├── TODO-LIST.md                  suivi du travail (existant)
├── core/                         noyau de domaine (existant)
│   ├── information/              modèle et validation (existant)
│   ├── backend/                  stockage Information sur fichiers (existant)
│   ├── threads/                  modèle, stockage, requêtes et service (existant)
│   ├── events/                   modèle et dépôt append-only (existant)
│   ├── operations/               journal, CLI et reprise des statuts Thread (existant)
│   ├── request_parser.py         enveloppes de requête (existant)
│   ├── request_dispatcher.py     routage actuellement limité aux Threads (existant)
│   ├── persistence.py            verrous et écritures durables (existant)
│   ├── storage_format.py         documents Markdown/JSON versionnés (existant)
│   ├── migration/                inventaire seul ; convertisseur prévu
│   ├── indexing/                 interface d'index dérivé/reconstructible (prévu)
│   └── integration/              adaptateurs vers Eidolon Core/API (prévu)
├── schemas/                      contrats Information, Thread, Event… (existant)
├── services/                     CLI historiques à auditer/migrer (existant)
├── desktop/                      interface graphique locale (prévu, à valider)
├── docs/                         format, reprise, déploiement (existant)
│   ├── ARCHITECTURE.md           contrats et frontières de composants (prévu)
│   └── MIGRATION.md              inventaire et décisions ouvertes (existant)
├── scripts/                      bootstrap Debian (existant)
├── tests/                        tests unitaires et de régression (existant)
│   ├── integration/              parcours complets isolés (prévu)
│   └── fixtures/                 exemples représentatifs anonymisés (existant/à enrichir)
└── memory/                       données au runtime, hors Git (créées selon config)
    ├── working/
    ├── persistent/               fichiers source de vérité
    └── history/
        ├── events/               dont thread-status-v1/
        ├── operations/           dont thread-status-v1/
        └── reviews/
```

Qdrant, s'il est raccordé, serait un index **reconstructible** à partir des
fichiers. Son emplacement et le découpage `indexing/` restent à valider ; aucun
connecteur Qdrant opérationnel n'est attesté par cette branche.

## État vérifié dans le dépôt

- **【FAIT】** T-001 — Modèles, stockage de fichiers et requêtes des Informations
  et Threads, dépôts Event et Operation, contrôle de révision des Threads.
- **【FAIT】** T-002 — Changement de statut Thread récupérable avec journal,
  snapshots, Event déterministe et commande `recover` explicite (`4e958aa`).
- **【FAIT】** T-003 — Format 0.2 préservant le Markdown arbitraire, avec lecture
  des fichiers du format core 0.1 (`b470bdf`).
- **【FAIT】** T-004 — Rejet des Events persistés ambigus ou invalides (`ff0fbc0`).
- **【FAIT】** T-005 — 212 tests exécutables réussis sur la copie de travail le
  2026-09-28 ; 5 tests de concurrence non exécutables dans cet environnement
  (socket local interdit). Cette preuve ne couvre pas la VM Debian.
- **【FAIT】** T-020 — Inventaire des formats et chemins produits par les anciens
  CLI, tableau de correspondance et outil de comptage en lecture seule ; voir
  `docs/MIGRATION.md` et `core/migration/inventory.py` (tests isolés, 2026-09-28).
- **【FAIT】** T-022a — Scénario intégré sur répertoire isolé : Information,
  Thread avec relation, interruption après Event, reprise et rejeu idempotent ;
  voir `tests/integration/test_memory_flow.py` (2026-09-28).

## Prochaines vérifications sur la VM Debian

1. **【À FAIRE】** T-010 — Relever branche, HEAD, modifications locales, services
   actifs, racine `MEMORY_ENGINE_ROOT` et emplacement réel des données avant mise
   à jour. Ne pas écraser les modifications locales.
2. **【À FAIRE】** T-011 — Arrêter les écrivains, sauvegarder checkout et données
   externes, contrôler archive et somme de contrôle. Suivre `docs/DEPLOYMENT.md`.
3. **【À FAIRE】** T-012 — Examiner les commits entrants puis avancer par
   fast-forward jusqu'au commit approuvé ; ne pas fusionner des historiques
   divergents sans analyse.
4. **【À FAIRE】** T-013 — Lancer la suite complète, y compris les **5 tests de
   concurrence**, avec `MEMORY_ENGINE_ROOT` temporaire et
   `PYTHONDONTWRITEBYTECODE=1`. Vérifier aussi les reprises après interruption.
5. **【À FAIRE】** T-014 — Tester en lecture seule sur un échantillon représentatif
   de données réelles (formats, requêtes, fichiers malformés, performances), puis
   vérifier journaux et services. Autoriser les écritures seulement après revue.
6. **【À VALIDER】** T-015 — Définir comment lancer `recover` avant toute nouvelle
   écriture après redémarrage ; aucun job automatique n'existe actuellement.

## Changements de code et tests suivants

- **【À FAIRE】** T-021 — Concevoir une migration explicite, réexécutable et
  vérifiable des documents CLI/front-matter et des anciens journaux. Prévoir
  simulation, sauvegarde, rapport de rejets, contrôle des identifiants/révisions
  et tests sur copies anonymisées. Ne jamais migrer silencieusement au démarrage.
- **【À FAIRE】** T-022 — Tester le parcours complet Information → Thread →
  Operation → Event → reprise après crash sur un répertoire isolé ; vérifier
  idempotence, conflits et absence de perte de données. T-022a couvre une partie
  du parcours ; il reste à définir et tester la création contrôlée du lien
  Information/Thread, sa validation et les Events propres à l'Information.
- **【À FAIRE】** T-023 — Clarifier les frontières entre anciens CLI et nouvelles
  écritures verrouillées ; supprimer ou adapter les chemins d'écriture
  concurrents avant de les lancer simultanément.
- **【À VALIDER】** T-024 — Définir le contrat de recherche/index Qdrant dérivé,
  sa reconstruction, sa cohérence après mutation et les tests de reconstruction.
- **【À VALIDER】** T-025 — Définir l'intégration réelle à Eidolon Core : API,
  authentification, erreurs, demandes en lecture et écritures contrôlées.
- **【À VALIDER】** T-026 — Décider si une vue Markdown éditable est nécessaire et
  comment traduire ses modifications en changements contrôlés par révision.
- **【À VALIDER】** T-027 — Étudier la cohérence lecteur pendant une opération
  multi-fichiers et les garanties face à coupure électrique ; les tests actuels
  couvrent l'arrêt de processus, pas une panne d'alimentation.
- **【À FAIRE】** T-028 — Documenter les décisions validées dans
  `docs/ARCHITECTURE.md`, puis adapter l'arborescence cible ci-dessus.
- **【À VALIDER】** T-029 — Définir une interface graphique de bureau : tableau de
  bord (volumes, statuts, opérations en attente, erreurs), RAM utilisée/disponible,
  disque utilisé/libre sur le volume des données, taille des fichiers du moteur
  et, si raccordé, de l'index Qdrant ; recherche et ouverture des fichiers
  Markdown en lecture seule. Préciser machine mesurée et date de rafraîchissement.
  Choisir si l'interface réside dans ce dépôt
  ou dans une application distincte, et si elle lit une API locale ou distante.
  Tester la fraîcheur des statistiques, les permissions et les gros volumes.
  L'édition éventuelle devra passer par les services et leurs révisions ; ne
  jamais écrire directement dans les fichiers du moteur.

## Critère de livraison

Le noyau sera considéré déployable lorsque la migration nécessaire sera décidée,
les tests complets et les parcours d'intégration passeront sur Debian avec une
racine isolée, qu'une sauvegarde restaurable sera vérifiée, et que la reprise
opérationnelle et les services réellement utilisés seront validés. Ces critères
ne supposent pas que toutes les extensions proposées soient nécessaires à la
première mise en service.
