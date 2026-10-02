# Résolution humaine FAILED — créations, statuts et éditions Thread

Ce parcours traite THREAD_STATUS_CHANGE dans `thread-status-v1`,
THREAD_UPDATE dans `thread-update-v1` et THREAD_CREATE dans
`thread-create-v1`, sous `memory/history/operations/`. Une personne peut autoriser la
reprise du **plan original**, après examen des effets présents. Il n'existe ni
abandon, ni remplacement des snapshots, ni annulation implicite des effets.
Les autres familles FAILED restent bloquantes et demandent un parcours dédié.

## Aperçu puis décision explicite

Sur une copie arrêtée, avec les écrivains legacy et outils directs arrêtés :

```sh
python -B -m core.operations.failed_resolution --root /copie \
  preview identifiant-operation > /hors-copie/revue.json

python -B -m core.operations.failed_resolution --root /copie \
  retry --review /hors-copie/revue.json \
  --resolution-id decision-unique --actor toytoy \
  --reason "Cause examinée, effets cohérents, reprise du statut original autorisée" \
  --timestamp 2026-10-02T16:30:00+02:00
```

Pour une édition (LINK/UNLINK, ADD_ACTION/ACTION_STATUS ou DETAILS), choisir
explicitement la famille lors de l'aperçu ; `retry` lit ensuite celle de la revue :

```sh
python -B -m core.operations.failed_resolution --root /copie \
  preview identifiant-operation --family thread-update-v1 > /hors-copie/revue.json
```

Pour une création liée, utiliser `--family thread-create-v1`. La revue donne
`information_id`, Thread ABSENT/AFTER et révisions 0 → 1. Les seuls états admis
sont : Thread absent/Event absent, Thread exact/Event absent, Thread exact/Event
exact. Un Event présent sans Thread est bloqué, ainsi qu'un autre journal de
création de la même identité, même COMMITTED. L'Information liée et tous les
CONCERNS doivent être présents et lisibles ; une demande de suppression tardive
reste en attente et n'est pas approuvée par la résolution. Le journal FAILED
réserve déjà le lien, puis le Thread créé conserve cette protection.
Les parents de routage non terminés et les autres familles FAILED restent
bloquants : cette extension ne résout pas leurs enfants indépendamment du parent.

Sans `--family`, le CLI conserve la famille de statut. La revue d'édition ajoute
la commande originale complète (`command`) pour l'examen humain.

`preview` est sans écriture, même sans arbre valide. Le shell peut écrire le
rapport au chemin explicitement choisi ; garder cette revue hors des journaux
canoniques. L'aperçu donne opération/cible, révisions, empreinte du plan et des
octets FAILED, état du Thread BEFORE/AFTER (ABSENT/AFTER pour création) et de
l'Event ABSENT/MATCH, effets encore nécessaires et décisions humaines antérieures. Les snapshots complets
restent consultables dans le journal source. L'aperçu ne vaut pas autorisation.

L'API générale expose `review_failed_thread(root, operation_id, *, family)` et
`retry_failed_thread(root, review, *, resolution_id, actor, reason, timestamp)`.
Les fonctions `review_failed_status` / `retry_failed_status` restent compatibles
avec leurs appels et revues antérieurs ; elles n'autorisent que les statuts.
Une décision exige un identifiant, un auteur, un motif non vide et une date avec
fuseau explicite. Le CLI retourne 1 avec BLOCKED au refus, 0 pour l'aperçu ou
la réussite. Les exceptions API conservent la cause du blocage.

## Contrôles avant autorisation

Le journal doit être FAILED, de la bonne famille, avec hash valide et snapshots
représentant exactement la transition métier. Le Thread courant doit être
identique au snapshot avant ou après ; l'Event doit être absent ou exactement
celui du plan. Un Event présent avec un Thread resté à l'état avant est refusé.
Les relations CONCERNS du résultat doivent rester valides.

Aucune autre opération non terminée ne peut réserver le même Thread ; aucun
autre opération de la famille ne peut réserver le même ID d'Event. Les FAILED
indépendants de cette même famille peuvent être résolus un par un. Une autre
famille FAILED, une opération PREPARED/APPLYING indépendante, une intention
parente de routage ou une source inconnue/corrompue bloque ce parcours, y compris un FAILED de l’autre famille supportée.
Terminer les opérations indépendantes par leurs procédures de reprise, ou
examiner les dépendances ; ce parcours ne contourne pas une intention parente.

Pour THREAD_UPDATE, les gardes du coordinateur sont aussi vérifiées **avant**
l'autorisation : aucune collision d'operation_id avec création/statut/suppression,
même COMMITTED ; informations du résultat présentes et lisibles ; réservations
d'écriture/routage des nouveaux liens respectées. L'Event attendu est construit
par la même fonction que la reprise ordinaire.

Une demande PENDING_DELETE arrivée après la préparation du LINK peut attendre,
comme lors d'une reprise ordinaire : le FAILED réserve déjà les cibles des deux
snapshots et empêche l'approbation de la suppression. Après reprise du LINK,
le lien canonique la bloque encore. Après UNLINK, la suppression peut être
approuvée si toutes ses autres gardes passent. La résolution n'approuve ni
n'annule cette demande. Les informations conservées dans le résultat sont
relues ; le plan Thread ne fige pas leur contenu ou leur révision.

L'aperçu est recalculé sous verrous Persistent → Thread → Operation → Event.
Même une modification des seuls octets du journal rend la revue périmée.
Les valeurs et leurs types JSON doivent correspondre. Une divergence ne publie
ni autorisation ni effet métier ; des fichiers de verrou et, pour un journal
restauré, le répertoire Events peuvent être initialisés pendant le contrôle.
Il n'y a aucune réécriture forcée des sources pour les faire correspondre.

## Autorisation atomique et reprise après arrêt

Une seule publication atomique du journal réalise ces deux changements :

1. Ajouter une entrée à `manual_resolutions` avec `resolution_id`, action
   RETRY_THREAD_STATUS_V1, RETRY_THREAD_UPDATE_V1 ou RETRY_THREAD_CREATE_V1
   selon la famille,
   auteur, motif, date, SHA-256 du journal FAILED et
   SHA-256 de la revue approuvée.
2. Passer ce même journal de FAILED à APPLYING, sans changer le plan,
   l'operation_id, l'event_id, la cible ou les révisions.

Le coordinateur existant reprend alors ce plan. Il ne réécrit pas un effet déjà
présent et identique, et conserve ses gardes de divergence. Après le commit,
le même identifiant de décision et les mêmes paramètres rendent le résultat
initial sans ajouter une autorisation ni un Event ; un Thread supprimé depuis
n'est pas recréé. Changer les paramètres d'une décision existante est refusé.

Avant la publication, un arrêt laisse FAILED sans autorisation. Après, il
laisse APPLYING avec sa trace durable : `recover-all` peut reprendre selon ses
gardes habituelles, sans nouvelle décision. Si d'autres FAILED subsistent,
le contrôle global reste bloqué jusqu'à leur traitement ; une reprise explicite
de cette même décision peut terminer l'opération autorisée. Après COMMITTED,
le rejeu est sans nouvel effet métier.

Si l'opération est déclarée FAILED à nouveau, réutiliser l'ancienne décision
ne la rouvre pas : nouvel aperçu, nouveau motif et nouvel identifiant requis.
Les décisions antérieures restent dans la liste. Une panne d'E/S ou un arrêt
pendant l'écriture temporaire peut laisser un fichier inconnu ; l'inventaire
continue de bloquer ce résidu pour examen, sans nettoyage aveugle.

## Format, compatibilité et limites

`manual_resolutions` est un champ optionnel strict du journal Operation, permis
ici pour THREAD_STATUS_CHANGE, THREAD_UPDATE et THREAD_CREATE, avec action correspondant
strictement au type d’opération. Il est omis si vide : les journaux
anciens ne sont pas migrés à la lecture ni enrichis artificiellement.
Le calcul de hash du **plan** exclut cette trace, comme il exclut le statut ;
les empreintes des plans existants restent inchangées. Les métadonnées de revue
ne sont pas des commandes métier et ne doivent pas changer leurs identités.

Le dépôt générique `update()` interdit toujours toute sortie de FAILED et
interdit de modifier/supprimer la trace. Seule la commande de résolution publie
cette transition spécialisée après ses contrôles. La validation refuse entrées
incomplètes, actions inconnues, dates invalides et IDs de décision dupliqués.
Readiness et recover-all utilisent ce lecteur strict : une trace mal formée
bloque la reprise. L'auteur est une identité déclarée ; cette trace n'est pas
un système d'authentification ni une signature contre l'édition malveillante.

Un ancien binaire qui ne connaît pas ce champ refusera les journaux résolus.
Ne pas enlever `manual_resolutions` pour rendre ces fichiers lisibles par une
ancienne version. Il faut conserver un lecteur compatible avec la nouvelle
trace lors d'un déploiement ou d'une restauration.

Il ne s'agit pas d'une résolution générale de FAILED : suppression
de Thread, écritures Information, parents de routage et conflits réels
restent hors de ce parcours. Aucun état ABANDONED ajouté. L'autorisation humaine
ne signifie pas que le moteur a identifié la cause initiale de l'échec ; cette
analyse motive la décision fournie par l'opérateur. Aucune commande n'est lancée
sur les données actives par la livraison de cette fonctionnalité.

## Preuves

36 cas dans `tests/test_failed_status_resolution.py` : trois états partiels,
aperçu sans écriture, métadonnées obligatoires, divergences, fraîcheur et types
de la revue, réservations Thread/Event, autorisation atomique, trois interruptions,
deux arrêts réels code 74, concurrence de deux processus sans Manager, rejeu sans
résurrection, deuxième échec exigeant une nouvelle décision, refus du dépôt
générique, corruption de trace, compatibilité des anciens journaux et CLI.

Supprimer expérimentalement la trace lors de la publication APPLYING fait
échouer un test ; réutiliser un aperçu sans le recalculer en fait échouer un
autre. Ces substitutions ne sont faites qu'en mémoire dans des processus de
preuve distincts. Aucune validation VM, disque réel en panne ou coupure électrique.

Premier lot statuts : 89 ciblés réussis en 2,96 s ; suite complète 1171 réussis,
cinq échecs de sockets Manager avant scénario en 68,78 s.

Extension éditions : 36 cas dans `tests/test_failed_update_resolution.py`, dont
les cinq commandes dans les trois états partiels (15 cas), revues périmées,
plan incohérent même rehashé, liens absents/corrompus, conflits Thread/Event/ID,
Event sans résultat Thread, demande de suppression en attente, UNLINK puis
suppression/rejeu sans résurrection, trois arrêts réels code 74, mauvais type
d'audit et CLI sans création d'arbre à l'aperçu.

Preuves négatives en processus séparés : omettre le contrôle des liens avant
autorisation donne un échec (lien absent ; le cas corrompu reste bloqué par
l'inventaire), omettre la revalidation de l'aperçu donne un échec, retirer
l'audit lors de la publication donne un échec. Aucune substitution conservée.
Groupe ciblé : **107 réussis en 4,52 s**. Dernière suite complète :
**1207 réussis, 5 échecs de sockets Manager avant scénario en 75,62 s**, aucun désélectionné,
Python 3.12.14/pytest 9.1.1. Aucun scénario VM compté comme validé.


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
