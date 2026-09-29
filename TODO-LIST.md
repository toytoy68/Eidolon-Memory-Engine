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

Dernière mise à jour : 2026-09-29. Branche suivie : `refactor/architecture-v1`.
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

Qdrant, s'il est raccordé, serait un index **reconstructible** à partir des
fichiers. Son emplacement et le découpage `indexing/` restent à valider ; aucun
connecteur Qdrant opérationnel n'est attesté par cette branche.

## Priorités après l'audit du dépôt

1. **【À FAIRE】** T-010 à T-015 — Sur VM, identifier les écrivains et données,
   sauvegarder et vérifier une restauration sur copie, tester les cinq cas de
   concurrence et définir l'ordre de `recover-all` au démarrage. Ne pas ouvrir
   les écritures core sur les données historiques avant cette revue.
2. **【À FAIRE】** T-031 — Définir le chemin canonique d'écriture Thread et
   Information : recenser tous les appels directs à `ThreadStorage`, au backend
   et aux anciens CLI ; adapter ou isoler ceux qui contournent les journaux,
   verrous ou Events. T-031a/b raccordent création et reprise dans le service ;
   les API bas niveau et les anciens services restent à adapter après migration.
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
4. **【À FAIRE】** T-033 — La première simulation **sans écriture** des
   Informations historiques propose une correspondance champ par champ et
   signale les blocages ainsi que les Events/Reviews à décider. Restent la
   validation des pertes sémantiques, des relations, de la révision structurée
   et du format cible avant un convertisseur effectif.
5. **【À VALIDER】** T-034 — Contrats d'intégration Eidolon Core et Qdrant : API,
   identité/authentification, erreurs, index dérivé, reconstruction et rattrapage
   après écriture. Tester sur copie anonymisée avant exposition au système réel.
6. **【À FAIRE】** T-035 — Enrichir les fixtures avec des exemples anonymisés
   représentatifs de la VM, tester les performances et l'interruption aux
   frontières de chaque écriture multi-fichiers ; distinguer crash processus et
   coupure d'alimentation dans les garanties.
7. **【EN ATTENTE】** T-029 — Reprendre le tableau de bord et son accès LAN lorsque
   la priorité au noyau sera levée par le projet.

## État vérifié dans le dépôt

- **【FAIT】** T-001 — Modèles, stockage de fichiers et requêtes des Informations
  et Threads, dépôts Event et Operation, contrôle de révision des Threads.
- **【FAIT】** T-002 — Changement de statut Thread récupérable avec journal,
  snapshots, Event déterministe et commande `recover` explicite (`4e958aa`).
- **【FAIT】** T-003 — Format 0.2 préservant le Markdown arbitraire, avec lecture
  des fichiers du format core 0.1 (`b470bdf`).
- **【FAIT】** T-004 — Rejet des Events persistés ambigus ou invalides (`ff0fbc0`).
- **【FAIT】** T-005 — 379 tests exécutables réussis sur la copie de travail le
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
- **【FAIT】** T-035c — Sortie brutale d'un processus à chacune des cinq
  frontières de la création Thread liée (journal préparé, en application,
  Thread, Event, commit) ; reprise et rejeu sans Event dupliqué. Cela ne simule
  pas une coupure d'alimentation (2026-09-29).
- **【FAIT】** T-035d — Script de mesure sur données synthétiques temporaires,
  exécuté localement à 15 000 fichiers ; chiffres et limites dans
  `docs/PERFORMANCE.md`. À refaire sur copie représentative de la VM
  (2026-09-29).
- **【FAIT】** T-034a — Première interface interne d'assemblage de contexte
  structurée, bornée en caractères et traçable par ID/révision ; vérification
  sur fichiers core. Pertinence, budgets en tokens, politique d'accès et
  intégration Core/Qdrant restent à définir (2026-09-29).
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
