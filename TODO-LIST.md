# Eidolon Memory Engine — feuille de route

**Avancement prévisionnel : ≈ 40 % (estimation révisée au 2026-09-29,
incertitude d'au moins ± 10 points).** Ce chiffre
représente la maturité estimée de la cible complète, pas le rapport entre les
tâches cochées et leur nombre. Le noyau Information/Thread/Event et la reprise
de certains parcours sont testés dans le dépôt ; migration des données anciennes,
intégration à Eidolon Core et à l'index, validation sur la VM et tableau de bord
restent à terminer ou à décider. Réévaluer ce pourcentage après chaque phase
majeure validée ; la cible peut encore évoluer. Voir le
[bilan détaillé de l'audit](docs/AUDIT-2026-09-29.md).

Dernière mise à jour : 2026-09-30. Branche suivie : `refactor/architecture-v1`.
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
├── README.md                     point d'entrée et état de la branche (existant)
├── TODO-LIST.md                  suivi du travail (existant)
├── core/                         noyau de domaine (existant)
│   ├── information/              modèle et validation (existant)
│   ├── backend/                  stockage Information sur fichiers (existant)
│   ├── threads/                  modèle, stockage, requêtes et service (existant)
│   ├── events/                   modèle et dépôt append-only (existant)
│   ├── operations/               journaux, CLI et reprise création/statut Thread (existant)
│   ├── request_parser.py         enveloppes de requête (existant)
│   ├── request_dispatcher.py     routage actuellement limité aux Threads (existant)
│   ├── persistence.py            verrous et écritures durables (existant)
│   ├── storage_format.py         documents Markdown/JSON versionnés (existant)
│   ├── migration/                inventaire et précontrôle ; convertisseur prévu
│   ├── monitoring/               mesures et première page HTML (existant)
│   ├── retrieval/                assemblage borné du contexte (existant, à enrichir)
│   ├── indexing/                 manifeste source en lecture seule ; connecteur prévu
│   └── integration/              adaptateurs vers Eidolon Core/API (prévu)
├── schemas/                      contrats Information, Thread, Event… (existant)
├── services/                     CLI historiques à auditer/migrer (existant)
├── docs/                         format, reprise, déploiement (existant)
│   ├── ARCHITECTURE.md           frontières actuelles, cible à compléter (existant)
│   ├── AUDIT-2026-09-28.md       bilan vérifié du dépôt (existant)
│   ├── AUDIT-2026-09-29.md       bilan actualisé du dépôt (existant)
│   └── MIGRATION.md              inventaire et décisions ouvertes (existant)
├── scripts/                      bootstrap Debian (existant)
├── tests/                        tests unitaires et de régression (existant)
│   ├── integration/              parcours complets isolés (existant, à enrichir)
│   └── fixtures/                 exemples représentatifs anonymisés (existant/à enrichir)
└── memory/                       données au runtime, hors Git (créées selon config)
    ├── working/
    ├── persistent/               fichiers source de vérité
    └── history/
        ├── events/               dont thread-create-v1/ et thread-status-v1/
        ├── operations/           dont thread-create-v1/ et thread-status-v1/
        └── reviews/
```

Qdrant est **volontairement différé** : il n'est pas encore installé pour ce
projet et son raccordement attend un besoin de recherche mesuré et le contrat
d'intégration d'Eidolon Core. S'il est raccordé, il sera un index
**reconstructible** à partir des fichiers. Son emplacement et le découpage
`indexing/` restent à valider ; aucun connecteur Qdrant opérationnel n'est
attesté par cette branche. `Eidolon-Bootstrap-Framework` est le dépôt du
déploiement de la plateforme, distinct d'Eidolon Core et du Memory Engine.

## Priorités après l'audit du dépôt

**Règle de priorité du projet :** construire et fiabiliser le Memory Engine
comme composant autonome et persistant avant le système agentique. Les formats,
la source de vérité, la validation et la reprise appartiennent au moteur ;
Eidolon Core et les futurs agents sont des clients susceptibles d'évoluer ou
d'être remplacés sans migration imposée de la mémoire. L'index éventuel reste
reconstructible. Prioriser la sûreté des données, la migration et les contrats
stables du moteur avant l'intégration aux agents.

1. **【À FAIRE】** T-010 à T-015 — Sur VM, identifier les écrivains et données,
   sauvegarder et vérifier une restauration sur copie, tester les cinq cas de
   concurrence et définir l'ordre de `recover-all` au démarrage. Ne pas ouvrir
   les écritures core sur les données historiques avant cette revue.
2. **【À FAIRE】** T-031 — Définir le chemin canonique d'écriture Thread et
   Information : recenser tous les appels directs à `ThreadStorage`, au backend
   et aux anciens CLI ; adapter ou isoler ceux qui contournent les journaux,
   verrous ou Events. T-031a/b raccordent création et reprise dans le service ;
   les API bas niveau et les anciens services restent à adapter après migration.
   `ThreadStorage.delete` reste notamment une suppression directe sans journal
   ni Event : décider son remplacement avant de l'exposer comme parcours métier.
   Un garde-fou empêche déjà le controller historique d'écrire dans Persistent
   Memory si des données core y sont détectées. Vérifier sur
   une copie que deux écrivains ne partagent pas une famille de fichiers.
3. **【À FAIRE】** T-032 — Concevoir et tester une suppression Information
   récupérable : journal avant retrait et reprise explicite par `approve_delete`
   sont en place pour les nouvelles demandes ; restent la résolution des
   demandes historiques incohérentes et les essais d'interruption sur VM.
   Garder l'audit
   actuel en lecture seule tant que la politique de réparation n'est pas fixée.
   T-032a protège déjà les demandes en attente contre l'écrasement.
   Le garde-fou T-032j refuse explicitement un reçu symbolique cassé lors
   de l'approbation ou de l'annulation (2026-09-29).
4. **【À FAIRE】** T-033 — La première simulation **sans écriture** des
   Informations historiques propose une correspondance champ par champ et
   signale les blocages ainsi que les Events/Reviews à décider. Restent la
   validation des pertes sémantiques, des relations, de la révision structurée
   et du format cible avant un convertisseur effectif.
   T-033a refuse désormais les liens symboliques dans les répertoires parents
   des sources lors de l'inventaire, du précontrôle et de la simulation
   (2026-09-29 ; test de non-parcours sur une racine `memory/` liée).
   T-033l signale les identifiants internes d'Events et Reviews historiques
   incohérents avec leur nom de fichier (2026-09-29 ; simulation en lecture seule).
   T-033m bloque les en-têtes des Events historiques sans front matter dont
   les champs d'identité, type ou référence sont déclarés plusieurs fois,
   ou dont le séparateur de fin d'en-tête manque
   (2026-09-29 ; simulation en lecture seule).
   T-033n classe une référence historique sous un dossier lié comme dangereuse
   même si sa cible n'existe pas (2026-09-29 ; simulation en lecture seule).
   T-033o refuse aussi un lien symbolique sur la racine du moteur ou un de ses
   ancêtres avant inventaire, précontrôle et simulation (2026-09-30).
   T-033p classe les journaux JSON à clés dupliquées ou valeurs non standard
   comme invalides dans l'inventaire, sans modifier les fichiers (2026-09-30).
5. **【À VALIDER】** T-034 — Définir l'API avec Eidolon Core,
   l'identité/authentification et les erreurs. Décider ensuite si Qdrant est
   utile selon les besoins mesurés ; si oui, préciser index dérivé,
   reconstruction et rattrapage après écriture. Tester sur copie anonymisée
   avant exposition au système réel.
6. **【À FAIRE】** T-035 — Enrichir les fixtures avec des exemples anonymisés
   représentatifs de la VM, tester les performances et l'interruption aux
   frontières de chaque écriture multi-fichiers ; distinguer crash processus et
   coupure d'alimentation dans les garanties.
7. **【EN ATTENTE】** T-029 — Reprendre le tableau de bord et son accès LAN lorsque
   la priorité au noyau sera levée par le projet.
8. **【À FAIRE】** T-036 — Concevoir et mesurer une récupération classée au sein
   du moteur : pertinence de la requête, qualité des preuves, statut
   épistémique, importance et récence comme signaux distincts. Définir une
   politique explicite pour les Informations réfutées, conflictuelles et
   périmées ; ne pas déduire la vérité d'un score. Garder les critères et
   explications du classement indépendants d'Eidolon Core et d'un fournisseur
   d'index. Le budget de tokens accepte déjà un compteur injectable ; choisir
   celui du consommateur et conserver les bornes en caractères.
9. **【À VALIDER】** T-037 — Définir le cycle de vie mémoire : consolidation,
   révisions, rétention et oubli. Préciser les liens, la provenance, les
   conflits, l'archivage et la reprise avant toute mutation automatique ;
   aucun niveau `retention` ne doit provoquer une suppression implicite.

## État vérifié dans le dépôt

- **【FAIT】** T-001 — Modèles, stockage de fichiers et requêtes des Informations
  et Threads, dépôts Event et Operation, contrôle de révision des Threads.
- **【FAIT】** T-038 — Le validateur Information accepte les membres Enum et
  leurs valeurs texte sans dépendre du test d'appartenance à `EnumType`, qui
  lève sur Python 3.11 pour une valeur invalide (2026-09-29 ; tests isolés).
- **【FAIT】** T-036a — Premier classement lexical optionnel de la recherche
  fichier : couverture des termes, contenu, phrase et fréquence plafonnée,
  avec score explicable et ordre déterministe. L'assembleur peut le demander
  sans perdre les statuts épistémiques ; aucun statut n'ajoute de bonus de
  vérité. Mesure synthétique de 15 000 fichiers documentée ; récence,
  importance, preuves et budget tokens restent ouverts (2026-09-29).
- **【FAIT】** T-036b — L'assembleur accepte un compteur de tokens injectable et
  borne les extraits par caractères et par somme de tokens isolés ; les tokens
  de prompt et de jointure restent à réserver par l'appelant (2026-09-29).
- **【FAIT】** T-036c — Le classement lexical distingue la phrase exacte des
  termes répétés servant à la couverture et cherche aussi dans les valeurs de
  provenance, temps, vérification et relations, sans utiliser les noms de
  champs comme preuves de pertinence (2026-09-29).
- **【FAIT】** T-036d — L'assembleur accepte un filtre explicite de statuts
  épistémiques, tout inclure par défaut, et poursuit la pagination au-delà
  des résultats écartés ; aucun statut ne change le score (2026-09-29).
- **【FAIT】** T-036e — Banc de jugements synthétiques ou anonymisés comparant
  `legacy` et `lexical_v1` par précision, rappel et MRR@k, sans afficher les
  textes ni les IDs ; voir `docs/RETRIEVAL.md` (2026-09-29).
- **【FAIT】** T-036f — Les extraits transportent importance, rétention et bornes
  de validité séparément du score ; aucune de ces étiquettes ne modifie l'ordre
  lexical sans politique validée (2026-09-29).
- **【FAIT】** T-036g — Le classement lexical normalise les formes Unicode
  équivalentes (NFC) et cherche dans les valeurs des contenus structurés,
  sans retirer les accents (2026-09-29).
- **【FAIT】** T-036h — La recherche fichier valide les options et le mode de
  classement même pour une requête vide ; l'assembleur fixe les statuts
  autorisés au début de la pagination (2026-09-29).
- **【FAIT】** T-036i — L’assembleur peut convertir explicitement les contenus
  structurés JSON en extraits bornés avec étiquette de format et de
  troncature ; la valeur persistée reste intacte (2026-09-29).
- **【FAIT】** T-037a — Audit du cycle de vie sur copie arrêtée : comptes de
  rétention et de période de validité distincts à une date explicite, sans
  suppression ni sortie du contenu ; voir `docs/LIFECYCLE.md` (2026-09-29).
- **【FAIT】** T-037b — L'audit distingue les périodes non commencées et
  terminées et signale les bornes temporelles incohérentes ou sans fuseau,
  sans déduire la vérité ou la suppression (2026-09-29).
- **【FAIT】** T-037c — L'audit compte les groupes de corps textuels strictement
  identiques sans exposer contenus, empreintes individuelles ou IDs ; aucun
  doublon n'est fusionné automatiquement (2026-09-29).
- **【FAIT】** T-037e — L’audit croise les politiques de rétention
  déclarées et les périodes d’applicabilité, sans identifier les documents
  ni déduire une action automatique (2026-09-30).
- **【FAIT】** T-037f — L'audit croise aussi les statuts épistémiques déclarés
  et les périodes d'applicabilité, avec catégories `missing` et `invalid`,
  sans exposer de contenu, modifier le classement ou inférer un oubli
  (2026-09-30).
- **【FAIT】** T-037d — Prévisualisation Python en lecture seule des groupes
  exacts avec IDs et noms de champs divergents pour revue humaine ; aucune
  proposition de fusion automatique (2026-09-29).
- **【FAIT】** T-032k — L'approbation core contrôle aussi les relations des
  autres Informations sous le verrou Persistent et refuse une cible liée,
  illisible ou ambiguë ; les références textuelles historiques restent à
  examiner lors de la migration (2026-09-29).
- **【FAIT】** T-032l — La reprise d'une suppression interrompue reste bloquée
  lorsqu'une autre Information a créé une référence vers la cible déjà retirée,
  au lieu de finaliser silencieusement le reçu (2026-09-29).
- **【FAIT】** T-032m — Inventaire en lecture seule des relations Information
  core vers une cible présente, elle-même, externe ou absente, invalide ou
  ambiguë, sans imposer que toute relation cible une Information
  (2026-09-29).
- **【FAIT】** T-032t — L'inventaire des relations distingue, lorsque la racine
  historique est fournie, une cible absente dont l'identité Information est
  réservée par un reçu de suppression valide. Il refuse un reçu illisible ou
  symbolique, sans exposer les identifiants ni modifier les données
  (2026-09-30).
- **【FAIT】** T-032o — Un reçu de suppression réserve l’identité
  Information : la création refuse sa réutilisation après suppression ou
  interruption, ainsi qu’un reçu symbolique (2026-09-29).
- **【FAIT】** T-032p — Les écritures Information refusent une nouvelle relation
  structurée vers une identité réservée par un reçu de suppression lorsque la
  cible n'existe plus. Une demande encore en attente laisse les liens vers sa
  cible présente possibles ; ils bloquent alors l'approbation. Tests de
  création, mise à jour et demande en attente (2026-09-30).
- **【FAIT】** T-032q — L'audit en lecture seule signale aussi un reçu
  `CANCELLED` dont l'Information a disparu, au lieu de le traiter comme une
  annulation cohérente ; aucune réparation n'est tentée (2026-09-30).
- **【FAIT】** T-032r — Pour un reçu `PENDING_DELETE`, l'audit lit l'Information
  encore présente et distingue fichier illisible/identité discordante et
  révision différente de celle demandée ; un reçu `CANCELLED` vérifie aussi
  l'identité et la lisibilité sans exiger une révision inchangée. Aucune demande
  n'est modifiée
  (2026-09-30).
- **【FAIT】** T-032s — L'approbation d'une suppression refuse une création
  Thread liée dont le journal n'est pas encore `COMMITTED`, même si le fichier
  Thread n'existe pas encore. La reprise peut ainsi terminer son lien ; test
  d'interruption après journal et refus avant/après reprise (2026-09-30).
- **【FAIT】** T-032n — L’audit et la reprise des suppressions refusent aussi
  les parents symboliques situés au-dessus de `--root`, avant tout parcours
  ou toute mutation (2026-09-29).
- **【FAIT】** T-002 — Changement de statut Thread récupérable avec journal,
  snapshots, Event déterministe et commande `recover` explicite (`4e958aa`).
- **【FAIT】** T-003 — Format 0.2 préservant le Markdown arbitraire, avec lecture
  des fichiers du format core 0.1 (`b470bdf`).
- **【FAIT】** T-003a — Le lecteur core 0.1 refuse une section Relations absente
  ou de mauvais type et les sections d'objet de mauvais type, plutôt que de
  laisser un objet invalide circuler après la lecture (tests isolés,
  2026-09-30).
- **【FAIT】** T-003b — Les lecteurs Information et Thread core 0.1 lisent leurs
  identités uniquement dans la section Identity et refusent les champs requis
  dupliqués. Un corps libre ne peut plus suppléer une identité manquante
  (tests isolés, 2026-09-30).
- **【FAIT】** T-003c — Les blocs JSON des documents core 0.1 refusent les
  clés dupliquées et les nombres non standard comme NaN/Infinity au lieu de
  choisir silencieusement une valeur ; tests Information et Thread
  (2026-09-30).
- **【FAIT】** T-004 — Rejet des Events persistés ambigus ou invalides (`ff0fbc0`).
- **【FAIT】** T-005 — 458 tests exécutables réussis sur la copie de travail le
  2026-09-29 ; 5 tests de concurrence non exécutables dans cet environnement
  (socket local interdit). Cette preuve ne couvre pas la VM Debian.
- **【FAIT】** T-020 — Inventaire des formats et chemins produits par les anciens
  CLI, tableau de correspondance et outil de comptage en lecture seule ; voir
  `docs/MIGRATION.md` et `core/migration/inventory.py` (tests isolés, 2026-09-28).
- **【FAIT】** T-020b — L'inventaire compte aussi les Events et Operations du
  journal `thread-create-v1`, avec reconnaissance de `THREAD_CREATE` ; test
  sur arborescence isolée (2026-09-28).
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
- **【FAIT】** T-028b — Audit du dépôt, bilan de maturité et priorités revues dans
  `docs/AUDIT-2026-09-28.md`, entrée `README.md`, et documentation de la reprise
  synchronisée avec `recover-all` (2026-09-28).
- **【FAIT】** T-031a — `ThreadService.create_linked` exige le coordinateur
  récupérable ; le CLI passe par ce service. Rejeu idempotent et Event contrôlés
  dans deux tests isolés (2026-09-28).
- **【FAIT】** T-031b — `ThreadService.recover_all` reprend les créations avant
  les changements de statut ; le CLI l'utilise et l'absence d'un des deux
  coordinateurs est refusée (2026-09-28).
- **【FAIT】** T-031c — Inventaire des anciens écrivains ; le controller conserve
  son rôle sur YAML isolé, verrouille ses mutations persistantes et refuse une
  racine contenant Information/Thread/journaux core. `memory-relations` reste
  limité à Working historique jusqu'à migration ; tests de refus isolés
  (2026-09-29).
- **【FAIT】** T-031aa — Le garde du controller historique refuse aussi les
  ancêtres symboliques des répertoires Persistent/History et du journal
  d'opérations, avant de parcourir des données potentiellement externes
  (tests isolés, 2026-09-30).
- **【FAIT】** T-031ab — Le garde refuse également un journal Event core
  `thread-create-v1` ou `thread-status-v1` conservé sans son journal Operation,
  plutôt que de conclure à tort que la racine est purement historique
  (test isolé, 2026-09-30).
- **【FAIT】** T-031ac — L'ancien CLI `memory-relations add` refuse les
  ancêtres symboliques de Working/Events/Reviews et ne lit plus une cible
  Information symbolique pendant sa recherche ; tests isolés sur des chemins
  externes (2026-09-30).
- **【FAIT】** T-031ad — Le verrou d'écriture partagé refuse une racine ou un
  fichier `.write.lock` symbolique avant ouverture ; tests isolés sans écriture
  sur une cible externe (2026-09-30).
- **【FAIT】** T-031ae — Les entrées d'écriture du controller historique
  refusent les racines de sortie liées ; la résolution de Review refuse un
  `information_id` contenant un chemin et une cible Information symbolique
  avant lecture (tests isolés, 2026-09-30).
- **【FAIT】** T-031af — La configuration conserve le chemin explicite de
  `MEMORY_ENGINE_ROOT` sans résoudre les liens avant les gardes de stockage ;
  test en sous-processus vérifiant qu'une racine liée ne crée aucun dossier
  dans sa cible (2026-09-30).
- **【FAIT】** T-031ag — Le plan d'exécution historique refuse un ID Information
  ou Operation contenant un chemin et une source hors Working ou symbolique ;
  l'entrée d'exécution recontrôle les identités et la source, et les opérations
  STORE/UPDATE directes recontrôlent leur identité et la source avant lecture
  (tests isolés, 2026-09-30).
- **【FAIT】** T-031ah — Le backend Information refuse avant création ou mise à
  jour les conteneurs structurels de mauvais type que son propre lecteur 0.2
  rejetterait, ainsi qu'une identité non textuelle ; tests de non-écriture et
  de conservation de la version précédente (2026-09-30).
- **【FAIT】** T-031ai — Le dépôt Event vérifie que l'Event sérialisé se relit
  sans perte avant sa publication append-only ; les tuples convertis en listes
  dans les preuves ou la transition sont refusés sans créer de fichier
  (2026-09-30).
- **【FAIT】** T-031aj — Le dépôt Operation valide les identités et les types du
  plan à l'écriture comme à la lecture ; une création Thread avec cible non
  textuelle ou snapshot non textuel ne peut plus produire un journal inutilisable.
  La sérialisation refuse les constantes numériques non JSON (2026-09-30).
- **【FAIT】** T-031ak — Les lecteurs JSON du noyau, des Events, Operations et
  reçus refusent un nombre dont l'exposant déborde en infini Python
  (`1e10000`) ; l'inventaire historique le classe comme invalide au lieu de
  reconnaître un journal exploitable (2026-09-30).
- **【FAIT】** T-031d — `ThreadStorage.create` vérifie les cibles `CONCERNS` sous
  les verrous persistent → threads ; la mise à jour directe ne peut plus changer
  ces cibles. Cela empêche une relation orpheline produite par l'API bas niveau,
  sans ajouter de journal/Event à cette API (2026-09-29).
- **【FAIT】** T-031e — L'ancien CLI `memory-relations add` refuse les sources
  hors `memory/working/*.md` et sérialise ses propres ajouts sous verrou Working.
  La coordination complète avec le controller YAML reste à faire ou à remplacer
  lors de la migration (2026-09-29).
- **【FAIT】** T-031f — Le controller historique partage maintenant le verrou
  Working pour `ingest`, `update` Working et `review`, et refuse les chemins
  de mise à jour hors des racines attendues ; test de contention entre threads
  (2026-09-29). Events et Reviews restent non transactionnels.
- **【FAIT】** T-031g — `memory-relations` publie source, Event et Review avec
  remplacement atomique ; son ajout modifie uniquement le champ YAML
  `relations` du front matter, conserve le corps et refuse les blocs inconnus
  sans perte de données. Les trois fichiers ne forment toujours pas une
  transaction récupérable (2026-09-29).
- **【FAIT】** T-031h — Le controller historique publie ses Information, Event,
  Review et reçus d'opération par écriture atomique avec synchronisation disque ;
  les écritures sur plusieurs fichiers restent sans transaction commune
  (2026-09-29).
- **【FAIT】** T-031i — Le stockage Thread refuse un répertoire ou un fichier
  Thread symbolique lors des lectures, créations et suppressions, sans suivre
  une cible extérieure (2026-09-29).
- **【FAIT】** T-031w — Le constructeur Thread refuse également une racine
  `persistent/` symbolique avant de créer `threads/` (2026-09-29).
- **【FAIT】** T-031x — Les quatre dépôts core refusent dès leur construction
  tout parent symbolique dans les chemins de stockage, avant la création des
  répertoires ; contrôle commun et tests isolés (2026-09-29).
- **【FAIT】** T-031z — Les lecteurs historiques Information et Thread
  rejettent une révision zéro comme les lecteurs du format core 0.2
  (2026-09-29).
- **【FAIT】** T-031y — La création commune des répertoires vérifie tous les
  chemins configurés avant la première écriture et rejette les parents
  symboliques, y compris avec les chemins par défaut (2026-09-29).
- **【FAIT】** T-031j — Le backend Information refuse les racines de stockage et
  fichiers Information symboliques pour les lectures directes, ignore ces
  entrées lors du listing et refuse leur écrasement à la création
  (2026-09-29).
- **【FAIT】** T-031k — Les dépôts Event et Operation refusent les répertoires
  symboliques et les fichiers symboliques au chargement ; leur création ne
  remplace pas un lien symbolique existant (2026-09-29).
- **【FAIT】** T-031l — `FilesystemBackend.list` et donc `search` écartent une
  Information dont l'identifiant interne ne correspond pas au nom du fichier,
  comme le faisait déjà `get` (2026-09-29).
- **【FAIT】** T-031m — Les quatre dépôts core utilisent la même publication
  atomique avec synchronisation disque et nettoyage du fichier temporaire en
  cas d'échec de remplacement ; suite existante vérifiée (2026-09-29).
- **【FAIT】** T-031n — Le backend refuse les révisions booléennes ou de mauvais
  type avant la création et la mise à jour d'une Information ; un fichier ainsi
  créé ne pouvait auparavant être relu par le format 0.2 (2026-09-29).
- **【FAIT】** T-031o — Le domaine et le stockage Thread refusent les révisions
  booléennes et les révisions attendues de mauvais type avant toute écriture ;
  la valeur entière 0 conserve son comportement de conflit de révision
  (2026-09-29).
- **【FAIT】** T-031p — Le modèle Operation refuse les révisions négatives,
  booléennes ou de mauvais type avant la création du journal ; quatre cas
  de régression (2026-09-29).
- **【FAIT】** T-031q — Une mise à jour Information sérialise une copie à la
  révision suivante ; un échec de publication ne modifie plus la révision de
  l'objet fourni par l'appelant (2026-09-29).
- **【FAIT】** T-031r — Les dépôts core traduisent les fichiers UTF-8 corrompus
  en erreurs métier lors des lectures directes ; le listing Information les
  écarte comme les autres documents invalides (2026-09-29).
- **【FAIT】** T-031s — Le dépôt Operation refuse les clés JSON inconnues du
  journal ou du plan avant une réécriture qui les aurait perdues ; deux cas
  de régression conservent les octets d'origine (2026-09-29).
- **【FAIT】** T-031t — Le lecteur Event core 0.2 refuse les champs structurels
  inconnus au sommet et dans ses blocs au lieu de les omettre silencieusement ;
  les données libres des transitions restent libres (2026-09-29).
- **【FAIT】** T-031u — Le lecteur Event core 0.2 ne remplace plus des blocs
  structurels vides mais de mauvais type par des conteneurs valides ; quatre
  formes invalides testées (2026-09-29).
- **【FAIT】** T-031v — Le lecteur de journal Operation refuse les clés JSON
  dupliquées et les constantes non standard au lieu de retenir une valeur
  arbitraire ; trois cas de régression (2026-09-29).
- **【FAIT】** T-035a — La recherche locale parcourt toutes les Informations
  valides sans plafond implicite de 10 000 fichiers ; test d'un résultat placé
  après ce seuil (2026-09-29). Les performances réelles restent à mesurer.
- **【FAIT】** T-035b — Le listing filtré arrête la lecture dès que la page
  demandée est complète, au lieu de parcourir tout le corpus pour les premières
  pages (2026-09-29). Mesurer le coût des pages profondes sur la VM.
- **【FAIT】** T-035e — Le listing refuse les décalages et limites booléens ou
  non entiers ainsi que les filtres de mauvaise forme avant de parcourir les
  fichiers ; tests isolés (2026-09-30).
- **【FAIT】** T-035c — Sortie brutale d'un processus à chacune des cinq
  frontières de la création Thread liée (journal préparé, en application,
  Thread, Event, commit) ; reprise et rejeu sans Event dupliqué. Cela ne simule
  pas une coupure d'alimentation (2026-09-29).
- **【FAIT】** T-035f — Sortie brutale d'un processus aux quatre états de
  suppression Information (demande, marqueur `APPLYING_DELETE`, fichier retiré,
  reçu `DELETED`) ; contrôle de la reprise explicite et de son idempotence sur
  répertoire isolé. Ce test ne simule pas une coupure d'alimentation
  (2026-09-30).
- **【FAIT】** T-035d — Script de mesure sur données synthétiques temporaires,
  exécuté localement à 15 000 fichiers ; chiffres et limites dans
  `docs/PERFORMANCE.md`. À refaire sur copie représentative de la VM
  (2026-09-29).
- **【FAIT】** T-034a — Première interface interne d'assemblage de contexte
  structurée, bornée en caractères et traçable par ID/révision ; vérification
  sur fichiers core. Un budget de tokens avec compteur injectable a ensuite
  été ajouté ; la pertinence, le choix du compteur côté consommateur, la
  politique d'accès et l'intégration Core/Qdrant restent à définir
  (2026-09-29).
- **【FAIT】** T-034b — Les extraits de contexte portent séparément les étiquettes
  épistémique, opérationnelle et de confiance lorsqu'elles existent ; leur
  politique de sélection et leur rendu pour le modèle restent à définir
  (2026-09-29).
- **【FAIT】** T-034c — La recherche accepte un décalage de pagination et
  l'assembleur peut dépasser une page entière de résultats sans texte
  utilisable tout en bornant chaque réponse (2026-09-29).
- **【FAIT】** T-034d — La recherche refuse les bornes de pagination de mauvais
  type, booléennes ou hors plage au lieu de les convertir silencieusement
  (2026-09-29).
- **【FAIT】** T-034e — L'assembleur garde chaque page de résultats à 100
  éléments même si l'appelant demande beaucoup d'extraits (2026-09-29).
- **【FAIT】** T-034f — L'assembleur s'arrête si un backend renvoie deux fois
  la même page entière au lieu de respecter le décalage (2026-09-29).
- **【FAIT】** T-034g — L'assembleur détecte aussi une alternance cyclique de
  pages entières déjà reçues et arrête la récupération (2026-09-29).
- **【FAIT】** T-024a — Manifeste déterministe en lecture seule des fichiers
  Information core (ID, révision, empreinte) ; échoue sur source invalide ou
  symbolique. Aucun index Qdrant n'est écrit (2026-09-29).
- **【FAIT】** T-024b — Comparaison déterministe de deux manifestes pour préparer
  ajouts, actualisations et retraits d'un futur index ; scénario intégré avec
  mise à jour et suppression Information, sans écriture dans l'index
  (2026-09-29).
- **【FAIT】** T-024c — Commande en lecture seule sur une ou deux copies :
  comptes, empreintes et nombres de changements sans sortie des contenus ;
  refuse une Information mal identifiée (2026-09-29).
- **【FAIT】** T-024d — La comparaison refuse les entrées invalides, identités
  répétées et empreintes globales incohérentes des manifestes fournis, avant
  de calculer les changements pour l'index (2026-09-29).
- **【FAIT】** T-024e — La construction du manifeste refuse une Information dont
  l'identifiant contient des caractères que le backend ne peut adresser,
  même si son nom de fichier et son identifiant interne concordent (2026-09-29).
- **【FAIT】** T-024f — L'API directe du manifeste refuse aussi les parents
  symboliques de la source avant la lecture des Informations (2026-09-29).
- **【FAIT】** T-028b — Le tableau des écrivains dans `docs/ARCHITECTURE.md`
  décrit les verrous et écritures atomiques des services historiques sans leur
  attribuer une transaction multi-fichiers (2026-09-29).
- **【FAIT】** T-032a — Une demande `PENDING_DELETE` ne peut plus être écrasée
  par une autre ; le rejeu strictement identique est sans écriture, un reçu
  illisible bloque la demande (trois tests, 2026-09-28).
- **【FAIT】** T-032b — L'approbation et l'annulation vérifient l'identité
  Information du reçu avant toute décision ; deux cas discordants testés
  (2026-09-28).
- **【FAIT】** T-032c — Lecture commune et stricte des reçus pour demande,
  approbation et annulation ; un JSON illisible bloque les deux décisions sans
  modifier l'Information (2026-09-28).
- **【FAIT】** T-032d — Pour les nouvelles suppressions, marqueur durable
  `APPLYING_DELETE` et empreinte du fichier avant retrait ; reprise explicite
  sous verrous avec le même identifiant d'opération, testée après interruption
  avant et après le retrait. L'audit signale les opérations à reprendre
  (`9d7c162`, 2026-09-28).
- **【FAIT】** T-032e — Commande explicite d'audit puis reprise `--apply` des
  seuls reçus `APPLYING_DELETE`, avec rapport des blocages et rejeu idempotent ;
  les anciens `PENDING_DELETE` incohérents restent pour revue humaine
  (2026-09-29).
- **【FAIT】** T-032f — Création, lecture, audit et approbation des demandes de
  suppression exigent auteur, motif, révision et identifiant d'opération
  utilisables ; les reçus incomplets bloquent la décision (2026-09-29).
- **【FAIT】** T-032g — La lecture du reçu de suppression est partagée par
  l'audit et le backend ; les clés JSON répétées et les nombres non finis
  bloquent l'approbation sans toucher à l'Information (2026-09-29).
- **【FAIT】** T-032h — Les champs inconnus et les empreintes prématurées d'un
  reçu en attente sont rejetés avant toute réécriture ; l'audit et le backend
  signalent la même anomalie (2026-09-29).
- **【FAIT】** T-032i — L'audit et la reprise explicite refusent les liens
  symboliques sur les répertoires parents `memory` et `memory/history` avant
  de parcourir les demandes (2026-09-29).
- **【FAIT】** T-032j — L'approbation et l'annulation refusent un reçu de
  suppression symbolique cassé au lieu de le traiter comme absent
  (2026-09-29).
- **【FAIT】** T-033a — Simulation déterministe en lecture seule des Informations
  anciennes : proposition de mapping, fichiers candidats/bloqués, inventaire
  Events/Reviews/Operations et blocage des valeurs YAML non représentables en
  JSON ; tests sur copie isolée (2026-09-29).
- **【FAIT】** T-033b — La simulation construit un aperçu core en mémoire et
  vérifie son aller-retour au format 0.2, y compris corps CRLF et révision
  structurée. Aucune conversion sur disque ni validation sémantique des
  relations n'est effectuée (2026-09-29).
- **【FAIT】** T-033c — La simulation signale les relations vers une cible absente,
  ambiguë ou bloquée (avec propagation), ainsi que les relations textuelles
  présentes dans le corps Markdown ; aucune cible n'est devinée ou réécrite
  (2026-09-29).
- **【FAIT】** T-033d — Le schéma Thread décrit le retour `TESTING` vers
  `IMPLEMENTATION` déjà autorisé par le code ; les relations Information
  utilisent `RELATED_TO` comme le modèle et l'ancien CLI. La simulation signale
  `RELATES_TO` pour décision au lieu de le renommer (2026-09-29).
- **【FAIT】** T-033e — Rapport en lecture seule des types d'Events historiques
  et statuts de Reviews reconnus, avec signalement des valeurs inconnues sans
  exposition de contenu ; `STORED` et `RELATION_ADDED` restent à archiver ou
  convertir selon une politique explicite (2026-09-29).
- **【FAIT】** T-033f — Le rapport signale les références `information_id`
  historiques absentes ou invalides pour Events et Reviews, sans exposer leurs
  valeurs ni décider qu'une suppression passée était illégitime (2026-09-29).
- **【FAIT】** T-033g — Les références historiques ambiguës entre Working et
  Persistent, structurellement invalides ou traversant un lien symbolique sont
  signalées sans lire la cible externe (2026-09-29).
- **【FAIT】** T-033h — Le précontrôle refuse les indicateurs de révision YAML
  structurée dont le type ne correspond pas au schéma, avant de proposer une
  candidate à convertir (2026-09-29).
- **【FAIT】** T-033i — La simulation bloque les types de relations inconnus ou
  invalides même quand la cible existe, sans exposer la valeur dans le rapport
  (2026-09-29).
- **【FAIT】** T-033j — Le précontrôle bloque les révisions structurées dont le
  numéro précédent ou l'indicateur `is_revision` contredit l'historique déclaré,
  sans inventer une chronologie de remplacement (2026-09-29).
- **【FAIT】** T-033k — La simulation ne compte un Event core 0.2 historique
  comme valide qu'après lecture complète et contrôle de l'identité correspondant
  au nom du fichier (2026-09-29).
- **【FAIT】** T-033o — L'inventaire et le précontrôle refusent un ancêtre
  symbolique de la racine du moteur avant lecture ; la simulation échoue de
  même via l'inventaire. Test sur un chemin parent lié (2026-09-30).
- **【FAIT】** T-033p — L'inventaire classe les fichiers JSON ambigus (clés
  dupliquées) et les constantes non standard (`NaN`, etc.) comme invalides ;
  test de deux journaux sans écriture ni exposition du contenu (2026-09-30).
- **【FAIT】** T-033q — La simulation bloque `INSTANCE_OF` avec un motif distinct
  car l'ancien modèle Relation et son CLI l'acceptent alors que la liste du
  schéma Information l'omet ; aucune décision de renommage n'est implicite
  (2026-09-30).
- **【FAIT】** T-033r — La simulation distingue aussi les types présents
  seulement dans `information.md` des types totalement inconnus. Ces extensions
  restent bloquées en attente d'une décision de contrat (2026-09-30).
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
- **【FAIT】** T-022m — Suppression core bloquée si une relation `CONCERNS` ne
  désigne pas une cible fiable ; l'audit des liens signale aussi deux cibles
  contradictoires (trois cas testés, 2026-09-28).
- **【FAIT】** T-022n — L'audit des liens refuse une racine dont un ancêtre est un
  lien symbolique et ignore `memory/` lié vers un autre arbre ; deux tests de
  non-traversée sur données isolées (2026-09-30).
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
6. **【À VALIDER】** T-015 — Définir comment lancer `recover-all` avant toute nouvelle
   écriture après redémarrage ; aucun job automatique n'existe actuellement.
   Proposition documentée dans `docs/DEPLOYMENT.md` : reprendre d'abord les
   créations/statuts Thread, auditer ensuite les suppressions Information et
   garder les écrivains arrêtés en présence d'un blocage. Vérifier cet ordre
   avec les services et données réels avant toute automatisation.

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
  orphelins et protègent la suppression core. T-022f à T-022m ajoutent un chemin
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
  certains états de suppression interrompue ; les nouvelles demandes en
  `APPLYING_DELETE` sont reprenables explicitement, mais les anciennes demandes
  ambiguës exigent toujours une revue humaine. Ne pas annoncer une garantie
  générale de suppression avant les essais sur VM et l'audit des écrivains.
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

## Concepts Eidolon hors Memory Engine

Les idées concernant Eidolon Core, agents, skills, modèles, Policy Engine,
EidolonOS, robotique et autres sous-projets sont volontairement suivies dans
[EIDOLON-GLOBAL-CONCEPTS.md](EIDOLON-GLOBAL-CONCEPTS.md). Cette TODO reste
strictement réservée au développement et au déploiement du Memory Engine.

## Critère de livraison

Le noyau sera considéré déployable lorsque la migration nécessaire sera décidée,
les tests complets et les parcours d'intégration passeront sur Debian avec une
racine isolée, qu'une sauvegarde restaurable sera vérifiée, et que la reprise
opérationnelle et les services réellement utilisés seront validés. Ces critères
ne supposent pas que toutes les extensions proposées soient nécessaires à la
première mise en service.
