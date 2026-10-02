# Créer explicitement un projet par le routage — T-043, format 3

Le parcours accepte une Information qualifiée STORE ou UPDATE avec un projet
**explicitement nouveau**. L'appelant fournit identité, titre, objectif et dates
du projet ; le moteur ne les infère pas du texte. Le format 3 inclut la
disponibilité et les échéances du format 2.

## API et CLI

```python
from core.routing.execution import RoutingExecutor
from core.routing.policy import RoutingContext
from core.threads.models import Thread

executor = RoutingExecutor(backend)
project = Thread(
    'cooling-project', 'Refroidissement', 'Mesurer rendement et température',
    created_at='2026-10-02T08:00:00Z', updated_at='2026-10-02T08:00:00Z')
context = RoutingContext(selected_project='cooling-project', query_scope={'goal': 'efficiency'})
prepared = executor.preview_new_project(memory, context, project=project)
result = executor.execute(
    prepared, intent_id='start-cooling-project', actor='human',
    timestamp='2026-10-02T08:00:00Z')
```

`memory` doit satisfaire la politique explicite existante. Pour UPDATE,
`context.update_target` fournit l'identité/révision de l'Information existante.
Le projet commence à la révision 1 ; l'Information commence à 1 pour STORE,
ou avance d'une révision pour UPDATE. Le premier lien CONCERNS est intégré à
la création, sans révision supplémentaire de Thread.

Le projet doit être PROPOSED, révision 1, sans action ni relation préexistante,
sans started_at/completed_at, avec created_at horodaté avec fuseau explicite
et updated_at identique. Contexte et provenance explicites sont conservés.
Son identité doit être celle du dossier projet choisi par la politique.
Un ancien projet avec historique de création/suppression ne devient pas un
nouveau projet : choisir une nouvelle identité ou reprendre l'ancien parcours.

Le CLI accepte `--new-project project.json` à la place de `--project-revision` :

```sh
python -B -m core.routing.execution_cli --root RACINE preview \
  --memory input.json --context context.json --new-project project.json > plan.json
python -B -m core.routing.execution_cli --root RACINE execute \
  --plan plan.json --intent-id start-cooling-project \
  --actor human --timestamp 2026-10-02T08:00:00Z
```

`project.json` utilise le JSON Thread complet, également produit par
`core.threads.serialization.thread_to_dict(project)` :

```json
{
  "thread_id": "cooling-project",
  "title": "Refroidissement",
  "objective": "Mesurer rendement et température",
  "status": "PROPOSED",
  "revision": 1,
  "context": {},
  "actions": [],
  "relations": [],
  "created_at": "2026-10-02T08:00:00Z",
  "updated_at": "2026-10-02T08:00:00Z",
  "started_at": null,
  "completed_at": null,
  "provenance": {"requested_by": "human"}
}
```

Preview n'écrit aucun fichier/répertoire moteur, même si la racine n'existe
pas encore. Execute peut initialiser les répertoires canoniques nécessaires.
Les fichiers d'entrée et le plan contiennent du texte complet : leur rétention
reste à la charge de l'appelant. Les deux options de projet sont exclusives.
`--with-lifecycle` n'est pas nécessaire pour le format 3, qui l'inclut toujours.

## Intention, enfants et reprise

Le plan figé ajoute `project_create`, snapshot du modèle Thread, avec
`project_before=null`. Le journal parent conserve la famille
`routing-execution-v1` mais porte `format_version=3`. Les lecteurs reconnaissent
les trois formats ; les formats 1/2 ne sont ni modifiés ni convertis. Un ancien
binaire qui ne connaît pas le format 3 ne doit pas reprendre ces intentions.

Avant la première mutation canonique, le moteur revalide politique, révisions,
absence du projet, readiness, réservations et historique connu de l'identité.
L'intention réserve l'Information et le projet encore absent. Le parcours est :

1. Écriture Information par son journal habituel.
2. Création liée du Thread par `thread-create-v1`, avec un ID enfant déterministe.
3. Reconstruction du dossier depuis les objets canoniques.
4. Enregistrement éventuel de l'échéance pour la révision obtenue.
5. Reçu COMMITTED compact du parent, sans les snapshots/textes.

Le résultat reprend la forme du format 2 : Information, projet,
projection_digest, deferred vide et lifecycle. Le journal Thread de création
garde son contrat de provenance : Event système `thread-create-service`, acteur
`eidolon`, date du modèle Thread. L'acteur et la date de la commande de routage
sont portés par le parent et l'écriture Information ; ils ne réécrivent pas
ce contrat d'Event existant.

Une interruption peut laisser l'Information créée avant le projet. Rejouer la
même commande/identité ou appeler `recover-all` reprend le parent puis ses
enfants. Un Thread simplement semblable au résultat ne suffit pas : son journal
enfant doit prouver que la création a commencé. Un conflit ne fusionne pas deux
projets. Deux créateurs de la même identité ne peuvent pas gagner tous deux.

Les services métier respectent la réservation parent ; les primitives de
stockage/import restent distinctes. Une édition directe hors protocole est
détectée à la reprise, sans écrasement automatique. Le rejeu du reçu après
suppression des objets ne les recrée pas. Les suppressions exigent toujours
leurs approbations/compactions existantes. Il n'y a pas de transaction atomique
globale, d'abandon automatique ou de nouveau système de rétention des snapshots.

## Vérifications et limites

24 nouveaux cas : preview sans écriture, premier projet, UPDATE vers projet
nouveau, modèles refusés, révision/absence périmée, identité supprimée, divergence
étrangère, rejeu sans résurrection, commande modifiée, CLI et index facultatif.
Cinq interruptions entre étapes, deux à l'intérieur du journal de création,
trois arrêts réels de processus code 74 et deux créateurs concurrents sans Manager.
Readiness/inventaire format 3, dossier courant et échéance exécutable vérifiés.

Groupe ciblé : **58 réussis, 5,69 s**, anciens formats compris. Retirer le refus
de l'historique, la projection ou le verrou nécessaire à l'index rend les trois
tests correspondants rouges (1 + 1 + 1) ; code restauré. Le défaut de verrou
trouvé lors du raccordement est corrigé aussi pour les projets existants.

Les branches NONE/REVIEW, lieu/thème, qualification automatique, clients externes
et ordonnanceur restent hors de ce lot. Le statut épistémique n'est pas promu
par la création du projet. Aucun benchmark de charge, corpus réel, recette VM
ou coupure physique n'est revendiqué. Suite complète : **1031 réussis, cinq
échecs Manager de création de sockets avant scénario, 55,00 s**, aucun
désélectionné. Ces cinq scénarios restent à valider en VM.
