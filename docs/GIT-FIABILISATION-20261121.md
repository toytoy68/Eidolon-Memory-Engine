# Fiabilisation Git — 21 novembre 2026

Eidolon Memory Engine — Eidolon Core Technologies (ECT)

## Demande et constat
Toytoy signale des erreurs Git récurrentes et demande leur résolution. Le pont NAS répond ready=false avec un message générique ; aucun stderr ni checkout de service n'est exposé. L'accès SSH NAS depuis X399 n'a pas de clé hôte connue ; aucune vérification SSH désactivée. GitHub direct fonctionne. La cause exacte de l'incident NAS reste non établie.

## Défauts reproduits et corrigés
1. Double récupération : fetch puis pull récupérait une seconde fois. Un push concurrent entre les deux faisait avancer HEAD puis échouer le contrôle du premier SHA. Test rouge sur vrai remote bare avant correction. Une seule récupération suivie d'une avance rapide vers son SHA fixe élimine cette course. La lecture indique le commit de son instantané ; elle ne prétend pas figer le serveur distant.
2. Tous les sous-processus Git échouaient sous une même erreur. Test rouge avant correction. Diagnostic borné par opération/catégorie/code de retour, audit local sans stderr ni credential ; aucune chaîne externe renvoyée.
3. Régressions opérationnelles : vrai index.lock préservé, arbres sales et divergences toujours refusés, push concurrent conservant le commit local et le commit distant. Aucun reset, nettoyage, rebase, push forcé, désactivation TLS/SSH ou relance automatique de publication.

## État du déploiement
Correctif préparé et testé sur X399 dans un worktree isolé de Memory. Code du pont conservé distinct de ses messages. Le NAS n'est pas annoncé réparé : conteneur/service et checkout doivent être identifiés, erreur réelle relevée, puis module déployé avec sauvegarde. Le critère final reste le succès des outils du pont eux-mêmes, avec commit/hashes cohérents.

Le manuel NAS a été actualisé par écriture conditionnelle et relecture : version 1.1, protocole P-009 Git. SHA256 : 1a7fb9b3e91060404379679afb58831c97abfb46b54a3d22b617015ffb9828fc. Il impose des checkouts distincts, un instantané de synchronisation unique, la conservation des contributions et une vérification par le service qui échouait.

## Autres travaux de la même session
Maintenance Memory rétablie et correctif minimal déployé, index conservé (205 points), zéro unité en échec. Défaut réel d'export Store/outbox Darme corrigé ; chaîne de refus signée et backend text.stats isolé testés. Core #17, #18 et #19, Memory #7 intégrés. Core #19 CI verte, merge 860a33e2ccbc63197424b8b21876d1027c565440. Détail : [rapport Core](https://github.com/toytoy68/Eidolon-Bootstrap-Framework/tree/feat/eidolon-core-v0.1/eidolon-core/docs/studies/2026-11-21-maintenance-darme).

## Validation
Deux tests rouges avant correctif ; 62 tests ciblés Git/MCP/déploiement réussis, avec clones et remote bare réels. Résultat de la suite complète et hashes dans le fichier de validation associé. Aucune validation NAS inventée ; X399 conservée allumée.

Suite complète exécutée : **3 250 réussis, 26 ignorés, 2 échecs attendus, 12 sous-tests réussis**, 151,96 s. Les ignorés sont les montages privilégiés et le serveur Qdrant jetable, sans lien avec le code Git modifié ; les échecs attendus Memory historiques restent ouverts. Résultats et SHA : GIT-FIABILISATION-20261121.json.
