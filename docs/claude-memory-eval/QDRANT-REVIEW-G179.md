# Contre-revue Claude de l'adaptateur Qdrant G179 (G178, tâche 4)

Auteur : Claude. Date : 12/10/2026, Europe/Paris.
Code relu : `core/indexing/qdrant_index.py` et `tests/test_qdrant_index.py`, commit `4185430`, **sans modification**.

**Sondes** : `tests/claude_memory_eval/test_qdrant_probes.py`, avec Qdrant
local (`:memory:`) et un embedding de hachage synthétique.
- Un test vert confirme un bon comportement.
- Un `xfail(strict=True)` marque un écart : il deviendra une erreur de suite
  le jour où l'écart sera corrigé, ce qui obligera à le relire.
- **Non rejoué** contre le serveur 1.15.4 de la VM.

## Ce qui est solide

- La reconstruction par génération et bascule d'alias garde l'index servi
  intact quand le modèle échoue en cours de route (sonde verte). La
  génération ratée reste en place, comme le rapport G179 l'annonce.
- Les résultats ne portent **jamais** le texte (sonde verte), et chaque
  résultat porte `canonical_revalidation_required`.
- Chaque opération revérifie le descripteur (dimension et `embedding_id`).
  Les points sont recoupés avec leur identifiant UUIDv5, et toute écriture
  incrémentale invalide le digest **avant** d'écrire.
- **Q1, vérifié et non retenu** : si la collection servie disparaît, son
  alias disparaît aussi (en local). `create=False` refuse, et `create=True`
  reconstruit proprement. **À confirmer sur le vrai serveur.**

## Écarts (xfail strict)

| # | Écart | Gravité | Proposition |
| --- | --- | --- | --- |
| **Q4** | `text_sha256` en clair dans chaque résultat. Pour un texte privé **court**, l'empreinte se retrouve hors ligne à partir d'une liste de candidats. La sonde retrouve « le code du portail est 4831 » en moins d'une seconde parmi 10 000 essais. | **haute** : fuite d'un secret court vers quiconque voit les résultats ou le payload Qdrant | Remplacer par un **HMAC-SHA256** avec une clé par index, gardée **hors de Qdrant** (côté canonique, 0600). Ou ne publier que la révision, l'empreinte restant côté serveur. |
| **Q3** | Après une écriture incrémentale, `source_digest` vaut `None` (index périmé), mais `query()` sert des résultats **sans aucun signal**. Seul `status()` le dit. | moyenne | `query()` lit déjà le descripteur : ajouter `index_source_digest` (ou `index_stale: true`) dans `ranking` de chaque résultat. |
| **Q2** | Changer de modèle d'embedding sur le même alias est refusé à chaque opération, y compris `rebuild` : c'est correct. Mais **aucune migration explicite** n'existe pour un changement de modèle voulu. | moyenne (exploitation) | `rebuild(root, migrate_to=EmbeddingIdentity)` explicite : construire une génération avec le nouveau descripteur, puis basculer l'alias. Ou documenter la règle « nouveau modèle = nouvel alias + bascule côté configuration serveur ». |

## Liens avec la baseline (tâche 3)

- Le payload ne porte ni date, ni statut, ni relation « remplacé par ». Sur
  le corpus v1, la recherche lexicale classe déjà l'ancienne consigne
  « Il faut acheter la V100 » **avant** sa correction (question neg-1).
  Qdrant ne corrigera pas cela : le filtre canonique (dates, remplacements,
  suppressions, droits) doit s'appliquer **après** les candidats, comme
  G179 le prévoit.
- **Abstention** : le cosinus renvoie toujours `limit` résultats. Le
  problème « 0/4 abstention » de la baseline restera entier sans seuil
  **mesuré** sur un vrai modèle.
- Pour comparer avec la baseline : `evaluate(corpus, recall)` de
  `tests/claude_memory_eval/run_baseline.py`, avec une fonction de rappel
  qui interroge Qdrant puis relit le canonique. Même corpus, mêmes mesures.

## Non couvert par cette revue

- Plusieurs écrivains en parallèle (hors contrat : un seul écrivain
  coordonné, annoncé).
- Performances d'ingestion.
- Comportement du vrai serveur pour Q1.
- Découpage des archives longues : contrat des passages à venir de Codex.
