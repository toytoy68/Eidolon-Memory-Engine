# Memory Engine — TODO active

Mise à jour : **2026-10-02**, audit initial `a779c9d`, T-048 puis refus migration mixte et commandes projet livrés, branche
`refactor/architecture-v1`. **Estimation globale gelée : 45 %. Grille : 52,75
points, inchangée.** Aucun avancement chiffré pour cet audit documentaire.

Références : [bilan actuel](docs/AUDIT-2026-10-02.md),
[architecture cible](docs/ARCHITECTURE-CIBLE.md),
[architecture actuelle](docs/ARCHITECTURE.md), [échanges Claude](ECHANGES.md).
L'[historique intégral](TODO-HISTORY-2026-10-01.md) conserve les anciens IDs et
preuves. Ses statuts et ordres périmés sont remplacés par ce fichier ; les
anciennes sous-tâches ne sont pas renumérotées.

## Convention et périmètre

- **FAIT EN LOCAL** : code et preuve comportementale, pas validation VM.
- **PARTIEL** : livrable présent mais critère d'achèvement non satisfait.
- **À FAIRE** : fonctionnalité/correction non livrée.
- **NON TESTÉ VM** : aucune preuve sur la machine réelle.
- **DIFFÉRÉ** : hors des travaux autorisés actuellement.
- Toute fonctionnalité/correction doit avoir un test comportemental vérifié
  rouge sans elle, un commit cohérent et ses limites explicites. Pas de test
  artificiel pour une édition documentaire.

Pas de travail sur Eidolon Core, Hermes, Qdrant ni de nouvelles validations
ou micro-durcissements T-031a…bc. Les constats datés restent conservés ; la séance du matin autorisée par toytoy
poursuit les lots prioritaires avec preuves et documentation par étape. Revue Claude demandée E-005 à E-007 ;
revue complète reçue par fichier, patch vérifié mais non intégré. Voir
[la contre-revue](docs/REVUE-CLAUDE-2026-10-01.md). Une revue ne vaut pas validation VM.

## Dernière vérification

Suite complète relancée lors du bilan du 02/10 sur `43a1214` : **947 réussis,
5 échecs d’environnement, 43,60 s**, pytest 9.1.1/Python 3.12.14, aucun
désélectionné. Les cinq tests Manager échouent à la création d’une socket
interdite avant scénario métier. 141 cas ajoutés depuis `9063313` (21 exécution,
15 rappel, 17 rapprochement, 16 catalogue, 8 scans, 25 cycle de vie, 19 raccordement, 20 entretien). Arrêts de processus, courses sans Manager et preuves négatives
comportementales détaillés dans les contrats. Aucune VM, donnée réelle ou
coupure électrique testée.

## Ordre prioritaire

| Ordre | Tâches | Résultat attendu |
| --- | --- | --- |
| 1 — Avant exploitation | T-048, T-021/T-033 | Reprise/inventaire et refus des sources mixtes livrés ; import opérationnel et recette VM restent ouverts |
| 2 — Parcours métier | T-031/T-041 puis T-043 | Commandes Thread et assemblage livrés ; façade complète et exécution des plans avec révisions/reprise |
| 3 — Projet utilisable | T-044 puis T-045 | Ajouter une Information au même projet, dossier actualisé ou explicitement périmé, catalogue reconstructible |
| Avant ingestion intensive | T-049 | Réduire les scans sans perdre réservations/conflits/reprise ; lot distinct |
| 4 — Disponibilité | T-046, décisions T-050 | Haute/intermédiaire/basse, réexamens et échéances durables |
| 5 — Rappel utile | T-047/T-036/T-022 | Client factice complet, sources/contexte/temps, budgets et mesures |
| Voie VM distincte | T-010 à T-015/T-032 | Copie arrêtée, restauration, concurrence, audits et données réelles |

On peut recueillir des constats VM avant T-048, mais un rapport incomplet ne
vaut pas autorisation de démarrage. Aucun résultat local ne remplace la recette
VM du commit candidat.

## Lots à réaliser

### T-048 — Reprise et inventaire complets — FAIT EN LOCAL / NON TESTÉ VM

A-01/A-02 corrigés : les trois recover Thread signalent FAILED ; famille
thread-delete-v1 inventoriée. Scan des fichiers et sous-familles inconnus sans
traverser les ancêtres symboliques, distinction verrous techniques/archives.

`core.operations.readiness` fournit un contrôle en lecture seule et la reprise
globale avec relecture finale sur disque. PREPARED/APPLYING et compaction sont
reprenables ; FAILED/inconnu/corrompu exigent une revue. PENDING_DELETE valide
reste en attente ; APPLYING_DELETE est repris. Le CLI et la recette VM utilisent
le contrôle. Les anciens appels par famille ne deviennent pas une barrière globale.

Preuves : 21 nouveaux cas dans `tests/test_startup_readiness.py`, notamment
CLI non nul, suppression Information interrompue, faux succès de coordinateur,
ancêtres symboliques et recette KO. Retrait des corrections : 3 + 6 + 1 + 1
échecs comportementaux. Voir [contrat et limites](docs/STARTUP-READINESS.md).

Restant exploitation : installation du contrôle dans les services réels,
dépendances sur corpus VM, commande de résolution humaine de FAILED avec examen
des effets partiels/réservations/rejeu. Aucun abandon automatique livré. Une
lecture ponctuelle ne protège pas contre le redémarrage ultérieur d'un écrivain legacy.

### T-021 / T-033 — Migration opérationnelle — PARTIEL / NON TESTÉ VM

Fait : simulation, conversion séparée idempotente, rejets, archives exactes
Events/Reviews/Working/opérations, vérification indépendante ; 500 Informations
legacy couvertes par les tests.

A-03 corrigé par refus préalable : avant toute création ou écriture dans la
destination, le convertisseur rejette les reçus de suppression (tous états),
les reçus compacts et les journaux opérationnels, y compris familles inconnues.
Le rapport est retourné à l’appelant/CLI (code non nul), sans même écrire
migration-report.json. Une destination préexistante reste inchangée. Les seules
opérations archivables par ce chemin sont les anciens enregistrements legacy
reconnus directement dans history/operations ; les liens ne sont pas suivis.

Preuves : 12 nouveaux cas rouges sur la base puis verts ; **47 tests de migration
réussis** avec conversion, simulation et vérification. La source demeure intacte.
Les versions de reçus injectées sont des données synthétiques ; aucune VM.

Restant : import opérationnel dédié conservant réservations DELETED/CANCELLED,
reçus de rejeu, Threads/actions et révisions ; aucune activation implicite des
journaux archivés. Le refus préalable ferme le défaut, mais ne livre pas cet
import. Migration réelle et revue des pertes de sens toujours non testées.

### T-031 / T-041 — Services métier canoniques — PARTIEL / NON TESTÉ VM

Fait : Information create/update/recover/compact ; Thread création liée,
statut et suppression journalisés. T-039 corrige le delete implicite canonique.
Preuves : tests Information/Thread et interruptions, commits `4f36f70`,
`0460f68`, `b967bf4`.

Ajout livré au lot du soir : famille THREAD_UPDATE et assemblage canonique
`ThreadService.for_backend`. Commandes LINK/UNLINK, ADD_ACTION/ACTION_STATUS et
DETAILS (titre/objectif/contexte), journalisées avec Event, révision attendue,
snapshots et rejeu sans résurrection. Réservations de liens, gardes des autres
familles, dossiers et contrôle de démarrage raccordés. Contrat et API/CLI :
[THREAD-UPDATES.md](docs/THREAD-UPDATES.md).

Preuves : 19 nouveaux cas, dont quatre interruptions par exception, deux arrêts
de processus, trois courses multiprocessus sans Manager. Trois suppressions
expérimentales de garanties donnent chacune un échec comportemental ; code
restauré après ces preuves. Groupe Thread/Events/reprise : 69 réussis.

Façade du premier parcours T-043 livrée ; restant : autres parcours,
recensement/migration des appelants métier et isolation des écrivains historiques
(T-023). L’assemblage Thread ne remplace pas une transaction globale ni le
contrôle de démarrage. Les primitives de stockage restent distinctes.

### T-043 — Politique et exécution des plans — PARTIEL, PREMIER PARCOURS LIVRÉ

Fait : plan déterministe expliqué sur qualifications explicites, 20 tests du
planner. Nouvelle tranche : preview sans écriture, exécution STORE/UPDATE vers
un projet existant, LINK si nécessaire, reconstruction du dossier et reçu final.
Versions de règles, snapshots et révisions revalidés ; intention durable et
sous-commandes rejouables. Inventaire/reprise globale et réservations raccordés.
Contrat : [ROUTING-EXECUTION.md](docs/ROUTING-EXECUTION.md).

Preuves : 21 nouveaux cas dont quatre arrêts de processus, deux scénarios
concurrents et deux interruptions dans les enfants. Groupe parcours/reprise :
42 réussis sur la première tranche. Plans ambigus, projet absent et retrait
d’obstacle refusés avant mutation. Aucun statut de vérité modifié par rôle ou pertinence.

Extension du 02/10 : format 2 opt-in (`--with-lifecycle`), disponibilité intégrée
à l’écriture initiale et échéance persistante enregistrée après dossier. Format 1
inchangé. Reprise globale, annulation intercalée et garde parent avant effet ;
19 nouveaux cas, deux arrêts réels de processus. Groupe ciblé 59 réussis.

Restant : création explicite de nouveaux projets par ce parcours, branches
NONE/REVIEW/lieu/thème, autres politiques et qualification automatique.
Disponibilité encore différée pour les seuls anciens plans format 1.
Pas de client externe ou de VM validé.

### T-044 — Dossiers vivants — PARTIEL

Fait : projection explicite depuis Thread/CONCERNS, récapitulatif, sources,
actions/décisions, mots-clés, notes préservées et état de fraîcheur ; 8 tests,
`7616455`.

Fait en plus via T-043 : actualisation après STORE/UPDATE et rattachement du
nouveau parcours, avec reprise après l’écriture canonique.

Nouvelle tranche livrée : `reconcile` sans écriture et `reconcile --apply`,
rapprochement de tous les Threads/vues présents avec manifeste de dépendances
IDs/révisions/SHA-256. Répare créations, corrections, liens/actions et suppressions
hors routage ; les vues orphelines sont retrouvées depuis les fichiers dérivés.
Reprise par relance, sans réexécuter de commande canonique ; notes et CRLF
conservés. Readiness et frontières endommagées bloquent avant publication.
17 nouveaux cas dont arrêt de processus et deux réparateurs concurrents ;
groupe ciblé 69 réussis. Retraits de garanties : 1 + 1 + 1 assertions rouges,
code restauré. Contrat : [PROJECT-DOSSIERS.md](docs/PROJECT-DOSSIERS.md).

Raccordement du 02/10 : la passe d’entretien explicite répare les vues après
reprise et échéances, puis contrôle leur état final. Voir MAINTENANCE-PASS.md.
Restant : déclenchement système récurrent, coût des scans/verrous
T-049, édition concurrente/ingestion explicite des notes non reconstructibles.
Le rappel écarte le texte des vues et signale leur fraîcheur. Lieux/thèmes après
projets. Le manifeste est recalculé, pas un index incrémental. Définir la clôture de purge
sur les vues gérées par le moteur, distincte du DELETED canonique actuel et des
copies hors de son contrôle. Aucun effacement automatique de notes humaines.

### T-045 — Catalogue léger — FAIT EN LOCAL / NON TESTÉ VM

Fiches ID/révision/hash, mots-clés, nature, contexte, statuts, échéances,
disponibilité déclarée et pointeurs, sans corps d'Information. Membres de projet
résolus par CONCERNS. Reconstruction atomique, contrôle de fraîcheur complet,
reprise par relance et filtres de découverte. PENDING_DELETE exclu de query ;
suppression et correction rattrapées par rebuild, ancien catalogue refusé.
Contrat : [INFORMATION-CATALOGUE.md](docs/INFORMATION-CATALOGUE.md).

16 nouveaux cas, groupe ciblé 28 réussis, dont arrêt réel de processus.
Trois retraits de garanties donnent chacun un échec comportemental. Destruction/
reconstruction identique et disparition des anciens mots-clés vérifiées.
Rattrapage raccordé à la passe d’entretien explicite T-046.
Restant : récurrence système, mesure sur corpus réel et accélération
des lectures ; cette version scanne le canonique pour prouver la fraîcheur.
Aucun connecteur externe ni activation autonome des disponibilités.

### T-049 — Coût des journaux — RÉDUCTION LIVRÉE / INGESTION INTENSIVE NON VALIDÉE

Trois scans par nouvelle écriture Information ramenés à un seul : réservations
validées une fois sous verrous, puis abandonnées en fin de commande. Aucun cache
entre commandes ; lecteur complet des reçus conservé, version 999 et divergences
bloquantes. La compaction relit toujours son reçu avant retrait du snapshot.

Benchmark reproductible livré, 50/150/300 create et create+compact. À 300 :
59,39 → 20,42 s pour create, 57,11 → 30,01 s pour create+compact ; ouvertures
JSON 135 450 → 45 450 et 181 500 → 91 500. Audit et égalité canoniques valides.
8 nouveaux tests, dont échanges/concurrence multiprocessus sans Manager ;
preuves négatives 2 + 1 + 1 échecs, code restauré.
Contrat et rapports : [JOURNAL-SCAN-COST.md](docs/JOURNAL-SCAN-COST.md).

Mesure entretien sur `43a1214` : à 300 Informations/cinq projets, passe inactive
3,270 s (snapshots) ou 2,454 s (reçus compactés), cinq échéances 5,543 s ou
4,139 s. Toujours 7 890 ouvertures JSON en passe inactive. Rapport et protocole :
[MAINTENANCE-COST.md](docs/MAINTENANCE-COST.md). Sortie rapide inactive en
préparation seulement, mise de côté à la demande d’audit ; aucun gain livré.

Restant : sortie rapide vérifiée pour entretien inactif, suppression du scan
linéaire par commande, annuaire reconstructible
et preuve de divergence/reprise, autres familles, scans des dérivés, corpus et
objectifs VM. L'ingestion totale demeure quadratique. Pas d'autorisation
d'ingestion intensive déduite de la réduction locale.

Contexte de la mesure antérieure et de la proposition Claude :

[Mesure antérieure](docs/benchmarks/information-writes-2026-10-01.json) : 500
créations en 215,869 s ; 9,517 s pour les 100 premières, 75,585 s pour les 100
dernières. Non rejouée pendant cet audit. Comparer annuaire de réservations
reconstructible ou autre stratégie évitant les relectures complètes. Un cache
local ne doit masquer ni écriture concurrente ni divergence journal/reçu.

Preuves : benchmark reproductible à plusieurs tailles, comptage des lectures,
régressions de conflits/rejeu/compaction. Fixer ensuite les objectifs VM, sans
seuil arbitraire. Nécessaire avant ingestion intensive, pas avant une démo minime.
La proposition Claude reste non intégrée : son décodage léger accepte un reçu
version 999 que la base bloque. Préserver cette garantie. Elle lit encore tous
les reçus ; gain de constante possible, pas suppression du coût linéaire par
commande. Mesure 120 create+compact rapportée par Claude, non reproduite ici.

### T-046 / T-037 — Disponibilité et cycle de vie — PREMIÈRE TRANCHE LOCALE

Fait : niveaux explicites haute/intermédiaire/basse par écriture Information,
réexamen et acquittement de revue sans changer vérité/rétention/validité.
Déclencheurs REACTIVATE/RECHECK persistants, temps/contexte d'exécution explicites,
annulation avant effet, acquittement durable, reprise globale et rejeu sans
résurrection. SCHEDULED est une attente ; APPLYING est repris. Source modifiée
→ STALE, mobile/obstacle/inconnu → revue, activation inapplicable → SKIPPED.
Catalogue et rappel exposent disponibilité/besoin de revue ; filtre de niveau
optionnel au rappel. Contrat : [LIFECYCLE-TRIGGERS.md](docs/LIFECYCLE-TRIGGERS.md).
25 nouveaux cas ; groupe ciblé 77 réussis. Deux arrêts de processus, concurrence
sans Manager, preuves négatives 1 + 2 + 2 assertions rouges ; code restauré.

Raccordement au parcours qualifié livré en format 2 : voir T-043.
Passe d’entretien explicite livrée : reprise globale → échéances → dossiers
→ catalogue → relecture finale. Inspection sans écriture, résultat PARTIAL si
backlog, reprise par relance et notes conservées. 20 nouveaux cas, groupe ciblé
72 réussis, deux arrêts réels et concurrence sans Manager ; trois preuves
négatives. Contrat : [MAINTENANCE-PASS.md](docs/MAINTENANCE-PASS.md).
Restant : récurrence/charge/fenêtre horaire, dérivés incrémentaux et consommateurs
externes. Aucun ordonnanceur système ni job récurrent installé.

Tests à horloge contrôlée : échéance dépassée pendant l'arrêt, révision changée,
annulation, rejeu, chat non présenté comme position actuelle, obstacle contourné
à revérifier. Consolidation autonome après contrat ; contenu identique ne
signifie pas même sens.
Entretien récurrent retenu comme besoin, pas installé : fenêtre matinale,
report si occupé, lots reprenables et rattrapage après arrêt. Le profil léger
quotidien / approfondi hebdomadaire proposé dans la discussion reste à fixer,
ainsi que l'heure exacte (souhait 3–4 h, fenêtre documentaire 4–8 h), les critères
d'occupation et d'inactivité. Il ne doit ni décider une vérité ni supprimer sur
le seul critère d'âge. Aucun cron, timer système ou automation externe créé.

### T-047 / T-036 / T-022 — Rappel et parcours complet — PREMIÈRE TRANCHE LOCALE

Fait : lexical_v1, budgets d’extraits, rappel appliquant contexte/temps et profil
operational/historical. Expiré/hors contexte/réfuté/supplanté/suppression en attente
exclus du mode operational ; inconnus et conflits visibles avec needs_review.
Provenance, temporalité, contexte, vérification, relations et raisons exposés.
Filtrage avant budgets et pagination ; sélection projet par CONCERNS ; canonique
courant et signalement CURRENT/STALE/MISSING du dossier. Reprise non résolue bloquante.

Parcours client factice démontré : entrée qualifiée → écriture → projet existant
→ dossier → rappel, puis correction canonique et dossier STALE. API sur la même
façade RoutingExecutor et CLI. Contrat : [CONTEXTUAL-RECALL.md](docs/CONTEXTUAL-RECALL.md).
15 nouveaux cas, groupe ciblé 65 réussis. Retirer filtre/readiness/needs_review
produit 1 + 1 + 3 échecs comportementaux ; code restauré.

Restant : qualité/latence sur corpus représentatif, politiques plus fines,
catalogue/recherche sémantique, clients réels et VM. Le mode historique ne restaure
pas les révisions textuelles remplacées. Les budgets ne couvrent pas les
métadonnées ni le prompt final ; verrou/scans à mesurer sous T-049.

### T-050 — Histoire et effacement — À CONCEVOIR

Sans rouvrir D1–D9, distinguer observations conservées et révisions remplacées.
Le reçu compact ne restitue pas l'ancien texte. Décider si une archive de
révisions est nécessaire et son interaction avec suppression, snapshots Thread,
dossiers/notes et sauvegardes. Pas de conservation cachée de contenu supprimé.
Tests futurs : histoire conservée selon politique, dérivés retirés, rejeu sans
résurrection ; limites d'effacement explicites. Claude E-006/E-007 propose des
archives optionnelles ; les statuts LONG_TERM/PERMANENT ne suffisent pas à
activer la conservation de toutes les versions. Aucun choix métier nouveau
considéré comme approuvé par la seule revue.

## Recette VM — NON TESTÉE

| Tâche | Preuve exigée |
| --- | --- |
| T-010 | Machine/racine effectives, branche/commit, écrivains/services/tâches ; ne pas supposer le numéro de VM |
| T-011 | Écritures arrêtées, sauvegarde et restauration avec hash de chaque fichier ; racines externes et notes incluses |
| T-012 | Adoption du commit candidat sans écraser de changements locaux, dépendances et environnement isolé |
| T-013 | Suite complète dont cinq Manager, interruptions et concurrence Information ; versions/commandes/rapports |
| T-014 | Audits/requêtes sur corpus réel, migration séparée, rejets, sens opérationnel et performances |
| T-015 | Après T-048, refus du démarrage si état bloquant ; répétition sur copie avant automatisation |
| T-032 | Suppressions récupérables sur copie, reçus anciens revus ; distinguer arrêt de processus, arrêt VM et coupure physique |

Outil : `python -B -m tools.vm_acceptance --source COPIE_ARRETEE --workdir DOSSIER_VIDE`.
Il enchaîne inventaire, restauration, cinq cas concurrents et quatre audits.
Le contrôle de démarrage T-048 complète ces audits ; inventaire des écrivains
heuristique et exécution VM toujours manquante.

## Acquis et chantiers transversaux

| IDs | État réel et suite |
| --- | --- |
| T-001 à T-004, T-030/T-038 | FAIT EN LOCAL : fondations/lecteurs/validateurs, preuves historiques conservées ; pas de nouvelle série de durcissement |
| T-005 | Résultat historique ; état actuel en tête de cette TODO |
| T-020 | FAIT EN LOCAL : inventaire complété par T-048 ; VM non testée |
| T-023 | PARTIEL : frontières/gardes historiques ; migration effective avec T-031 |
| T-024 | PARTIEL : IndexPort/référence testés, synchronisation T-045 ; Qdrant DIFFÉRÉ |
| T-025/T-034 | DIFFÉRÉ pour intégrations externes ; interface interne/client factice T-043/T-047 |
| T-026 | PARTIEL : projections et notes T-044 ; édition canonique uniquement par commandes à définir |
| T-027 | PARTIEL : interruptions/processus testés ; lecture multi-fichiers et coupure électrique non validées |
| T-028 | FAIT POUR CE BILAN DOCUMENTAIRE : architecture actuelle/cible et TODO consolidées ; aucun déploiement validé |
| T-029 | DIFFÉRÉ : dashboard local présent, navigateur/LAN/VM non validés |
| T-035 | PARTIEL : corpus reproductible 500 legacy/499 core, 12 Threads ; données réelles anonymisées/mesures VM manquantes |
| T-039 | FAIT EN LOCAL : delete implicite coordonné ; assemblage manuel T-031 |
| T-040 | FAIT EN LOCAL v0.1 : contrat/mapping, 500 candidats ; pas de qualification automatique |
| T-042 | FAIT EN LOCAL v1 : compaction/reçus/rejeu testés ; rétention globale/snapshots Thread T-050, VM non testée |

## Prochaines livraisons démontrables

Le premier parcours qualifié vers un projet existant et son rappel est désormais
livré en local ; le rapprochement global des dossiers hors parcours est maintenant
disponible à la demande, comme le catalogue reconstructible T-045. T-049 réduit
les scans par commande ; un annuaire reconstructible et la mesure VM restent
nécessaires avant ingestion intensive. Disponibilité et échéances raccordées
au routage ; entretien explicite assemblé. Récurrence, coût des scans et
autres branches des plans à poursuivre. La mise en service exige toujours import/migration décidée,
restauration vérifiée et recette VM au commit candidat.
