# G230 — Reprise durable journal / index, 14 octobre 2026

Auteur : Codex/GPT. Base Memory : `fb82360b961b05b26370ff274905b6fca95a6135`.
Suite autorisée par toytoy à 19 h 55 Europe/Paris. Branche de développement uniquement.

## Qualification du code publié

Commit testé : `180f3a72064636964e718e2d81e88e198aeac01f`.

| Validation | Résultat observé |
| --- | --- |
| [Suite Memory complète](https://github.com/toytoy68/Eidolon-Memory-Engine/actions/runs/38611998863) | **2353 tests et 12 sous-tests réussis**, 258,42 s |
| Contrat du worker expérimental, même workflow | **19 réussis**, 1,84 s ; contrat distinct du nouveau consommateur |
| [Qdrant et worker ciblés](https://github.com/toytoy68/Eidolon-Memory-Engine/actions/runs/38611998817) | **98 réussis**, 2,59 s |
| [Core épinglé sur Memory G230](https://github.com/toytoy68/Eidolon-Bootstrap-Framework/actions/runs/38612137486), Core `e7cba2b` | **1763 tests et 1299 sous-tests réussis, 7 ignorés, 0 avertissement pytest**, 286,59 s |

Les six échecs locaux passent sur le runner Linux ; aucun test n'a été masqué.
Les lots se chevauchent et ne doivent pas être additionnés. Les avertissements
Node des actions GitHub sont de l'infrastructure, distincts des résultats pytest.

## Livré dans ce lot

- `JournalUpsertWorker` consomme une liste bornée et complète d'intentions existantes, sous le même verrou que les écrivains canoniques. Une seconde exécution concurrente retourne BUSY. Il utilise le lecteur Markdown réel et le chemin public `apply_upsert` de G229.
- Une intention INTENT ne passe à PUBLISHED qu'après vérification des octets, de la révision et des droits, puis `fsync` du fichier et du répertoire. L'indexation est faite au tour suivant. Échec de synchronisation disque : intention conservée.
- Une intention PUBLISHED ne passe à INDEXED qu'après vérification du digest canonique complet, du modèle, de la génération, nouvelle lecture du canon et nouveau contrôle des droits. La transition SQLite compare atomiquement la ligne complète observée ; une transition concurrente bloque la clôture.
- Après accusé perdu ou arrêt du processus entre l'upsert et la clôture, une nouvelle exécution relit la preuve persistée et peut terminer sans recalculer l'embedding ni réécrire le point. Aucune nouvelle tentative n'est faite dans le tour ayant rencontré un effet incertain.
- Une source plus récente, un digest contradictoire, une suppression, une lecture impossible ou une preuve incohérente ne sont pas approuvés automatiquement. Les séquences différées et leurs raisons sont dans le rapport ; DONE signifie fin du tour, pas synchronisation de toutes les intentions.
- `reconcile_plan` et l'aperçu acceptent désormais des preuves `IndexEvidence` avec modèle et génération attendus. À révision égale, un digest différent produit INTEGRITY_ALERT et une revue ; une preuve absente produit une proposition d'upsert. Les appels historiques en mode révision seule sont conservés et ne prouvent pas l'intégrité du contenu.

## Preuves locales

- Quatre tests rouges sans les nouvelles API, puis verts après implémentation.
- **134 tests ciblés réussis avec `-W error`**, couvrant journal, lecteur, worker, planificateur et adaptateur Qdrant ; puis **38 nouveaux cas réussis avec `-W error`**, dont un test interprocessus ajouté après cette première campagne. Comptes chevauchants, non additionnables.
- Suite complète locale avant ce dernier test : **2346 tests et 12 sous-tests réussis, 6 échecs**, 90,00 s. Les six échecs sont les restrictions AF_UNIX/Manager déjà documentées en G229 ; ils ne sont ni supprimés ni masqués. La CI Linux a ensuite confirmé le code publié (table ci-dessus).
- Arrêt réel d'un sous-processus avec `os._exit(73)` après écriture du point et avant la transition INDEXED : redémarrage sur SQLite et Qdrant local sur disque, clôture réussie sans ré-embedding.
- Autres cas : droits refusés/révoqués, source modifiée pendant l'indexation, digest divergent à révision égale, point historique sans preuve, index indisponible, modèle incorrect, troncature, horloge reculée, transition concurrente du journal, génération modifiée, échec fsync, deux workers concurrents et écrivain bloquant dans un autre processus.
- Core : `fork` résiduel de `test_profile_registry_probes` remplacé par `spawn` ; **44 tests et 18 sous-tests ciblés réussis**, `-W error`. La CI complète confirme leur disparition ; les sept tests ignorés concernent les moteurs/modèles d’identité optionnels.

## Limites — J2 reste ouvert

Ce consommateur est une API explicite, sans daemon ni activation dans les services.
Il traite les intentions présentes, pas l'inventaire complet des documents et des points.
Les écrivains canoniques, les changements de droits et les bascules d'alias doivent coopérer
avec le protocole de verrouillage ; cela ne crée pas une transaction distribuée.
Une preuve du payload ne démontre pas la justesse sémantique d'un vecteur.

Restent prioritaires :

1. Balayage borné et complet du manifeste pour les événements absents du journal, avec preuves de point et reprise du curseur. Pas de branchement automatique sur le corpus réel.
2. Contrat complet des 19 scénarios historiques sur ce nouveau consommateur, notamment absence prouvée/réapparition, délai d'abandon et politique de chunker. Les tests historiques restent exécutés séparément contre le worker expérimental ; ils ne sont pas réattribués au nouveau worker.
3. Qualification de la concurrence, des bascules et coupures contre un serveur Qdrant réel et les modèles réels. Ici Qdrant utilise son moteur local en mémoire ou sur disque et des vecteurs synthétiques.
4. Contre-revue Claude puis recette B01–B12 VM/PC au retour des accès. Aucun accès rétabli ou déploiement à déduire de ces tests.

Les suppressions, clôtures ABANDONED/SUPERSEDED et migrations restent sous revue.
Une file qui dépasse la limite refuse le tour : pagination/ordonnancement à compléter.
Aucune branche main, donnée réelle, VM ou service actif modifié.
