# Memory Engine — TODO active

Mise à jour : **2026-10-01**, code audité `a779c9d`, branche
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
ou micro-durcissements T-031a…bc. Les défauts de l'audit sont enregistrés,
**pas corrigés pendant cette séance**. Revue Claude demandée E-005 à E-007 ;
une réponse absente ne vaut pas validation.

## Dernière vérification

Suite complète : **754 réussis, 5 échecs d'environnement, 31,46 s**,
pytest 9.1.1/Python 3.12.14, aucun désélectionné. Les cinq tests utilisant
Manager échouent à la création d'une socket interdite, avant le scénario
métier ; ils restent non validés. Deux autres tests concurrents Information
passent. Aucune VM, donnée réelle ou coupure électrique testée.

## Ordre prioritaire

| Ordre | Tâches | Résultat attendu |
| --- | --- | --- |
| 1 — Avant exploitation | T-048, T-021/T-033 | Reprise et inventaire complets ; migration des invariants, constats A-01/A-02/A-03 |
| 2 — Parcours métier | T-031/T-041 puis T-043 | Assemblage canonique, commandes Thread manquantes, exécution de plans avec révisions et reprise |
| 3 — Projet utilisable | T-044 puis T-045 | Ajouter une Information au même projet, dossier actualisé ou explicitement périmé, catalogue reconstructible |
| Avant ingestion intensive | T-049 | Réduire les scans sans perdre réservations/conflits/reprise ; lot distinct |
| 4 — Disponibilité | T-046, décisions T-050 | Haute/intermédiaire/basse, réexamens et échéances durables |
| 5 — Rappel utile | T-047/T-036/T-022 | Client factice complet, sources/contexte/temps, budgets et mesures |
| Voie VM distincte | T-010 à T-015/T-032 | Copie arrêtée, restauration, concurrence, audits et données réelles |

On peut recueillir des constats VM avant T-048, mais un rapport incomplet ne
vaut pas autorisation de démarrage. Aucun résultat local ne remplace la recette
VM du commit candidat.

## Lots à réaliser

### T-048 — Reprise et inventaire complets — À FAIRE

A-01 : les recover Thread ignorent FAILED ; le CLI peut retourner 0 avec un
journal FAILED persistant. A-02 : thread-delete-v1 manque à l'inventaire.

Rapporter FAILED comme nécessitant intervention, sans le résoudre/supprimer
implicitement. Inventorier toutes les familles et distinguer archives et
états actifs. Vérifier les états persistants après reprise, avec les dépendances
inter-familles ; ne pas se limiter aux résultats renvoyés par recover-all.

Preuves attendues : transition valide PREPARED → FAILED → rapport/code non nul ;
journal Thread delete corrompu → KO ; état sain → succès ; reprises et
interdiction de démarrage sur état bloquant. Tests rouges sur le code audité.
Claude E-005. Rien implémenté, aucune VM validée.

### T-021 / T-033 — Migration opérationnelle — PARTIEL / NON TESTÉ VM

Fait : simulation, conversion séparée idempotente, rejets, archives exactes
Events/Reviews/Working/opérations, vérification indépendante ; 500 Informations
legacy couvertes par les tests.

Restant prioritaire A-03 : une source mixte avec reçu DELETED est archivée sans
réactiver la réservation, autorisant la recréation de l'identité en destination.
Définir un rejet explicite ou un import dédié conservant ces invariants.
Ne pas copier des journaux sous un chemin actif pour les reprendre implicitement.

Tester PENDING_DELETE/APPLYING_DELETE/DELETED/CANCELLED, révisions historiques,
liens et Threads/actions. Distinguer actif, archivé et rejeté dans le rapport.
Les suppressions du générateur sont dans core/, pas legacy/. Conserver D1/D4/D9 :
import distinct, aucun CREATED historique fabriqué, réservation d'identité.
Revue des pertes de sens sur copie réelle. Claude E-006.

### T-031 / T-041 — Services métier canoniques — PARTIEL / NON TESTÉ VM

Fait : Information create/update/recover/compact ; Thread création liée,
statut et suppression journalisés. T-039 corrige le delete implicite canonique.
Preuves : tests Information/Thread et interruptions, commits `4f36f70`,
`0460f68`, `b967bf4`.

Restant : assemblage commun injectant toutes les familles ; commandes
journalisées pour objectifs/métadonnées/actions et ajout/retrait CONCERNS sur
un Thread existant. Le stockage direct refuse les modifications de CONCERNS,
mais aucun service ne les réalise encore. Recenser/migrer les appelants métier,
garder l'import explicite et isoler les anciens écrivains (T-023).

Tests : seconde Information du même projet, concurrence lien/suppression,
modification d'action, révision obsolète, interruption et rejeu. Les étapes
Information/Thread/dossier doivent être reprenables sans transaction globale
supposée. Claude E-007.

### T-043 — Politique puis exécution des plans — PARTIEL

Fait : plan déterministe expliqué sur qualifications explicites, portée/validité,
conflit déclaré ; 20 tests, `8cefac1`. Les 14 scénarios sont couverts côté plan,
pas pour tous leurs effets.

Restant : raccordement aux services T-031/T-041, contrôle de révision à
l'exécution, version des règles et revue des ambiguïtés. Premier parcours
explicitement qualifié ; extraction de texte brut différée. Un trigger proposé
n'est pas une échéance durable. Tests : simulation sans écriture, plan périmé,
exécution répétée sans double Information/projet.

### T-044 — Dossiers vivants — PARTIEL

Fait : projection explicite depuis Thread/CONCERNS, récapitulatif, sources,
actions/décisions, mots-clés, notes préservées et état de fraîcheur ; 8 tests,
`7616455`.

Restant : actualisation après mutation/lien/suppression, suivi des dépendances,
reprise entre COMMITTED et projection ; écarter/signaler les vues périmées à
la lecture automatique. Sauvegarder les notes humaines non reconstructibles,
définir édition concurrente/ingestion explicite. Lieux/thèmes après projets.
Tests : deuxième apport, correction propagée, source retirée, projection
interrompue puis reprise sans rejouer le canonique, notes conservées.

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

### T-046 / T-037 — Disponibilité et cycle de vie — À FAIRE, AUDITS EXISTANTS

Activation haute/intermédiaire/basse, éviction et réexamen, indépendamment de
rétention/applicabilité. Déclencheurs persistants, annulations, acquittements
et reprise après redémarrage, effet moteur idempotent. Aucun ordonnanceur ni
job de maintenance installé.

Tests à horloge contrôlée : échéance dépassée pendant l'arrêt, révision changée,
annulation, rejeu, chat non présenté comme position actuelle, obstacle contourné
à revérifier. Consolidation autonome après contrat ; contenu identique ne
signifie pas même sens.

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
résurrection ; limites d'effacement explicites. Claude E-006/E-007.

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
A-02 limite sa couverture Thread ; inventaire des écrivains heuristique.

## Acquis et chantiers transversaux

| IDs | État réel et suite |
| --- | --- |
| T-001 à T-004, T-030/T-038 | FAIT EN LOCAL : fondations/lecteurs/validateurs, preuves historiques conservées ; pas de nouvelle série de durcissement |
| T-005 | Résultat historique ; état actuel en tête de cette TODO |
| T-020 | PARTIEL : inventaire livré, omission Thread delete sous T-048 |
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
