# Commandes de projet coordonnées — T-031, lot du 01/10 au soir

Livré en local, non testé sur VM. Les commandes modifient un Thread existant :
liens CONCERNS, actions, titre, objectif et contexte. Elles ne créent ni dossier
ni échéance et n’exécutent pas encore RoutingPlan.

## Entrée et assemblage

`ThreadService.for_backend(backend)` assemble les coordinateurs canoniques
création/statut/suppression/modification dans les familles du history_root du
backend. `service.update_thread(thread_id, command, previous_revision=…,
operation_id=…, event_id=…, actor=…, timestamp=…)` transmet une commande complète.
Le client fournit une identité d’intention stable, la révision attendue et les
mêmes acteur/horodatage au rejeu. Aucun identifiant n’est dérivé du seul contenu.

| Commande | Champs obligatoires en plus de kind |
| --- | --- |
| LINK | information_id |
| UNLINK | information_id |
| ADD_ACTION | action : action_id, description, status, metadata |
| ACTION_STATUS | action_id, status |
| DETAILS | fields : sous-ensemble non vide de title, objective, context |

Les champs inconnus sont refusés. DETAILS remplace les champs fournis en entier,
notamment context ; il ne fusionne pas implicitement ses clés. Actions et liens
sont explicites, sans déduction de similarité. Une nouvelle commande LINK sur un
lien présent ou UNLINK sur un lien absent est un conflit ; rejouer la même
opération rend son résultat initial. Les projets COMPLETED/CANCELLED refusent
ces nouvelles mutations. Les statuts d’actions suivent les règles existantes
du ThreadManager ; aucune nouvelle politique de transition n’est ajoutée.

Exemple command.json :

```json
{"kind":"LINK","information_id":"info-second"}
```

Sur une racine de test isolée configurée par MEMORY_ENGINE_ROOT :

```sh
python -B -m core.operations.cli update-thread project-id \
  --command-file command.json --previous-revision 1 \
  --operation-id link-second --event-id event-link-second \
  --actor human --timestamp 2026-10-01T17:30:00Z
```

## Journal, reprise et dépendances

Les familles sont `operations/thread-update-v1` (Operation THREAD_UPDATE) et
`events/thread-update-v1` (Event UPDATED ciblant un Thread). Le plan contient la
commande JSON normalisée, acteur/horodatage et snapshots complets avant/après.
Son empreinte couvre les champs immuables. Le lecteur reconstruit la transition
métier et compare le résultat au snapshot avant toute reprise. Une divergence
n’est jamais écrasée. Une révision supplémentaire est publiée par commande.

L’ordre des verrous est Persistent → Thread → Operation → Event. Le journal est
publié avant les effets ; APPLYING précède le Thread et l’Event ; COMMITTED
termine l’opération. Le rejeu terminal retourne le snapshot initial même après
évolution ou suppression du Thread, sans le recréer. L’Event conserve les
révisions et empreintes, le type de commande et la provenance, sans copier le
texte des objectifs/actions. L’Event n’est pas un bus d’exécution.

Un lien ajouté exige une Information lisible et sans écriture Information en
attente. Une demande de suppression déjà présente doit être annulée avant le
LINK. Si une demande arrive après la préparation du lien, la reprise du lien
reste possible, mais l’approbation de suppression est bloquée par ses snapshots
puis par le lien effectif. Une demande en attente n’autorise donc pas la perte
d’une réservation préparée. UNLINK retire explicitement le lien ; les snapshots
non terminés réservent encore leurs cibles jusqu’à COMMITTED.

Les coordinateurs de création, statut et suppression Thread consultent aussi
ce journal. Les dossiers refusent de reconstruire depuis une mutation en cours.
L’inventaire, readiness et recover-all connaissent la nouvelle famille ; la
reprise globale l’exécute avant les suppressions Thread, puis relit le disque.
Les familles FAILED/inconnues restent bloquantes. Le guard legacy reconnaît
le journal même si les objets courants ont été supprimés.

## Preuves et limites

19 nouveaux cas couvrent second apport au même projet, actions, détails,
révisions obsolètes, collisions d’identité/Event, rejeu après suppression,
blocage inter-familles, Information en cours de modification, fraîcheur du
dossier, CLI et divergences. Quatre frontières interrompues par exception ;
deux arrêts réels de processus à code 74 ; trois scénarios multiprocessus
sans Manager (même commande, intentions concurrentes, lien contre suppression).

Preuves négatives exécutées puis retirées : omettre l’Event fait échouer le
parcours projet ; omettre la réservation des snapshots permet une suppression
et fait échouer le test d’interruption ; omettre la garde inter-familles fait
échouer le test statut/suppression/dossier. Les trois sont des assertions
comportementales, distinctes de l’import absent avant implémentation.

Les snapshots Thread et commandes restent conservés ; leur rétention/compaction
relève de T-050. La suppression canonique d’une Information ne garantit pas
l’effacement de tous les snapshots, dossiers, notes ou sauvegardes. Les appels
bas niveau restent disponibles pour stockage/import explicite, et une mutation
externe peut provoquer un conflit. La façade complète Information/plan/dossier,
les mises à jour automatiques des dérivés, la recette VM et les coupures de
stockage ne sont pas livrées par ce lot. Le résultat de recover_all de ThreadService
reste un rapport de familles ; seul le contrôle global readiness vaut contrôle
de démarrage ponctuel sur une racine arrêtée.
