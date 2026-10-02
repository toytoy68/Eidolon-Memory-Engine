# Exécution reprenable des plans — T-043 / T-046

Lot du 01/10/2026, après les commandes Thread. Le parcours livré est :
Information qualifiée STORE/UPDATE → projet **existant** → dossier actualisé.
Il conserve les règles et statuts du planner sans promotion de vérité.
Depuis le 02/10, le [format 3](ROUTING-NEW-PROJECT.md) ajoute un projet
explicitement nouveau ; les paragraphes format 1/2 ci-dessous décrivent le
parcours existant conservé.

## Contrat

`RoutingExecutor(backend).preview(memory, context, project_revision=…)` produit
un plan JSON figé sans écrire. Il contient Memory complet, contexte, décisions
et versions de règles, snapshots Information/Thread utilisés pour le contrôle
de révision. Les racines persistent/history sont les racines sœurs canoniques.
Le dossier est placé dans `memory/dossiers` afin que la reprise globale retrouve
la même destination après redémarrage.

`execute(prepared, intent_id=…, actor=…, timestamp=…)` revalide les décisions et
les snapshots avant de commencer. Le même intent_id et la même commande rendent
le résultat initial sans nouvel effet ; un autre plan sous cette identité est
un conflit. Deux intentions différentes ne sont jamais fusionnées à partir du
seul texte. Une révision devenue obsolète ou un état divergent est refusé.

Cette tranche accepte STORE et UPDATE avec LINK/CREATE_OR_LINK vers un projet
existant explicitement résolu. Si l’Information y est déjà liée, UPDATE ne
réécrit pas le Thread. La création automatique de projet, les dossiers lieu/thème,
les plans REVIEW/NONE et le retrait d’obstacle restent refusés **avant** la
première mutation. Le format 1 reste inchangé : échéances refusées et
disponibilité différée (`deferred: ["availability"]`).

Depuis le 02/10, `preview(..., include_lifecycle=True)` produit explicitement un
format 2. La disponibilité de la politique est intégrée à la première écriture
Information, sans révision/Event supplémentaire. Le besoin de réexamen est
conservé ou activé pour un obstacle ; aucune revue existante n’est acquittée
implicitement. Une proposition REACTIVATE valide enregistre une échéance durable
pour la révision obtenue, après actualisation du dossier. Les dates nécessitent
un fuseau explicite. Le reçu porte `deferred: []` et
`lifecycle: {availability, trigger_id}` ; un identifiant nul signifie sans échéance.
Il décrit l’enregistrement initial, pas le statut actuel du déclencheur.

## Journal et interruption

Une intention APPLYING est publiée dans
`memory/history/operations/routing-execution-v1` avant ses enfants. Elle réserve
les identités Information (y compris les relations proposées) et le projet.
Les services métier, suppressions et dossiers refusent d’utiliser ces cibles
hors du parcours propriétaire tant que celui-ci reste incomplet. Les appels
bas niveau/import demeurent distincts : une modification externe est détectée
par les snapshots et demande une revue, elle n’est jamais écrasée.

Les sous-commandes Information et LINK ont des IDs déterministes dérivés de
l’identité d’intention et de l’étape, pas du contenu. Leur propre journal prouve
si l’écriture a commencé ; voir un fichier qui ressemble au résultat ne suffit
pas à adopter une mutation étrangère. Le parcours relit les états et rejoue ces
commandes sous verrous Persistent → Thread → intention → journal enfant → Event.
Aucune transaction atomique multi-fichiers n’est revendiquée : une Information
peut être écrite alors que le dossier n’est pas encore reconstruit.

Après reconstruction et, en format 2, enregistrement de l’échéance, un reçu COMMITTED remplace atomiquement la commande et
ses snapshots. Il conserve empreinte, identités/révisions et empreinte de la
projection, sans le contenu de l’Information. Les journaux enfants gardent leurs
propres règles de compaction/rétention (T-042/T-050). Une exception après
publication se résout par le rejeu. Le reçu ne prouve pas la fraîcheur **actuelle**
du dossier : sa projection_digest décrit le résultat au moment du commit.

Inventaire et readiness reconnaissent la famille. `recover-all` reprend ces
parcours avant les reprises isolées des enfants, puis contrôle à nouveau les
fichiers. Les états inconnus ou corrompus bloquent. Un plan divergent reste
APPLYING mais sa reprise rapporte BLOCKED ; aucun abandon automatique.
Le guard legacy et la migration préalable prennent cette famille en compte.
Les formats 1, 2 et 3 cohabitent dans le même répertoire versionné ; les anciens
plans et reçus ne sont ni réinterprétés ni réécrits.

Une échéance enregistrée reste SCHEDULED même si elle est déjà dépassée.
`run-due` refuse de commencer son effet tant que le parcours parent réserve la
source ; la reprise termine d’abord le parcours, sans cycle de dépendance.
L’enregistrement interne exempte seulement l’intention propriétaire de sa
barrière readiness ; toute autre corruption ou opération incomplète bloque.
Une annulation explicite après enregistrement et avant reçu reste annulée
après reprise. Une correction ultérieure rend l’ancienne échéance STALE.

## CLI

Les fichiers d’entrée et de plan peuvent contenir du texte sensible. Les exemples
supposent un répertoire de travail choisi et une racine de test existante :

```sh
python -B -m core.routing.execution_cli --root RACINE preview \
  --memory input.json --context context.json --project-revision 1 > plan.json
python -B -m core.routing.execution_cli --root RACINE execute \
  --plan plan.json --intent-id intent-project-second \
  --actor human --timestamp 2026-10-01T18:30:00Z
```

Ajouter `--with-lifecycle` à preview pour le format 2 ; execute consomme ensuite
ce plan sans autre option. Le déclenchement reste un appel explicite à
`core.lifecycle.cli run-due`, voir [LIFECYCLE-TRIGGERS.md](LIFECYCLE-TRIGGERS.md).

Le mode preview ne crée aucun fichier/répertoire moteur. La redirection du shell
crée uniquement le fichier de sortie explicitement demandé. Le mode execute
écrit et renvoie un code non nul en cas de refus. Une erreur ne garantit pas
qu’aucune étape antérieure n’a été appliquée : reprendre avec la même intention
ou utiliser recover-all sur la copie arrêtée.

## Preuves et limites

21 nouveaux cas : aperçu sans écriture, correction d’une Information liée et
notes humaines préservées, refus des plans périmés et non pris en charge,
identité stable, reçu sans corps, rejeu après suppression sans résurrection,
contrôle CLI, corruption, dépendances et reprise globale. Quatre interruptions
par exception entre étapes, deux interruptions dans les enfants, quatre arrêts
réels de processus à code 74 et deux scénarios concurrents sans Manager.

Actualisation automatique limitée à ce parcours. Les autres commandes canoniques
peuvent encore rendre une vue STALE ; `core.dossiers.cli reconcile --apply`
répare maintenant ce retard à la demande (voir PROJECT-DOSSIERS.md).
Aucun ordonnanceur, aucun modèle/extracteur et aucun client externe connecté.
Le catalogue reconstructible existe à la demande ; un effet de déclencheur rend
les dérivés STALE jusqu’à leur reconstruction explicite. Le rappel contextualisé T-047 est livré (CONTEXTUAL-RECALL.md). Aucun
résultat VM, coupure de stockage ou corpus réel n’est acquis.

Suite complète locale : 827 réussis, cinq échecs sockets Manager avant scénario,
41,54 s. Retirer temporairement la réservation, la reconstruction ou le reçu
compact fait échouer pour chaque cas une assertion comportementale ; code restauré.

## Extension cycle de vie du 02/10

19 nouveaux cas : disponibilité dans la révision initiale, échéance/temps
explicites, correction et invalidation de l’ancienne échéance, annulation pendant
la reprise, garde parent avant effet, corruption étrangère bloquante et reçu
sans résurrection. Cinq interruptions entre étapes et deux arrêts réels de
processus code 74 ; CLI opt-in et anciens tests format 1 conservés. Groupe
parcours/cycle de vie : 59 réussis. Les preuves négatives et le résultat global
sont consignés dans ECHANGES.md. Aucun résultat VM acquis.

## Extension nouveau projet — format 3

`preview_new_project(memory, context, project=template)` et le CLI
`preview --new-project project.json` créent un plan explicite, sans écrire.
Le projet absent est réservé par l'intention et créé via le journal Thread
existant, avec son premier lien CONCERNS en révision 1. Disponibilité,
échéance, dossier et reçu compact sont inclus. Contrat, exemple JSON et
limites : [ROUTING-NEW-PROJECT.md](ROUTING-NEW-PROJECT.md).
Le routage prend désormais aussi le verrou du journal Information pendant
son contrôle préalable de réservations pour l'index facultatif.

## Entrée client NONE/REVIEW — 03/10

`assess(memory, context)` / CLI `assess` traite les résultats sans mutation :
NO_ACTION, REVIEW_REQUIRED, PREVIEW_REQUIRED ou CAPABILITY_REQUIRED. Le client
résout explicitement les points de revue et le projet, puis utilise le parcours
journalisé existant. Aucun résultat d’assessment ne vaut plan exécutable ou
readiness moteur. [Contrat et limites](ROUTING-OUTCOMES.md).
