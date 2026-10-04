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

## Revue Claude C2/C3 — reçue le 4 octobre 2026

Compte rendu 4a85b81, archive claude-fc44d09093464297a029747893a61d41.md,
SHA 494aa46d3c536126597e752bc9514713ded02829dbf695ec9be2f615728d5c9d vérifié.
Sur clone c0f1f53 : 1877 tests VM réussis, MCP exclus ; 34 ChatGPT verts,
trois répétitions ; rappel réel PASS, unchanged/references_exact vrais,
1,354 à 1,448 s par requête, couverture identique et corpus v1 inchangé.
Ces preuves sont reçues de Claude, pas des exécutions GPT sur VM.

Recette visuelle sur instance synthétique temporaire à 127.0.0.1:18767,
clone 2c2ff26, Chromium émulé. Dashboard actif non modifié. Mode texte
correct à 350x220/800x220 et retour normal sans reload ; mais 360x740/320x640
perdaient aussi toute navigation. Correctif CSS testé par Claude : mode texte
si hauteur <=260, ou largeur <=360 ET hauteur <=540. Téléphones portrait
retrouvent la navigation sans défilement horizontal ; petites fenêtres restent
texte seul. Patch exact intégré ici, 36 tests dashboard/sources/installateur
locaux verts ; pas de nouvelle mesure visuelle GPT ou téléphone physique.
Cibles tactiles 32 px en compact et vrai setpriv root restent non validés.

C3 reproduit F1a (référence d'un détail déplacée), F1 (substitution sans détail)
et F1b (extraction supprimée puis autre pilote) sur sources synthétiques.
Contrat d'engagement durable proposé, pas implémenté. Décisions toytoy transmises
par Claude : référence discordante = avertissement visible/non bloquant ;
manuscrit existant libre/sans engagement ; aucun commit-extraction implicite.


## Vérification 10d87ad et incident tmpfs — rapport Claude 5c88587

Suite complète sur clone VM isolé : **1898 réussis, MCP exclus**. Premier essai
invalide : 4 échecs/302 erreurs de création de dossiers, inodes /tmp épuisés,
pas une régression de code. Après retrait des propres basetemp de Claude,
relance verte ; dashboard/MCP sans authentification 401 et aucun défaut signalé
dans le journal du dashboard. Environ 565140 inodes utilisés (54 %) restent
selon son inventaire e9f8442 ; aucune suppression ancienne effectuée par GPT.
Ces résultats sont reçus de Claude, non exécutés par GPT sur la VM.
Les prochaines recettes doivent isoler leurs basetemp et nettoyer leur propre
corpus temporaire après conservation des logs, jamais purger /tmp globalement.

## F1/F1b et D-F1-1 — rapport Claude 4bef177

Clone VM isolé propre à 7cb1f9a, données synthétiques uniquement :
**1975 tests réussis, 15 MCP exclus**, aucun échec. 88 tests ciblés verts,
trois répétitions. La reprise séquentielle de deux attentes est validée ;
source neuve refusée pendant attente, anomalie distincte toujours bloquante,
engagement et committed_at conservés. Annexes intégrées sans changement métier.

Procédure manuelle de résidu testée : mort réelle pendant écriture, readiness
bloquée, copie privée hors memory/ vérifiée par empreinte, retrait du seul
résidu, audit prêt puis extraction explicite terminée. Aucune purge automatique.

Preuves rapportées par Claude, pas revérifiées VM par GPT. Journaux conservés
sous /tmp/eme-claude-20261004-OXyYeC/c7/. /tmp à 1 % d'inodes après essais.
/opt, services et corpus privés non touchés : validation du clone ≠ déploiement.
ext4/coupure électrique, boot réel, upload cloisonné, téléphone physique et
setpriv root restent non testés. Avancement global toujours gelé à 45 %.
