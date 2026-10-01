# Memory Engine — TODO active

Mise à jour : **2026-10-01**, audit initial `a779c9d`, T-048 puis refus migration mixte et commandes projet livrés, branche
`refactor/architecture-v1`. **Estimation globale gelée : 45 %. Grille : 52,75
points, inchangée.** Aucun avancement chiffré pour cet audit documentaire.

Références : [audit](docs/AUDIT-2026-10-01.md),
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
ou micro-durcissements T-031a…bc. Les constats datés restent conservés ; la séance du soir autorisée par toytoy
poursuit les lots prioritaires avec preuves et documentation par étape. Revue Claude demandée E-005 à E-007 ;
revue complète reçue par fichier, patch vérifié mais non intégré. Voir
[la contre-revue](docs/REVUE-CLAUDE-2026-10-01.md). Une revue ne vaut pas validation VM.

## Dernière vérification

Suite complète après T-043 (premier parcours) : **827 réussis, 5 échecs
d’environnement, 41,54 s**, pytest 9.1.1/Python 3.12.14, aucun désélectionné.
Les cinq tests Manager échouent à la création d’une socket interdite avant
scénario métier. Les 21 nouveaux cas du parcours passent, dont quatre arrêts
de processus et deux courses sans Manager. Aucune VM, donnée réelle ou coupure
électrique testée. Trois garanties retirées temporairement donnent chacune
un échec comportemental (réservation, projection, reçu sans corps), puis code restauré.

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
42 réussis. Plans ambigus, projet absent, échéances et retrait d’obstacle refusés
avant mutation. Aucun statut de vérité modifié par rôle ou pertinence.

Restant : création explicite de nouveaux projets par ce parcours, branches
NONE/REVIEW/lieu/thème, intentions programmées T-046, autres politiques et
qualification automatique. Disponibilité signalée différée dans le résultat.
Pas de client externe ou de VM validé.

### T-044 — Dossiers vivants — PARTIEL

Fait : projection explicite depuis Thread/CONCERNS, récapitulatif, sources,
actions/décisions, mots-clés, notes préservées et état de fraîcheur ; 8 tests,
`7616455`.

Fait en plus via T-043 : actualisation après STORE/UPDATE et rattachement du
nouveau parcours, avec reprise après l’écriture canonique.

Restant : actualisation après les autres mutations/liens/suppressions, suivi des dépendances,
reprise entre COMMITTED et projection ; écarter/signaler les vues périmées à
la lecture automatique. Sauvegarder les notes humaines non reconstructibles,
définir édition concurrente/ingestion explicite. Lieux/thèmes après projets.
Tests : deuxième apport, correction propagée, source retirée, projection
interrompue puis reprise sans rejouer le canonique, notes conservées.
Retenir le rapprochement par manifeste comme réparation, avec IDs/révisions
et hashes tant que les écritures directes existent. Définir la clôture de purge
sur les vues gérées par le moteur, distincte du DELETED canonique actuel et des
copies hors de son contrôle. Aucun effacement automatique de notes humaines.

### T-045 — Catalogue léger — À FAIRE

IDs/révisions, mots-clés, nature, contexte, statuts, échéances et pointeurs,
y compris vers mémoire basse. Reconstruction depuis les fichiers, fraîcheur,
suppression et rattrapage ; aucun connecteur externe. Tests : détruire/reconstruire
le catalogue, retrouver les mêmes données actives, correction/suppression
sans anciens extraits. IndexPort seul ne remplit pas ce contrat.

### T-049 — Coût des journaux — À FAIRE

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

### T-046 / T-037 — Disponibilité et cycle de vie — À FAIRE, AUDITS EXISTANTS

Activation haute/intermédiaire/basse, éviction et réexamen, indépendamment de
rétention/applicabilité. Déclencheurs persistants, annulations, acquittements
et reprise après redémarrage, effet moteur idempotent. Aucun ordonnanceur ni
job de maintenance installé.

Tests à horloge contrôlée : échéance dépassée pendant l'arrêt, révision changée,
annulation, rejeu, chat non présenté comme position actuelle, obstacle contourné
à revérifier. Consolidation autonome après contrat ; contenu identique ne
signifie pas même sens.
Entretien récurrent retenu comme besoin, pas implémenté : fenêtre matinale,
report si occupé, lots reprenables et rattrapage après arrêt. Le profil léger
quotidien / approfondi hebdomadaire proposé dans la discussion reste à fixer,
ainsi que l'heure exacte (souhait 3–4 h, fenêtre documentaire 4–8 h), les critères
d'occupation et d'inactivité. Il ne doit ni décider une vérité ni supprimer sur
le seul critère d'âge. Aucun cron, timer système ou automation externe créé.

### T-047 / T-036 / T-022 — Rappel et parcours complet — PARTIEL POUR LES PRIMITIVES

Fait : lexical_v1, extraits bornés, filtre épistémique explicite, deux jeux
synthétiques de 30 requêtes, parcours isolés de reprise. Restant : appliquer
contexte/temps, exposer provenance/preuves/fraîcheur/raisons ; client factice
via façade métier. Tester projet repris, recommandations conditionnelles,
contexte inconnu, conflit non résolu et mode historique REFUTED/CONFLICTED.
Mesurer qualité/latence sur données représentatives. Aucun client externe à
modifier dans ce lot.

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

## Prochaine livraison démontrable

Une entrée explicitement qualifiée crée une Information, la rattache à un projet
existant, actualise son dossier et se rappelle avec son contexte via un client
factice. Rejeu/interruption sans doublon, refus des états non résolus, fraîcheur
visible, pas de résurrection. La mise en service exige en plus migration décidée,
restauration vérifiée et recette VM au commit candidat.
