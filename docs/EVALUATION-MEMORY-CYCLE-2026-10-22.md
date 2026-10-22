# Cycle d'évaluation Memory Engine — 22 octobre 2026

**Périmètre :** VM110, code `a707f78`, Qdrant bêta et Memory Bridge, tests isolés et rappels réels en lecture seule. **Aucune correction de production ni redémarrage.** Les logs complets sont conservés localement dans `/home/toytoy/eidolon-validation/g288/memory-cycle-20261022.log` et `/home/toytoy/eidolon-beta-memory/veille-eval-20261022.json` (ce dernier ne contient que des identifiants/métriques).

## Résultats

- Suite complète sous `umask 077`, Python venv G288, pytest 9.1.1 : **3158 passed, 26 skipped, 3 xfailed, 12 subtests passed**, durée **75.04 s**, sortie 0.
- Tests ciblés remember/bridge/Qdrant : **11 passed, 4 skipped** ; autre lot erreurs remember/Qdrant : **5 passed, 9 skipped**. Ces comptes chevauchent la suite complète, ne pas les additionner.
- 15 requêtes de recherche sur les quinze fiches techniques nouvellement intégrées : **15/15 au rang 1**, **15/15 dans les cinq premiers**, aucune erreur HTTP, latence médiane **3,825 s**. Requêtes contenant des noms explicites, donc non représentatives de paraphrases difficiles. Les SHA-256 des quinze fichiers canoniques sont inchangés avant/après.
- Deux requêtes sans réponse attendue (terme absurde et GPU fictif en 2035) renvoient chacune **5 candidats** : la sélection des voisins n'est pas une preuve de réponse. `core/retrieval/indexed.py` indique explicitement qu'aucun seuil implicite d'abstention n'est appliqué. **Risque d'interprétation côté Core**, pas une corruption ou régression prouvée de Qdrant.
- Premier essai ciblé avec umask permissif : **8 passed, 1 failed** avant arrêt, refus du lecteur de snapshot sur un fichier de test group-writable. Reprise avec `umask 077` : **11 passed, 4 skipped**. Cause environnementale cohérente avec `core/runtime_json.py` ; aucune correction applicative justifiée par ce seul résultat.

## Anomalies / améliorations candidates

**R1 — P1 : pertinence et abstention explicite.** Préparer un jeu de validation indépendant avec questions connues, paraphrases, négatives et contradictoires, annoté par réponse attendue et provenance. Mesurer précision@1/5, faux positifs, rappel, couverture, latence. Calibrer une décision « preuve insuffisante » distincte du classement des candidats ; ne pas définir un seuil de score brut sans calibration ni transformer un résultat similaire en fait confirmé. Tests de contrat Core↔Memory avant modification de l'API.

**R2 — P1 : fiabilité du banc.** Fixer `umask 077` dans les lanceurs de tests isolés; vérifier et documenter les permissions de fichiers et les environnements Python épinglés. Ne pas assouplir les protections du lecteur de snapshots.

**R3 — P2 : cas exclus.** Exécuter séparément les 26 scénarios ignorés, notamment Qdrant jetable et isolation par namespaces, dans des environnements explicitement autorisés. Ne pas les déclarer PASS.

**R4 — P2 : performance.** Les 3,825 s médians comprennent HTTP, embedding, index, récupération canonique et éventuel reranking. Instrumenter chaque étape et comparer plusieurs charges avant toute optimisation. Ne pas extrapoler ce chiffre à un benchmark de débit.

**R5 — P2 : robustesse.** Tester sur copies isolées panne Qdrant, perte du tunnel d'embeddings, reprise, index périmé, permissions, concurrence et absence de mutation du corpus. Aucun arrêt volontaire de services de production dans cette campagne.

## Décision

**Cycle de diagnostic validé ; pas de patch fonctionnel déployé.** Le moteur a passé ses tests et les 15 rappels ciblés. Le principal problème d'usage observé est la possible confusion entre « candidats retrouvés » et « réponse démontrée ». Un changement de logique de pertinence doit être testé sur un jeu négatif et paraphrasé indépendant avant revue/merge. Priorité bêta Core/Memory inchangée.
