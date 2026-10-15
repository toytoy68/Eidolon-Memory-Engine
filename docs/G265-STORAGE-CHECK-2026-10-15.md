# G265 — Diagnostic du stockage canonique avant démarrage

Auteur : Codex/GPT, 15 octobre 2026. Base Memory `a25a41da815cac2fea908d5336633a205ac7946f`, code readonly G263 `86950c8`.

## Commande explicite

Depuis le code et son environnement Python préparés, sur une arborescence de recette déjà initialisée :

```bash
python -B -m services.memory_bridge --root /chemin/recette --check-storage
```

La commande produit une seule ligne JSON `eidolon-memory-storage-check/1`, puis termine. Elle ne demande pas de jeton, ne charge pas le reranker et n'ouvre pas de serveur ou connexion réseau. Elle ne crée ni répertoire ni verrou. Elle impose le mode G263 de verrous préexistants ouverts en lecture seule sur Linux local. `--read-only-storage` est redondant mais accepté ; `--port` et `--reranker-cache` sont refusés dans ce mode. Les erreurs de syntaxe CLI restent les erreurs argparse (stderr, code 2), sans rapport JSON.

Le diagnostic ne configure pas le prochain lancement. Un service qui doit utiliser le mode readonly doit toujours recevoir explicitement `--read-only-storage` lors de son propre démarrage. Le mode serveur conserve le port par défaut 18765, les vérifications du jeton et son comportement de chargement des modèles.

## Contrat du résultat

| État | Code de sortie | Sens |
| --- | --- | --- |
| READY | 0 | Arborescence, acquisition des verrous existants et audit readiness réussis à cet instant |
| BLOCKED | 2 | L'audit canonique remonte un état nécessitant revue/reprise ; aucune réparation exécutée |
| BUSY | 3 | Un autre détenteur occupe persistent ou threads ; aucune attente sur flock |
| UNAVAILABLE | 4 | Prérequis de stockage manquant/invalide, accès impossible ou erreur d'entrée/sortie remontée |
| UNSUPPORTED | 5 | Mode readonly non supporté par la plateforme |
| ERROR | 6 | Erreur inattendue ; aucun détail d'exception divulgué |

Le rapport contient `schema`, `scope: canonical_storage_only`, `state`, `read_only_locks: true`, `issues` et `warnings`. Ces deux compteurs sont null tant que l'audit ne s'est pas achevé. Aucun chemin, identifiant de mémoire/opération, contenu, jeton ni texte d'exception n'est renvoyé. Des problèmes d'accès que les auditeurs internes convertissent déjà en problèmes de readiness apparaissent dans BLOCKED ; UNAVAILABLE couvre les erreurs remontées jusqu'au diagnostic. Un avertissement seul ne transforme pas automatiquement READY en BLOCKED : la règle de l'audit existant est conservée.

## Cohérence et limites

`ContextualRecall.storage_snapshot()` centralise l'ordre des verrous : persistent puis threads si présent. Le rappel utilise le même contexte que le préflight G263 et G265. G265 reprend les verrous après construction et les conserve pendant **tout** l'audit ; la vérification de construction seule ne suffit pas. Chaque acquisition G265 est non bloquante. Une erreur sur le second verrou libère le premier ; les erreurs de lecture libèrent les deux.

La commande est une inspection ponctuelle, pas une réservation durable ni un feu vert de déploiement. Elle ne valide pas le compte de service attendu, le montage readonly effectif, le cache/modèle, Qdrant, le réseau ni la configuration du service. Ces contrôles restent distincts. Les limites Linux local et coopération des écrivains de G263 restent applicables.

**Le scan readiness n'a pas de budget global de temps ou de taille de corpus dans ce lot.** Non bloquant désigne l'acquisition des verrous, pas une durée garantie pour l'inspection. Exécuter cette commande à la demande sur le corpus de recette ; ne pas la transformer en sonde de santé HTTP récurrente. Pendant le scan, les écrivains coopératifs attendent. Aucune boucle, reprise automatique, installation de compte, migration ou activation systemd n'est introduite.

## Vérification locale

22 nouveaux tests `tests/test_storage_check_g265.py`. CLI réellement lancée dans des processus Python indépendants sans jeton : READY, BUSY sur chacun des deux verrous puis reprise, BLOCKED sur journal interrompu et Markdown corrompu, UNAVAILABLE sur prérequis manquants ou lien. Contrôle de l'exclusion interprocessus pendant le scan, des empreintes inchangées, de la confidentialité, de la libération sur erreur et d'un verrou perdu entre construction et scan. Refus de plateforme simulé séparément ; dépendances modèle/réseau instrumentées pour interdire leur utilisation. Refus EROFS injecté sur ouvertures en écriture et mkdir. Le comportement serveur exige encore un jeton valide.

Régression ciblée, `-W error` : 139 réussis, 1 ignoré (test G263 de permissions sous UID ordinaire dans ce runtime root), 5 sous-tests. Modules : G265, G263, persistence_atomic/leaf_g249, contextual_recall, settled_read_phase, threads/test_serialization, bridge/limits/freshness/write_deadline, verrou G259 et sondes Claude G259. Qualification complète CI à consigner après publication. Pas de recette VM ou modèle réel revendiquée.
