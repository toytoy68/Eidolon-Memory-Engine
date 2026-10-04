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

Au moment de la première recette, le checkout actif était `88050bc` ;
l’état courant est donné dans la reprise ci-dessous. La version chargée du
processus ancien n’a pas été établie. Les nouvelles corrections sont testées dans le clone mais
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


## Validation directe de toytoy sur /opt — 09 h 38

Sortie terminal transmise par toytoy : pull ff-only de 88050bc vers 9819d6b
sur `/opt/eidolon-memory-engine`, puis suite **entière : 1824 tests réussis
en 44,25 s**, aucune exclusion ni échec indiqué. Les 15 tests MCP sont inclus.
Cette preuve complète le rapport Claude (1809 + 15 = 1824).

Rappel sur `/home/toytoy/eidolon-corpus-gpt-test` : **PASS**, unchanged et
references_exact vrais ; pertinence sémantique non évaluée. Eidolon : 1,327 s,
roman : 1,344 s, mémoire robot : 1,328 s, Dans les bras : 1,376 s,
requête inexistante : 1,290 s. Couverture identique au rapport Claude.

Le code du checkout /opt est donc à jour sur 9819d6b. Aucune preuve de
redémarrage du processus dashboard n’est fournie : sa reprise et le rendu
compact restent à vérifier. Les journaux VM ne sont pas directement accessibles
à GPT ; cette validation repose sur la sortie terminal fournie par toytoy.


## Reprise et service — état reçu à 10 h 35

/opt sur fc675a4 depuis 09 h 52. Dashboard relancé, puis installé en service
systemd eidolon-dashboard à 10 h 18, sous toytoy ; token protégé dans /etc,
journal applicatif dans /home/toytoy/eidolon-dashboard.log. Démarrage au boot
configuré, restart et reprise après SIGKILL vérifiés (401/200), reboot non testé.
MCP/Cloudflare/Ollama non modifiés ; upload sous cloisonnement non testé.
La capture toytoy de 09 h 47 valide les deux jauges compactes côte à côte ;
elle ne valide pas le mode texte fc675a4 ni toutes les tailles mobiles.

Revue Claude reçue au commit ed56415 : accord sur b18dad0/873487a/9819d6b,
73 tests de revue rapportés, neuf cas nouveaux répétés dix fois. Les tests
originaux de 873487a et b18dad0 sont rouges comportementalement sur leurs
parents ; D10 a un cas comportemental rouge et trois erreurs d’absence de
module/attribut. Les limites v1 révisée, normalisation, coût sont conservées.
Ces constats sont reçus, non réexécutés par GPT sur la VM.

## Suite complète VM — rapport toytoy du 4 octobre 2026 à 16 h 59

Checkout /opt/eidolon-memory-engine propre avant pull, fast-forward
42831d7 → d7426c8. Commande .venv/bin/python -m pytest -q :
**1873 réussis en 46,15 s**, sans exclusion ou test sauté signalé.
Résultat fourni par toytoy, non exécuté indépendamment par GPT sur la VM.
Les cinq cas Manager exclus ici sont donc couverts par cette suite VM.
Ce résultat ne valide pas le rendu navigateur, le reboot, le vrai repli root
ou un benchmark de performance VM ; les outils synthétiques passent leurs tests.
Aucun restart de dashboard, import ou migration demandé pour cette mise à jour.
Estimation globale gelée à 45 %.
