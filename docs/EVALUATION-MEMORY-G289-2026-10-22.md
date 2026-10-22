# G289 — Cycle de robustesse et qualification du rappel — 22/10/2026

## Livraisons

- Outil d'évaluation **observationnel** `tools/evaluation/relevance_audit.py` : sépare les questions avec identité attendue des questions sans réponse, compte rang 1/top 5 et faux candidats sur les négatives, valide strictement le schéma et ne prétend jamais avoir établi la vérité ni calibré un seuil. Aucun appel réseau ni mutation canonique.
- Six tests unitaires `tests/test_relevance_audit_g289.py` : positifs, négatifs, absence de confusion entre présence de candidats et réponse, refus des entrées mal formées.
- Reprise des tests Qdrant réels sur serveur **jetable** avec binaire déjà installé : 13 tests rappel/maintenance + 6 tests de récupération après panne, tous PASS ; le service Qdrant bêta n'a pas été arrêté.
- Relecture des 15 fiches : 15/15 rang 1 sur des questions contenant le nom du sujet ; deux requêtes négatives retournent des candidats sans preuve d'une réponse. L'outil G289 classe ce comportement séparément, sans inventer de seuil de confiance.

## Contre-validation

Suite complète avec `umask 077`, venv G288, `EIDOLON_TEST_QDRANT_BINARY` pointant sur le binaire Qdrant 1.15.4 installé : **3183 passed, 7 skipped, 3 xfailed, 12 subtests passed en 113.53 s** ; sortie 0. Les 7 skips restants ne sont pas déclarés validés. Journal local : `/home/toytoy/eidolon-validation/g288/memory-g289-full.log`.

## Conclusion et limites

- Les scénarios de Qdrant jetable et de reprise après panne testés passent. La régression liée à `umask` était un problème d'environnement de test, pas une raison d'affaiblir la sécurité.
- **La qualité de réponse à des questions absentes reste non qualifiée** : une liste de candidats ne constitue pas une réponse, même si la recherche est exacte. L'outil de diagnostic G289 ne change volontairement pas le contrat `ContextualRecall` ni le comportement de Core.
- Les questions paraphrasées, contradictoires et ambiguës doivent être annotées par un évaluateur indépendant avant de calibrer une abstention automatique. Un seuil arbitraire sur les scores Qdrant serait un risque de faux négatifs.
- Pas de modification des services, du corpus canonique ou de l'index de production. Ne pas confondre validation de code et bêta complète Core ↔ Memory ↔ PC.
