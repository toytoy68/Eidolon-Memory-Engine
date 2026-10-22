# G290 — Paraphrases, exploration de calibration et compatibilité générale

Date : 22 octobre 2026. Périmètre : tests non destructifs VM110, puis contrats Core VM100. Aucun seuil de production déployé.

## Mesures sur l'index réel

- 15 questions **reformulées**, sans reprendre directement les titres complets : 15/15 retrouvent l'identité attendue au rang 1. Ce petit jeu est dérivé des mêmes quinze fiches : il n'est pas indépendant des connaissances évaluées.
- Trois questions sans réponse attendue retournent néanmoins des candidats. Ce résultat est attendu d'un moteur de recherche de voisins, mais **ne doit pas devenir une réponse factuelle non sourcée**.
- Scores du premier résultat : positifs de **0,4809934 à 0,7676452** ; négatifs de **0,33592412 à 0,3920407**. La médiane et les intervalles ne sont pas des garanties hors échantillon.
- Milieu expérimental de séparation : **0,43651705**. Ce chiffre **n'est pas un seuil validé** et ne doit pas être branché dans le rappel Core/Memory. Le score est spécifique à ce modèle, à cet index et à ce corpus.

## Modifications

- `tools/evaluation/calibration.py` : analyse des scores positifs/négatifs annotés, validation stricte, résultat explicitement `deployment_approved=false`, `independent_validation=false`, `score_is_proof=false`.
- `tests/test_calibration_g290.py` : six tests couvrant séparation, chevauchement et entrées malformées. Aucun changement de l'API de rappel ni des données canoniques.

## Test général et compatibilité

- Memory Engine complet avec Qdrant 1.15.4 jetable, `umask 077` : **3189 passed, 7 skipped, 3 xfailed, 12 subtests passed**, durée **113.44 s**, code retour 0. Journal `/home/toytoy/eidolon-validation/g288/memory-g290-full.log`.
- Contrats Core ↔ Memory ciblés sur VM100 : **37 passed, 8 skipped, 6 subtests passed**. Les skips ne sont pas des validations.
- Aucun changement de schéma JSON/HTTP : compatibilité descendante préservée par conception. Les scénarios Windows/PC et les pannes du réseau réel restent hors de ce lot.

## Décision

Le diagnostic des rappels positifs est encourageant et les tests logiciels ne montrent pas de régression. **La calibration d'une abstention automatique reste ouverte** : exiger un corpus de validation indépendant, davantage de négatifs proches et des cas contradictoires, avec critères d'acceptation sur les faux refus et faux accords. Ne pas confondre similarité vectorielle, preuve suffisante et vérité.
