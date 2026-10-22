# G294 — Intégration du holdout contradictoire Memory (22 octobre 2026)

## Modifications
Le patch 0068 de Claude est intégré sur `refactor/architecture-v1` :
- `tests/evaluation/memory-holdout-g294.json` : 12 questions négatives proches et 8 paraphrases sans mot-clé, annotées avant exécution.
- `tools/evaluation/run_memory_holdout.py` : lecture seule sur le pont local, score et provenance des candidats, sans décision automatique d'abstention.
- `tests/test_memory_holdout_g294.py` : 6 tests de contrat et de notation.

## Validation VM110
Suite complète `pytest -q tests/` avec `umask 077` et Qdrant 1.15.4 jetable : **3196 passed, 7 skipped, 3 xfailed, 12 subtests passed en 159,94 s**, code de sortie 0.

Holdout réel sur Qdrant sémantique VM110 : **20/20 appels sans erreur**, médiane **4,737 s**.
- Négatives proches : **8/12** renvoient le document piège en rang 1 et **11/12** dans le top 5; 12/12 renvoient des candidats. Scores de premier résultat : 0,319–0,771.
- Paraphrases sans mot-clé : **6/8** retrouvent la fiche attendue en rang 1 et **7/8** dans le top 5; scores 0,422–0,671.

**Interprétation** : le document piège est authentique mais n'apporte pas nécessairement la réponse demandée. Ce résultat mesure la récupération, pas une hallucination de Core. Le chevauchement des scores interdit de conclure à un seuil global de vérité.

Logs privés : `/home/toytoy/eidolon-validation/g294/memory-full.log`, `memory-holdout.json`, `memory-holdout.log`.

## Suites
Les 20 questions restent un holdout de référence pour les futurs changements de classement. Une amélioration de la suffisance de preuve doit être mesurée **sur les réponses réellement générées**, avec un validateur distinct et contrôle de l'entité/du benchmark/de l'année. Ne pas modifier les sources canoniques ni le modèle d'embeddings pour satisfaire les attentes du test.
