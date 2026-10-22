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

## Contre-vérification finale Core (ajout après exécution)

- Suite complète Core `tests/` sur VM100, `umask 022` : **2283 passed, 43 skipped, 1 warning, 1328 subtests passed en 214.53 s**, sortie 0. Journal `/home/toytoy/eidolon-validation/g288/core-g290-final.log`.
- Un premier essai Core sous `umask 077` avait échoué sur **trois tests dépendant explicitement des permissions des fichiers créés** (signature, inventaire de copies, export média). Ces trois tests repassent sous `umask 022` et la suite complète passe. Ce sont des hypothèses d'environnement de test, pas une incompatibilité démontrée entre Core et Memory. L'écart de politique `umask` entre suites doit être documenté dans les lanceurs de validation; **ne pas affaiblir les contrôles de permissions en production**.
- Une collecte `pytest` sans chemin ciblé sur Core inclut deux anciens scripts `docs/validation/.../test_apt_*.py` attendant un argument externe, et échoue dès la collecte (`FileNotFoundError: '-q'`). Le périmètre standard doit être `tests/` ; ces scripts historiques ne sont pas des tests pytest autonomes.
- Les 43 skips Core et les 7 skips Memory restent des cas non validés, pas des PASS. Aucun échec inattendu dans les deux suites finales avec leurs prérequis appropriés.
