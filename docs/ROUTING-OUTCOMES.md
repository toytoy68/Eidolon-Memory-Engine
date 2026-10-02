# Résultats client NONE/REVIEW

`RoutingExecutor.assess(memory, context)` et `core.routing.outcomes.assess`
retournent un résultat `routing-outcome/1`, sans accès aux fichiers moteur ni
écriture. Le plan de référence original et ses raisons sont conservés. Les
qualifications restent explicites ; ni rôle ADMIN ni pertinence ne confirme une
Information. Le résultat ne contient pas le corps de l’Information.

| Résultat | Prochaine étape |
| --- | --- |
| NO_ACTION | DO_NOT_PERSIST : aucune persistance, suppression ou échéance |
| REVIEW_REQUIRED | RESOLVE_REVIEW : qualification, association ou preuves à revoir explicitement |
| PREVIEW_REQUIRED | PREVIEW_EXISTING_PROJECT si dossier explicitement fourni ; sinon RESOLVE_PROJECT |
| CAPABILITY_REQUIRED | UNSUPPORTED_ROUTE : voie sans projet, lieu ou thème non exécutée |

Les dimensions du plan sont indépendantes. NONE avec une association demandée
ne devient pas un succès silencieux : cela exige une commande explicite de
rattachement, signalée par REVIEW_REQUIRED. Une association ambiguë, une
qualification manquante, une date invalide, un conflit non résolu et un retrait
observé appellent une revue. Des références déclarées ne valident pas seules la
preuve d’un retrait. NONE conserve les mémoires préexistantes intactes.

Le résultat expose `writes_performed=false` et `execution_validated=false`.
PREVIEW_REQUIRED n’affirme ni existence/absence du projet, ni readiness moteur,
ni disponibilité de l’identité, ni fraîcheur des révisions. Le client doit
résoudre le projet et utiliser `preview`/`preview_new_project`, puis autoriser
explicitement `execute`. Une absence de `existing_dossier` ne prouve jamais que
le projet est neuf. Le résultat d’assessment est refusé comme plan exécutable.

```sh
python -B -m core.routing.execution_cli --root RACINE assess \
  --memory input.json --context context.json
```

Le code de sortie est zéro pour un résultat valide, y compris une revue requise ;
une entrée invalide produit BLOCKED et un code non nul. Une racine absente ou
bloquée n’est ni initialisée ni réparée. L’évaluation reste utilisable avant
connexion au moteur ; exécuter une mutation exige ensuite les contrôles normaux.

Un client peut afficher NO_ACTION sans stocker le corps ; pour une revue il
présente les raisons à l’humain, refait l’assessment après correction explicite,
puis passe au parcours journalisé. Aucune file de revue durable, résolution
humaine automatique, journal d’assessment, qualification automatique ou client
externe n’est livré. Les branches lieu/thème et rattachement d’une Information
déjà stockée restent ouvertes.

Preuves du 03/10 : 28 nouveaux cas, 25 rouges sur le squelette, 106 ciblés verts.
Client factice qualification → assessment → aperçu/exécution → rappel avec
incertitude conservée, NONE sur mémoire existante, arbres absents/bloqués
inchangés, associations explicites et valeurs sans alias. Preuves et suite VM
complète : [rapport daté](VM-TESTS-2026-10-02.md).
