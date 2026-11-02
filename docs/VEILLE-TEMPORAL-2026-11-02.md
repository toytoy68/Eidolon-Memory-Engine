# Qualification temporelle issue de la veille — 2 novembre 2026

Base : `0691e68b452fb79c671ab10b9a6c054a67e6d4d3`, après la campagne FR100.
Branche : `codex/veille-temporal-20261102`. Aucun code de production modifié.

Le correctif Hindsight
[`7b46a07`](https://github.com/vectorize-io/hindsight/commit/7b46a07c82f997903230f0fb33deafe9dfd2e22b)
montre pourquoi un extrait « hier » doit garder la date de sa source. Sa date
d'événement et sa date de mention ne sont pas interchangeables. Ce correctif
est postérieur au tag v1.1.0 ; installer ce tag ne suffit pas à l'obtenir.

Huit nouveaux cas Eidolon dans `tests/test_veille_temporal_evidence.py` couvrent :
conservation des dates après réouverture/troncature/sérialisation à deux dates de
requête, absence de date source, deux occurrences de l'heure locale au passage à
l'heure d'hiver, contradictions, historique d'une source remplacée et retrait
d'un élément complet si le budget ne permet pas de garder ses métadonnées.

Résultats dans l'environnement isolé Python 3.12 : **8/8 nouveaux cas réussis**.
Suite ciblée élargie : **66 tests et 5 sous-tests réussis**, aucun ignoré, 2,15 s
(JUnit : 71 entrées, aucune erreur). qdrant-client 1.15.1, PyYAML 6.0.3, pytest
9.2.0 ; aucun Qdrant de production contacté. La suppression expérimentale du
champ temporel dans le résultat provoque deux échecs attendus ; mutation retirée.

Commande depuis ce dépôt, avec les dépendances installées :

```bash
python -m pytest -q -ra tests/test_veille_temporal_evidence.py \
  tests/test_contextual_recall.py tests/test_recall_payload.py \
  tests/test_memory_bridge.py tests/test_memory_bridge_freshness_g245.py \
  tests/test_bridge_recall_lock_g259.py
```

Ce résultat valide le transport et les règles déclarées, **pas** la résolution
automatique de « hier », la vérité d'une source ou la pertinence du classement.
`temporal.created_at` désigne la création de l'objet ; `observed_at` l'observation.
Le sens de `provenance.timestamp` dépend encore du producteur : `remember` y met
la date de la commande. Un import d'archive doit documenter séparément la date du
propos original ; il ne faut pas généraliser l'ancrage de cette fixture à tous les
imports. Aucun nouveau schéma temporel n'est activé par ces tests.

Autre lacune : le bridge HTTP courant accepte uniquement le mode opérationnel
et fixe `at` à l'heure serveur. `ContextualRecall` expose un mode historique en
Python, qui rend les enregistrements actuels avec leurs réserves ; il ne reconstruit
pas toutes leurs anciennes révisions. Une future API historique doit fixer la
portée, la date de référence, les droits et ce sens exact avant son activation.

Ces tests ne corrigent pas les erreurs de sélection de source observées sur
FR100. Les prochaines recettes doivent distinguer identité du document, sujet,
date du propos, date du fait, validité et contradiction. Le bilan transversal
est dans le dépôt `toytoy68/Eidolon`, branche `research/veille-open-source-2026-11-02`.
