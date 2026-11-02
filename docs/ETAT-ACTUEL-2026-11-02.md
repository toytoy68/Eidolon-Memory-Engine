# État vérifié — 2 novembre 2026

Auteur : Codex/GPT. Lot autorisé par toytoy : tâches de l'audit réalisables sans console.
Base : a5e2ab0a2d5be08e8f11b36af607b23407f57c28 ; branche de travail codex/audit-ci-20261102.

## Acquis et corrections

G294/G295 est intégré : le module tools/evaluation/run_memory_holdout.py existe.
L'échec CI 39842921560 portait sur une révision antérieure à cet ajout. Les filtres
CI omettaient tools/** ; corrigés avec services/**, deployment/** et entrées de
configuration de tests. Les PR vers refactor/architecture-v1 déclenchent désormais
les deux suites. La suite générale conserve un rapport JUnit.

## Preuves exécutées sur X399 / Memory-engine-tests

- Suite non-root, umask 077, Qdrant 1.15.4 jetable isolé : **3196 passed,
  7 skipped, 3 xfailed, 12 subtests**, 330,76 secondes.
- Les sept cas de montage ignorés ont ensuite été exécutés séparément sous root,
  dans des namespaces privés sur corpus synthétiques : **7 passed**, 1,92 seconde.
- Aucun endpoint Qdrant de production ni corpus personnel utilisé par ces suites.
- Les deux workflows modifiés sont relus avec un parseur YAML ; git diff --check passe.
- Journaux privés : ~/eidolon-validation/audit-20261102/{memory-tests.log,memory.xml,mount-tests.xml}.
- Ceci est une validation locale ; la validation GitHub du nouveau SHA reste distincte.

## Limites encore ouvertes

Les trois xfail concernent : nettoyage des générations après reconstruction échouée ;
ancienneté des écritures en attente d'index ; API de suppression/upsert de Qdrant
sans contrat de revue. Ils ne sont pas transformés en PASS.
Le lecteur en montage RO est déjà implémenté (G263/G265, read_only_storage=True) :
ne pas réimplémenter la proposition historique G262 comme si elle était absente.
Le déploiement sous compte système dédié et la recette applicative complète restent à faire.

## Suite et attribution des états

A05 validé localement, CI distante à constater. A08 : suites et montages validés,
recette de panne étendue à poursuivre. A06 pertinence sémantique, A07 corpus de
comparaison, A11 isolation applicative : ouverts. FTS5 #3 reste expérimental.
Les anciens TODO et messages sont conservés comme historique. Une demande opérateur
ou un résultat rapporté par un autre auteur n'est pas une exécution de ce lot.
