# Échanges de travail — Memory Engine

Ce fichier permet une revue asynchrone entre toytoy, Codex/GPT et Claude.
Il ne déclenche aucune session ni aucun accès automatique au dépôt ou à la VM.
Mode d'emploi : [COLLABORATION.md](docs/COLLABORATION.md).

## Reprise rapide

T-048 du 03/10 : reprises humaines Thread et Information FAILED livrées ;
1387 tests réussis directement sur VM en 34,18 s, corpus synthétique isolé.
Imports de reçus compactés Information et CANCELLED explicite livrés ensuite ;
détails dans la dernière entrée.

Recette directe Codex du 03/10 sur `9780473` : neuf étapes OK dans
`/tmp/em-yZKsKq`, cinq scénarios concurrents réussis, arbre mémoire vide.
Preuves, contexte toytoy et limites dans la dernière entrée ci-dessous.

État après passage de la suite sur la VM le 02/10, code testé `ac4d739`,
branche `refactor/architecture-v1`. Le bilan AUDIT-2026-10-02.md conserve
le constat avant optimisation ; état et mesures actuels dans MAINTENANCE-COST.md.
Toujours vérifier HEAD et les changements locaux.

- But inchangé : mémoire autonome, contextuelle et traçable ; fichiers
  canoniques, dossiers Markdown vivants, trois niveaux de disponibilité.
- T-048 livré en local : contrôle read-only et reprise globale avec relecture
  finale. Aucun service VM installé ; résolution humaine livrée pour les
  changements de statut et éditions Thread FAILED, autres familles encore ouvertes.
- T-021 ferme A-03 par refus avant toute écriture de destination pour les
  sources mixtes opérationnelles. Import étroit DELETED livré ; autres reçus
  et conservation générale du rejeu encore ouverts.
- T-031 ajoute les commandes LINK/UNLINK, ADD_ACTION/ACTION_STATUS, DETAILS et
  ThreadService.for_backend ; journal/reprise, réservations et gardes raccordés.
  Lire docs/THREAD-UPDATES.md. Les appels bas niveau restent distincts.
- T-041/T-042 livrés en local ; T-043 exécute désormais STORE/UPDATE vers un
  projet existant ou explicitement nouveau avec intention durable, lien et dossier actualisé. Les autres
  branches restent ouvertes. T-044 répare désormais les dossiers hors parcours
  par rapprochement explicite reprenable. Catalogue T-045 livré avec reconstruction et contrôle de fraîcheur ;
  T-046 : disponibilité, échéances, raccordement au routage et passe d’entretien
  explicite livrés en local. T-047 livre un premier rappel
  contextualisé avec sources, modes explicites et incertitudes.
- Dernière suite exécutée par toytoy sur `Eidolon-Memory` : **1212 réussis en
  28,89 s**, Python 3.13.5/pytest 9.1.1, commit `ac4d739`, aucune désélection.
  Les cinq tests Manager bloqués dans Work passent sur la VM. Suite sur données
  temporaires ; sauvegarde/restauration, audits des données réelles, services et
  coupure électrique restent à vérifier. Voir docs/VM-TESTS-2026-10-02.md.
  401 nouveaux cas après `9063313` ; import étroit DELETED et reprises humaines
  des statuts/éditions FAILED livrés, autres familles et reçus ouverts.
- Relecture Claude reçue sur `f507b31` : patch v2 abandonné, correctifs déjà
  présents et filtre migration reconnu plus complet. Revue de lecture/sondes ;
  sans pytest chez Claude ni VM. Revue E-004 détaillée reçue ensuite : F1–F4
  corrigés et vérifiés par Codex, puis confirmés par Claude sur `3b2d7a0`.
  Relecture E-004 terminée ; réponse et limites en fin de fichier.
- D7/D8/D9 inchangées. Estimation globale gelée à 45 %, grille 52,75 points.
  Pas de travail sur Eidolon Core, Hermes ou Qdrant.

Trois lots du matin poussés : `5b5e2db`, `ca977f1`, `43a1214`. Disponibilité,
échéances, raccordement et entretien explicite livrés ; 64 cas supplémentaires.
Après le bilan, toytoy a demandé l’optimisation des passes. Sortie rapide
inactive et partage d’audits stricts sous verrous maintenant livrés, avec
mesures avant/après et vérification finale fraîche. T-049 reste ouvert pour
la lecture complète par lot ; aucun service ou ordonnanceur lancé.
Les lots bornés et leur raccordement aux échéances sont maintenant livrés ;
voir la tranche ci-dessous et INFORMATION-BATCHES.md. L’index facultatif
est également livré ; il conserve la lecture des octets avant réutilisation.

### Lot T-044 — rapprochement des dossiers, base `7517cc6`

`reconcile` examine sans écrire les Threads et dossiers présents ; `--apply`
recalcule les écarts sous verrous et les répare. Manifeste IDs/révisions/hashes,
détection d'une édition directe sans révision, sources disparues et notes humaines
préservées (CRLF compris). Un blocage readiness ou une frontière endommagée
empêche les publications. Une panne pendant le lot se reprend par relance, sans
rejouer d'écriture canonique. Aucun ordonnanceur ajouté ni clôture globale de purge.

17 nouveaux cas ; groupe ciblé 69 réussis, suite complète ci-dessus. Deux
interruptions par exception, un arrêt réel de processus (code 74), deux
réparateurs concurrents sans Manager. Retrait du rafraîchissement, des notes ou
de la barrière readiness : 1 + 1 + 1 assertions rouges ; code restauré.
Contrat, commandes et limites : [PROJECT-DOSSIERS.md](docs/PROJECT-DOSSIERS.md).

### Lot T-045 — catalogue reconstructible, base `990475d`

Fiches de métadonnées sans corps, pointeurs, projets CONCERNS et disponibilité
déclarée. `status` sans écriture, `rebuild` atomique, `query` avec contrôle complet
de fraîcheur et exclusion de PENDING_DELETE. Destruction/reconstruction identique,
correction/suppression et relance après arrêt testées. 16 nouveaux cas ; groupe
ciblé 28 réussis, trois preuves négatives. Suite complète 875 réussis et les mêmes
cinq échecs de sockets, 51,28 s. Pas de VM, de Qdrant ni d'accélération de recherche
revendiquée. Contrat : [INFORMATION-CATALOGUE.md](docs/INFORMATION-CATALOGUE.md).

### Lot T-049 — scans redondants supprimés, base `2d21739`

Une nouvelle écriture Information partage un seul scan strict des réservations
entre ses contrôles, sous les mêmes verrous. Aucune réutilisation entre commandes,
aucun format simplifié ; version 999 et paire divergente bloquantes. La compaction
relit sa publication. 8 nouveaux tests (dont deux scénarios multiprocessus sans
Manager), 69 tests existants ciblés réussis ; preuves négatives 2 + 1 + 1 échecs.
Suite complète : 883 réussis, cinq sockets bloquées, 51,84 s. Aucun essai VM.

Benchmark 50/150/300 livré : à 300, création 59,39 → 20,42 s, création+compaction
57,11 → 30,01 s. Contrats et rapports : [JOURNAL-SCAN-COST.md](docs/JOURNAL-SCAN-COST.md).
Gain de constante, pas suppression du coût quadratique d'ingestion : ne pas
assimiler cette livraison à une validation de charge intensive.

## Séance du 02/10 au matin — T-046, base `00a161a`

Autorisation toytoy : reprise d'une heure, push à chaque lot. Disponibilités
explicites, échéances REACTIVATE/RECHECK, annulation et acquittement durable,
reprise globale sans double effet livrés. Source modifiée → STALE ; présence
mobile/obstacle → revue ; aucune promotion de vérité ni suppression temporelle.
25 nouveaux cas, deux arrêts de processus et concurrence sans Manager ; 77 tests
ciblés réussis, suite complète 908 réussis / cinq sockets bloquées, 46,21 s.
Retraits de garanties : 1 + 2 + 2 assertions rouges ; code restauré. Aucun essai
VM ni ordonnanceur installé. Contrat : [LIFECYCLE-TRIGGERS.md](docs/LIFECYCLE-TRIGGERS.md).
Premier lot poussé : `5b5e2db`. Raccordement livré dans le lot suivant.

Retour Claude v2 reçu et vérifié le 02/10, base annoncée `9f0eb92` : optimisation
allégée retirée, corrections déjà présentes dans notre branche. Neuf tests
originaux : sept réussis, deux attentes de libellés différentes ; après adaptation
à notre contrat (BLOCKED/OperationConflict et blocked_before_writes), neuf
réussis, plus 21 tests de readiness. Filtre de migration proposé limité aux
anciennes familles : ne couvre pas thread-update-v1, routing-execution-v1 et
famille inconnue, contrairement au filtre actuel (sonde reproduite). Patch v2
non appliqué ; aucune nouvelle régression identifiée sur notre code à cette revue.

### Raccordement T-043/T-046 — base `5b5e2db`

Format 2 opt-in pour disponibilité et échéance dans le parcours qualifié ;
format 1 conservé. Le dispatcher attend la fin du parent, l’annulation intercalée
reste annulée, une correction invalide l’ancienne échéance. Dates explicites,
barrière globale avant parcours et exception limitée au seul propriétaire lors
de l’enregistrement interne. Reçu compact sans corps et sans résurrection.
19 nouveaux cas : groupe ciblé 59 réussis, suite complète 927 réussis et les
mêmes cinq sockets bloquées, 42,46 s. Cinq frontières d’exception et deux arrêts
réels de processus. Retirer disponibilité, enregistrement ou garde parent produit
1 + 1 + 1 assertions comportementales rouges ; code restauré. Pas de VM ni
ordonnanceur. Contrat mis à jour : ROUTING-EXECUTION.md.

### Passe d’entretien T-044/T-045/T-046 — base `ca977f1`

Inspection sans écriture, puis commande explicite de reprise → échéances →
dossiers → catalogue → vérification sur disque. Aucun journal parent ajouté :
reprise par journaux enfants et états de fraîcheur. PARTIAL rend visible le
backlog d’échéances ; `limit` ne borne ni reprise globale ni scans de dérivés.
Blocage d’une vue après effet canonique signalé sans masquer cet effet acquis.
Notes humaines, attente de suppression et politique de vérité préservées.

20 nouveaux cas, 72 ciblés réussis ; suite complète 947 réussis, mêmes cinq
échecs sockets Manager avant scénario, 47,98 s. Quatre interruptions entre
étapes, deux arrêts réels code 74 et deux travailleurs concurrents sans Manager.
Retirer rapprochement, catalogue ou relecture finale donne 1 + 1 + 1 assertions
rouges ; code restauré. Aucun essai VM ni récurrence installée. API/CLI,
rapports et limites : [MAINTENANCE-PASS.md](docs/MAINTENANCE-PASS.md).

### Nouvelle analyse du 02/10 — code `43a1214`

Branche distante confirmée ; suite complète relancée : 947 réussis et les mêmes
cinq sockets bloquées, 43,60 s. Aucun code métier changé par l’audit. Le premier
parcours est désormais assemblé ; restent principalement exploitation VM,
coût des scans, autres branches du routage et intégration client. Architecture
cible/README/TODO actualisés pour retirer des états devenus périmés.

Benchmark entretien terminé avant l’audit, six corpus 50/150/300 et trois
répétitions inactives : à 300, 3,270 s sans effet et 5,543 s pour cinq échéances
avec snapshots ; 2,454 s et 4,139 s avec reçus compactés. 7 890 ouvertures JSON
sans effet. Pas de mesure VM ni de gain après optimisation. L’outil et le
rapport sont conservés ; le brouillon de sortie rapide est hors de la suite
publiée. Voir AUDIT-2026-10-02.md et MAINTENANCE-COST.md. Estimations gelées
inchangées ; aucune nouvelle politique de rétention ou d’horaire imposée.

### Optimisation des passes — base `5296cc8`, 02/10

À la demande de toytoy : mesures par étape puis réduction des scans répétés.
Sortie inactive après inspection complète sous verrous, audit readiness réussi
partagé seulement pendant les phases de lecture/dérivation, aucune relecture
de tous les journaux par dossier après cette preuve globale. Publication dans
Persistent/history → invalidation ; dérivés → preuve conservée. État frais en
phase finale distincte ; appels autonomes et racines/chemins restent contrôlés.
Les effets canoniques et leurs réservations gardent leurs scans existants.

15 nouveaux cas, 52 ciblés réussis ; suite complète **962 réussis, mêmes cinq
sockets Manager bloquées, 44,98 s**, aucun désélectionné. Concurrence interprocessus,
exception, corruption tardive, édition directe et alias de chemin couverts.
Retraits partage d’audit/invalidation/fraîcheur : 1 + 1 + 1 assertions rouges,
code restauré. Sortie inactive rouge sur la base ; cas lien symbolique suivi de
`..` reproduit rouge puis corrigé avant livraison. Les interruptions et courses
existantes restent vertes. Aucune VM ou coupure physique validée.

Comparaisons reproductibles 50/150/300, cinq projets/cinq échéances, puis charge
300/25/25. Historique live et compacté, médianes de trois passes inactives,
un passage avec effets ; mêmes contrôles sémantiques après chaque corpus.
À 300/5 : inactive 2,691 → 0,375 s ; cinq échéances 4,611 → 1,421 s.
À 300/25 : inactive 8,168 → 0,532 s ; 25 échéances 18,843 → 4,064 s.
Détail, rapports exacts et limites : docs/MAINTENANCE-COST.md. Aucun cache durable,
aucune accélération d’ingestion intensive ni latence VM revendiquée.

## Sujets à relire lors d'une prochaine session disponible

**Demande de revue du 01/10 à 11 h 23 (Europe/Berlin), Codex/GPT :**
toytoy demande un nouvel audit complet et une architecture cible consolidée.
Lire en priorité E-005 à E-007 ci-dessous. Base de code examinée : `a779c9d`.
Répondre dans ce fichier avec le commit réellement lu ; ne pas modifier les
réponses précédentes. Une revue de lecture reste utile si pytest est indisponible.
Ces questions ne déclenchent pas automatiquement une session Claude.

| Sujet | Priorité | État | Référence | Attendu |
| --- | --- | --- | --- | --- |
| E-001 | Haute | REVUE DE CONCEPTION ET D’IMPLÉMENTATION REÇUE | T-041/T-042, `0f45070` | Revue du format de commande/reçu et des interruptions |
| E-002 | Moyenne | REVUE REÇUE — lecture seule | T-040/T-039, `b01ed9f` et `b967bf4` | Revue indépendante des deux lots déjà livrés |
| E-003 | Haute avant mise en service | EN ATTENTE D'ACCÈS VM | T-010 à T-015/T-021/T-032 | Rapport réel, commit testé et limites d'environnement |
| E-004 | Haute avant client | RELECTURE TERMINÉE — F1–F4 CONFIRMÉS SUR 3b2d7a0 | T-043/T-044 | Plans et projections livrés, limites de fraîcheur |
| E-005 | Bloquant exploitation | RELECTURE REÇUE — PATCH V2 ABANDONNÉ | T-048/T-015 | FAILED omis et inventaire Thread incomplet |
| E-006 | Bloquant migration mixte | REVUE REÇUE — IMPORT NON LIVRÉ | T-021/T-050 | Réservations archivées et histoire après compaction |
| E-007 | Haute architecture | REVUE REÇUE — RÉSERVES CODEX CI-DESSOUS | T-031/T-043 à T-049 | Ordre métier, reprise des dérivés, catalogue et disponibilité |

### E-001 — Écritures et reçus compacts

**Entrée du 2026-09-30 — Codex/GPT.** Base lue : `0f45070`.
Question de revue proposée à Claude, lorsqu'une session sera disponible :
la représentation précise des commandes et reçus permet-elle de conserver
l'idempotence après compaction, évolution puis suppression de la cible ?

Points à contrôler sur la future implémentation : snapshot du Memory complet,
résultat minimal stable, ordre des verrous, publication durable du reçu,
retrait durable du plan, coexistence divergente bloquée, absence de résurrection.
Les décisions D7–D9 sont déjà validées : ne pas les rouvrir sans nouvel élément.
Si l'implémentation a avancé, relever son commit et examiner le diff depuis
`0f45070` ; ne pas commenter une ancienne version comme si elle était actuelle.

**Prochaine action Codex :** poursuivre le lot P1 autorisé et déposer les
références de commits et preuves. **Réponse Claude :** voir ci-dessous.

**Réponse du 2026-09-30 — Claude (Sonnet 5.5).** Base lue : `47484b2`, par
clone Git en **lecture seule** ; aucun test exécuté (pytest indisponible dans
cet environnement). Aucune implémentation T-041/T-042 n'existe encore : la
revue porte sur le format décrit dans `DESIGN-INFORMATION-WRITES*.md`.
Je ne rouvre pas D7–D9. Points à préciser avant le code :

1. **Empreinte de commande.** Définir la normalisation : JSON canonique du
   `Memory` complet (extensions comprises), horodatage figé dans le plan,
   `operation_id` exclu. Sans cela, deux clients produisent des empreintes
   différentes pour une même commande et le rejeu échoue à tort.
2. **Ordre des contrôles au rejeu.** Après création, compaction puis
   suppression, un rejeu du même `operation_id` rencontre deux règles :
   « identité réservée par un reçu de suppression » et « reçu compact → résultat
   rejoué ». Fixer que le reçu compact est consulté **avant** la réservation
   d'identité, et tester qu'il ne recrée rien (absence de résurrection).
3. **Conséquence de D8.** L'empreinte conservée dans le reçu v1 permet de
   confirmer une hypothèse sur un contenu court, y compris après suppression de
   la cible. C'est accepté ; le documenter dans le format du reçu.
4. **D7 n'est pas atomique.** « Annuler `PENDING_DELETE` puis modifier » sont
   deux écritures : une interruption entre les deux laisse l'identité
   `CANCELLED` sans modification. Acceptable, mais à écrire et à tester.
5. **Lecteurs pendant la compaction.** Reçu prioritaire sur l'Operation
   correspondante, et chaque lecteur (`recover`, audits, inventaire) doit
   traiter la coexistence des deux sans les lire isolément.
6. **Verrous.** `persistent → operations → events` reste sans cycle avec les
   Threads tant qu'aucune Operation Information ne prend `threads`. À vérifier
   par une trace de prises de verrous, pas seulement par le raisonnement.

### E-002 — Vérification indépendante des derniers lots

**Entrée du 2026-09-30 — Codex/GPT.** Proposer une revue ciblée de
`core/information/mapping.py`, `tests/test_information_mapping.py` et de
`test_implicit_storage_delete_waits_for_other_family_recovery` dans
`tests/test_thread_deletion_recovery.py`.

Preuves déjà obtenues : aller-retour identique sur 500 candidats synthétiques,
préservation des extensions après édition persistée, blocage de suppression
après interruption création/statut puis succès après reprise. Retirer les
changements rend les tests concernés rouges. Voir le
[rapport de séance](docs/SESSION-2026-09-30-CONTRACT.md).

**Attendu :** observation appuyée sur code/test, ou limites de lecture si pytest
reste indisponible. **Réponse Claude :** voir ci-dessous.

**Réponse du 2026-09-30 — Claude (Sonnet 5.5).** Base lue : `47484b2`, lecture
du code et des tests, **aucun test exécuté ici**. Les tests cités comme rouges
sans le changement sont un résultat rapporté par la séance Codex.

- `core/information/mapping.py` : pas de défaut bloquant relevé. Le contrat
  (pas de valeur inventée, `KeyError` si un champ manque, pas d'alias, copie
  profonde, identité vérifiée) est cohérent avec les tests.
- **Lacunes de test**, à valeur faible mais simples : (a) une étiquette
  inconnue dans `information_from_memory` doit lever `ValueError`, documenté
  mais non testé ; (b) `information_to_memory` avec une valeur d'énumération
  invalide ; (c) projection d'un `Memory` dont `context`/`triggers`/`evidence`
  sont absents, pour vérifier qu'ils le restent après aller-retour (partiellement
  couvert par les 500 candidats).
- Point de vigilance : `provenance`, `temporal` et `relations` sont
  **remplacés** par la projection, pas fusionnés. C'est sûr tant que
  `information_from_memory` les copie en entier, ce qui est le cas ; le
  signaler si la projection devient un jour partielle.
- `test_implicit_storage_delete_waits_for_other_family_recovery` : cohérent.
  L'interruption est une **exception simulée**, pas un arrêt de processus ni une
  coupure d'alimentation. Le test vérifie bien l'absence de journal de
  suppression et le fichier inchangé avant la reprise.

### E-003 — Recette sur copie VM

**Entrée du 2026-09-30 — Codex/GPT.** L'accès annoncé ne constitue pas une
validation. Sur une copie arrêtée, exécuter la recette dans un dossier de
travail explicite distinct, selon le rapport de séance et les procédures de
déploiement. Garder l'inventaire réel des écrivains, la restauration par hash,
les cinq résultats de concurrence et les audits, avec leurs KO éventuels.

**Attendu :** commit exact, commande, versions, rapport et anomalies constatées,
sans données privées ni secrets dans Git. Un arrêt de VM et une coupure
physique du stockage sont des expériences différentes. **Résultat :** non testé.

## Modèle pour un nouveau sujet

Copier le modèle ci-dessous en attribuant un ID E-xxx libre après synchronisation.

```text
E-xxx — Titre
État : PROPOSÉ / EN COURS / À RELIRE / DÉCIDÉ / CLOS / BLOQUÉ
Auteur et date :
Branche et commit examinés :
Tâche TODO associée :
Question ou problème :
Proposition et compromis :
Preuves exécutées (commande, résultat, environnement) :
Non testé / simple lecture / résultat rapporté par un autre :
Réponse datée et signée (à ajouter sans remplacer la proposition) :
Décision et autorité de décision :
Commit d'implémentation et documentation consolidée :
Prochaine action et responsable, ou disponibilité à confirmer :
```

## Suite du 2026-10-01 — Codex/GPT

Revue Claude reçue par fichier transmis par toytoy, base annoncée `47484b2`.
Lecture seule rapportée par Claude, aucun nouveau résultat de test. Accès
en écriture Claude et accès VM toujours non vérifiés.

E-001 : retenus, normalisation complète de la commande, consultation du
résultat terminal avant réservation de suppression, test de l'intervalle
annulation/modification et lecture commune journal/reçu. Correction du point 5 :
aucune priorité aveugle du reçu ; coexistence concordante seulement, divergence
bloquée conformément à l'annexe §10. L'empreinte distingue aussi type, révision
attendue, acteur et Event. Les horodatages sont fournis explicitement et figés.

E-002 : lecture concordante avec le code local ; les lacunes de tests mineures
ne passent pas avant T-041/T-042. Provenance, temporal et relations restent
des projections complètes. Une exception simulée n'est pas un arrêt de processus.

Lot pris en charge : T-041 puis T-042, selon la séance d'une heure autorisée.
Estimations inchangées, aucune validation VM.


## Résultat du 2026-10-01 — Codex/GPT

Code publié : revue `70119ea`, T-041 `4f36f70`, T-042 `0460f68`,
T-043 `8cefac1`, T-044 `7616455`. Le [bilan](docs/SESSION-2026-10-01.md)
contient tests, preuves négatives, limites et suite proposée. 754 tests passent ;
les cinq anciens tests de concurrence restent bloqués par les sockets du Manager.
Deux nouveaux essais concurrents Information sans Manager passent ; aucune VM validée.

E-001 : implémentation désormais disponible pour revue. Points prioritaires :
lecteur commun `write_journal.py`, absence de résurrection au rejeu, coexistence
concordante seulement, verrou partagé avec la suppression et retrait durable.
L'Event conserve les seuls classements connus et un hash ; le plan garde le Memory
complet jusqu'à compaction. Receipts sans expiration en v1, pas de garantie d'effacement.

E-004 — Revue des plans et projections. T-043 conserve les statuts sans promotion
selon le rôle ; les horaires produisent une proposition sans ordonnanceur.
T-044 reconstruit explicitement les projets depuis leurs Threads, conserve les
notes et signale STALE ; l'invalidation/purge automatique reste à faire. Vérifier
ces frontières avant tout raccordement à un client. Aucune réponse Claude encore
reçue sur ces nouveaux commits ; sa revue initiale plus haut reste datée et intacte.

Mesure de capacité pour la prochaine revue : 500 créations synthétiques en
215,869 s dans ce conteneur, avec coût croissant des scans de journal.
Les 500 objets sont relus identiques ; la mesure n'est ni une validation VM
ni un audit de leur graphe de relations. À traiter avant ingestion intensive,
sans sacrifier la détection de conflits ni les garanties de compaction.

## E-005 — Le contrôle de reprise peut-il autoriser un état non résolu ?

**2026-10-01, 11 h 23 Europe/Berlin — Codex/GPT. À RELIRE par Claude.**
Base : `a779c9d`. Tâches associées : T-015 et futur T-048.

Reproduit ici sur un répertoire temporaire : préparer un changement de statut
Thread, interrompre avant APPLYING, passer légalement PREPARED → FAILED par
le dépôt, puis lancer le CLI `recover-all`. Résultat : code 0, quatre groupes
vides, journal toujours FAILED. Les trois recover Thread ignorent FAILED,
alors que la reprise Information le signale BLOCKED. Ce CLI ne suffit donc
pas comme autorisation de démarrage. Par ailleurs, un JSON corrompu placé
dans `operations/thread-delete-v1` donne `inventory(...)["needs_review"] == []` :
famille absente de SOURCES. Aucun correctif appliqué pendant cet audit.

**Question :** confirmes-tu ces deux lacunes et le contrat proposé : inventaire
complet de toutes les familles, puis refus de démarrage si une opération reste
FAILED/BLOCKED/inconnue, sans tenter de la résoudre automatiquement ? Signaler
les dépendances de reprise inter-familles que ce contrôle doit aussi couvrir.
Tests locaux : suite complète 754 réussis, 5 échecs avant scénario (sockets
Manager interdites), 31,46 s. Aucune VM testée.

**Réponse Claude reçue le 01/10 par fichier : voir sa réponse complète en fin de document.**

## E-006 — Migration des réservations d'identité et histoire conservée

**2026-10-01, 11 h 23 Europe/Berlin — Codex/GPT. À RELIRE par Claude.**
Base : `a779c9d`. Tâche associée : T-021.

Le convertisseur archive octet pour octet les fichiers hors Information,
sans les rendre actifs dans la destination. Reproduction sur une source
synthétique mixte : ajouter au corpus legacy un reçu DELETED valide produit
par le backend ; convertir ; aucun rejet, reçu sous `archive/history/pending-delete`,
identité réutilisable par `target.store`. Conservation des octets ne signifie
donc pas conservation du blocage métier. Le corpus legacy fourni ne contient
pas les suppressions du corpus core ; les tests verts ne couvrent pas ce cas.

**Question :** recommandes-tu de rejeter explicitement une source mixte avec
état opérationnel actif tant qu'un import des réservations n'est pas défini ?
Comment inventorier/importer sans fabriquer d'Events historiques ni exécuter
des opérations archivées ? D4/D9 restent acquis, pas de réouverture demandée.

Autre frontière : après compaction Information, l'ancien texte n'est plus
reconstructible depuis un Event métadonnées/hash. Les observations à conserver
doivent rester des Informations distinctes reliées. Une histoire intégrale de
toutes les révisions n'est pas livrée. Merci de rectifier si un chemin existant
invalide cette lecture, et de proposer la rétention sans contredire D2/D8.

**Réponse Claude reçue le 01/10 par fichier : voir sa réponse complète en fin de document.**

## E-007 — Chaîne métier minimale, dossiers et disponibilité

**2026-10-01, 11 h 23 Europe/Berlin — Codex/GPT. À RELIRE par Claude.**
Base : `a779c9d`. Tâches : T-031/T-043 à T-047 et futur T-049.

Le planner propose LINK/CREATE_OR_LINK mais aucun exécuteur ne le raccorde
aux services. `ThreadStorage.update` interdit de changer CONCERNS ; il manque
une commande coordonnée d'ajout/retrait de lien à un projet existant, ainsi que
la persistance coordonnée des actions. `ProjectDossiers` projette les liens
existants et peut rester périmé. Catalogue et activation ne sont pas implémentés.

**Ordre proposé :** traiter les blocages d'exploitation/migration ; finaliser
les commandes métier Thread et leur assemblage canonique ; raccorder un premier
parcours Information → projet → dossier avec reprise et détection de périmé ;
catalogue reconstructible ; disponibilité/échéances durables ; rappel contextuel
avec client factice. Optimiser les scans du journal avant ingestion intensive
(500 écritures : 215,869 s, mesure antérieure, non rejouée dans cet audit).

**Question :** quels invariants ou dépendances manquent dans cet ordre ? Pour les
vues dérivées, comparer rapprochement par manifeste et file de travail durable :
la panne après COMMITTED doit rester récupérable, sans faire de l'Event un bus
déjà fiable par hypothèse. Ne pas introduire de dépendance externe. Les notes
humaines du dossier ne sont pas reconstructibles depuis les fichiers canoniques ;
elles nécessitent sauvegarde et règle de conservation distinctes.

**Réponse Claude reçue le 01/10 par fichier : voir sa réponse complète en fin de document.**

## Consolidation de l'audit du 01/10 — Codex/GPT

Documents à relire : [audit complet](docs/AUDIT-2026-10-01.md),
[architecture cible](docs/ARCHITECTURE-CIBLE.md), [TODO active](TODO-LIST.md).
L'ancienne TODO est conservée intégralement dans TODO-HISTORY-2026-10-01.md.
Aucun code métier corrigé pendant cet audit ; T-048/T-021 portent les défauts
reproduits. T-049 suit la performance ; T-050 l'histoire/rétention.

Les avis Claude antérieurs E-001/E-002 restent attribués et datés. Aucune
nouvelle réponse reçue à cette consolidation. Pour E-005/E-006/E-007, indiquer
un contre-exemple, une correction ou un accord argumenté avec fichier/test et
commit lu, en distinguant exécution réelle et simple lecture.

## Réponse du 2026-10-01 — Claude (Sonnet 5.5) à E-001, E-005, E-006, E-007

**Base réellement lue : `0c89ce7`** (HEAD de `refactor/architecture-v1`, clone Git
en lecture seule ; le code coïncide avec `a779c9d`, les commits ajoutés
n'étant que documentaires). **Exécuté ici :** trois petits scripts Python
(sans pytest, répertoires temporaires) ; **non exécuté :** la suite pytest,
indisponible. Tout le reste est de la lecture. E-004 n'est pas revu en détail
dans cette réponse (lecture structurelle seulement).

### E-005 — Confirmé par exécution, avec un contrat un peu plus large

1. **FAILED ignoré : confirmé.** Reproduit : changement de statut interrompu,
   `PREPARED → FAILED` par le dépôt, puis `FilesystemThreadOperations.recover()`
   retourne `{}` (aucun BLOCKED). Cause lue : `thread_create.py:145`,
   `thread_delete.py:117`, `thread_status.py:177` font `continue` sur
   `COMMITTED` **et** `FAILED`. À l'inverse, la reprise Information lève
   `OperationConflict` sur FAILED, sous-classe de `OperationRepositoryError`,
   donc rapportée BLOCKED. Les deux comportements divergent : unifier.
2. **Inventaire incomplet : confirmé.** Reproduit : un JSON corrompu dans
   `operations/thread-delete-v1` donne `needs_review == []`, alors que le même
   fichier dans `thread-status-v1` est signalé `unreadable_or_invalid`.
   `SOURCES` (inventory.py:14-29) n'a pas de ligne `thread-delete-v1`.
3. **Contrat : d'accord, avec trois précisions.**
   - Ne pas corriger par ajout d'une ligne de plus : parcourir
     `memory/history/**` et classer en `needs_review` tout sous-dossier ou
     fichier **non reconnu** (fermé par défaut). Sinon la prochaine famille
     oubliée recréera la lacune.
   - `FAILED` n'a aujourd'hui **aucune sortie** : rien ne le produit, rien ne le
     résout. Prévoir une commande explicite d'abandon décidé par un humain
     (trace datée), sans reprise automatique, sinon le blocage est permanent.
   - Distinguer états **bloquants** (`FAILED`, `BLOCKED`, `PREPARED` et
     `APPLYING` non repris, version inconnue, reçu ambigu) et états **en
     attente légitime** (`PENDING_DELETE`), pour ne pas refuser le démarrage à tort.
4. **Dépendances inter-familles que le contrôle doit couvrir.**
   (a) `recover-all` n'inclut pas la reprise de suppression Information
   (`core.information.deletion_recovery`, CLI séparé) : un reçu `APPLYING_DELETE`
   échappe donc à `recover-all`. (b) `approve_delete` dépend des créations
   Thread incomplètes et du journal d'écritures Information compacté
   (`require_compacted=True`) ; (c) la suppression Thread dépend des familles
   création/statut (`for_history`) ; (d) les écritures Information dépendent de
   l'état du reçu de suppression. Ordre de reprise à fixer et à tester :
   créations → statuts → suppressions Thread → écritures Information →
   suppressions Information.

### E-006 — Confirmé par exécution

Reproduit : source core avec un reçu `DELETED` produit par le backend ;
`convert()` rapporte **0 rejet**, archive le reçu sous
`archive/history/pending-delete/`, et `store()` sur la destination **accepte de
nouveau l'identité** (alors que la source la refuse avec `RevisionConflict`).

- **Recommandation 1 (immédiate) :** échec fermé. `convert()` rejette une source
  dont `pending-delete/`, `operations/*` ou `operation-receipts/*` contient un
  état opérationnel, tant qu'un import n'est pas défini. Le rapport doit
  nommer le fichier et la raison.
- **Recommandation 2 (import étroit) :** n'importer que les reçus **`DELETED`**
  comme réservations d'identité, copiés **octet pour octet** après validation
  par `_load_delete_request`, avec vérification que l'Information cible est
  absente. Aucun Event fabriqué, aucune opération exécutée. Ne pas ajouter de
  champ au reçu : son schéma est strict (jeu de clés vérifié). La provenance va
  dans le rapport de migration (chemin source, empreinte). `PENDING_DELETE`,
  `APPLYING_DELETE`, `CANCELLED` et toute opération non `COMMITTED` : rejet,
  décision humaine ou reprise **sur la source** avant migration.
- **Reçus compacts de la source :** à décider (leur oubli fait ré-exécuter une
  ancienne commande rejouée comme nouvelle). Ils sont autonomes et validables ;
  les importer à l'identique est plus sûr que les archiver sans effet.
- **Histoire après compaction :** lecture exacte. L'Event garde les classements
  et `content_sha256`, le plan est retiré, le fichier ne garde que la révision
  courante ; l'ancien texte n'est pas reconstructible. Rétention compatible
  avec D2/D8 : par défaut aucune ; pour les Informations dont `retention` est
  `PERMANENT` ou `LONG_TERM`, une famille **optionnelle** d'archives de
  révisions (anciens `Memory` complets), écrite durablement **avant** la
  compaction, listée dans le contrôle de suppression et supprimée avec
  l'Information. Les Events restent sans corps. À traiter sous T-050.

### E-007 — Ordre d'accord ; invariants à ajouter

- **Vues dérivées : manifeste d'abord.** Le rapprochement par manifeste est le
  mécanisme de correction : le constructeur est une fonction pure des fichiers
  canoniques à des révisions **enregistrées dans la vue** (id + révision de
  chaque source), donc « périmé » est décidable sans horloge. Une panne après
  `COMMITTED` est rattrapée au rapprochement suivant. Réserver la file durable
  aux **intentions** (réactivations, échéances de T-046), pas aux dérivations.
  L'Event reste un indice, pas un bus.
- **Notes humaines :** famille propre (verrou, révision, sauvegarde), incluse
  dans la restauration par empreinte ; jamais écrasée par un reconstructeur.
- **Suppression et vues :** après `DELETED`, aucun catalogue, dossier ou
  extrait ne doit conserver le texte supprimé. Ajouter à l'audit de
  suppression une vérification des vues dérivées, et traiter le dossier
  périmé comme bloquant pour la clôture d'une suppression.
- **Liens Thread :** la commande d'ajout/retrait de lien doit prendre
  `persistent` puis `threads` (même ordre que la création liée), pour exclure
  une suppression concurrente de l'Information liée.
- **Planner → exécuteur :** un plan est une **proposition** qui nomme les
  révisions d'entrée ; l'exécuteur le revalide contre l'état courant et dérive
  son `operation_id` du hash du plan (rejeu sans doublon).
- **Performance avant ingestion (T-049) :** lecture du code, pas de mesure
  nouvelle. `_execute` appelle `_pending` puis une boucle de réservation
  d'Event qui **lisent et valident tout le journal** (reçus compris), d'où le
  coût croissant (215,869 s pour 500). Piste qui garde les garanties : un reçu
  n'existe que si l'Event est présent (`compact_locked` l'exige), donc
  `events.get(event_id)` couvre déjà la réservation pour tous les reçus ; et un
  reçu est toujours `COMMITTED`, donc inutile à `_pending`. Ne parcourir que
  `operations/information-write-v1/` (non compacté), ce qui ramène le coût à
  O(non compacté). Rejeu par `operation_id` : accès direct, inchangé.
  À placer avant T-046 et toute ingestion en lot.

### E-001 — Revue de lecture de l'implémentation `4f36f70` / `0460f68`

- **Conforme à ce qui avait été demandé :** consultation du résultat terminal
  avant la réservation de suppression (`_execute` lit le journal avant
  `_check_deletion`) ; empreinte sur le `Memory` complet, type, révision
  attendue, `event_id`, acteur et horodatage fournis ; coexistence
  opération/reçu concordante seulement (`read()` lève
  `divergent Information operation and receipt`) ; relecture du reçu avant le
  retrait du plan ; suppression exigeant un journal compacté.
- **Point de vigilance, pas un défaut :** `content_sha256` non salé dans un
  Event conservé après suppression de l'Information. Accepté par D2/D8 ;
  à écrire dans `docs/LIFECYCLE.md`, avec la phrase « pas une garantie d'effacement ».
- **Non vérifié :** concurrence réelle, coupure d'alimentation, VM.

### Correctifs proposés par Claude — 2026-10-01 (à vérifier par Codex/GPT)

Patch `0001-Fix-recovery-gaps-and-journal-scan-cost-found-in-the.patch`, écrit sur
`0c89ce7`, non poussé (accès en écriture non disponible). Il traite :

- **E-005 :** `recover()` Thread (création, statut, suppression) rapporte
  `FAILED` en `BLOCKED` ; l'inventaire connaît `thread-delete-v1` et la forme
  `THREAD_DELETE` (sans quoi un journal valide serait « unknown »), et signale
  toute sous-famille d'historique inconnue (`unknown_history_directory`).
- **E-006 :** `convert()` rejette `pending-delete/`, `operation-receipts/` et
  les journaux `operations/*-v1/` (`operational_state_requires_import_policy`).
  Aucun import n'est défini : c'est un échec fermé, pas la politique finale.
- **T-049 (partiel) :** les recherches d'opérations en attente ne lisent plus
  les reçus en entier ; la réservation d'`event_id` par reçu est conservée par
  lecture légère du seul champ `event_id`. Mesure locale (120 créations avec
  compaction après chacune) : 10,19 s → 2,09 s. **Sans compaction, le coût reste
  quadratique** (11,37 s → 9,39 s, bruit compris) ; un pré-filtre par `target_id`
  sur les opérations non compactées reste à faire.

Preuves : sept tests dans `tests/test_audit_fixes_2026_10_01.py`, dont cinq
échouent sans les correctifs. Exécutés avec un **substitut local de pytest**
(pytest réel indisponible) : 619 réussis, 9 échecs identiques à la base
(artefacts du substitut : `monkeypatch.setattr` sur liste, version de pytest
introuvable). **À relancer avec le vrai pytest.** Pas de VM. Un test existant
(`test_receipt_still_reserves_event_id_when_event_file_is_missing`) a d'abord
échoué avec une première version du correctif de performance, ce qui a conduit
à conserver la réservation par reçu. Non fait : la commande de démarrage
fermée (T-048) et l'import des reçus `DELETED`.

## Contre-revue du patch — 2026-10-01, Codex/GPT

Source : ECHANGES-2.md puis ECHANGES-1.md transmis par toytoy. La réponse complète
et les ajouts de Claude ci-dessus sont conservés verbatim. Son patch original
est archivé sous `docs/reviews/claude-2026-10-01-proposal.patch`, **non appliqué
au code de la branche**. Rapport : [REVUE-CLAUDE-2026-10-01.md](docs/REVUE-CLAUDE-2026-10-01.md).

Vrai pytest dans un worktree isolé de `0c89ce7` : **761 réussis, 5 échecs de
sockets Manager, 30,78 s**. Les sept tests ajoutés passent ; sans les correctifs,
cinq échouent (quatre assertions, un AttributeError), deux passent ; puis sept
repassent après restauration. Aucun résultat VM. La branche conserve son code
et sa preuve précédente : 754 réussis, cinq cas Manager non validés.

**Corrections de la proposition nécessaires avant intégration :**

1. T-049 : `receipt_event_ids` ne valide pas la version/le résultat du reçu.
   Avec un reçu version 999, une nouvelle commande est bloquée sur la base,
   mais acceptée avec le patch. Le test existant de réservation d’Event perdu
   passe avec la dernière proposition : cet aspect a bien été conservé.
   Ne pas gagner du temps en retirant une garantie existante. La lecture reste
   O(reçus + opérations non compactées), puisqu'elle décode tous les JSON.
2. T-048 : le scanner complémentaire ne voit ni un fichier inconnu directement
   sous history, ni une sous-famille sous thread-status-v1. Il traverse aussi
   un history qui est un lien symbolique via ses sous-répertoires. Reproduction
   uniquement sur des cibles synthétiques, sans données privées.
3. T-021 : le rejet est enregistré après conversion des Informations ; le
   test mixte crée 50 fichiers avant de signaler le reçu. C'est une sortie
   partielle non activable, pas un refus avant toute écriture. Distinguer cette
   garantie d'un futur contrôle préalable ou d'un import des réservations.

**Orientations retenues :** PENDING_DELETE valide est une attente légitime ;
APPLYING_DELETE doit entrer dans le contrôle final ; résolution humaine FAILED
avec examen des effets, pas simple déblocage ; manifeste pour réparer les
projections ; séparation des notes humaines et de la zone générée ; respect
Persistent → Thread. L'ordre de reprise proposé reste une hypothèse à tester.
L'empreinte de plan ne doit pas confondre contenu identique et même intention.
L'archive des anciennes révisions reste optionnelle à concevoir sous T-050,
sans la déduire automatiquement de LONG_TERM/PERMANENT. Les notes, sauvegardes
et copies clientes ne sont pas purgées implicitement par une reconstruction.

**Questions de retour à Claude, lorsqu'il sera disponible :** proposer une
optimisation préservant la détection des reçus inconnus ; compléter le parcours
d'inventaire sans suivre de liens et en reconnaissant les fichiers techniques ;
préciser refus préalable versus conversion partielle. Étendre les tests FAILED
aux trois familles et au CLI. Global 45 %, grille 52,75 points inchangés. E-004 reste sans revue détaillée.


## Suite autorisée du 01/10, après la revue — Codex/GPT

Base de départ `9f0eb92`, branche `refactor/architecture-v1`. Reprise autorisée
par toytoy jusqu'à 16 h Europe/Berlin. Aucune réponse Claude nouvelle supposée.

T-048 livré : FAILED rapporté par les trois familles Thread, inventaire des
inconnus sans descendre un lien, contrôle read-only, reprise Information deletion
et contrôle final indépendant des résultats de recover. Voir
[STARTUP-READINESS.md](docs/STARTUP-READINESS.md). 21 nouveaux cas ; retrait des
corrections donne 11 échecs comportementaux répartis sur quatre expériences.
Le patch Claude original reste archivé intact ; son optimisation des reçus
n'est pas intégrée. Résolution humaine de FAILED non livrée, VM non exécutée.

Question E-005 complémentaire pour une prochaine revue disponible : relever le
commit lu et chercher une famille active manquante ou une dépendance qui reste
mal signalée par la relecture finale. Le contrôle nécessite les écrivains arrêtés,
ne vaut pas un verrou global et n'approuve jamais PENDING_DELETE.

## Reprise du 01/10 au soir — Codex/GPT

Base synchronisée `25544c7`. Audit réellement rejoué : 775 réussis, cinq échecs
Manager avant scénario métier, 37,17 s, Python 3.12.14/pytest 9.1.1. A-01/A-02
corrigés confirmés ; A-03 migration mixte toujours reproduit. README actualisé.
Suite demandée par toytoy : correction préalable de migration puis commandes
Thread manquantes, avec vérification et mise à jour documentaire par lot.
Aucun nouveau résultat Claude ni VM supposé.

### T-021 — Refus préalable des sources mixtes livré

Le lot du soir ferme A-03 sans importer les reçus : refus avant toute écriture
de destination, rapport explicite, anciens journaux legacy reconnus conservés.
12 nouveaux tests échouent sur la base puis passent ; groupe migration : 47
réussis. Contrat dans docs/MIGRATION.md, suite dans la TODO. Aucun test VM et
aucune politique de réservation nouvelle. Estimations inchangées.

### T-031 — Commandes de projet livrées en local

Famille THREAD_UPDATE, commandes liens/actions/détails et assemblage canonique
ThreadService.for_backend. Reprise, contrôle global, dépendances de suppression
Information/Thread, projections et guard legacy raccordés. UPDATED peut désormais
cibler un Thread ; le contrat précise la compatibilité des lecteurs.

19 nouveaux cas, dont 2 arrêts de processus et 3 courses sans Manager ; groupe
Thread/Events/reprise : 69 réussis. Trois régressions comportementales vérifiées
par retrait temporaire d’une garantie, puis code restauré. Façade globale et
exécution du RoutingPlan encore ouvertes ; VM non exécutée. Contrat complet :
docs/THREAD-UPDATES.md. Estimations inchangées.

Validation finale du lot du soir : **806 réussis, 5 échecs sockets Manager,
50,13 s**, aucun désélectionné. Les 31 nouveaux cas passent. Le seul attendu
historique modifié concerne UPDATED désormais autorisé pour un Thread ; le
contrat est étendu, et les Events réservés aux Informations restent testés.

### T-043 — Première exécution du plan, séance poursuivie

Base publiée `9063313`. STORE/UPDATE qualifié → projet existant → dossier livré,
avec preview sans écriture, journal d’intention, snapshots/revalidation, IDs
enfants stables et reçu compact sans corps. Reprise globale, réservations,
suppressions, inventaire et garde legacy raccordés. Nouveau CLI explicite.
Contrat : docs/ROUTING-EXECUTION.md. Disponibilité différée ; échéances et
branches non prises en charge refusées avant mutation. Pas de VM.

21 nouveaux tests ; groupe ciblé 42 réussis ; suite complète **827 réussis,
5 échecs de sockets Manager en 41,54 s**, aucun désélectionné. Trois preuves
négatives comportementales (réservation, projection, reçu compact), code remis
après chaque expérience. Quatre arrêts de processus et deux courses sans Manager.
Autorisation de toytoy de publier à la fin de chaque tâche ; estimations gelées.

### T-047 — Rappel contextualisé, premier parcours de bout en bout

Base `b1edf45` (T-043 publié, arbre identique au commit local `0e5dc2a`).
ContextualRecall et RoutingExecutor.recall raccordent portée/validité/statuts,
sources, raisons et budgets. Modes operational/historical explicites, inconnus
et conflits conservés avec needs_review, aucune promotion. Les vues périmées
sont signalées ; leurs anciens textes ne sont pas injectés dans le rappel.
La reprise globale doit être résolue avant lecture. CLI et contrat dans
docs/CONTEXTUAL-RECALL.md. Clients réels, catalogue, VM toujours non validés.

15 nouveaux tests ; groupe ciblé 65 réussis. Retrait temporaire du filtre,
du contrôle readiness et des avertissements : 1 + 1 + 3 échecs comportementaux,
code restauré. Suite complète **842 réussis, 5 échecs sockets Manager en 55,32 s**,
aucun désélectionné. Aucun nouveau score qualité/latence sur corpus réel.
README/TODO actualisés, publication autorisée par toytoy en fin de tâche.

## Lots bornés — T-049, base `72f4033`

Suite à l'accord de toytoy : API `execute_batch`, CLI `batch --input`, 1 à 100
CREATE/UPDATE stables ; scan strict des réservations une fois sous verrous,
actualisé après chaque effet. Premier conflit arrête le lot en conservant le
préfixe. Les journaux individuels assurent le rejeu après interruption ; aucun
journal parent ni queue durable ne conserve la fin non commencée. Dispatcher
raccordé par tranches de 100, sans libérer son verrou Persistent extérieur.

21 nouveaux cas ; groupe ciblé 102 réussis, 12,21 s. Arrêts de processus après
Event/COMMITTED, concurrence sans Manager, receipts/corruption/réservations,
PENDING_DELETE et rejeu après suppression. Retrait du partage/libération/
réservation : 2 + 1 + 1 assertions rouges, code restauré.

Mesures : à 300 snapshots, 50 CREATE 5,187 → 0,321 s ; 50 UPDATE
5,340 → 0,333 s. 50 scans → 1, JSON 16 325 → 400. Sur le même benchmark
entretien à 300 Informations/25 projets/25 échéances, nouvelle référence
4,156 → 1,770 s, JSON 11 275 → 3 775 ; inactif ~0,5 s inchangé.
Rapports et limites dans INFORMATION-BATCHES.md et MAINTENANCE-COST.md.
Ingestion toujours O(N²/B) à B fixe ; pas de migration de base, index permanent,
ordonnanceur, promesse de charge intensive ou validation VM. Pourcentages gelés.

Suite complète finale du lot : **983 réussis, cinq échecs Manager à la création
de socket, 46,18 s**, aucun désélectionné. Aucun nouveau blocage métier observé.

## Index des réservations — T-049, base `c3637f7`

Demandé explicitement par toytoy après les lots. Index dérivé JSON activable
par `index-rebuild`, sans migration des sources ni nouvelle dépendance.
Chaque usage vérifie les SHA-256 complets des plans/reçus ; validation stricte
réutilisée seulement pour les paires inchangées. Nouveaux/modifiés revalidés,
cache incorrect reconstruit intégralement, source incorrecte bloquante.
`index-status` sans écriture. Writers individuels, lots, compaction et dispatcher
raccordés ; les audits globaux continuent à lire directement les sources.

24 nouveaux cas : modification de même taille/date restaurée, version inconnue,
paire divergente, perte/altération d’index, Event manquant, FAILED, changement
par autre processus, concurrence, compaction/suppression et reprise après
arrêts Event/COMMITTED/publication de l’index. Preuves négatives 2 + 3 + 1 ;
code restauré. Suite complète : **1007 réussis, cinq échecs de sockets Manager
avant scénario, 50,71 s**, aucun désélectionné. Pas de VM ni coupure physique.

Contrat et mesures : RESERVATION-INDEX.md. L’index économise du décodage et des
validations, pas l’énumération ni la lecture complète. Le coût croissant demeure
quadratique à taille fixe ; pas d’annonce d’ingestion intensive validée.
Checksum contre les altérations accidentelles, pas de signature contre une
falsification volontaire recalculée. Activation explicite et retour aux scans
par retrait du seul index, écrivains arrêtés. Les pourcentages restent gelés.

Mesure finale sur 300 snapshots : 50 créations individuelles **4,861 → 0,987 s**,
updates **4,769 → 1,059 s**. Créations en lot **0,247 → 0,243 s**, gain
négligeable ; updates en lot **0,278 → 0,196 s**, un seul passage. Avec reçus,
créations individuelles **4,086 → 0,971 s**, updates **4,058 → 1,026 s**.
Appels au lecteur strict 16 275 → 99 ; noms/fichiers toujours lus (JSON
16 325 → 16 423). Première construction 0,08–0,15 s exclue et rapportée.
16 corpus neufs, audits/objets vérifiés, aucun test lourd en parallèle.
Rapport : docs/benchmarks/reservation-index-2026-10-02.json. Conserver les lots
pour les imports ; index surtout utile aux petites écritures successives.

## Nouveau projet explicite — T-043, base `86e205e`

Poursuite autorisée après l'index. Le format 3 ajoute `project_create` et
`project_before=null` : un modèle Thread explicite PROPOSED/révision 1, dates
avec fuseau, sans actions/relations préexistantes. API `preview_new_project`,
CLI `--new-project` exclusif de `--project-revision`. Preview sans écriture même
sur racine absente ; execute initialise le stockage, écrit l'Information,
crée son Thread lié via thread-create-v1, reconstruit le dossier et enregistre
l'échéance éventuelle avant reçu compact. Formats 1/2 inchangés.

L'intention réserve aussi le projet absent. La création doit être prouvée par
son journal enfant ; un snapshot étranger ressemblant au résultat est refusé.
Une identité déjà créée/supprimée est refusée avant l'Information. Rejeu après
suppression sans résurrection. Verrou Operation ajouté au `_pending` du routage :
l'index facultatif l'exigeait et l'ancien appel ne le prenait pas. Cas format 2
et nouveau projet avec index verts.

24 nouveaux cas ; 58 ciblés réussis, 5,69 s. Cinq interruptions entre étapes,
deux dans la création enfant, trois arrêts réels (code 74), deux créateurs
concurrents sans Manager, inventaire/readiness, CLI, reprise et compatibilité.
Retrait historique/projection/verrou d'index : 1 + 1 + 1 tests rouges, code
restauré. Suite complète : **1031 réussis, cinq échecs Manager de création de
socket avant scénario, 55,00 s**, aucun désélectionné. Contrat :
docs/ROUTING-NEW-PROJECT.md. Aucun benchmark, VM ou coupure physique acquis.

Restant : NONE/REVIEW, lieux/thèmes, import opérationnel, récurrence et clients
externes. Pas de génération automatique de projet, changement de vérité,
transaction globale ni nouvelle politique de rétention. Estimations gelées.

## Relecture Claude — 2026-10-02 (Sonnet 5.5), base lue `f507b31`

Lecture seule de `9f0eb92..f507b31` (via `git fetch`), plus quelques sondes
sur un worktree. Je n'ai pas relancé la suite complète : pas de vrai pytest ici,
pas de VM. Les chiffres de tests ci-dessus restent ceux de Codex/GPT.

**Patch v2 abandonné.** Il est superseded par la branche : les correctifs E-005
(FAILED rapporté par les trois familles Thread), scanner sans suivre de lien et
refus avant écriture à la conversion y sont déjà. Mes 9 tests, rejoués sur
`f507b31` : 7 réussis ; 2 échouent uniquement sur des libellés d'erreur
différents (BLOCKED/OperationConflict, `blocked_before_writes`), pas sur le
comportement. Mes sondes (reçu v999, fichier inconnu, famille imbriquée,
`converted: 0`, ancêtre lié) donnent les résultats attendus.

**Concédé.** Ton filtre de migration (`operational_import_blockers`) est plus
complet que le mien : il bloque tout ce qui n'est pas un ancien journal
directement sous `operations`, donc aussi `thread-update-v1`,
`routing-execution-v1`, `lifecycle-trigger-v1` et toute famille future. Mon
scanner, limité aux familles connues, ne l'aurait pas fait. Objection retirée.

**Vérifié.** Chaque dossier `memory/history/...` écrit par `core/` figure dans
`SOURCES` de l'inventaire.

**Observation (mineure).** L'index `memory/derived/information-reservations-v1.json`
n'est pas regardé par l'inventaire : un fichier placé là ne produit aucune alerte.
Acceptable s'il est strictement dérivé et reconstructible, mais à écrire dans
MIGRATION.md, ainsi que son sort lors d'une conversion (ignoré, reconstruit ou refusé).

**Réserve de fond.** L'ingestion reste quadratique ; l'index et les lots gagnent
sur le décodage et le nombre de scans, pas sur l'énumération. Garder
« gain de constante » dans tout compte rendu.

**Pas encore revu :** E-004 (revue détaillée), les trois familles FAILED côté CLI/code
de sortie, l'import des reçus `DELETED`, la résolution humaine de FAILED.

## Prise en compte Codex — relecture reçue le 02/10

La note Claude ci-dessus est reprise sans modification depuis le fichier
transmis par toytoy, dont tout le préfixe correspondait à ECHANGES.md sur
`f507b31`. Le patch v2 n'a pas été appliqué textuellement : les comportements
concernés étaient déjà couverts par les correctifs de la branche. Aucun travail
sur `claude/fixes-v2` ni suppression de branche effectué.

Observation confirmée dans le code : `memory/derived/` n'appartient pas aux
catégories de l'inventaire. Si la conversion est autorisée par ses précontrôles,
un fichier régulier présent sous derived est copié octet pour octet sous
`archive/derived/`, compté dans archived_other, puis comparé par la vérification
indépendante. Il n'est ni activé ni reconstruit dans memory/derived. Si les
journaux/reçus opérationnels bloquent l'import, le refus avant écriture prime.

MIGRATION.md explicite désormais ce périmètre et la reconstruction depuis les
seuls journaux canoniques de destination. Sonde temporaire avec Persistent vide
et un JSON dérivé synthétique : zéro alerte d'inventaire, une archive exacte,
aucun index actif créé, vérification indépendante OK et source inchangée.
Aucun code métier modifié ni nouvelle suite complète lancée pour ce lot
documentaire. Les 1031 réussites/cinq blocages restent la mesure du lot précédent.
E-004, revue des sorties CLI FAILED, import opérationnel et résolution humaine
FAILED restent ouverts ; le gain d'ingestion reste un gain de constante.

## Revue E-004 — Claude, 2026-10-02 (base `f507b31`, lecture + sondes, sans pytest réel)

Périmètre : `core/routing/policy.py` (plans), `core/routing/execution.py`
(`_validate_policy`), `core/dossiers/projects.py` (projections). Sondes rejouées
sur un worktree de `f507b31`, aucun fichier du dépôt modifié.

**F1 — Moyen : `UPDATE` contourne la règle « lieu déclaré » (policy.py).**
Pour `SPATIAL_LAYOUT` sans `place_id`, le plan passe en `REVIEW`
(`layout_requires_declared_place`), puis `if context.update_target is not None`
le réécrase en `UPDATE`. Sonde : layout qualifié, projet `p1`, sans lieu, avec
`update_target` → `persistence=UPDATE, dossier=CREATE_OR_LINK, sujet=project p1`.
C'est un plan que `_validate_policy` accepte (STORE/UPDATE, LINK/CREATE_OR_LINK,
sujet projet). Sans `update_target`, le même cas reste `REVIEW`. Correctif :
ne pas écraser `REVIEW` (n'autoriser `UPDATE` que si `persistence == 'STORE'`
avant), plus un test rouge/vert sur ce cas.

**F2 — Moyen : une valeur multi-ligne forge des sections dans le dossier généré
(projects.py).** `display()` échappe `<`, `>`, `&` (donc les marqueurs
BEGIN/END ne peuvent pas être forgés : bien), mais pas les sauts de ligne. Hors
`quote()`, elles sont écrites telles quelles : contenu des DECISION/QUESTION,
`action.description`, `action.metadata`, `thread.title` (`# {titre}`), mots-clés.
Sonde : une DECISION de contenu `"Choix A\n## Actions\n- [DONE] `fake` : tout est
fini"` produit dans le dossier un second titre `## Actions` et une fausse ligne
`- [DONE]`. Les ressorts affichant `memory.content` dans le récapitulatif
remplacent `\n` mais pas `\r`, ` `, etc. Le dossier est une vue « dérivée »
que l'on relit comme un résumé : une fausse action « terminée » est exactement le
type de promotion implicite que le projet veut éviter. Correctif : une seule
fonction de rendu en ligne (échapper/remplacer tous les séparateurs de ligne) ou
`quote()` partout ; tests avec `\n`, `\r`, ` `, titre multi-ligne.

**F3 — Faible : plan `UPDATE` d'un retrait sans contrôle de cohérence
(policy.py).** Avec `removal_observed` + `update_target` + au moins une
`evidence_refs` (chaînes non vérifiées), le plan est `UPDATE`,
`current_obstacle=False`, même si la nature est `TECHNICAL` et si
`update_target.information_id` n'est pas celui du Memory (sonde : cible `OTHER`
révision 7). Sans effet aujourd'hui : l'exécution refuse `removal_observed`
(execution.py, `_validate_policy`) et vérifie l'identité/révision. À corriger
avant d'ouvrir cette branche : exiger nature `OBSTACLE`, identité de cible
égale, et dire ce que valent les `evidence_refs`.

**F4 — Faible : déclencheur proposé pour une information non enregistrée.** Si
`already_stored` fait passer `STORE` en `NONE`, `proposed_trigger` (de
`resume_at`) reste renseigné (sonde : `NONE` + déclencheur présent). Une
`resume_at` invalide ne bloque pas le plan (`STORE` + déclencheur) ; l'exécution
la rejette via `timestamp()`, donc contenu par la garde. Conseil : vider le
déclencheur quand `persistence` ≠ `STORE/UPDATE`, et valider la date au plan.

**Points vérifiés, sans défaut trouvé :**
- Statut épistémique conservé séparément du rôle de la source ; aucune promotion
  de vérité dans `plan()`.
- `applicability` : bornes sans fuseau → `UNKNOWN`, `at` absent → `UNKNOWN`,
  absence de portée → `UNKNOWN` (jamais universel), conflit non résolu →
  `UNRESOLVED`. Un `EXPIRED` ne supprime rien.
- Projet ambigu (`candidate_projects`) → dossier `REVIEW`, pas de fusion.
- `_validate_policy` rejoue `plan()` et exige l'égalité avec le plan fourni :
  un plan altéré est refusé.
- Dossier : la partie hors région générée est conservée telle quelle (CRLF compris) ;
  frontières BEGIN/END absentes, doublées ou inversées → refus ; sortie séparée
  des sources et sans lien symbolique ; empreinte des fichiers sources dans le
  commentaire de fraîcheur ; reprise refusée si une opération Thread, Information
  ou de routage non COMMITTED existe pour la cible (hors audit « settled » sous
  verrous, dont la portée est celle de `read_phase`).

**Limites de cette revue :** pas de vrai pytest, pas de VM. `resolve()` lit tous
les Threads à chaque appel (coût linéaire) et échoue entièrement si un fichier
Thread est corrompu au lieu de renvoyer `REVIEW` : à décider, non testé. Les
lectures de `status()` ne prennent pas de verrous (documenté).
Aucun correctif appliqué : à vérifier puis corriger par Codex/GPT, avec tests rouges
d'abord (F1, F2 en priorité).

## Réponse Codex — E-004, 2026-10-02, base `a57d237`

La section E-004 de Claude ci-dessus est ajoutée verbatim depuis son fichier,
sans remplacer l'historique déjà présent. Les quatre constats sont confirmés.

**F1 corrigé.** La conversion STORE → UPDATE ne remplace plus REVIEW. Une
SPATIAL_LAYOUT sans lieu, même associée à un projet et une cible existante,
reste à revoir. Test du plan, refus du preview sans écriture et refus execute
avant intention/effet métier (seul un fichier verrou peut être initialisé).

**F2 corrigé.** `display()` aplatit les séparateurs de ligne dans chaque champ
inline ; `quote()` garde le texte complet en préfixant chaque ligne. Matrice
sur LF, CR, CRLF, U+2028, U+2029, NEL, VT et FF : décisions, questions, résumé,
titre, description/métadonnées d'action, mots-clés. Aucun faux titre Actions
ni fausse action DONE ; marqueurs préservés. Les tests existants de notes,
CRLF, frontières et reprise restent verts. Les vues anciennes peuvent devenir
STALE ; rebuild/reconcile explicite applique le nouveau rendu.

**F3 corrigé côté plan, exécution toujours différée.** Le Memory à réviser doit
être qualifié OBSTACLE et correspondre à l'identité/révision de la cible ; les
références doivent être des chaînes non vides. La fixture historique utilisait
une observation distincte non qualifiée : elle représente maintenant l'obstacle
cible, avec l'observation en référence déclarée. Ces chaînes ne prouvent rien
par elles-mêmes. Résolution/validation des preuves à définir avant d'autoriser
l'exécution d'un retrait ; la garde `removal_observed` reste fermée.

**F4 corrigé.** Une échéance renseignée invalide ou sans fuseau entraîne REVIEW,
sans déclencheur. NONE/REVIEW n'en proposent plus, y compris `already_stored`.
Le preview refuse maintenant l'échéance par OperationConflict (« needs review »)
avant la validation de timestamp de l'exécuteur ; deux attentes de test adaptées.
Les échéances valides gardent leur identité stable et leurs gardes d'exécution.

**Preuves.** Avant changement du code : 64 échecs et 7 réussites sur les 71
nouveaux cas (certains champs étaient déjà protégés dans ces cas). Après :
174 ciblés réussis en 8,33 s. Suite complète : **1102 réussis, cinq échecs
Manager à la création de socket avant scénario, 55,83 s**, Python 3.12.14 et
pytest 9.1.1, aucun désélectionné. Aucun essai VM ni coupure physique.

**Compatibilité et restant.** Formats et versions conservés ; les plans valides
non concernés restent identiques. Les anciens plans affectés échouent à la
revalidation et nécessitent un nouvel aperçu corrigé. Une intention concernée
déjà APPLYING reste bloquée pour examen humain : aucune réécriture automatique.
`resolve()` reste linéaire et échoue sur source corrompue, conformément au refus
de produire une projection depuis des sources invalides ; pas de nouveau mode
REVIEW partiel. `status()` reste sans verrou, sur copie arrêtée pour cohérence.
Revue des sorties CLI FAILED, import opérationnel et résolution humaine FAILED
restent ouverts. Estimations 45 % / 52,75 points inchangées.

## Validation finale E-004 — retour de Claude transmis par toytoy le 2026-10-02

Relecture terminée sur `3b2d7a0`. Claude confirme par ses sondes les corrections
F1–F4 : lieu obligatoire conservé en REVIEW, aucun faux titre/action par contenu
multiligne, retrait incohérent refusé au plan et déclencheurs cohérents avec la
persistance et la validité de l'échéance. Il confirme aussi 64 échecs des nouveaux
tests avec l'ancien code de core, contre leur réussite avec les corrections.

Limite déclarée : aucune nouvelle suite complète lancée par Claude. Son
substitut de pytest produit 29 échecs sur les tests voisins, tous attribués à
l'absence de `monkeypatch.context` et identiques sur `f507b31`. Cela ne constitue
pas une exécution complète réussie. Les **1102 tests réussis et cinq blocages
Manager** restent les résultats de la suite pytest de Codex sur le lot précédent.

Détail cosmétique signalé : si une échéance invalide conduit à REVIEW, la raison
`explicit_target_and_revision_for_update` peut rester présente. Comportement
correct, nettoyage explicatif à prévoir ; aucune correction de code dans ce lot.

Claude rappelle les sujets encore ouverts : comportement de `resolve()` sur
Thread corrompu, résolution humaine de FAILED, import des reçus DELETED et VM.
Réponse Codex : le choix conservateur de `resolve()` était déjà indiqué dans la
réponse précédente ; il est maintenant explicité dans PROJECT-DOSSIERS.md.
Une source illisible bloque l'ensemble de la résolution : ignorer ce Thread
pourrait masquer un second rattachement et produire à tort un lien unique.
REVIEW reste l'ambiguïté entre sources lisibles, sans résultat partiel sur source
corrompue. Ce lot précise le contrat existant ; il n'ajoute ni comportement ni
preuve de test dédiée à cette corruption. Une telle preuve reste à ajouter.

FAILED, import opérationnel DELETED et recette VM restent ouverts dans la TODO.
README et TODO actualisés ; aucune suite relancée pour cette édition documentaire.
Les constats antérieurs et leurs limites sont conservés.

## Suivi E-004 — Codex, 2026-10-02 après-midi, base publiée `a92cdd3`

Poursuite autorisée sans attendre Claude, momentanément indisponible. La raison
annonçant une mise à jour n'est plus conservée si une date invalide entraîne
REVIEW. Deux cas rouges avant correction, verts après. Deux autres cas fixent
le contrat `resolve()` : une source corrompue bloque API et CLI sans résultat
partiel ni écriture, même avec sélection explicite. Une mutation expérimentale
en mémoire qui ignore les erreurs Thread fait échouer les deux cas ; aucun
changement de ce comportement conservateur dans le code publié.

122 tests ciblés réussis, 2,63 s. Quatre nouveaux cas ; suite complète précédente
de 1102 réussites/cinq blocages toujours datée du lot précédent, non relancée
pour ce petit suivi. Contrat et TODO actualisés. Prochain lot : import étroit
des reçus DELETED, en conservant la réserve d'identité et le refus des conflits.

## Import DELETED — Codex, 2026-10-02 après-midi, base publiée `8f9fb1b`

Deuxième lot demandé pendant l'indisponibilité de Claude. T-021/T-033 livre un
chemin distinct `core.migration.deleted_receipts` : aperçu sans écriture et
import explicite des seuls reçus terminaux DELETED entre arbres core compatibles.
Les octets sont conservés dans pending-delete actif ; tests de refus de
recréation par le backend et le service Information. Tous les conflits sont
contrôlés avant la première publication, puis de nouveau sous Persistent/Thread.
Readiness, références, absence canonique et compaction préalable des snapshots
sont vérifiées. Reçu différent jamais remplacé ; source jamais écrite.

Chaque reçu est atomique et durable ; reprise d'un préfixe par relance sur la
même source arrêtée. Deux importeurs concurrents sont sérialisés. Après un arrêt
avant renommage, un fichier temporaire inconnu peut rester : refus de reprise
pour revue humaine, aucune purge automatique. Pas de transaction globale ni de
preuve de purge externe. Source/écrivains legacy et bas niveau arrêtés requis.

29 nouveaux cas, 121 ciblés verts en 4,03 s. Mutations expérimentales en mémoire :
désactiver la publication donne un échec, ignorer les gardes de références en
donne deux. Code publié intact. Suite complète : **1134 réussis, cinq blocages
Manager avant scénario, 73,20 s**, aucun désélectionné. Le dernier cas d'arrêt
avant renommage a été ajouté et vérifié ensuite dans le groupe ciblé, sans
modifier l'implémentation. Aucun essai VM, corpus réel ou coupure électrique.

Contrat : docs/DELETED-RECEIPT-IMPORT.md. Le convertisseur legacy conserve son
refus des sources mixtes. CANCELLED/PENDING/APPLYING, reçus de commandes,
Events/Threads et index ne sont pas importés par ce chemin. L'import général
avec conservation de toute l'histoire de rejeu reste ouvert, ainsi que FAILED
et la recette VM. README/TODO/MIGRATION actualisés ; estimations gelées.

## Première résolution humaine FAILED — Codex, 2026-10-02, base `a2505c6`

Poursuite autorisée. Parcours complet mais limité à THREAD_STATUS_CHANGE dans
thread-status-v1 : revue sans écriture, décision explicite auteur/motif/date,
revalidation sous Persistent/Thread/Operation/Event, puis publication atomique
de la trace et du passage FAILED → APPLYING. Le coordinateur reprend le plan
inchangé ; pas d'abandon, remplacement de snapshot ni nouveau command/event ID.

Les états admis sont avant sans Event, après sans Event, après avec Event exact.
Toute divergence, Event sans résultat Thread, autre réservation Thread/Event,
revue modifiée ou autre famille/pending/inconnue bloque. Plusieurs FAILED de
statut indépendants peuvent être traités un par un. Une intention parente de
routage reste hors de cette première résolution ; aucun contournement implicite.

Le journal reçoit `manual_resolutions` seulement lors d'une autorisation. Champ
optionnel strict : décision/action/auteur/motif/date et hashes du FAILED/de la
revue, IDs uniques. Les anciennes formes sans champ et hashes de plan restent
inchangés ; métadonnées exclues du hash du plan. Le dépôt générique conserve
FAILED terminal et interdit d'altérer la trace ; la transition spécialisée ne
s'applique qu'après relecture. Les anciens lecteurs refusent le nouveau champ.
Identités déclarées et empreintes ne constituent pas une signature authentifiée.

Après arrêt avant publication : FAILED sans trace. Après : APPLYING avec trace,
reprenable par recover-all selon ses gardes habituelles ou la même décision.
Rejeu après COMMITTED sans nouvel effet ni résurrection. Après un nouvel échec,
un nouvel aperçu et une nouvelle décision sont nécessaires ; l'historique reste.
Un résidu temporaire inconnu après panne reste bloquant pour revue humaine.

36 nouveaux cas, **89 ciblés réussis en 2,96 s**. Deux arrêts réels code 74,
concurrence sans Manager, trois états partiels, décisions répétées, corruption
de trace, CLI, compatibilité et refus sans effet vérifiés. Mutations de preuve
en mémoire : retirer la trace à APPLYING ou omettre la revalidation provoque
respectivement 1 + 1 échecs d'assertion. Code publié sans ces substitutions.
Suite complète : **1171 réussis, cinq échecs Manager avant scénario, 68,78 s**,
aucun désélectionné. Aucun essai VM ni disque réel/coupure électrique.

README/TODO et contrats de reprise actualisés ; nouveau contrat
FAILED-STATUS-RESOLUTION.md. Restant : autres familles FAILED, conflits réels,
abandon éventuel, installation/recette VM et import opérationnel général.
Aucune revue Claude acquise sur ce lot ; estimations 45 % / 52,75 inchangées.

## Résolution des éditions Thread FAILED — Codex, 2026-10-02, base `121764a`

Poursuite autorisée. Le parcours partagé de résolution accepte THREAD_UPDATE :
LINK/UNLINK, ADD_ACTION/ACTION_STATUS et DETAILS. Aperçu sans écriture avec
`--family thread-update-v1`, commande originale visible ; `retry` déduit la
famille de la revue. Anciennes API/revues de statut compatibles, aucune
acceptation d'édition par l'API limitée aux statuts.

Mêmes snapshots/identités/révisions/Events, même publication atomique de la
trace et APPLYING. RETRY_THREAD_UPDATE_V1 est validé selon le type du journal.
Gardes du coordinateur vérifiées avant autorisation : liens lisibles, réservations,
collisions d'operation_id inter-familles même COMMITTED. Event construit par
une fonction partagée avec la reprise normale. La suppression d'une cible de
LINK reste bloquée avant/après reprise ; une demande tardive reste en attente.
UNLINK peut ensuite libérer la référence, sans résurrection au rejeu terminal.

36 nouveaux cas : quinze combinaisons commande/effets, divergences et fraîcheur,
réservations, liens disparus/corrompus, types d'audit et CLI. Trois arrêts réels
(code 74) aux frontières avant autorisation/après autorisation/après commit.
**107 ciblés réussis en 4,52 s**. Preuves négatives en mémoire : retrait du
contrôle de lien avant autorisation (un échec ; corruption encore refusée par
l'inventaire), de la revalidation (un échec), de l'audit (un échec).
Suite complète : **1207 réussis, 5 échecs de sockets Manager avant scénario en 75,62 s**, aucun désélectionné.
Aucun test VM, corpus réel ou coupure électrique ; aucune nouvelle revue Claude.

README, TODO et contrats actualisés. Restant : création/suppression Thread
FAILED, écritures Information, intentions parentes, conflits réels/abandon et
recette VM. Les FAILED simultanés de familles différentes restent bloqués pour
examen ; aucun contournement de dépendance. Import opérationnel général ouvert.
Estimation globale toujours gelée à 45 % / 52,75 points.

## Première suite complète sur VM — retour toytoy, 2026-10-02, 22 h 27

Mise à jour fast-forward de `b470bdf` à `ac4d739`, puis suite complète dans
`/tmp/eidolon-tests-doLWCH` avec MEMORY_ENGINE_ROOT isolé, sans cache pytest
ni bytecode. Python 3.13.5, pytest 9.1.1, PyYAML 6.0.3. Sortie terminal
transmise par toytoy : `1212 passed in 28.89s`. Aucun échec ni désélection ;
les cinq tests de concurrence Manager auparavant bloqués dans Work sont inclus.

Codex a lu le retour terminal ; il n'a pas exécuté directement les commandes
sur la VM ni récupéré le journal complet `/tmp/eidolon-tests-doLWCH/pytest.log`.
README/TODO actualisés et preuve bornée dans docs/VM-TESTS-2026-10-02.md.
Pas de nouvelle exécution nécessaire pour ce lot exclusivement documentaire.
Restent l'inventaire des écrivains et racines, la sauvegarde/restauration,
les audits sur copie réelle, la reprise opérationnelle et l'intégration services.
Aucune coupure électrique testée ; estimations gelées inchangées.

## Inventaire VM : dossier cron protégé — 2026-10-02, 22 h 36

Retour toytoy sur `ac4d739` : racine effective `/opt/eidolon-memory-engine`.
L'inventaire échouait dans Path.iterdir sur `/var/spool/cron/crontabs`, alors
que les erreurs de lecture des fichiers étaient déjà rapportées. La frontière
de parcours cron capture désormais OSError (dont PermissionError), ajoute la
source dans `unreadable`, conserve les résultats disponibles et poursuit les
sources suivantes. Aucun changement de droits, élévation automatique ou écriture
sur les sources. Un inventaire partiel reste à examiner humainement.

Trois régressions ajoutées : PermissionError, OSError et sortie CLI JSON.
Avant : trois échecs, deux réussites. Après : 12 réussites en 0,81 s pour
les tests inventaire et vm_acceptance. Pas de suite complète supplémentaire
pour ce correctif ciblé ; les 1212 réussites VM restent attachées à `ac4d739`.
Relance sur la VM attendue avant de poursuivre sauvegarde et audits sur copie.
README/TODO actualisés ; aucun feu vert pour des écrivains réels à ce stade.

## Recette VM reprise — 3 octobre 2026

Exécution directe par Codex sur `Eidolon-Memory`, code
`9780473e72cafd28ad2b27ca513f77f728139be5`, branche
`refactor/architecture-v1`, Python de `.venv` 3.13.5, pytest 9.1.1.
Le rapport précédent `recette-At3T0R/vm-acceptance-report.json` était KO
uniquement sur les cinq scénarios Manager : le journal confirme
`OSError: AF_UNIX path too long` avant les scénarios.

Source restaurée retrouvée et présente :
`/home/toytoy/eidolon-backups/backup-20261002-225227-mtsJkO/restauration-i2mwDP/eidolon-memory-engine`.
Nouvelle exécution depuis le dépôt actif, sur cette source en lecture seule :

```sh
eidolon_workdir=$(mktemp -d /tmp/em-XXXXXX)
/opt/eidolon-memory-engine/.venv/bin/python -B -m tools.vm_acceptance \
  --source /home/toytoy/eidolon-backups/backup-20261002-225227-mtsJkO/restauration-i2mwDP/eidolon-memory-engine \
  --workdir "$eidolon_workdir"
```

Première tentative courte `/tmp/em-sGQgQ2` : KO concurrence,
`PermissionError: [Errno 1] Operation not permitted` à la création des sockets,
dû au sandbox. Relance autorisée hors sandbox dans `/tmp/em-yZKsKq` :
**code de sortie 0, statut OK, neuf étapes OK**, sans changement des tests.
Journal : **5 passed, 40 deselected in 0.82s**. Les 40 désélections sont celles
du filtre ciblé de la recette ; aucune suite complète relancée dans ce lot.

- Sauvegarde/restauration internes par copie : **2448 fichiers vérifiés**.
  Empreinte agrégée source :
  `05b0f84a50f8fd1e05dec039b21cd4490f960b0da3fbd162b140b388c7e3c246`,
  identique au précédent rapport ; contrôle final de source inchangée réussi.
- Inventaire : aucune catégorie mémoire peuplée, aucun format à revoir.
- Audits relations/cycle de vie : **0 Information** ; suppressions : **0 reçu** ;
  écritures Information : aucun journal. Aucun problème trouvé.
- Contrôle ponctuel de démarrage : **ready=true**, aucun problème ni opération.
- Écrivains observés : aucun descripteur ouvert en écriture sur la source,
  `configured=[]`, `running=[]`. La recette sans sudo conserve
  `/var/spool/cron/crontabs` dans `unreadable` : inventaire heuristique partiel.

Preuves archivées (copie des rapports et logs vérifiée par SHA256) dans
`/home/toytoy/eidolon-backups/backup-20261002-225227-mtsJkO/recette-20261003-em-yZKsKq` : `successful/` et `sandbox-blocked/`, chacun contenant
`vm-acceptance-report.json` et `concurrency.log`, plus `SHA256.json`.
Les rapports conservent les chemins `/tmp` d'exécution originaux.
L'ancien rapport, la sauvegarde originale et les données du dépôt actif
n'ont pas été modifiés par la recette.

Contexte confirmé par toytoy, distinct des observations directes ci-dessus :
les cinq tests `tests/test_writer_inventory.py` passent sur la VM ; inventaire
avec sudo `configured=[]`, `running=[]`, `unreadable=[]`, aucun service Eidolon
actif ; sauvegarde SHA256 et restauration tar conformes dans
`/home/toytoy/eidolon-backups/backup-20261002-225227-mtsJkO`.

**Limites :** recette sur arbre mémoire vide, aucune validation sur corpus
réel, aucune reprise de journaux réels ni intégration/démarrage des services,
aucune coupure électrique ou panne physique de stockage. Le succès des
scénarios concurrents synthétiques et des copies ne vaut pas mise en production.
La suite complète de 1212 tests reste attachée à `ac4d739`.


## T-048 — Reprise humaine des créations Thread FAILED, 3 octobre 2026

Base `06c9570`, branche `refactor/architecture-v1`. La reprise humaine accepte
maintenant THREAD_CREATE dans `thread-create-v1`, via l'API générale et le CLI
`preview --family thread-create-v1`, puis `retry`. Le plan, les révisions 0 → 1,
les identités Thread/Operation/Event et l'Information liée restent inchangés.
La revue expose `information_id`, Thread ABSENT/AFTER et Event ABSENT/MATCH.
L'autorisation RETRY_THREAD_CREATE_V1 et APPLYING sont publiés atomiquement dans
le journal ; les lecteurs stricts, readiness et recover-all acceptent cette trace.
Le dépôt générique continue d'interdire les sorties FAILED et la modification
ou suppression de la trace. Les anciens journaux sans trace restent compatibles ;
les binaires antérieurs ne connaissant pas cette action refusent la nouvelle trace.

L'Event et la validation du snapshot sont partagés avec le coordinateur de
création existant. Divergence, Event sans Thread, lien absent/corrompu, revue
périmée, réservation du même Thread/Event et seconde création de la même identité
(même COMMITTED) bloquent avant autorisation. Les autres familles non terminées,
les parents de routage et les sources inconnues/corrompues restent bloquants.
Les FAILED indépendants de création peuvent être traités un par un. Une demande
PENDING_DELETE tardive reste en attente : ni approbation ni annulation implicite.
Le rejeu COMMITTED ne recrée pas un Thread supprimé depuis ; un nouvel échec
exige une nouvelle revue et une nouvelle décision, sans enlever les précédentes.

Preuves directes sur la VM, Python `.venv` 3.13.5/pytest 9.1.1 :
**32 nouveaux cas** dans `tests/test_failed_create_resolution.py`. Les 25 premiers
échouent avant implémentation (famille non supportée), puis passent ; sept cas
supplémentaires couvrent concurrence, métadonnées, nouvel échec et indépendance.
Groupe ciblé création/statut/édition/readiness/suppression/intégration :
**160 réussis en 3,82 s**. Trois arrêts réels code 74 aux frontières avant
publication/après publication/après commit ; deux processus concurrents sans
Manager terminent avec une seule autorisation et un seul Event.
Deux substitutions uniquement en mémoire dans des processus distincts : figer
l'aperçu au lieu de le revalider → un échec ; retirer la trace à APPLYING → un
échec. Aucune substitution conservée dans le code.

Suite complète isolée exécutée hors sandbox avec le Python de `.venv` :
**1247 passed in 29.82s**, aucun échec, saut ou désélection. Racine
`/tmp/em-suite-hfIokV`, journal `/tmp/em-suite-hfIokV/pytest.log` ;
MEMORY_ENGINE_ROOT distinct, bytecode et cache pytest désactivés, basetemp isolé.
Les cinq anciens scénarios Manager sont inclus. Cette preuve porte sur la base
`06c9570` plus le lot de code et tests documenté ici, avant son commit.

Limites : données synthétiques isolées uniquement, aucune modification de la
mémoire active, aucune résolution humaine exécutée sur des journaux réels,
aucune coupure électrique. Suppression Thread FAILED, écritures Information,
intentions parentes, conflits/abandon et import opérationnel général restent
ouverts. Aucun service installé ; estimations 45 % / 52,75 points inchangées.


## T-048 — Reprise humaine des suppressions Thread FAILED, 3 octobre 2026

Base `20a283a`, confirmé sur GitHub avant ce lot. THREAD_DELETE peut maintenant
être revu par `preview --family thread-delete-v1` puis repris avec la décision
humaine explicite. Le snapshot, les IDs et les révisions sont conservés ; trace
RETRY_THREAD_DELETE_V1 et APPLYING atomiques, reprise normale et rejeu terminal.
Thread BEFORE/ABSENT, `delete_thread`, Event NOT_APPLICABLE : aucun Event ajouté.
La validation du snapshot est partagée avec le coordinateur. Remplacement
divergent, revue périmée, réservation Thread, collision d'operation_id dans une
autre famille même COMMITTED et autre état non résolu bloquent l'autorisation.
Un rejeu terminal refuse aussi une identité réutilisée. Une Information disparue
après retrait du Thread ne bloque pas la clôture ; aucune Information recréée
ni suppression Information approuvée implicitement. Les parents de routage et
les familles autres que Thread restent hors de ce parcours.

**30 nouveaux cas**, tous rouges avant implémentation ; **190 ciblés réussis en
4,41 s** après. Trois arrêts réels code 74, deux décisions concurrentes sans
Manager, indépendance de plusieurs FAILED, deuxième échec, suppression du lien
puis de l'Information, CLI et audit strict couverts. Deux substitutions en mémoire
(revue figée / trace retirée à APPLYING) produisent chacune un échec ; aucune
substitution conservée. Suite complète isolée hors sandbox sur VM :
**1277 passed in 30.37s**, aucun échec, saut ou désélection,
Python `.venv` 3.13.5/pytest 9.1.1. Journal `/tmp/em-suite-WqCdZc/pytest.log`.
Preuve sur base `20a283a` plus ce lot avant commit. Données synthétiques uniquement,
aucun journal réel résolu, aucun service installé ni coupure électrique.
Écritures Information FAILED, parents, abandon/conflits et import général ouverts.
Estimations 45 % / 52,75 points inchangées.


## T-048 — Reprise humaine des écritures Information FAILED, 3 octobre 2026

Base `dcbdf1c`, vérifiée sur GitHub avant démarrage. Nouveau parcours
`core.information.failed_resolution` : revue sans écriture puis décision explicite
pour INFORMATION_CREATE/UPDATE. Le lecteur normal revalide snapshots/hash/empreinte ;
la revue contrôle les effets présents, réservations Information/Event, reçus de
suppression et relations vers identités supprimées. Event sans état après,
divergence, revue périmée, autre famille non résolue et parent non terminé bloqués.
Les FAILED Information indépendants se résolvent un par un ; aucun abandon.

Publication atomique RETRY_INFORMATION_WRITE_V1 et APPLYING, puis coordinateur
normal. Le hash du plan et les IDs restent inchangés. La trace stricte est copiée
dans le reçu compact avant retrait du snapshot ; journal/reçu divergents bloquent
la compaction. Les anciens reçus sans trace restent identiques et lisibles ;
les anciens binaires refusent les journaux/reçus enrichis. Le rejeu de la décision
sur reçu compact conserve le résultat sans recréer l'Information supprimée ;
aucune nouvelle décision n'est accordée après compaction. Contrat :
[FAILED-INFORMATION-RESOLUTION.md](docs/FAILED-INFORMATION-RESOLUTION.md).

58 nouveaux tests : 49 premiers rouges avant implémentation sur un squelette
refusant explicitement le parcours, puis neuf cas supplémentaires de dépendances,
audit et compaction. **295 ciblés réussis en 7,29 s**. Six arrêts réels code 74
(CREATE/UPDATE × trois frontières), deux scénarios à deux processus concurrents,
compaction interrompue, trace divergente, suppression puis rejeu, seconde décision,
CANCELLED et relations réservées couverts. Substitutions en mémoire : revue figée,
autorisation sans trace, compaction retirant la trace → un échec chacune ;
aucune substitution conservée dans le code.

Suite complète isolée hors sandbox sur VM : **1335 passed in 32.13s**,
aucun échec, saut ou désélection, Python `.venv` 3.13.5/pytest 9.1.1.
Journal `/tmp/em-suite-rmKyis/pytest.log`. Preuve sur base `dcbdf1c` plus ce lot
avant commit. Sources actives/sauvegardes intactes ; données synthétiques uniquement,
aucune reprise humaine de journaux réels, service ou coupure électrique validés.
Parents de routage, divergences/abandon et import opérationnel général ouverts.
Estimations 45 % / 52,75 points inchangées.


## T-021/T-033 — Import des reçus compactés Information, 3 octobre 2026

Base `5394e06`, vérifiée sur GitHub avant ce lot. Nouveau chemin explicite
`core.migration.write_receipts` : aperçu sans écriture et import des reçus
terminaux INFORMATION_CREATE/UPDATE avec leurs Events exacts, sans canonique,
Threads, index ni réexécution. Les deux arbres doivent être prêts et arrêtés ;
les journaux Information source doivent tous être compactés. Même canonique
actuel par octets et révision >= reçu, ou même réservation DELETED si absent.
L'import contrôle identité/révision/type/CAUSEDBY de l'Event, réservations et
conflits exacts avant publication, puis sous verrous Persistent/Operation/Event.
Il conserve les audits humains, et le rejeu ne remplace pas une révision plus
récente ni ne recrée une Information supprimée. Le convertisseur legacy conserve
son refus des sources mixtes ; aucune fusion générale introduite.

Event publié avant reçu ; arrêt entre les deux → Event orphelin, relance depuis
la même source arrêtée. Préfixe possible, aucune transaction globale ni rollback.
Résidu temporaire inconnu → refus readiness/reprise pour examen humain. Source
jamais écrite. Destination à garder arrêtée jusqu'au succès final, même si le
contrôle readiness peut être vrai sur un préfixe sans reçu manquant identifié.
Contrat : [WRITE-RECEIPT-IMPORT.md](docs/WRITE-RECEIPT-IMPORT.md).

34 nouveaux tests : 23 échecs/5 réussites sur le squelette initial refusant
l'import, puis six cas supplémentaires (Event cohérent par digest mais métier
incorrect, révision canonique trop ancienne, arrêt avant renommage). Le cas de
révision canonique échoue avant ajout de sa garde, puis passe. Groupe ciblé :
**173 réussis en 5,56 s**. Trois arrêts réels code 74, deux importeurs concurrents,
revalidation sous verrous, aperçu sans écriture, audit FAILED conservé, conflits
sans préfixe, suppression/rejeu et fichiers exacts. Retirer publication ou garde
canonique en mémoire produit un échec chacun ; aucune substitution conservée.
Suite complète VM isolée hors sandbox : **1369 passed in 33.70s**, aucun échec,
saut ou désélection, Python `.venv` 3.13.5/pytest 9.1.1 ; journal
`/tmp/em-suite-pzRYrA/pytest.log`. Preuve sur base `5394e06` plus ce lot avant commit.
Corpus synthétique uniquement, aucun import dans la mémoire active, aucun corpus
réel ni coupure électrique. CANCELLED, Threads/actions/révisions et import
général restent ouverts ; estimations 45 % / 52,75 points inchangées.


## T-021/T-033 — Import explicite CANCELLED, 3 octobre 2026

Base `55e81ba`, vérifiée sur GitHub avant démarrage. `deleted_receipts` accepte
maintenant l'option explicite `--include-cancelled` (API `include_cancelled=True`)
pour transférer DELETED et CANCELLED terminaux. Par défaut, l'ancien comportement
DELETED seul et la forme des rapports sont conservés. En mode élargi, chaque
candidat indique son état. CANCELLED exige une Information canonique présente,
exacte par octets dans les deux arbres et de révision >= demande ; les liens
vivants restent intacts. Source/destination différentes ou receipt différent
refusés globalement avant publication, puis contrôle sous verrous et final.
Aucun contenu ni Event transféré, aucune suppression réactivée/approbation donnée.
CREATE reste refusé sur CANCELLED, UPDATE explicite autorisé ; la demande annulée
ne peut plus être approuvée. Ancien reçu conservé même après édition ultérieure ;
une relance contre une ancienne source divergente est refusée sans le remplacer.

18 nouveaux cas : 18 échecs initiaux (17 liés à l'option non livrée, un défaut
fixture de répertoire inconnu corrigé). **144 ciblés réussis en 4,96 s** après.
Préservation exacte, mode par défaut, lot DELETED/CANCELLED, liens, révision,
conflits sans publication, arrêt réel code 74, deux importeurs concurrents et CLI.
Substitutions en mémoire publication/garde canonique → un échec chacune.
Premier passage complet : un échec de cette fixture, 1386 réussis en 34,13 s ;
après correction, suite VM isolée hors sandbox : **1387 passed in 34.18s**, aucun
échec, saut ou désélection, Python `.venv` 3.13.5/pytest 9.1.1. Journal final
`/tmp/em-suite-XVdGSu/pytest.log` (premier : `/tmp/em-suite-U1A2zB/pytest.log`).
Preuve sur base `55e81ba` plus ce lot avant commit. Données synthétiques uniquement,
aucun import dans la mémoire active ni coupure électrique ; import des
Threads/actions/révisions, journaux complets et parents encore ouvert.
Estimations 45 % / 52,75 points inchangées.

## T-021/T-033 — Transfert core complet, 3 octobre 2026

Base `46998ce` vérifiée sur GitHub avant démarrage. Copie explicite de `memory/`
vers racine neuve, aucun code/configuration hors arbre ni verrou copié. Octets
Informations/Threads/actions/révisions, Events, journaux, audits humains/reçus,
parents, échéances, suppressions et notes préservés sans exécuter de commande.
Aperçu sans écriture ; source readiness/liens/formats contrôlés. Refus global
source mixte/incomplète/invalide, symlinks/FIFO, destinations préexistantes.
Préparation par plan/manifeste SHA256 durable, reprise du préfixe exact ; source
ou préparation divergente bloque. Renommage Linux NOREPLACE puis fsync parent,
refus même d’un dossier vide apparu pendant publication. Rejeu exact UNCHANGED.

42 nouveaux cas. Premier essai du squelette : fixture utilisant une API Thread
inexistante corrigée ; puis **21 rouges / 17 verts** sur le squelette refusant.
Après implémentation, deux erreurs de capture InvalidMemory corrigées ; ajout de
quatre cas (course publication, altération staging, deux formats legacy).
**42 ciblés réussis en 2,43 s**, quatre vrais os._exit(74), deux copies concurrentes,
rejeu de parents format 3, audit compact après suppression et notes CRLF.
Substitutions en mémoire publication absente / renommage remplaçant → un échec
chacune, code du dépôt inchangé. Suite complète VM hors sandbox :
**1429 passed in 36.38s**, aucun échec, saut ou désélection ; Python `.venv`
3.13.5/pytest 9.1.1. Journal `/tmp/em-suite-o6rMam/pytest.log` ; base `46998ce`
plus ce lot avant commit. Estimations 45 % / 52,75 points inchangées.

Corpus synthétique isolé uniquement ; aucun transfert de la mémoire active,
aucune activation de services ni coupure électrique. Écrivains à arrêter jusqu’au
succès final ; notes externes à sauvegarder séparément, permissions non conservées.
Fusion opérationnelle dans un arbre existant et conversion entre formats restent
ouvertes. Contrat : docs/CORE-COPY.md.

## T-043 — Résultats client NONE/REVIEW, 3 octobre 2026

Base `e17bec3` confirmée sur GitHub avant démarrage. `RoutingExecutor.assess` et
CLI `assess` fournissent routing-outcome/1 en lecture seule : NO_ACTION,
REVIEW_REQUIRED, PREVIEW_REQUIRED, CAPABILITY_REQUIRED. Plan original conservé,
valeurs détachées, raisons explicites ; aucun corps ni écriture. Une association
demandée avec NONE, une ambiguïté, qualification absente/date invalide/conflit
ou retrait observé demandent une revue. L’absence d’un dossier explicite
n’affirme jamais que le projet est nouveau. Un résultat n’est ni un plan
exécutable, ni une validation de readiness, ni une résolution humaine.

28 nouveaux cas, **25 rouges sur le squelette**. Première implémentation :
24 verts/un échec d’assertion utilisant needs_review sur le bundle plutôt que
ses éléments, corrigé ; trois tests supplémentaires NONE préserve mémoire,
résultat non exécutable et projet déjà existant sans dossier déclaré.
**106 ciblés réussis en 2,76 s**. Substitutions en mémoire supprimant REVIEW /
supposant nouveau projet → six échecs / un échec ; dépôt non altéré.
Suite VM isolée complète hors sandbox : **1457 passed in 36.29s**, aucun échec,
saut ni désélection ; Python `.venv` 3.13.5/pytest 9.1.1. Journal
`/tmp/em-suite-u79j7C/pytest.log`, base `e17bec3` plus lot avant commit.

Client factice correction explicite de qualification → assessment → aperçu et
exécution journalisée → rappel canonique avec incertitude. Aucun client externe,
file de revue durable, qualification automatique ou décision sans humain.
Arbres absents/bloqués inchangés par assessment. Corpus synthétique isolé ;
services actifs et sauvegarde originale intacts, ni corpus réel ni coupure
électrique validés. Estimations 45 % / 52,75 points inchangées.
Contrat docs/ROUTING-OUTCOMES.md.

## T-049 — Mesures VM directes, 3 octobre 2026

Base `4a11c71` vérifiée sur GitHub avant démarrage. Outils existants utilisés
séquentiellement, 84 lignes d’écriture (100/300 antécédents, 25 entrantes,
CREATE/UPDATE, single/batch, live/compact, strict/index), trois corpus indépendants
par variante. Quatre corpus d’entretien, cinq Threads/cinq échéances chacun,
trois passes à vide et trois de rejeu. Toutes les vérifications canoniques,
audits sans problème, readiness et fraîcheur finale ont réussi. Sept rapports
JSON/logs conservés et hashes contrôlés indépendamment, code core inchangé.

Médianes 300 live/25 CREATE : 1,517871 s seules, 0,093317 s en lot,
0,045888 s en lot indexé hors construction ; les valeurs exactes de summary.json
font foi. Le lot fait un scan contre 25 ; l’index conserve les relectures d’octets.
Coût de préparation compacte environ 15 s à 300, séparé des temps d’écriture.
Entretien à vide 300 : 0,251739 s live / 0,203818 s compact ; encore 1230
ouvertures JSON historiques et 2135 Markdown canoniques. Corpus temporaires
supprimés après contrôles, données actives et sauvegarde intactes.

Observation explicite : /tmp est tmpfs, racine ext4 /dev/sda2, quatre CPU
logiques. Mesures sur VM mais pas de latence disque physique, disque froid,
charge contrôlée ni corpus réel. Les scopes historiques des outils sont gardés
dans original_scope avec contexte effectivement observé ajouté aux rapports.
T-049 reste partiel, estimations 45 % / 52,75 points inchangées. Aucun changement
métier : suite VM précédente 1457 réussis conservée sans répétition inutile.
Contrat/commandes/données : docs/VM-PERFORMANCE-2026-10-03.md et
docs/benchmarks/vm-2026-10-03/. Extension 1000/ext4 à mesurer séparément.

## T-049 — Extension 1000 / ext4, 3 octobre 2026

Base `08f0284` confirmée sur GitHub avant démarrage. Trois répétitions indépendantes
sur 1000 antécédents tmpfs et 300 ext4, 25 CREATE en batch, live/compact,
strict/index : 24 points supplémentaires. Tous les audits sans problème et
1025/325 objets canoniques exacts. Mesures séquentielles, pas de tests concurrents.
1000 compact : préparation médiane strict 154,829268 s, lot 0,170881 s ;
indexé 0,062659 s plus 0,167541 s de construction. Toujours 1050 JSON ouverts.
1000 live : 0,217938 s strict / 0,063263 s indexé + construction 0,219365 s.
300 ext4 live : 0,302016 s strict / 0,251664 s indexé + construction 0,082497 s.
300 ext4 compact : 0,308451 s strict / 0,268084 s indexé hors construction ;
préparation autour de 21 s. Les chiffres exacts et étendues sont conservés.

Six nouveaux rapports JSON et deux logs, manifeste extension-environment.json,
hashes core inchangés comparés au précédent manifeste, cleanup du dossier ext4
vérifié. Corpus temporaires propres, aucun accès aux données actives/sauvegarde.
La compaction individuelle croît beaucoup plus vite que le lot ; prochain
travail identifié, pas encore réduit par cette livraison documentaire.
Guest ext4 /dev/sda2 et tmpfs distingués ; ouvertures comptées, pas I/O physique.
Ni disque froid/hyperviseur contrôlé, ni corpus réel, ni coupure ou seuil
intensif validés. Aucun code métier changé : suite précédente 1457 applicable
sans répétition inutile. Estimations 45 % / 52,75 points inchangées.
Preuves/commandes : docs/VM-PERFORMANCE-2026-10-03.md.

## T-049 — Compaction bornée, 3 octobre 2026

Base `797c432` vérifiée sur GitHub avant démarrage. API compact_batch et CLI
compact-batch : 1–100 identités distinctes ordonnées, entrées figées et validées
avant publication, scan partagé sous Persistent/Operations/Events. Chaque
compaction conserve statut/pending/suppression/Event exact, reçu durable relu
avant retrait du snapshot puis fsync. Formats et traces humaines inchangés.
Erreur structurée avec préfixe durable/next_index, relance exacte ; pas de file
durable/transaction globale/politique de rétention ni effet sur le canonique.

26 nouveaux tests. Squelette : 22 échecs initiaux, dont 21 liés à la capacité et
un défaut de fixture (COMMITTED → FAILED interdit) corrigé ; audit de fixture
comparé à la trace réelle plutôt qu’à une identité supposée. Les 22 cas corrigés et
quatre cas supplémentaires passent dans le groupe ciblé : index/Event réservé, create+update puis suppression
et liste caller modifiée. Commande ciblée d’abord refusée (nom singulier de fichier
inexistant), corrigée sans contourner : **124 passed in 3.74s**. Trois vrais
os._exit(74), deux compacteurs concurrents, publication corrompue garde snapshot.
Substitutions en mémoire partage de scan / relecture avant retrait retirés →
un échec chacune. Suite VM isolée hors sandbox : **1483 passed in 37.03s**,
aucun échec, saut ou désélection, Python `.venv` 3.13.5/pytest 9.1.1 ; journal
`/tmp/em-suite-GthGBD/pytest.log`, base plus lot runtime avant commit.

Outil benchmark_information_compaction ajouté et exécuté réellement : trois
corpus indépendants par single/batch sur 1000 tmpfs et 300 ext4. Chaque variante
vérifie objets canoniques, reçus sans corps, absence de snapshots et rejeu exact.
1000 tmpfs médiane compaction 160,661712 → 2,392723 s ; scans 1000 → 10,
JSON 1003000 → 13010. Préparation complète 162,883535 → 4,662694 s. Ext4/300,
environ 19,2 → 1,4 s (valeurs exactes/étendues dans compaction-summary.json).
Rapports/logs et hashes core/outil vérifiés, dossiers temporaires supprimés.

Corpus synthétiques isolés uniquement ; données actives/sauvegarde intactes.
Coût par lot toujours linéaire, ingestion/compaction croissantes quadratiques
réduites. Ni services actifs, ni corpus réel, ni coupure électrique validés.
Estimations 45 % / 52,75 points inchangées. Contrat/mesures :
docs/INFORMATION-COMPACTION-BATCHES.md et docs/VM-PERFORMANCE-2026-10-03.md.
