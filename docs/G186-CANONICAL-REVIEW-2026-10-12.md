# G186 — Corrections de la contre-revue Memory de Claude

Auteur correctifs : Codex/GPT. Auteur sondes initiales : Claude.
Date : 12/10/2026, Europe/Paris.
Base Memory : `283912ddacdbdb95a06136b3b98f03a9fc8971d4` (inclut les idées
open-source ajoutées à EIDOLON-GLOBAL-CONCEPTS, intégralement préservées).
Sondes : patch 0005 publié par Claude dans Core
`6135fb8f688ec1f48486ea72a9ca934b842521df`, commit source déclaré
`36d266352f8363be9048eec5d7f633138aa3133b`.

## Reproduction avant correction

Le patch original a été appliqué avant de modifier le code :

```text
6 passed, 4 xfailed in 0.78s
```

Les quatre xfail stricts P1–P4 sont reproduits. Après les correctifs, les quatre
sondes sont XPASS(strict), comme prévu pour signaler leur résolution. Une sonde
positive attendait explicitement la négation tronquée ; son attente est adaptée
au contrat renforcé P3 (négation conservée), ainsi que l'ancienne sonde Codex.
Les quatre marqueurs xfail sont ensuite retirés : leurs assertions sont conservées.
Le fichier original reste dans le commit d'import qui précède les correctifs,
et le patch source de Claude est inchangé dans Core. Le corpus d'évaluation
figé et ses réponses attendues ne sont pas modifiés.

## Résolutions

| Écart | Correction | Limite explicite |
| --- | --- | --- |
| P1 — référence hors du texte interrompt tout le rappel | Vérification des positions contre le canonique ; exclusion INDEX_PASSAGE_UNRESOLVED ; les candidats suivants restent examinés | Une structure de lot/identifiant/score/révision invalide continue à faire échouer le lot entier |
| P2 — archive sans référence sémantique perdue silencieusement | Exclusion INDEX_PASSAGE_MISSING, même en présence de mots communs ; aucun remplacement lexical implicite | L'identifiant d'une archive seul ne localise pas le passage pertinent |
| P3 — négation juste avant l'extrait omise malgré un budget suffisant | Extension au début de la phrase quand tout l'extrait sélectionné et ce contexte tiennent ; offsets canoniques conservés | Si le budget ne le permet pas, contexte partiel et nombre de marqueurs omis restent explicites |
| P4 — découpage entre lettre et accent combiné | Frontières déplacées avant la base et ses marques Unicode Mn/Mc/Me, y compris le chevauchement | Graphemes emoji ZWJ/drapeaux non garantis ; séquence de marques plus longue que le budget refusée explicitement |

La déduplication intervient après l'acceptation d'un candidat : une mauvaise
référence ne masque plus un passage valide ultérieur de la même information.
Les exclusions comptent les candidats refusés (des références distinctes du
même document peuvent donc contribuer plusieurs fois). Une information valide
reste retournée au plus une fois ; fusion de plusieurs passages non implémentée.

Politiques versionnées : `chatgpt-archive-chunks-v2` et
`chatgpt-indexed-passage-v2`. Le banc sémantique inclut la politique de découpage
dans son embedding_id et les deux versions dans ses résultats. Aucun index
existant n'est migré silencieusement ; reconstruire pour adopter le découpage v2.
Le contenu des chunks reste verbatim, offsets compris : aucune normalisation
du texte ni interprétation de vérité. Les filtres canoniques restent en vigueur.

## Vérification exécutée

Environnement Linux de développement, Python 3.12.14, pytest 9.1.1, corpus
fictifs. Le client Qdrant, les modèles et les VM ne sont pas utilisés ici.

```sh
python -m pytest tests/claude_memory_eval/test_canonical_probes.py \
  tests/test_canonical_passage_recovery.py tests/test_archive_chunks.py \
  tests/test_indexed_recall.py tests/test_contextual_recall.py \
  tests/test_chatgpt_passages.py tests/test_context_assembly.py \
  tests/test_passage_g180.py tests/test_recall_payload.py tests/test_lexical_ranking.py -q
```

```text
185 passed in 1.68s
```

Ces tests incluent les 12 000 cas de frontière A5-02 de Claude, les quatre
régressions converties en tests ordinaires, 18 cas supplémentaires Codex,
les budgets/extraits/payloads, le classement lexical et les filtres canoniques.
Compilation Python du banc sémantique vérifiée, sans l'exécuter.

Pas de suite globale, de recette serveur Qdrant ni de gain sémantique chiffré
revendiqué pour ce lot. Les journaux G182 déjà lancés sur VM restent à lire à
la reprise MCP avant toute relance. Aucun service ou corpus réel modifié.
Contre-revue des corrections demandée à Claude dans G186.
