# Disponibilité et échéances durables — première tranche T-046

Livré le 02/10/2026 en local. Commandes explicites, sans service VM, cron,
automation externe, notification ni fenêtre horaire installée.

## Disponibilité indépendante du sens

`AvailabilityService(backend).set_level(memory, level, operation_id=...,
event_id=..., actor=..., timestamp=...)` écrit HIGH, INTERMEDIATE ou LOW dans
`metadata.availability` par le service Information journalisé. Le client fournit
le snapshot Memory original et le conserve pour rejouer exactement la commande.
Révisions, Events et reçus suivent T-041/T-042. Descendre en LOW est une éviction
du niveau actif, pas une suppression du contenu.

`acknowledge_review(memory, mêmes identifiants...)` acquitte explicitement
`metadata.recheck_required` sans modifier vérité, temporalité ou corps. Changer
seulement la disponibilité ne supprime jamais le besoin de revue. Le format
des Events reste inchangé ; les détails de mutation demeurent dans les snapshots/
empreintes du journal Information jusqu'à compaction.

Le catalogue expose disponibilité et besoin de revue. `ContextualRecall.recall`
accepte `availability='HIGH'|'INTERMEDIATE'|'LOW'` et expose le niveau retourné ;
sans filtre tous les niveaux restent candidats. Contexte, validité et statuts
restent contrôlés. `recheck_required` rend `needs_review` vrai, même si le fait
est CONFIRMED dans un contexte connu.

## Échéances déclarées

`LifecycleTriggers(backend).schedule(target_id, revision=..., kind=...,
due_at=..., trigger_id=..., actor=..., created_at=...)` conserve une intention
REACTIVATE ou RECHECK dans `history/operations/lifecycle-trigger-v1`. Le client
fournit son identité : deux intentions identiques peuvent avoir des IDs différents.

Le journal garde commande, empreinte, révision/hash du fichier source, état et
résultat, sans snapshot du corps. Le contexte d'exécution peut contenir des
données sensibles ; les empreintes ne garantissent pas la confidentialité.
Un ID rejoué rend son état courant ; une commande différente avec le même ID
est refusée, même après annulation ou disparition de la cible.

La programmation exige la révision courante et un moteur prêt. Elle ne réserve
pas l'Information pendant l'attente : les corrections restent possibles. Une
révision ou un hash modifié rend l'échéance STALE au traitement, sans écraser
la correction ni reporter silencieusement la date sur une nouvelle version.

## Horloge et politique explicites

`run_due(at=..., query_scope={}, limit=100)` traite les échéances dépassées,
triées par date puis ID. Les dates incluent un fuseau. La sélection est bornée ;
le reste demeure durable. Aucun appel implicite à l'heure système. Après arrêt,
un nouvel appel avec l'heure réelle rattrape les échéances dépassées.

Le contexte fourni est celui de l'exécution. Une REACTIVATE applicable,
CONFIRMED et sans besoin de revue passe en HIGH. Un contexte inconnu, conflit
ou fait non confirmé demande RECHECK et reste INTERMEDIATE. MOBILE_PRESENCE
et OBSTACLE restent à revérifier : un chat anciennement observé n'est pas
présenté comme encore à cette position ; contourner un obstacle n'est pas sa
disparition. Les dates d'observation et sources sont conservées.

Une REACTIVATE expirée, hors contexte, REFUTED ou SUPERSEDED est SKIPPED. Une
RECHECK peut marquer une observation historique à examiner sans étendre sa
validité ni changer sa vérité. Suppression en attente → SKIPPED ; source
modifiée/retirée → STALE. Reprogrammer exige une nouvelle intention explicite.

## Annulation et reprise

| État | Signification |
| --- | --- |
| SCHEDULED | Attente normale ; readiness reste autorisée |
| APPLYING | Exécution figée, effet ou acquittement à reprendre |
| COMPLETED | Résultat enfant journalisé puis acquittement durable |
| CANCELLED | Annulation explicite avant début d'effet |
| STALE | Source modifiée ou disparue avant effet |
| SKIPPED | Politique d'activation ou suppression en attente empêche l'effet |

`cancel(trigger_id, actor=..., at=..., reason=...)` n'annule que SCHEDULED ; son
rejeu exact est stable. APPLYING exige une reprise. COMPLETED est l'acquittement
moteur après effet ; il ne prétend pas qu'un humain a lu un message ou revu le fait.

Verrous : Persistent → Déclencheur → journal/Event Information. APPLYING fige
heure/contexte/effet et empreinte enfant, puis une commande Information emploie
des IDs dérivés du trigger_id. Avant l'enfant, la source est revalidée. Une panne
à cet endroit peut devenir STALE si une autre écriture a modifié la source.

Si l'enfant existe, sa commande doit correspondre à l'empreinte figée. Sa reprise
ou son reçu fait autorité, jamais la seule révision courante. Une panne après
effet mais avant acquittement se reprend sans doubler l'effet, même après
compaction de l'enfant et suppression de la cible. Les snapshots enfants gardent
leur politique de compaction existante.

`recover-all` reconnaît la famille et reprend uniquement APPLYING, avec contrôle
final sur disque. Il ne lance jamais SCHEDULED, même en retard. Corruption et
FAILED restent bloquants. La migration refuse ces intentions avant toute écriture.

## CLI

```sh
python -B -m core.lifecycle.cli --root RACINE list
python -B -m core.lifecycle.cli --root RACINE schedule info-1 --revision 1 \
  --kind REACTIVATE --due-at 2026-10-03T06:00:00+02:00 \
  --trigger-id wake-info-1 --actor toytoy --at 2026-10-02T06:00:00+02:00
python -B -m core.lifecycle.cli --root RACINE run-due \
  --at 2026-10-03T07:00:00+02:00 --scope contexte-actuel.json --limit 20
python -B -m core.lifecycle.cli --root RACINE cancel wake-info-1 \
  --actor toytoy --at 2026-10-02T08:00:00+02:00 --reason "Report décidé"
python -B -m core.lifecycle.cli --root RACINE recover
```

`list` ne crée aucun fichier. `set-level` et `acknowledge-review` prennent
`--memory SNAPSHOT.json --operation-id ID --event-id ID --actor NOM --at DATE`,
et `--level HIGH|INTERMEDIATE|LOW` pour set-level. Les mutations peuvent créer
des verrous techniques. Une commande bloquée sort avec code 1.

## Preuves et suite

25 nouveaux cas `tests/test_lifecycle_triggers.py` ; groupe avec readiness,
rappel et catalogue : 77 réussis. Temps, rattrapage, annulation, correction/hash,
suppression, mobile/obstacle, inapplicabilité, deux interruptions aux frontières,
une dans l'enfant, deux arrêts de processus, deux exécuteurs concurrents,
reprise après compaction/suppression, CLI et lots bornés. Retirer activation,
prudence mobile/obstacle ou signal de revue au rappel donne 1 + 2 + 2 assertions
rouges ; code restauré. Aucune validation VM ni coupure électrique.

Dans cette tranche, le planificateur de routage reste séparé. Catalogue/dossiers
peuvent devenir STALE après effet ; leurs réparations restent explicites. Pas
de fenêtre matinale, détection de charge, récurrence, notification ou installation
VM. Scans/verrous à mesurer sur corpus réel. HIGH seul n'est pas un budget de contexte.

Suite complète du lot : **908 réussis, 5 échecs sockets Manager, 46,21 s**,
Python 3.12.14/pytest 9.1.1, aucun désélectionné.
