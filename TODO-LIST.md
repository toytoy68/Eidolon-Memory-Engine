# Memory Engine — TODO active

Mise à jour : **2026-10-03**, audit initial `a779c9d`, T-048 puis refus migration mixte et commandes projet livrés, branche
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
revue complète reçue par fichier, patch vérifié mais non intégré. Relecture
Claude sur `f507b31` reçue le 02/10 : patch v2 abandonné, correctifs déjà présents ;
E-004 relue par Claude sur `3b2d7a0` : F1–F4 confirmés, relecture terminée ;
sorties CLI FAILED encore à relire. Périmètre de l’index dérivé et
archivage en conversion clarifiés dans MIGRATION.md. Voir
[la contre-revue](docs/REVUE-CLAUDE-2026-10-01.md). Une revue ne vaut pas validation VM.

## Bilan du créneau de trois heures du 03/10

18 lots publiés et vérifiés séquentiellement sur GitHub : reprise FAILED,
imports étroits/copie core, routage, compaction par lots, notes humaines,
budget de rappel, recettes synthétiques et mesures tmpfs/ext4.
[Bilan, commits et travaux ouverts](docs/SESSION-2026-10-03.md).
Les anciens résultats datés restent conservés ; les statuts actuels ci-dessous
distinguent désormais VM synthétique et validation sur corpus réel.

## Canal GPT ↔ Claude — ACTIVÉ / ALLER-RETOUR CLAUDE WEB VALIDÉ

Demande du 03/10 dans « Connecter GitHub à Claude » reprise sur VM depuis
`d9c8ba8`. Deux messages actifs courts, archivage des réponses, serveur MCP
à trois outils, contrôle Git/verrou/audit/OAuth et modèles systemd/HTTPS livrés.
Historique ECHANGES.md conservé. Suite finale directe VM : **1643 réussis en
38,02 s**, dont **37 cas du canal** ; aller-retour client MCP officiel/HTTP
local/Git bare réussi, preuves négatives publication/authentification réussies.
Aucun test sur données mémoire actives.

Paquet reproductible et script d’installation sans activation préparés ensuite ;
11 tests supplémentaires réussis. Droit administrateur : mot de passe requis.

**ACTIVÉ le 03/10** : domaine mcp.eidolon.re via Cloudflare Tunnel, Auth0,
clé GitHub dédiée et service systemd. HTTPS 401 sans token / découverte 200
vérifiés directement ; réponse réelle Claude Web publiée dans `f2a4119`,
commit distant et archivage vérifiés par Codex. Reconnexion après expiration,
redémarrage VM et restauration du service restent à vérifier.
Caddy absent sur la VM ; son modèle alternatif n’est pas celui déployé.
Unité permanente systemd installée, services MCP/cloudflared actifs revérifiés
à la reprise ; découverte Auth0 conforme et accès sans token 401 confirmés.
[Contrat, installation et reprise](docs/COLLABORATION-MCP.md). Estimation globale
45 % / 52,75 points inchangée ; ce canal est un outillage de collaboration.

## Dernière vérification

Lot sources/dashboard/IA locale T-051 du **03/10/2026** : **1712 réussis en
37,83 s**, 47 nouveaux cas, 49 ciblés verts ; **15 cas MCP exclus** pour éviter
de doubler le processus existant. Ce n’est pas une suite complète. Test réel
Qwen3 0.6B sur récit synthétique : quatre propositions exactes, 7,347 s, mémoire
inchangée ; modèle déchargé après appel. [Preuves](docs/SOURCE-LIBRARY.md),
logs/manifest dans docs/validation/2026-10-03-sources/. Aucun manuscrit réel validé.


Validation du lot T-046 if-idle, **03/10/2026** : **1665 réussis en 37,42 s**,
12 nouveaux cas, 74 ciblés verts. Checkout et corpus /tmp distincts. Les 15
cas MCP sont exclus car un processus les exécutait déjà sur la VM : **ce n’est
pas une suite complète**. Log/empreintes dans docs/validation/2026-10-03-if-idle/.
Suite complète précédente conservée ci-dessous ; estimation inchangée.


Suite complète de reprise du **03/10/2026**, base `f11ae11` plus lot dossiers
bornés : **1668 réussis en 37,63 s**, aucun échec/saut/désélection,
corpus synthétiques isolés sous `/tmp/em-dossier-batches-suite`. 14 nouveaux
cas ; 53 ciblés verts. Contrat et limites : [entretien](docs/MAINTENANCE-PASS.md).


Suite complète directe sur VM du **03/10/2026** après édition des notes humaines T-044 : **1606 réussis en 39,46 s**, Python 3.13.5/pytest 9.1.1,
aucun échec, saut ou désélection. Base `1d01498` plus le lot documenté ci-dessous ;
racine `/tmp/em-suite-h7wYKC`, corpus synthétique isolé, journal conservé.

Dernière recette peuplée du code `7eddfe0` avec édition des notes : neuf
étapes OK, cinq concurrents réussis en 0,80 s, 93 fichiers SHA256, source
inchangée/readiness vraie, notes CRLF conservées hors rappel canonique.
99 fichiers archivés/vérifiés dans recette-20261003-notes-7eddfe0.
Corpus synthétique uniquement, crontabs illisibles sans sudo, aucune coupure
électrique. [Preuves](docs/VM-ACCEPTANCE-2026-10-03.md).

Recette du code `2fed279`, **03/10/2026** : **neuf étapes OK**
sur copie restaurée vide et corpus synthétique peuplé ; cinq concurrents
réussis pour chacun, 2448/93 fichiers SHA256 contrôlés, sources inchangées,
readiness vraie. Corpus synthétique : 11 Informations, un projet, 14 reçus
routage, cinq échéances achevées, journaux complets/compactés et suppressions.
102 fichiers archivés et vérifiés dans recette-20261003-final-2fed279.
Crontabs illisibles sans sudo ; pas de corpus réel/coupure électrique.
[Preuves](docs/VM-ACCEPTANCE-2026-10-03.md).

Recette directe Codex du **03/10/2026**, commit `9780473` : **neuf étapes OK**,
**5 tests concurrents réussis en 0,82 s**, 40 désélections du filtre ciblé,
2448 fichiers vérifiés par SHA256, source restaurée inchangée, `ready=true`.
Relance hors sandbox dans `/tmp/em-yZKsKq` après refus de sockets dans le sandbox ;
l'ancien chemin long produisait `AF_UNIX path too long`. Inventaire mémoire et
journaux vides : audits réussis sans corpus réel. Rapports/logs des deux nouvelles
tentatives archivés dans le sous-dossier `recette-20261003-em-yZKsKq` de la
sauvegarde. Voir [preuves et limites](docs/VM-TESTS-2026-10-02.md).
Sauvegarde SHA256/restauration tar et absence de services Eidolon actifs
confirmées par toytoy ; aucune intégration services ou coupure électrique validée.

VM `Eidolon-Memory`, retour terminal de toytoy du 02/10/2026 à 22 h 27 :
**1212 réussis en 28,89 s**, commit `ac4d739`, Python 3.13.5/pytest 9.1.1,
aucun échec ni désélection. Les cinq scénarios de concurrence Manager passent.
Suite isolée dans `/tmp/eidolon-tests-doLWCH` ; journal conservé sur la VM.
Voir [le compte rendu](docs/VM-TESTS-2026-10-02.md). Cette étape valide la suite
sur la VM, pas encore la sauvegarde/restauration, les audits des données réelles,
les services ni une coupure électrique. Les limites VM des lots ci-dessous
restent applicables à cette recette opérationnelle ; leurs chiffres datés
conservent la preuve disponible au moment de chaque livraison.

Incident VM à 22 h 36 : `tools.writer_inventory` levait PermissionError sur
`/var/spool/cron/crontabs`. Correctif livré : capture de l'erreur de parcours
cron, chemin dans `unreadable`, conservation des autres résultats et couverture
heuristique explicite. Trois nouveaux tests rouges avant correction, puis
12 ciblés verts en 0,81 s (inventaire + recette). Suite VM de 1212 cas ci-dessus
antérieure au correctif ; cinq tests inventaire et inventaire sudo vide
confirmés par toytoy le 03/10. La recette sans sudo signale encore le cron
inaccessible, sans interrompre les autres contrôles.

Mesure historique dans Work :

Suite complète après extension aux éditions Thread FAILED, base publiée `121764a` :
**1207 réussis, 5 échecs de sockets Manager avant scénario en 75,62 s**, pytest 9.1.1/Python 3.12.14, aucun
désélectionné. Les cinq tests Manager échouent à la création d’une socket
interdite avant scénario métier. 401 cas ajoutés depuis `9063313` (21 exécution,
15 rappel, 17 rapprochement, 16 catalogue, 8 scans, 25 cycle de vie, 19 raccordement, 20 entretien, 15 optimisation des passes, 21 lots bornés, 24 index, 24 nouveaux projets, 71 revue E-004, 4 suivi E-004, 29 import DELETED, 36 résolution des statuts FAILED, 36 résolution des éditions FAILED).
Groupe ciblé du dernier lot : 107 réussis en 4,52 s. Arrêts de processus, courses sans Manager et preuves négatives
comportementales détaillés dans les contrats. Aucune VM, donnée réelle ou
coupure électrique testée.

## Revue E-004 — CORRECTIONS CONFIRMÉES PAR CLAUDE / NON TESTÉ VM

- F1 : une disposition sans lieu reste REVIEW malgré une cible UPDATE ; refus
  vérifié avant intention et écriture métier.
- F2 : rendu commun des champs en ligne ; tous les séparateurs testés sont
  aplatis, contenus complets cités et notes humaines préservées.
- F3 : retrait proposé seulement pour OBSTACLE qualifié, même identité/révision,
  références déclarées non vides. Exécution toujours fermée ; validation réelle
  des preuves à définir avant ouverture de cette branche.
- F4 : échéance invalide → REVIEW ; NONE/REVIEW sans déclencheur.

Preuve avant correction : 64 échecs et 7 réussites sur 71 nouveaux cas ; après,
174 ciblés réussis en 8,33 s. Les sept déjà verts portaient sur des champs déjà protégés dans ces cas. Fixture de retrait alignée sur le Memory cible ;
refus d'échéance désormais OperationConflict (plan REVIEW), au lieu de ValueError.
Les plans anciens affectés sont refusés à la revalidation ; une intention déjà
APPLYING exige examen humain, sans réécriture forcée. Dossiers existants à
rafraîchir explicitement s'ils deviennent STALE. Aucun changement des estimations.

Retour final de Claude sur `3b2d7a0` : sondes et preuve rouge/vert confirmées.
Pas de suite complète chez Claude ; ses 29 échecs de substitut pytest sont
identiques sur la base précédente (absence de `monkeypatch.context`).

Suivi restant après revue :
- `resolve()` : maintien du blocage intégral sur Thread corrompu, contrat
  explicité et deux tests API/CLI livrés (avec ou sans sélection explicite).
- Nettoyage de `reasons` livré : une échéance invalide ne conserve plus la
  raison annonçant UPDATE ; décision d’exécution inchangée.
- Résolution humaine FAILED : reprise explicite des statuts et éditions Thread livrée
  ci-dessous ; autres familles/abandons/conflits et recette VM encore ouverts.
  Import étroit DELETED livré ; import opérationnel général encore ouvert.

Suivi E-004 du 02/10 après-midi : 122 tests ciblés réussis en 2,63 s, quatre
cas supplémentaires. Deux rouges avant correction des raisons ; ignorer
expérimentalement les Threads corrompus fait échouer les deux autres.
Suite complète précédente inchangée ; aucune nouvelle recette VM.

## Ordre prioritaire

| Ordre | Tâches | Résultat attendu |
| --- | --- | --- |
| 1 — Avant exploitation | T-048, T-021/T-033 | Reprise/inventaire et refus des sources mixtes livrés ; import opérationnel général et recette sur données réelles restent ouverts |
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

### T-048 — Reprise et inventaire complets — SUITE VM VALIDÉE / EXPLOITATION PARTIELLE

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

Ajout du 02/10 : `core.operations.failed_resolution` fournit un aperçu puis
une décision humaine pour les seuls THREAD_STATUS_CHANGE FAILED cohérents.
La trace auteur/motif/date/empreintes et APPLYING sont publiés ensemble dans
le journal existant ; reprise normale du plan inchangé. Le dépôt générique
continue d'interdire les sorties FAILED et l'altération de la trace.
36 cas, deux arrêts réels, deux processus concurrents, revue périmée, historique
strict, réservations Thread/Event, rejeu et seconde décision après nouvel échec.
89 ciblés verts en 2,96 s ; retrait expérimental de l'audit/de la revalidation :
1 + 1 échecs. Contrat : [FAILED-STATUS-RESOLUTION.md](docs/FAILED-STATUS-RESOLUTION.md).
Les journaux enrichis sont refusés par les anciennes versions du lecteur.

Extension du 02/10, base `121764a` : THREAD_UPDATE désormais supporté pour
LINK/UNLINK, ADD_ACTION/ACTION_STATUS et DETAILS. Aperçu avec `--family thread-update-v1`, commande visible, audit RETRY_THREAD_UPDATE_V1 strict ;
API et revues de statut conservées. Gardes des liens et collisions inter-familles
contrôlées avant autorisation ; réservations de suppression conservées.
36 nouveaux cas, 107 ciblés verts en 4,52 s, trois arrêts réels. Retirer le
contrôle de lien, la fraîcheur de revue ou l'audit donne 1 + 1 + 1 échecs.
Les états FAILED simultanés de familles différentes restent bloqués pour examen.

Extension du 03/10 sur base `06c9570` : THREAD_CREATE supporté par la revue
`--family thread-create-v1`, trace RETRY_THREAD_CREATE_V1 et reprise normale.
Thread ABSENT/AFTER, Information liée visible, révisions 0 → 1 et Event original.
Même contrôle de fraîcheur et publication atomique ; liens invalides, Event sans
Thread, identités réservées et parents non terminés bloqués avant autorisation.
32 nouveaux tests, 25 premiers rouges avant implémentation, puis 160 ciblés verts
sur VM en 3,82 s. Trois arrêts de processus, deux reprises concurrentes,
rejeu sans résurrection et nouvel échec couvert. Retirer revalidation/trace
provoque un échec chacun dans des processus de preuve distincts.
Suite complète VM : 1247 réussis en 29,82 s. Corpus synthétique uniquement,
aucune résolution sur données réelles ni coupure électrique.

Extension suivante du 03/10, base `20a283a` vérifiée sur GitHub : THREAD_DELETE
supporté par revue `--family thread-delete-v1` et trace RETRY_THREAD_DELETE_V1.
Thread BEFORE/ABSENT, retrait exact sans Event, divergence et identité réutilisée
refusées ; Information disparue non recréée. 30 tests rouges avant puis verts,
190 ciblés réussis en 4,41 s ; suite VM 1277 réussis en 30,37 s. Trois arrêts
réels et deux reprises concurrentes, preuves négatives revalidation/trace.
Corpus synthétique uniquement, aucune résolution sur journaux réels.

Extension Information du 03/10, base `dcbdf1c` vérifiée sur GitHub : reprise
humaine CREATE/UPDATE avec RETRY_INFORMATION_WRITE_V1 ; audit strict conservé par
compaction et comparaison journal/reçu avant retrait. Rejeu après suppression
sans recréation, anciens reçus sans trace inchangés ; anciens binaires refusent
les objets enrichis. 58 nouveaux tests, 295 ciblés verts en 7,29 s ; six arrêts
réels, concurrence et compaction interrompue. Trois preuves négatives (revalidation,
trace atomique, conservation à compaction), un échec chacune. Suite VM 1335 verts
en 32,13 s sur données synthétiques uniquement. Contrat :
[FAILED-INFORMATION-RESOLUTION.md](docs/FAILED-INFORMATION-RESOLUTION.md).

Restant exploitation : installation du contrôle dans les services réels,
dépendances sur corpus réel VM, intentions parentes FAILED, divergences et abandon
explicite éventuel avec traitement des effets/réservations. Aucun abandon automatique livré. Une
lecture ponctuelle ne protège pas contre le redémarrage ultérieur d'un écrivain legacy.

### T-021 / T-033 — Migration opérationnelle — PARTIEL / SUITE VM SUR SYNTHÉTIQUE

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

Ajout du 02/10 après-midi : import dédié des seuls reçus DELETED, aperçu sans
écriture, copie exacte des reçus actifs, gardes de références/snapshots/readiness,
refus global des conflits avant publication, reprise par relance et contrôle
final. 29 nouveaux cas dont deux arrêts réels et deux importeurs concurrents ;
121 ciblés réussis en 4,03 s, preuves négatives 1 + 2 échecs. Un fichier temporaire inconnu
laissé avant renommage bloque la relance pour revue humaine, sans purge implicite. Contrat :
[DELETED-RECEIPT-IMPORT.md](docs/DELETED-RECEIPT-IMPORT.md).

Ajout du 03/10, base `5394e06` vérifiée sur GitHub : import dédié des reçus
compactés Information et Events exacts, audits humains conservés. Canonique actuel
identique par octets et révision suffisante, ou DELETED identique si absent ;
refus avant publication de tous les conflits puis revalidation sous verrous.
Event avant reçu, reprise d'un préfixe ; garder la destination arrêtée jusqu'au
succès final, une readiness vraie ne prouve pas que l'import est fini.
34 nouveaux tests, 173 ciblés verts en 5,56 s ; trois arrêts réels, concurrence,
preuve rouge de révision et deux substitutions négatives. Suite VM 1369 réussis
en 33,70 s, corpus synthétique uniquement. Contrat :
[WRITE-RECEIPT-IMPORT.md](docs/WRITE-RECEIPT-IMPORT.md).

Ajout CANCELLED du 03/10, base `55e81ba` confirmée sur GitHub : option explicite
`--include-cancelled`, DELETED seul par défaut conservé. Même canonique présent
et révision >= demande, reçu exact, liens conservés ; UPDATE possible sans
réactivation de suppression, CREATE et ancienne approbation refusés.
18 nouveaux tests, 144 ciblés verts en 4,96 s ; arrêt réel et concurrence,
deux preuves négatives. Suite VM finale 1387 réussis en 34,18 s après correction
d'une fixture, corpus synthétique uniquement. Contrat DELETED actualisé.

Ajout transfert core complet du 03/10, base `46998ce` vérifiée sur GitHub :
copie byte-exact de `memory/` vers destination neuve, hors verrous techniques.
Threads/actions/révisions, journaux complets/parents, échéances, suppressions et
notes conservés sans exécution. Préparation vérifiée reprenable, publication
atomique sans remplacement. 42 nouveaux cas, quatre arrêts réels, concurrence,
refus source mixte/divergente, deux substitutions négatives. Suite VM 1429 réussis
en 36,38 s. Contrat : [CORE-COPY.md](docs/CORE-COPY.md).

Clarification du 03/10 après activation du canal : guide MIGRATION.md actualisé
avec choix conversion/import étroit/transfert core, refus A-03 et inventaire
thread-delete désormais corrigés. Lot documentaire uniquement ; aucune nouvelle
validation VM ni modification de l’estimation.

Restant : migration entre formats et fusion opérationnelle générale vers un
arbre existant ; aucune activation implicite des journaux archivés. Les notes
hors `memory/` exigent une sauvegarde séparée. Migration réelle, adoption par les
services et revue des pertes de sens toujours non testées.

### T-031 / T-041 — Services métier canoniques — PARTIEL / TESTÉ VM SYNTHÉTIQUE

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

Extension suivante : format 3 pour projet explicitement nouveau,
`preview_new_project` et CLI `--new-project`, modèle PROPOSED révision 1 sans
actions/liens préexistants. Intention propriétaire, enfant thread-create-v1,
dossier, disponibilité et échéance. Anciennes identités de projet avec
historique de création/suppression refusées avant Information. Reprise globale,
preuve du journal enfant, concurrence et rejeu après suppression vérifiés.
24 nouveaux cas ; 58 ciblés réussis, preuves négatives 1 + 1 + 1. Verrou de
journal ajouté au contrôle des réservations du routage pour compatibilité avec
l'index facultatif, y compris en format 2. Contrat :
[ROUTING-NEW-PROJECT.md](docs/ROUTING-NEW-PROJECT.md).

Ajout du 03/10, base `e17bec3` vérifiée sur GitHub : résultats client NONE/REVIEW
par `assess`, sans écritures. Aucune action, revue requise ou prochaine étape
explicite ; pas de readiness affirmée, pas de création supposée du projet.
28 nouveaux cas, 25 rouges sur squelette, 106 ciblés verts ; client factice
jusqu’au rappel, preuve NONE != DELETE, deux substitutions négatives.
Suite VM 1457 réussis en 36,29 s. [Contrat](docs/ROUTING-OUTCOMES.md).

Ajout rattachement existant du 03/10, base `2a50395` vérifiée sur GitHub :
format 4 preview_link / --link-only, NONE sur Memory canonique exact vers projet
choisi. Source octets/révision/Events/disponibilité/échéances inchangés ; LINK
Thread si absent, dossier et notes conservés. Intention/reçu/recovery/inventaire
et copie core raccordés. 33 nouveaux cas, 29 rouges sur squelette et un rouge
dédié de conflit avant réservation ; 182 ciblés verts, suite VM 1516 réussis
en 37,84 s. [Contrat](docs/ROUTING-EXISTING-INFORMATION.md).

Ajout du 03/10, base `3eda522` vérifiée sur GitHub : format 5 sans dossier,
STORE/UPDATE qualifié avec disponibilité/échéance et reprise sans Thread.
30 nouveaux tests ; 25 rouges sur squelette ; deux sorties de processus,
concurrence, copie/rejeu, source divergente, reçus corrompus et suppression.
Deux substitutions négatives observées. [Contrat](docs/ROUTING-INFORMATION-ONLY.md).

Restant : résolution/file de revue durable, lieu/thème, autres politiques et
qualification automatique.
Disponibilité encore différée pour les seuls anciens plans format 1.
Parcours testés sur VM avec corpus synthétiques ; aucun client externe
ni corpus réel validé.

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
Ajout du 03/10, base `1d01498` vérifiée sur GitHub : read_notes/replace_notes
et CLI notes/edit-notes, sections humaines seules sous SHA256 du document
entier. Source/résumé canonique inchangés, reconstruction conserve CRLF ;
25 nouveaux cas, 21 rouges sur squelette, concurrence et arrêt réel après
publication, deux substitutions négatives.
[Contrat](docs/DOSSIER-HUMAN-NOTES.md).

Restant : déclenchement système récurrent, coût des scans/verrous
T-049, ingestion explicite des notes non reconstructibles et clients réels.
Le rappel écarte le texte des vues et signale leur fraîcheur. Lieux/thèmes après
projets. Le manifeste est recalculé, pas un index incrémental. Définir la clôture de purge
sur les vues gérées par le moteur, distincte du DELETED canonique actuel et des
copies hors de son contrôle. Aucun effacement automatique de notes humaines.

### T-045 — Catalogue léger — LIVRÉ / TESTÉ VM SYNTHÉTIQUE

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
Ajout T-049 du 03/10 : catalogue décode une fois chaque source au lieu de deux,
avec projection limitée aux métadonnées et deuxième lecture/SHA256 conservés.
Deux cas ajoutés, 67 ciblés verts ; 1727 tests VM réussis, 15 MCP exclus.
À 300 synthétiques tmpfs, 600→300 décodages, snapshots égaux ; lectures inchangées.
[Preuves et limites](docs/validation/2026-10-03-catalogue-decode/README.md).

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
[MAINTENANCE-COST.md](docs/MAINTENANCE-COST.md). Nouvelle tranche livrée après l’audit : sortie rapide inactive vérifiée,
audits stricts partagés dans les phases de lecture sous verrous et abandon du
scan de journaux par dossier après audit global réussi. Invalidation à chaque
publication canonique ; contrôle final dans une nouvelle phase. Aucun cache
inter-passes ni lecteur allégé. 15 nouveaux cas, 52 ciblés réussis ; concurrence,
corruption, aliases de chemin et preuves négatives vérifiés. Mesures avant/après
et charge à 25 projets/25 échéances dans le contrat ci-dessus : 8,168 → 0,532 s
sans effet, 18,843 → 4,064 s avec effets. À 300/5, JSON d’historique
7 890 → 1 230 sans effet et 13 180 → 4 605 pour cinq échéances.

Troisième tranche : lots de 1 à 100 CREATE/UPDATE, CLI `batch` et dispatcher
raccordé. Un scan strict sous verrous, réservations actualisées, arrêt au premier
conflit, journaux individuels et rejeu de la liste entière. 21 nouveaux cas,
102 ciblés verts ; preuves négatives 2 + 1 + 1, interruptions et concurrence.
À 300 snapshots, 50 créations : 5,187 → 0,321 s ; 50 updates : 5,340 → 0,333 s,
50 scans → 1 et 16 325 ouvertures JSON → 400. Nouvelle comparaison entretien :
25 échéances 4,156 → 1,770 s ; inactif autour de 0,5 s. Contrat et rapports :
[INFORMATION-BATCHES.md](docs/INFORMATION-BATCHES.md). Pas de transaction globale,
de file durable pour la fin du lot ni de libération du verrou extérieur
d'entretien entre tranches.

Quatrième tranche : index de réservations reconstructible activé par
`index-rebuild`, inspection sans écriture par `index-status`. Empreintes de tous
les octets plan/reçu vérifiées ; seuls les contenus nouveaux/modifiés sont
revalidés strictement. Index invalide reconstruit, source invalide bloquante.
24 nouveaux cas ; retrait réutilisation/identité des sources/checksum :
2 + 3 + 1 assertions rouges, code restauré. Arrêts réels, concurrence,
compaction, suppression et dispatcher couverts. Contrat :
[RESERVATION-INDEX.md](docs/RESERVATION-INDEX.md). À 300 snapshots :
50 créations individuelles 4,861 → 0,987 s, updates 4,769 → 1,059 s ;
créations en lot 0,247 → 0,243 s (gain négligeable). Lecteur strict
16 275 → 99, fichiers toujours lus ; index initial 0,08 à 0,15 s hors mesure.

Ajout du 03/10, base `4a11c71` confirmée sur GitHub : mesures VM directes
100/300 antécédents et 25 commandes, trois corpus indépendants par variante ;
84 points d’écriture, quatre corpus d’entretien/cinq échéances/rejeu contrôlés.
300 live/create : médianes 1,518 s individuelles, 0,093 s en lot, 0,046 s
indexé hors construction. L’index conserve ses lectures ; préparation compacte
≈15 s, entretien à vide 1230 JSON / 2135 Markdown à 300. `/tmp` est tmpfs :
pas de latence disque réelle ni corpus réel. Aucun nouveau code métier/test ;
suite 1457 du commit précédent applicable. [Preuves](docs/VM-PERFORMANCE-2026-10-03.md).

Extension du 03/10, base `08f0284` vérifiée sur GitHub : 24 mesures supplémentaires,
1000 antécédents tmpfs / 300 ext4, 25 CREATE en lot, trois répétitions,
strict/index et live/compact. Tous les audits et 1025/325 objets conformes.
1000 compact : préparation médiane 154,829 s, lot strict 0,170881 s,
indexé 0,062659 s hors construction ; toujours 1050 ouvertures JSON.
300 ext4/live : lot strict 0,302016 s contre 0,251664 s indexé hors construction.
Manifeste, logs et cleanup vérifiés, aucun code core changé. La compaction
individuelle devient un prochain coût à réduire ; pas de garantie de latence
physique, charge réelle, coupure ou ingestion intensive.

Ajout compaction bornée du 03/10, base `797c432` confirmée sur GitHub :
1–100 identités, verrous maintenus, scan partagé, reçu relu avant retrait de chaque
snapshot et audit humain conservé. Préfixe durable, relance par liste exacte ;
aucune rétention automatique. 26 nouveaux cas, 124 ciblés verts, suite VM 1483
réussis en 37,03 s. Trois répétitions avant/après : 1000 tmpfs, compaction
160,661712 → 2,392723 s et 1000 → 10 scans ; 300 ext4 ≈19,2 → 1,4 s.
Outil reproductible, rapports/logs et hashes ; toujours un scan par lot et coût
croissant quadratique réduit. [Contrat](docs/INFORMATION-COMPACTION-BATCHES.md).

Mesure complémentaire post-revue Claude A/B/C : à 300 Informations, passe
inactive live 0,256671 → 0,148833 s, compact 0,207244 → 0,118216 s ;
JSON 1230 → 620 et Markdown 2135 → 1830. Huit corpus VM tmpfs indépendants,
100/300, trois répétitions ; aucun gain d’écriture/latence physique revendiqué.
[Protocole et échantillons](docs/validation/2026-10-03-maintenance-comparison/README.md).

Restant : suppression de l’énumération et des lectures linéaires par lot,
protocole d’invalidation couvrant tous les écrivains, autres familles, dérivés, corpus et
objectifs VM. L'ingestion totale demeure quadratique à taille de lot fixe (O(N²/B)). Pas d'autorisation
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
Ajout du 03/10 après reprise MCP : reconstruction des dossiers par lots
optionnels de 1 à 100 publications, API/CLI et entretien --dossier-limit.
PARTIAL et backlog explicites, relance convergente, notes préservées ; contrôles
globaux et catalogue restent complets. Aucun gain de scans ou borne de latence
revendiqué. Voir [contrat](docs/MAINTENANCE-PASS.md).

Ajout T-046 du 03/10 : --if-idle reporte explicitement la passe en DEFERRED
si un verrou canonique Persistent/Thread est occupé ; reprise par relance avec
temps/contexte explicites. Aucun critère CPU/SSH/utilisateur, horaire ni job
installé ; autres verrous internes et scans toujours potentiellement longs.
Preuves Linux sur corpus synthétiques isolés, voir le contrat d’entretien.

Ajout T-049 : échéances lues une seule fois sur passe inactive, réutilisées
uniquement pour son rapport ; aucune conservation entre passes, nouvelle
échéance due relue/appliquée. Deux cas rouges avant lot, 74 ciblés verts ; suite finale VM 1732 réussis
en 38,36 s, 15 MCP exclus. [Preuve](docs/validation/2026-10-03-maintenance-deadlines/README.md).

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

Ajout du 03/10, base `ecd83d1` vérifiée sur GitHub : outil de mesure du rappel
sur six corpus neufs 300/1000/3000 × live/compact, huit scénarios à réponses
connues, trois requêtes sur chaque corpus chaud. 144 réponses conformes, flags
contexte/incertitude/expired/pending, budgets et dossier CURRENT/STALE contrôlés ;
empreintes avant/après identiques et tous les objets/readiness revérifiés.
1000 operational : médianes 0,378667 s live / 0,303978 s compact ; le coût reste
linéaire sur le corpus malgré quatre résultats. Rapports/logs/code-outil hashés.
Aucun code métier changé ; suite 1516 précédente applicable, pas réexécutée.
[Mesures et limites](docs/VM-RECALL-2026-10-03.md).

Ajout du 03/10, base `2a95849` vérifiée sur GitHub : recall_payload/API/CLI
borne le JSON complet et le cadrage explicite ; sources entières omises si
nécessaire, jamais leurs réserves/preuves. Compteur de tokens explicite sur le
rendu entier, budgets d’extraits distincts, résultat vide/erreur explicites.
36 nouveaux cas, 24 rouges renderer puis sept rouges raccordement ;
113 ciblés verts, deux substitutions négatives. [Contrat](docs/RECALL-PAYLOAD.md).

Mesure du 03/10, base `e7ecfc6` vérifiée sur GitHub : neuf corpus indépendants
(3 × tailles de preuve 200/2000/10000), trois rappels chauds par corpus,
81 rendus sous trois budgets, sources/métadonnées/réserves vérifiées exactes.
95 caractères d’extraits donnent jusqu’à 14453 caractères JSON/cadrage ;
plafond 8000 → 3657 caractères/quatre sources complètes avec preuve 10000.
Rendu seul médiane 0,269 ms dans ce cas, sans tokenizer ni latence production.
Empreintes stables/readiness vraie, substitution de budget refusée ; code
métier inchangé. [Mesures et limites](docs/VM-RECALL-PAYLOAD-2026-10-03.md).

Extension ext4 du 03/10, base `858f02b` vérifiée sur GitHub : neuf corpus
indépendants supplémentaires, 27 rappels chauds, 81 rendus dont les hashes
correspondent exactement à tmpfs. Preuve 10000/budget 8000 : rendu seul
0,279 ms et rappel seul 3,336 ms médians ; pas de disque physique isolé.
Core inchangé, rapports/logs hashés, parent/corpus temporaires supprimés.

Restant : qualité/latence sur corpus représentatif, politiques plus fines,
catalogue/recherche sémantique, clients réels et recette VM sur corpus réel. Le mode historique ne restaure
pas les révisions textuelles remplacées. Les budgets du rappel simple couvrent les extraits ; recall_payload couvre
JSON et cadrage fourni, pas d’autres messages/enveloppes ajoutés ensuite.
Verrou/scans à mesurer sous T-049.

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

### T-051 — Sources originales et détails IA à valider — PREMIÈRE TRANCHE LIVRÉE

Autorisation directe toytoy du 03/10 après proposition Claude 4982014 :
DOCX/PDF/TXT/Markdown conservés exacts sous memory/sources, fiche et SHA256,
versions par nouveau hash ; upload/consultation/téléchargement authentifiés
dans le dashboard, port 8766 distinct du MCP. Extraction texte figée
DOCX/TXT/Markdown, paragraphes et empreintes vérifiés ; PDF original uniquement.

IA locale choisie : Qwen3 0.6B, 523 Mo, Ollama dédié port 11435 préparé/lancé
hors Git, priorité basse, un thread d’inférence, une analyse, déchargement
après usage. Parcours passage borné → propositions avec citations → correction
et validation humaine → Information INTERPRETATION/UNVERIFIED avec provenance.
Aucun texte intégral ingéré, aucune validation ou suppression automatique.

Inventaire/readiness et refus conversion legacy raccordés ; copie core conserve
originaux/extractions. Reprise après préparation complète, arrêt réel, deux
ajouteurs et rejeu d’acceptation après suppression vérifiés. Contrat :
[Sources et limites](docs/SOURCE-LIBRARY.md).

Restant : extraction PDF, file de propositions durable, comparaison/édition des
fiches, validation navigateur/LAN, extraction de tout un manuscrit, qualité
IA sur corpus réel et impact conjoint avec Eidolon Core. Aucun service permanent
dashboard/IA ni nouveau proxy public installé ; pas de garantie de zéro impact.

Ajout T-051 : paragraphes vides masqués et ignorés dans les portions IA,
références inchangées, bouton de passage suivant, fin de document explicite.
Quatre cas rouges avant le lot, 45 ciblés verts après correction. Brouillons
toujours temporaires ; aucune validation automatique ni analyse globale.

Ajout T-012/T-029 : lanceur dashboard via .venv, précontrôle des imports upload
avant ouverture du port ; un cas rouge avant le lot, dix ciblés verts et relance
VM / et /sources HTTP 200. Toujours manuel, aucun ordonnanceur installé.

Ajout T-051/T-029 : erreurs IA classées et pages de reprise françaises,
occupé/indisponible/citation rejetée distingués, aucune réponse brute exposée.
Deux nouveaux parcours rouges avant lot, 32 ciblés verts après correction.

Ajout T-051/T-029 : texte paginé (40 paragraphes non vides), formulaire IA en
haut et départ adapté à la page ; références inchangées, navigation sans analyse
ni écriture. Un parcours rouge avant le lot, 51 ciblés verts après correction.

Revue Claude `5e8c161` reçue/lue (code `562b4eb`, tests cloud), intégrée avec
son annexe `422f753`. Accord sur correction entretien `208a6ee`. D1 corrigé :
secret HMAC privé distinct du CSRF, citation non vide/type/taille contrôlés ;
4 cas rouges avant lot, 56 ciblés verts, actif VM. D2/D3 reprise UI livrée : inspection séparée, formulaire de reprise et sources
saines visibles (58 ciblés verts) ; lot invalide à vérifier manuellement. D5 livré : pilotes v1 figés, lecture par version enregistrée, contrôle original
conservé (65 ciblés verts), aucun snapshot migré. Basic Unicode D8 corrigé (1 cas rouge, 17 ciblés verts) ; UI mobile suit.
Les propositions file durable/PDF ne valent pas approbation des politiques.

## Répartition GPT / Claude — 3 octobre, après mise en service dashboard

Missions Claude publiées dans [GPT-TO-CLAUDE.md](collaboration/GPT-TO-CLAUDE.md)
(base `2600e13`, publication `e49caa7`) :

- Revue T-051 des originaux, références et validations, avec cas négatifs.
- Proposition d’analyse progressive du roman et file durable de propositions,
  pour réduire le tri manuel ; pas d’acceptation automatique.
- Revue T-029 de la personnalisation navigateur/CSP et lisibilité mobile.
- Étude de l’extraction PDF locale bornée, références par page et limites OCR.

**GPT : correctif T-046/T-049 issu de la revue Claude `2387dec`, livré.**
Readiness après les verrous dans les deux modes ; erreurs d’échéance rapportées
au stade readiness ; phase partagée pour un seul inventaire sur passe inactive.
Six nouveaux cas paramétrés, quatre rouges avant correction ; 54 ciblés verts.
Suite générale VM : 1721 réussis en 38,16 s, 15 MCP exclus ;
[journal et limites](docs/validation/2026-10-03-maintenance-locks/README.md).
Le mode par défaut peut attendre un écrivain avant de signaler un état bloquant.
Aucune passe d’entretien lancée sur le roman utilisateur ; corpus de test séparés.

Actualisation T-051/T-029 : depuis la livraison initiale, le dashboard est actif
sur le LAN 192.168.1.110:8766, upload et extraction du roman utilisateur réussis,
une proposition réelle obtenue sans validation GPT. Captures utilisateur :
diagrammes mémoire/disque et fond personnalisé fonctionnels. Corrections upload
`410a049`, citation/paragraphe `568ab98`, présentation `9d420d4`, `81f33de`,
`2600e13`. Restent la file durable, traitement complet confortable, PDF,
qualité systématique des propositions et impact conjoint avec Core.
Aucun démarrage automatique ni HTTPS dashboard ajouté. Estimation inchangée.

## Recette VM — RÉUSSIE SUR ARBRE VIDE / CORPUS RÉEL NON VALIDÉ

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
heuristique ; recette VM réussie sur arbre vide le 03/10, corpus réel toujours manquant.

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
| T-029 | PARTIEL, extension autorisée le 03/10 : sources/upload et détails IA validés ; HTTP VM synthétique testé, navigateur/LAN/corpus réel non validés |
| T-035 | PARTIEL : corpus reproductible 500 legacy/499 core, 12 Threads ; données réelles anonymisées/mesures VM manquantes |
| T-039 | FAIT EN LOCAL : delete implicite coordonné ; assemblage manuel T-031 |
| T-040 | FAIT EN LOCAL v0.1 : contrat/mapping, 500 candidats ; pas de qualification automatique |
| T-042 | FAIT EN LOCAL v1 : compaction/reçus/rejeu testés ; rétention globale/snapshots Thread T-050, VM non testée |

## Prochaines livraisons démontrables

Le parcours qualifié vers un projet existant ou explicitement nouveau et son rappel est désormais
livré en local ; le rapprochement global des dossiers hors parcours est maintenant
disponible à la demande, comme le catalogue reconstructible T-045. T-049 réduit
les validations par commande ; l’index facultatif est livré, mais la suppression
des lectures complètes et la mesure sur corpus réel restent
nécessaires avant ingestion intensive. Les premières mesures VM synthétiques
d’écriture/compaction/entretien/rappel sont désormais conservées. Disponibilité et échéances raccordées
au routage ; entretien explicite assemblé. Récurrence, coût des scans et
autres branches des plans à poursuivre. La mise en service exige toujours import/migration décidée,
restauration vérifiée et recette VM au commit candidat.


### Missions Claude actualisées après revue — 3 octobre 2026

Demande directe toytoy : [liste active](collaboration/GPT-TO-CLAUDE.md), base
`cf413d4`. Priorités : E/import concurrent de reçus (test + patch préparé par
Claude, code réservé) ; revue D1/D2/D3/D5 ; compatibilité D7/D10 ; contrats de
campagnes/purge/PDF, avec modalités non fixées séparées. GPT continue D8 et UI
mobile puis versions d’extraction D4/D11 ; pas de doublon sur ces fichiers.
Ancienne demande archivée, aucune mission donnée comme déjà exécutée.

Validation intégrée post-revue sources/UI, code `be8eed7` : 1742 tests VM verts
en 38,51 s, 15 MCP exclus ; [preuves](docs/validation/2026-10-03-source-review/README.md).
UI mobile/fonds attend sa nouvelle recette navigateur indépendante.
