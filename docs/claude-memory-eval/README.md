# Évaluation du rappel mémoire — corpus synthétique v1 et baseline lexicale (G178, tâches 2 et 3)

Auteur : Claude. Date : 12/10/2026, Europe/Paris. Demandé par Codex (G178), accepté par toytoy.

**Nature** :
- **rappel seulement**, sans génération ni modèle ;
- données **synthétiques**, inventées, aucun corpus privé ;
- exécution en conteneur, pas sur la VM.

## Corpus ([corpus-v1.json](corpus-v1.json))

- 30 documents courts et 27 questions.
- Les réponses attendues ont été **écrites et commitées avant toute
  exécution** (commit `7e541df`). Le test
  `tests/claude_memory_eval/test_corpus_and_runner.py` fige le corpus par son
  SHA-256 : changer une réponse attendue oblige à créer une v2.

| Catégorie | Questions | Ce qu'elle mesure |
| --- | ---: | --- |
| direct | 4 | Contrôle : la question reprend les mots du document |
| paraphrase | 5 | Mêmes idées, autres mots (« copie de sécurité des images » pour « sauvegarde des photos ») |
| negation | 3 | La source porte une négation : l'extrait doit la garder |
| corrected | 3 | Un fait et sa correction datée : la version récente doit passer devant |
| tech_vs_fiction | 2 | « NAS » technique contre le robot « Nas » d'une histoire |
| homonym | 4 | Mercure (planète, métal, dieu), deux personnes nommées Paul |
| condition | 2 | « si… » et « seulement si… » gardés dans l'extrait |
| absence | 4 | Aucune réponse dans le corpus : un bon moteur s'abstient |

## Résultats ([baseline-lexical-v1.json](baseline-lexical-v1.json))

Moteur : `ContextualRecall` avec ses réglages par défaut (5 résultats,
`lexical_passage_v1`). La colonne « avant A5-02 » rejoue le même banc sur
`f713623`, soit l'ancien découpage v2
([résultat](baseline-lexical-v1-passage-v2.json)).

| Mesure | Avec A5-02 (passage v3) | Avant A5-02 (v2) |
| --- | ---: | ---: |
| rappel@1 (23 questions avec réponse) | **0,783** | 0,739 |
| rappel@5 | 0,826 | 0,826 |
| Vérifications d'extrait (négation, condition, ordre) | **10/10** | 8/10 |
| Négation gardée dans l'extrait | **3/3** | 1/3 |
| Abstention sur les 4 questions sans réponse | **0/4** | 0/4 |
| Latence médiane / maximale par question | 8,5 / 32 ms | — |

## Lecture honnête

1. **A5-02 corrigé, effet mesuré** : la négation passe de 1/3 à 3/3 dans
   l'extrait. Le gain en rappel@1 (+0,04) vient du contexte ajouté, qui
   apporte des mots ; il ne dit rien de la compréhension.
2. **Paraphrase : 1/5.** La recherche lexicale ne trouve pas une idée dite
   avec d'autres mots. C'est la limite attendue que des embeddings et Qdrant
   devront mesurer **sur ce même corpus**.
3. **Aucune abstention (0/4).** Le moteur renvoie toujours 5 résultats, même
   sans réponse, sur de simples mots partagés (« port », « serveur »,
   « Paul »). Un consommateur ne doit pas lire « résultat présent » comme
   « réponse trouvée ». Il faudrait un seuil ou un signal de couverture,
   **mesuré** et non choisi au hasard.
4. **Faits corrigés : 3/3 en tête, mais par chance lexicale.**
   - L'ancienne version suit **toujours** en 2e position : le moteur ne
     connaît pas les dates.
   - **Cas dangereux (neg-1)** : à « Faut-il acheter la V100 cette
     semaine ? », l'ancienne consigne (« Il faut acheter… ») sort **avant**
     sa correction (« ne pas acheter… »).
   - Une relation de remplacement explicite, ou un tri tenant compte de la
     date, est nécessaire avant tout usage décisionnel.
5. Homonymes, technique contre fiction et conditions : réussis ici, sur des
   phrases courtes et explicites. Ce n'est **pas** une preuve sur un vrai
   corpus.

## Rejouer

```sh
python3 tests/claude_memory_eval/run_baseline.py          # écrit baseline-lexical-v1.json
python3 -m pytest -q tests/claude_memory_eval
```

Pour comparer Qdrant ou un autre moteur : garder `corpus-v1.json` et
`evaluate()`, remplacer seulement la fonction de rappel passée au banc.
