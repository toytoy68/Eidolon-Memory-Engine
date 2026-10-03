# Rattachement explicite d’une Information déjà stockée — format 4

`RoutingExecutor.preview_link(memory, context, project_revision=...)` produit un
aperçu en lecture seule. `context.already_stored=true` et `existing_dossier`
désignent un projet existant explicitement choisi ; sa révision est exigée.
Le plan de référence doit être NONE avec un rattachement projet compatible.
L’Information fournie doit être **exactement le Memory canonique actuel**,
y compris corps, métadonnées, provenance, dates et révision.

Modifier la qualification, la disponibilité ou le texte dans l’entrée n’est pas
un rattachement : effectuer d’abord une commande UPDATE explicite. L’aperçu
refuse source absente/différente, révisions incohérentes, revue/ambiguïté, retrait
observé, mise à jour proposée et dossier divergent. L’ancienne méthode preview
STORE/UPDATE n’accepte pas ce plan ; utiliser le point d’entrée dédié.

```sh
python -B -m core.routing.execution_cli --root RACINE preview \
  --memory canonical-memory.json --context link-context.json \
  --project-revision 1 --link-only > link-plan.json
python -B -m core.routing.execution_cli --root RACINE execute \
  --plan link-plan.json --intent-id stable-link-intent \
  --actor human --timestamp 2026-10-03T01:00:00Z
```

Exemple de contexte, lorsque l’Information porte le project_id correspondant :

```json
{"already_stored": true, "existing_dossier": "project", "query_scope": {"goal": "efficiency"}}
```

Un selected_project explicite peut choisir une association supplémentaire ; le
Memory canonique n’est pas réinterprété ni sa metadata.context réécrite.
`--link-only` exclut `--new-project` et `--with-lifecycle`.

## Effets et reprise

Le format 4 reprend les intentions, réservations et reçus du routage existant.
Avant réservation : revalidation du plan, des snapshots et de la readiness,
contrôles de suppression/pending et conflits enfants. L’Information ne reçoit
**aucune écriture, révision supplémentaire, opération ou Event nouveau**.
Ses octets présents sont conservés, même les fins de ligne autour du document.
La disponibilité et les échéances restent inchangées ; le résultat indique
`deferred=["availability"]`, sans champ lifecycle ni trigger créé.

Le projet reçoit LINK par le journal Thread habituel si la relation CONCERNS
manque, puis le dossier est reconstruit avec les notes humaines conservées.
Si le lien existe déjà, pas de nouvelle révision/commande/Event Thread. Une
intention distincte peut tout de même reconstruire le dossier explicitement.
Le résultat renvoie la révision Information existante, la révision du projet et
le digest de projection. Le reçu terminal ne garde aucun corps Information.

Pendant APPLYING, le parent contient temporairement les snapshots nécessaires
à la revalidation ; il réserve les cibles jusqu’à la reconstruction du dossier.
Les autres écrivains coopérants attendent/refusent ces cibles. Une interruption
se reprend via la même intention ou recover-all. Les snapshots parents sont
remplacés par le reçu compact après succès ; la rétention des snapshots enfants
Thread reste régie par les contrats existants, pas par une nouvelle politique.

Rejeu terminal : même intention/plan/acteur/date retourne le résultat historique
sans refaire le lien, réécrire une Information éditée depuis ou recréer un projet
supprimé. Une identité réutilisée avec un autre plan reste refusée. Inventaire,
readiness et transfert core reconnaissent ce format ; formats 1/2/3 inchangés.
Après copie, le premier appel peut recréer les verrous techniques exclus du
transfert, sans modifier les données ou le reçu.

## Résultat client

`assess` signale désormais PREVIEW_REQUIRED / PREVIEW_LINK_EXISTING pour NONE
avec un projet existant explicitement choisi. Ce résultat ne consulte pas le
stockage et ne vaut ni readiness ni source valide : l’aperçu vérifie la source
et les révisions, puis l’exécution contrôle la readiness avant réservation.
Sans résolution explicite du projet, le cas reste REVIEW_REQUIRED. NONE seul
reste NO_ACTION ; aucune suppression implicite.

## Preuves et limites

33 nouveaux cas : 29 rouges sur le squelette, puis quatre cas supplémentaires
(identité enfant conflictuelle avec preuve rouge dédiée, notes CRLF, plan modifié,
CLI incompatible). Révisions/octets/Events/échéances conservés, refus, réservations
et recovery global à quatre frontières ; trois arrêts réels, deux processus
concurrents, copie/rejeu et rejeu après édition/suppression du projet.
182 ciblés réussis ; suite VM complète 1516 réussis en 37,84 s.
Preuves négatives et logs au rapport daté.

Pas de création implicite de projet, activation de client/service, qualification
inférée, corpus réel ou coupure électrique validés. Le nouveau lien ne transforme
pas une observation en vérité confirmée. Les dossiers lieu/thème et la résolution
durable des revues restent des capacités distinctes.
