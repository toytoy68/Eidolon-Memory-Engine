# Mesure du rendu complet du rappel sur VM — 3 octobre 2026

Base GitHub `e7ecfc6` confirmée avant ce lot ; code métier inchangé depuis
`7eddfe0`, suite précédente 1606 réussis. Python 3.13.5, VM Eidolon-Memory,
/tmp tmpfs. L’outil `tools.benchmark_recall_payload` crée neuf corpus indépendants :
trois répliques pour chacune des tailles de preuve 200/2000/10000 caractères.
Chaque corpus contient huit Informations synthétiques UNVERIFIED/MATCH,
provenance ADMIN sans promotion de vérité, texte identique « payload measurement ».
La première source est riche en preuves, les autres ont des preuves courtes.

Après un warmup non mesuré, trois rappels sur chaque corpus chaud sélectionnent
cinq sources. Chacun des **27 bundles** est rendu sous trois budgets
2000/8000/20000 : **81 rendus mesurés**, neuf par cellule. Les timings de rappel
sont partagés par les trois rendus d’un bundle, pas 81 rappels indépendants.
Le temps de rendu inclut calcul du JSON/cadrage/budget ; il exclut lecture
canonique, contrôles readiness et vérification des réponses du benchmark.

## Résultats

Les extraits totalisent toujours **95 caractères**, alors que le rendu JSON
complet et cadrage explicite contient 4653/6453/14453 caractères. Chaque texte
UTF-8 compte quatre octets de plus ici ; le budget porte sur des caractères
Unicode, pas les octets. Aucun compteur/tokenizer réel employé.

| Preuve première source | Budget | Rendu caractères | Sources retenues | Médiane rendu seul |
| --- | --- | --- | --- | --- |
| 200 | 2000 | 1351 | 1 | 0,241 ms |
| 200 | 8000 | 4653 | 5 | 0,072 ms |
| 200 | 20000 | 4653 | 5 | 0,070 ms |
| 2000 | 2000 | 1997 | 2 | 0,255 ms |
| 2000 | 8000 | 6453 | 5 | 0,073 ms |
| 2000 | 20000 | 6453 | 5 | 0,071 ms |
| 10000 | 2000 | 1997 | 2 | 0,279 ms |
| 10000 | 8000 | 3657 | 4 | 0,269 ms |
| 10000 | 20000 | 14453 | 5 | 0,081 ms |

Les rappels seuls ont des médianes de **2,966 / 3,014 / 3,033 ms** respectivement
par taille de preuve, sur huit objets et historique léger uniquement. Les
min/max du rendu et toutes les durées brutes sont conservés. Le rendu avec
omissions réencode des candidats, ce qui coûte plus qu’un rendu intégral qui
rentre d’emblée. Le choix conserve l’ordre des sources, pas le nombre maximal :
avec une preuve 200 et budget 2000, la première source tient et laisse une seule
source retenue ; avec une preuve 2000, elle est trop grosse et deux suivantes
plus petites tiennent. Aucun statut, preuve ou relation n’est tronqué pour gagner
une place. Le traitement se limite aux cinq éléments déjà sélectionnés.

## Contrôles et preuve

Chaque rendu exact est reparsé sans son cadrage ; tous les champs de chaque
source retenue sont comparés au bundle d’origine. Identités, revisions,
UNVERIFIED/MATCH, needs_review, provenance, preuves, budget total Unicode,
comptage des omissions et totaux d’extraits conformes. Empreintes de fichiers
avant/après requêtes/rendus identiques, huit objets par corpus revérifiés en
révision 1 et readiness vraie. Les corpus temporaires sont supprimés en fin de
mesure ; aucune donnée du dépôt actif ou sauvegarde touchée.

Substitution en mémoire du budget par un plafond trop grand : le vérificateur
refuse la réponse dépassant le budget réellement demandé. Outil/code core et
rapport/log hashés ; aucune modification métier. Cette preuve directe n’ajoute
pas de tests artificiels ni répétition de la suite core inchangée.

[Rapport brut](benchmarks/vm-2026-10-03/recall-payload.json),
[log](benchmarks/vm-2026-10-03/recall-payload.log) et
[manifeste](benchmarks/vm-2026-10-03/recall-payload-manifest.json).
[Contrat du rendu](RECALL-PAYLOAD.md).

## Limites

Petit corpus synthétique chaud sur tmpfs ; aucune qualité sur corpus réel,
latence disque physique, réseau, modèle, tokenizer, client externe ou prompt
additionnel mesurée. Trois requêtes sur un corpus chaud ne sont pas trois
corpus indépendants ; ces derniers sont explicitement au nombre de neuf.
Pas de seuil de production revendiqué ni de coupure électrique. Les mesures
volumiques 300/1000/3000 du rappel restent distinctes : voir
[VM-RECALL-2026-10-03.md](VM-RECALL-2026-10-03.md).
