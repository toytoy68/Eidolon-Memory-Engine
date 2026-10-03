# Recette VM du code 2fed279 — 3 octobre 2026

Deux recettes indépendantes sont exécutées sur `Eidolon-Memory` avec le Python
3.13.5 de `/opt/eidolon-memory-engine/.venv`, pytest 9.1.1, branche
refactor/architecture-v1. Le code exécutant tests/audits est
`2fed27951f9272b9f8ed68019eafbcbbe47e35aa`, confirmé sur GitHub avant ce lot.
La source restaurée est un arbre de données arrêté ; ses anciens fichiers de
code ne sont pas utilisés pour exécuter les tests de concurrence.

| Source | Dossier court | Étapes | Concurrence | SHA256 copie/restauration |
| --- | --- | --- | --- | --- |
| Restauration de la sauvegarde d’origine, mémoire vide | /tmp/em-oJIl9V | 9 OK | 5 réussis en 0,81 s, 40 désélections du filtre | 2448 fichiers |
| Corpus synthétique neuf peuplé | /tmp/em-jQ4gTi | 9 OK | 5 réussis en 0,80 s, 40 désélections du filtre | 93 fichiers |

Les durées exactes pytest figurent dans les logs joints ; les étapes concurrency
complètes prennent respectivement 0,909 et 0,906 s. Les empreintes de source sont
recontrôlées à la fin de chaque recette, sans changement. Aucun chemin de travail
long ni erreur AF_UNIX. Le scénario utilise des objets factices, pas une ingestion
ou transformation de données utilisateur.

## Scénario peuplé

`tools.vm_synthetic_scenario` refuse un répertoire source déjà peuplé ou un chemin
avec symlink, avant initialisation des repositories. Le report doit être nouveau
et extérieur à la source. Le scénario crée dix Informations sans dossier, puis
une Information/projet explicitement nouveau, rattache une source canonique
existante sans la réécrire et corrige une Information par révision attendue.
Il interrompt un parcours après l’écriture durable et le récupère avec la reprise
globale. Chaque parcours est rejoué à l’identique sans nouvel effet.

Il ajoute une action au projet, crée/supprime un autre projet, annule une demande
de suppression d’Information et approuve une autre après compaction du journal.
La première tentative avait omis cette compaction : refus observé
InformationDeletionBlocked, sans contournement. L’ordre a été corrigé via l’API
supportée et le scénario relancé sur un répertoire neuf ; son log est conservé.

Une passe d’entretien à date/contexte explicites exécute cinq échéances et
reconstruit dossier/catalogue. Les cinq effets sont RECHECK, les sources restant
UNVERIFIED. La compaction par lot conserve volontairement un journal complet
pour contrôler un historique mixte. Le rappel borné sérialisé du projet expose
CURRENT, provenance et needs_review ; aucun statut n’est promu par le rôle ADMIN.

Inventaire final observé : **11 Informations core 0.2**, **un Thread core 0.2**,
**18 Events Information**, **17 reçus Information compactés + un journal complet**,
**14 reçus de routage** (v3 : 1, v4 : 1, v5 : 12), **cinq déclencheurs achevés**,
**deux reçus de suppression Information** et l’historique de suppression du
projet éphémère. Audits formats/relations/cycle de vie/suppressions/écritures
sans problème, readiness vraie. Aucune opération FAILED n’est fabriquée ici.

Deux contrôles négatifs en mémoire : payload avec needs_review effacé refusé par
le vérificateur du scénario ; dépôt actif peuplé refusé avant mutation et
empreintes memory inchangées. Les commandes métier n’ont pas été modifiées.
Ce nouveau scénario est exercé directement ; le code core reste celui de la
suite précédente **1581 réussis en 38,62 s**, sans répétition artificielle.

## Preuves et conservation

Les rapports JSON, logs de concurrence, rapport du scénario, première tentative,
manifestes/hashes core et outil sont versionnés dans
[vm-acceptance/2026-10-03-final](vm-acceptance/2026-10-03-final).
L’archive séparée, avec corpus synthétique intégral et fichier SHA256.json,
contient **102 fichiers vérifiés** :
`/home/toytoy/eidolon-backups/backup-20261002-225227-mtsJkO/recette-20261003-final-2fed279`.
Les arbres temporaires, source et résultats, sont conservés pour inspection.

La source d’origine est toujours
`/home/toytoy/eidolon-backups/backup-20261002-225227-mtsJkO/restauration-i2mwDP/eidolon-memory-engine`.
L’inventaire écrivains de ces deux recettes constate configured=[], running=[]
et aucun descripteur writable sur la source. **unreadable contient
/var/spool/cron/crontabs**, puisque ces recettes ne tournent pas sous sudo.
La confirmation antérieure par toytoy sous sudo est une preuve distincte ;
cette recette ne renouvelle pas une inspection exhaustive des services/jobs.

## Limites

La sauvegarde restaurée a toujours un inventaire mémoire vide. Le corpus ajouté
est synthétique et réduit : il augmente la couverture de scénario VM, sans
valider la qualité/latence d’un corpus réel, une migration réelle, un client
externe ou une intégration avec services actifs. Les interruptions injectées et
les arrêts de processus des tests ne constituent pas une coupure électrique.
Aucune coupure, aucun service installé ni donnée active modifiée. Estimation
45 % / 52,75 points inchangée.
