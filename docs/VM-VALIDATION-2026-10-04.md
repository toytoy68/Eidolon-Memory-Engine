# Validation VM du 4 octobre 2026 — rapport Claude Code

Compte rendu transmis par toytoy le 04/10. Exécution effectuée par Claude Code,
non par GPT. Les journaux sont conservés sur la VM dans
`/tmp/eme-claude-20261004-OXyYeC` ; GPT n’a pas accès à leur contenu et ne
revendique pas une vérification indépendante de ce rapport.

Commit testé : `9819d6bf1892884a5a3ac3cb1857fbfe06591088`, clone GitHub isolé
sous `/tmp/eme-claude-20261004-OXyYeC/repo`. Python 3.13.5 du venv de `/opt`,
exécution depuis le clone avec `nice -n 10` et dossiers de tests isolés.
Clone et checkout en service signalés propres après exécution.

| Contrôle | Résultat communiqué |
| --- | --- |
| Suite hors MCP | 1809 réussis en 47,61 s, aucun échec ou saut |
| Exclusion explicite | tests/test_collaboration_mcp.py : 15 tests non exécutés |
| Recette ciblée, neuf fichiers | 136 réussis en 3,38 s |
| Rappel ChatGPT réel, deux exécutions | PASS ; unchanged et references_exact vrais |
| Temps par requête | 1,298 à 1,381 s |
| Empreintes corpus réel avant/après | Identiques, contenu et métadonnées ; 1365 fichiers, 10 dossiers, trois verrous compris |
| memory/ du checkout /opt | Identique avant/après ; dix fichiers, compte seulement |
| Services actifs | Aucun modifié ni relancé |

Couverture lexicale : Eidolon et roman : cinq extraits 1/1 ; mémoire robot :
deux extraits 2/2 suivis de trois 1/2 ; Dans les bras : cinq extraits 3/3 ;
requête inexistante : aucun résultat. Aucun texte privé affiché ou conservé.
La pertinence sémantique n’est pas évaluée. Le temps total de chaque recette
n’a pas été mesuré ; les durées indiquées sont celles des requêtes.

## État opérationnel et limites

Le checkout actif `/opt/eidolon-memory-engine` et le tableau de bord restent
sur `88050bc`. Les nouvelles corrections sont testées dans le clone mais
ne sont pas encore déployées. La vue compacte et la visite mobile restent
à vérifier après mise à jour/reprise du dashboard, ou sur instance isolée.
Ollama est signalé inactif et rien n’écoute sur 11435 ; aucun appel réel au
modèle n’est validé par cette recette, aucune intervention sur Ollama effectuée.

Le rapport valide les tests de `9819d6b`, pas une relecture du code. Claude
propose ensuite de relire `b18dad0` (interruptions, concurrence, opérations
non terminées), `873487a` et `9819d6b`, sur clone sans modification du dépôt.
Cette revue reste à recevoir. F1 (engagement d’extraction) reste ouvert.
La suite exclut MCP ; ne pas la présenter comme la suite entière sans exclusion.

## Reprise

Conserver le dossier de validation tant que la revue est en cours. L’intégration
sur `/opt` se fait après contrôle Git, par pull ff-only ; les tests documentaires
n’exigent aucune réimportation du corpus. Mettre à jour le code ne relance pas
un processus Python existant : la reprise du dashboard est une étape distincte.
