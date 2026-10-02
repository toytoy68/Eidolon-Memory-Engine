# Résolution humaine FAILED — reprise des statuts Thread

Ce premier parcours traite uniquement les opérations THREAD_STATUS_CHANGE de
`memory/history/operations/thread-status-v1`. Une personne peut autoriser la
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

`preview` est sans écriture, même sans arbre valide. Le shell peut écrire le
rapport au chemin explicitement choisi ; garder cette revue hors des journaux
canoniques. L'aperçu donne opération/cible, révisions, empreinte du plan et des
octets FAILED, état du Thread BEFORE/AFTER et de l'Event ABSENT/MATCH, effets
encore nécessaires et décisions humaines antérieures. Les snapshots complets
restent consultables dans le journal source. L'aperçu ne vaut pas autorisation.

L'API expose `review_failed_status(root, operation_id)` et
`retry_failed_status(root, review, *, resolution_id, actor, reason, timestamp)`.
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
autre changement de statut ne peut réserver le même ID d'Event. Les FAILED
indépendants de cette même famille peuvent être résolus un par un. Une autre
famille FAILED, une opération PREPARED/APPLYING indépendante, une intention
parente de routage ou une source inconnue/corrompue bloque cette première version.
Terminer les opérations indépendantes par leurs procédures de reprise, ou
examiner les dépendances ; ce parcours ne contourne pas une intention parente.

L'aperçu est recalculé sous verrous Persistent → Thread → Operation → Event.
Même une modification des seuls octets du journal rend la revue périmée.
Les valeurs et leurs types JSON doivent correspondre. Une divergence ne publie
ni autorisation ni effet métier ; des fichiers de verrou et, pour un journal
restauré, le répertoire Events peuvent être initialisés pendant le contrôle.
Il n'y a aucune réécriture forcée des sources pour les faire correspondre.

## Autorisation atomique et reprise après arrêt

Une seule publication atomique du journal réalise ces deux changements :

1. Ajouter une entrée à `manual_resolutions` avec `resolution_id`, action
   RETRY_THREAD_STATUS_V1, auteur, motif, date, SHA-256 du journal FAILED et
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
ici uniquement pour THREAD_STATUS_CHANGE. Il est omis si vide : les journaux
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

Il ne s'agit pas d'une résolution générale de FAILED : création/suppression/
édition de Thread, écritures Information, parents de routage et conflits réels
restent hors de ce parcours. Aucun état ABANDONED ajouté. L'autorisation humaine
ne signifie pas que le moteur a identifié la cause initiale de l'échec ; cette
analyse motive la décision fournie par l'opérateur. Aucune commande n'est lancée
sur la VM par la livraison de cette fonctionnalité.

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

Groupe ciblé : **89 réussis en 2,96 s**. Suite complète : **1171 réussis, cinq
échecs de sockets Manager avant scénario en 68,78 s**, aucun désélectionné,
Python 3.12.14/pytest 9.1.1. Aucun scénario VM compté comme validé.
