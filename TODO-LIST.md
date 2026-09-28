# Eidolon Memory Engine — feuille de route

**Avancement prévisionnel : ≈ 45 % (estimation au 2026-09-28).** Ce chiffre
représente la maturité estimée de la cible complète, pas le rapport entre les
tâches cochées et leur nombre. Le noyau Information/Thread/Event et la reprise
de certains parcours sont testés dans le dépôt ; migration des données anciennes,
intégration à Eidolon Core et à l'index, validation sur la VM et tableau de bord
restent à terminer ou à décider. Réévaluer ce pourcentage après chaque phase
majeure validée ; la cible peut encore évoluer.

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
- **【EN ATTENTE】** : travail volontairement suspendu à la demande du projet.

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
│   ├── monitoring/               mesures et première page HTML (existant)
│   ├── indexing/                 interface d'index dérivé/reconstructible (prévu)
│   └── integration/              adaptateurs vers Eidolon Core/API (prévu)
├── schemas/                      contrats Information, Thread, Event… (existant)
├── services/                     CLI historiques à auditer/migrer (existant)
├── docs/                         format, reprise, déploiement (existant)
│   ├── ARCHITECTURE.md           frontières actuelles, cible à compléter (existant)
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
- **【FAIT】** T-005 — 262 tests exécutables réussis sur la copie de travail le
  2026-09-28 ; 5 tests de concurrence non exécutables dans cet environnement
  (socket local interdit). Cette preuve ne couvre pas la VM Debian.
- **【FAIT】** T-020 — Inventaire des formats et chemins produits par les anciens
  CLI, tableau de correspondance et outil de comptage en lecture seule ; voir
  `docs/MIGRATION.md` et `core/migration/inventory.py` (tests isolés, 2026-09-28).
- **【FAIT】** T-022a — Scénario intégré sur répertoire isolé : Information,
  Thread avec relation, interruption après Event, reprise et rejeu idempotent ;
  voir `tests/integration/test_memory_flow.py` (2026-09-28).
- **【FAIT】** T-021a — Contrôle structurel en lecture seule des Informations
  historiques persistantes, avec rapport de blocages sans contenu utilisateur ;
  voir `core/migration/preflight.py` (tests isolés, 2026-09-28).
- **【FAIT】** T-029a — Mesures locales de RAM hôte, volume disque et taille des
  données du moteur, avec hôte et heure de mesure ; voir `core/monitoring/metrics.py`
  et `docs/MONITORING.md` (tests isolés, 2026-09-28).
- **【FAIT】** T-029b — Comptage en lecture seule des Threads par statut et des
  opérations en attente, avec signalement des fichiers inconnus ; voir
  `core/monitoring/overview.py` (tests isolés, 2026-09-28).
- **【FAIT】** T-029c — Première page HTML avec accès HTTP Basic, écoute locale
  par défaut, mesures et statuts ; voir `core/monitoring/dashboard.py`. Rendu et
  authentification testés sans socket, 2026-09-28. Accès LAN à valider sur VM.
- **【FAIT】** T-029d — Parcours paginé et aperçu texte des Markdown autorisés,
  avec échappement HTML, blocage des liens et limite de taille ; voir
  `core/monitoring/files.py` (tests isolés, 2026-09-28).
- **【FAIT】** T-023a / T-028a — Frontières des écrivains et protocole Thread
  documentés dans `docs/ARCHITECTURE.md` (revue du code, 2026-09-28).
- **【FAIT】** T-030 — Lecture des Events : rejet des révisions converties
  implicitement (`"2"`, booléen), des identifiants et structures JSON de mauvais
  type ; six tests de régression (2026-09-28).
- **【FAIT】** T-022b — Création contrôlée d'un Thread avec relation `CONCERNS`
  vers une Information persistée, vérifiée sous verrou commun ; scénario intégré
  adapté et quatre tests dédiés (2026-09-28).
- **【FAIT】** T-021b — Le contrôle préalable des Informations anciennes signale
  aussi les valeurs de type/état inconnues et les blocs YAML de forme incompatible
  avec le modèle ; test de régression (2026-09-28).
- **【FAIT】** T-021c — Le contrôle préalable bloque aussi les métadonnées et
  sous-champs de révision inconnus pour éviter leur perte lors d'une conversion
  future ; rapport sans valeurs privées et test isolé (2026-09-28).
- **【FAIT】** T-021d — Le contrôle préalable signale les identifiants de fichiers
  historiques que le backend core ne pourrait pas adresser ; test isolé
  (2026-09-28).
- **【FAIT】** T-021e — Le contrôle préalable ne compte un document core reconnu
  comme déjà présent qu'après lecture et vérification de son identité ; les
  documents tronqués ou discordants sont signalés sans contenu privé
  (2026-09-28).
- **【FAIT】** T-022c — Audit en lecture seule des relations `CONCERNS` vers une
  Information absente ou illisible ; voir `core/threads/link_audit.py`, deux tests
  sur données isolées (2026-09-28).
- **【FAIT】** T-022d — Chemin protégé d'approbation de suppression : bloque une
  Information liée ou des Threads illisibles, sans effacer la demande en attente ;
  voir `core/information/deletion_service.py`, trois tests isolés (2026-09-28).
- **【FAIT】** T-022e — L'approbation directe du backend contrôle également les
  liens Thread sous verrou ; tests de régression sur lien, fichier illisible et
  lien symbolique ; audit d'orphelin conservé sur une suppression simulée par
  un ancien écrivain (2026-09-28).
- **【FAIT】** T-022f — Contrat Event étendu à `CREATED` pour un Thread avec
  révision 1 et statut initial ; validation et schéma adaptés (2026-09-28).
- **【FAIT】** T-022g — Création liée journalisée avec Event `CREATED`, reprise
  après interruption et rejet d'un Thread divergent ; commande
  `recover-creations` et quatre scénarios intégrés (2026-09-28).
- **【FAIT】** T-022h — CLI `create-linked` raccordé à la création journalisée,
  avec identifiants d'opération/Event et date explicite pour un rejeu stable ;
  scénario isolé de bout en bout (2026-09-28).
- **【FAIT】** T-022i — Scénario intégré création liée journalisée → changement
  de statut interrompu → reprise ; vérifie les deux Events et la conservation
  de l'Information et de la relation (2026-09-28).
- **【FAIT】** T-022j — Une création journalisée rejette une révision initiale
  autre que 1 et une seconde opération ciblant un Thread déjà journalisé,
  y compris avant l'écriture du Thread ; deux tests isolés (2026-09-28).
- **【FAIT】** T-022k — Le changement de statut par le CLI refuse un Thread dont
  la création journalisée reste incomplète ; contrôle injectable dans le service
  Python et scénario d'interruption puis reprise (2026-09-28).
- **【FAIT】** T-022l — Commande `recover-all` : créations puis statuts, rapport
  distinct et code d'erreur si une reprise reste bloquée ; deux tests isolés
  (2026-09-28).
- **【FAIT】** T-027a — Audit en lecture seule des suppressions interrompues et
  demandes incohérentes ; voir `core/information/deletion_audit.py`, deux tests
  isolés (2026-09-28).
- **【FAIT】** T-027b — Audit des demandes : rejette aussi une révision nulle ou
  un identifiant d'opération vide, et indique le bon chemin en présence d'un
  lien symbolique sur le répertoire Information ; trois cas testés (2026-09-28).

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
  et tests sur copies anonymisées. T-021a/b/c/d/e couvrent seulement le contrôle
  préalable ; aucune conversion n'est autorisée. Ne jamais migrer silencieusement
  au démarrage.
- **【À FAIRE】** T-022 — Tester le parcours complet Information → Thread →
  Operation → Event → reprise après crash sur un répertoire isolé ; vérifier
  idempotence, conflits et absence de perte de données. T-022a/b couvrent la
  création liée et la reprise d'un statut ; T-022c/d/e détectent les liens
  orphelins et protègent la suppression core. T-022f/g/h/i ajoutent un chemin
  journalisé de création avec Event ; il manque encore l'adaptation des autres
  chemins de création, les Events propres à l'Information et le
  raccordement des anciens chemins de suppression à cette protection.
- **【À FAIRE】** T-023 — Clarifier les frontières entre anciens CLI et nouvelles
  écritures verrouillées ; supprimer ou adapter les chemins d'écriture
  concurrents avant de les lancer simultanément. Frontières documentées (T-023a),
  adaptation effective encore à faire après inventaire de la VM.
- **【À VALIDER】** T-024 — Définir le contrat de recherche/index Qdrant dérivé,
  sa reconstruction, sa cohérence après mutation et les tests de reconstruction.
- **【À VALIDER】** T-025 — Définir l'intégration réelle à Eidolon Core : API,
  authentification, erreurs, demandes en lecture et écritures contrôlées.
- **【À VALIDER】** T-026 — Décider si une vue Markdown éditable est nécessaire et
  comment traduire ses modifications en changements contrôlés par révision.
- **【À VALIDER】** T-027 — Étudier la cohérence lecteur pendant une opération
  multi-fichiers et les garanties face à coupure électrique ; les tests actuels
  couvrent l'arrêt de processus, pas une panne d'alimentation. T-027a détecte
  certains états de suppression interrompue mais ne les répare pas ; prévoir
  un protocole récupérable avant d'annoncer une garantie de suppression.
- **【À FAIRE】** T-028 — Documenter les décisions validées dans
  `docs/ARCHITECTURE.md`, puis adapter l'arborescence cible ci-dessus. T-028a
  couvre l'architecture existante ; les choix futurs doivent être ajoutés après
  validation.
- **【EN ATTENTE】** T-029 — Construire un tableau de bord HTML servi sur le réseau
  local depuis la VM, consultable sur le PC principal : volumes, statuts,
  opérations en attente et erreurs, RAM utilisée/disponible,
  disque utilisé/libre sur le volume des données, taille des fichiers du moteur
  et, si raccordé, de l'index Qdrant ; recherche et ouverture des fichiers
  Markdown en lecture seule. Préciser machine mesurée et date de rafraîchissement.
  Prévoir accès restreint au réseau local et contrôle d'accès avant exposition.
  Valider port, adresse et intégration aux services de la VM lors du déploiement.
  Tester la fraîcheur des statistiques, les permissions et les gros volumes.
  T-029a/b fournissent les mesures locales et T-029c une première page HTML.
  L'accès LAN, le test navigateur, le déploiement et les vues plus détaillées
  restent à valider/développer.
  L'édition éventuelle devra passer par les services et leurs révisions ; ne
  jamais écrire directement dans les fichiers du moteur. Reprendre uniquement
  après la priorité donnée au noyau mémoire (demande du 2026-09-28).

## Critère de livraison

Le noyau sera considéré déployable lorsque la migration nécessaire sera décidée,
les tests complets et les parcours d'intégration passeront sur Debian avec une
racine isolée, qu'une sauvegarde restaurable sera vérifiée, et que la reprise
opérationnelle et les services réellement utilisés seront validés. Ces critères
ne supposent pas que toutes les extensions proposées soient nécessaires à la
première mise en service.
