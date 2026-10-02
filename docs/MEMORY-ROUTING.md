# Router mémoire de référence v0.1 — T-043

Le module `core.routing.policy` produit un **plan explicable sans écriture**.
Il traite un Memory déjà qualifié et un `RoutingContext` explicite. Il ne lit
pas des mots-clés dans le texte pour deviner s'il s'agit de technique, de
philosophie ou de vision robot. L'extraction et la qualification automatique
restent au producteur/futur adaptateur ; une qualification absente donne REVIEW.

## Ce qui est exécuté

- La source/provenance, les dates et le statut épistémique sont conservés
  séparément. Le rôle ADMIN ne promeut jamais UNVERIFIED en CONFIRMED.
- Le contexte exact est comparé : toutes les conditions déclarées connues et
  égales donnent MATCH, une contradiction connue OUT_OF_SCOPE, une condition
  manquante UNKNOWN. Scope absent n'est pas universel. Un conflit non résolu
  déclaré dans le contexte correspondant donne UNRESOLVED, sans gagnant.
- Les bornes temporelles déclarées sont interprétées avec un instant explicite
  et des fuseaux. Validité terminée donne EXPIRED, sans réfutation ni effacement.
- Les dimensions STORE/UPDATE/NONE/REVIEW, HIGH/INTERMEDIATE/LOW et
  CREATE_OR_LINK/LINK/NONE/REVIEW sont décidées séparément, avec raisons stables.
- Une mise à jour proposée référence une identité et une révision explicites.
  Un retrait observé exige un Memory qualifié OBSTACLE dont l'identité et la
  révision correspondent à la cible, ainsi que des références déclarées non
  vides (chaînes). Ces références ne constituent pas des preuves vérifiées.
  Un compte rendu de contournement ne modifie pas son état de présence.

## Profil de référence et limites

Les règles v0.1 sont un profil versionné, pas des vérités universelles :
réflexion générale sans demande mémoire ni projet → HIGH/NONE ; passage
mobile sans suivi/signification/demande → HIGH/NONE ; disposition des lieux
avec lieu explicite → candidate durable, HIGH pendant navigation sinon LOW ;
obstacle → conservation et réexamen, puis INTERMEDIATE après la tâche ;
projet ou réflexion à reprendre → fiche intermédiaire et proposition de dossier.

Pour un projet ambigu, le rattachement passe à REVIEW ; aucune fusion ni
création automatique n'a lieu. Le dossier peut être référencé par son identité
connue ou proposé à partir d'un sujet explicite (projet, thème, lieu). Sa
résolution réelle et le fichier Markdown vivant restent T-044. LOW conserve
ce pointeur dans le plan, mais le catalogue reconstructible reste T-045.

Le contexte de conflit est fourni explicitement. Le module ne découvre pas
encore seul que deux phrases parlent de la même pièce à la même date. De même,
une référence de preuve déclarée n'est pas vérifiée contre un capteur ou une
source externe par ce module. Aucun contrôle de robot n'est envoyé.

Une échéance produit un `proposed_trigger` stable dérivé de l'identité, de la
révision et de la date. Cette proposition n'est **ni persistée ni exécutée**.
L'exécution unique après redémarrage et la gestion des échéances manquées
restent T-046. Aucun TTL, suppression ou transition de niveau effective n'est
appliqué par le planificateur. NONE ne signifie jamais DELETE.

## Utilisation

API : `plan(memory, RoutingContext(...))` renvoie un `RoutingPlan`, avec
`contract_version=memory-policy/0.1`, `rules_version=reference/0.1`, identité et
révision sources, source/provenance et dates copiées, décisions et raisons.
Les annotations s'appuient sur `metadata.qualification` version 0.1 (nature,
horizon, qualified_by) et `metadata.context` ; voir le contrat fonctionnel.

```sh
python -B -m core.routing.cli --memory memory.json --context routing-context.json
```

Les deux entrées sont des objets JSON correspondant à Memory et RoutingContext.
Le CLI n'initialise aucun répertoire Memory Engine et affiche le plan uniquement.
L'exécuteur historique `services/memory-router` reste distinct ; le raccordement
métier vers T-041 et les projections T-044/T-046 n'est pas livré dans ce lot.

## Preuves

`tests/test_memory_policy.py` : 20 tests, dont les 14 scénarios du contrat pour
leur partie planification, source inchangée, conditions manquantes, contexte
contradictoire, preuve/révision de retrait, CLI en lecture seule. Retirer la règle
UNKNOWN fait échouer le scénario de contexte manquant. Les obligations de
persistance et d'activation du scénario programmé ne sont pas comptées validées.

## Exécuteur ajouté au lot du 01/10 au soir

Le planner reste pur. RoutingExecutor exécute désormais le sous-ensemble
STORE/UPDATE → projet existant → dossier, avec revalidation, intention durable,
reprise et reçu compact. Les autres branches sont refusées ou explicitement
différées ; voir [ROUTING-EXECUTION.md](ROUTING-EXECUTION.md).

## Corrections après revue E-004 du 02/10

Une disposition spatiale sans `place_id` reste REVIEW, même avec une cible de
mise à jour explicite et un projet. UPDATE ne remplace que STORE, jamais REVIEW.
Le retrait cohérent reste une **proposition** : l'exécuteur refuse toujours
`removal_observed`. L'ouverture de cette branche nécessite encore de définir
la résolution et la validation des preuves, sans déduire une vérité de simples
chaînes `evidence_refs`. Le Memory proposé est celui de l'obstacle à réviser ;
une observation distincte doit être référencée comme preuve déclarée.

`resume_at`, lorsqu'il est renseigné (non null), doit être une date valide avec
fuseau explicite. Sinon le plan exige REVIEW sans déclencheur ; le preview
exécutable refuse ce plan par OperationConflict. NONE/REVIEW ne portent jamais
de `proposed_trigger`, notamment après `already_stored`. Les échéances valides
conservent leur identifiant déterministe et leur garde à l'exécution.

Les formats et versions restent inchangés ; les plans valides non concernés
conservent leur résultat. Un ancien plan affecté par ces corrections est refusé
à la revalidation : refaire l'aperçu après correction des entrées. Si une
intention affectée est déjà APPLYING, elle reste bloquée pour examen humain ;
ne pas la réécrire ni forcer sa reprise automatiquement.
