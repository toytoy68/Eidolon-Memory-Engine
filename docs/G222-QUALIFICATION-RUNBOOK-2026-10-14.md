# G222 — Reprise de qualification Core / Memory

Date : 14 octobre 2026. Préparé hors VM. **Ne pas exécuter contre le corpus réel ni la production.**

## Gel des révisions

- Consigner le SHA de Core et Memory avant toute recette.
- Vérifier qu'aucun changement local non enregistré n'existe.
- Exécuter dans des copies jetables, avec variables de racine Memory dirigées vers un répertoire temporaire privé.
- Conserver stdout/stderr, durée, environnement Python, dépendances, résultats et empreintes.
- Ne pas comparer les résultats d'une ancienne révision aux nouveaux commits comme s'il s'agissait de la même preuve.

## Ordre d'exécution

1. `python -m compileall -q core tests` et équivalent Core.
2. Tests ciblés : `test_worker_preflight.py`, `test_worker_prepare.py`, `test_worker_status.py`, `test_reconcile_preview.py`, `test_passages.py`.
3. Migration/journal : `test_change_journal.py`, `test_change_journal_security.py`, `test_journal_migration.py`, `test_journal_migration_sequence.py`, `test_journal_terminal.py`.
4. Core : `test_web_budget.py`, puis tests de dialogue, Web W1 et I1.
5. Suites complètes séparées Core et Memory ; tests Qdrant sur serveur jetable explicitement isolé.
6. Seulement après : 12 scénarios B01–B12 de la recette intégrée Core ↔ Memory ↔ PC.

## Critères bloquants

- Zéro test en échec inattendu. Tout `xfail` ou `skip` doit être justifié.
- Aucune mutation de la mémoire canonique réelle.
- Une suppression Qdrant n'est jamais autorisée par un simple score ou une absence de lecture.
- Un appel modèle, une réponse Web ou un SOUL ne confère aucun droit d'exécution.
- Un résultat `INDEX_CURRENT` ne vaut pas preuve de cohérence tant que la télémétrie réelle n'est pas raccordée.
- Toute panne de connexion ou de confirmation conserve un état incertain ; pas de rejeu aveugle.

## Conditions d'arrêt

Arrêter immédiatement la recette en cas de données réelles modifiées, service de production impacté, configuration inconnue, permissions excessives, corpus absent, sauvegarde non vérifiée ou révision Git inattendue.

## Validation attendue

Tableau final par SHA : total PASS/FAIL/XFAIL/SKIP, durée, 19 scénarios worker, 12 scénarios bêta, latence mémoire, latence du premier token, comportement dégradé et résultat de restauration. Pas de fusion main sans accord explicite.
