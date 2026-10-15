# G263 — Rappel explicite sur stockage en lecture seule

Auteur : Codex/GPT, 15 octobre 2026. Base Memory : `795784a34f566d02c04eb184b06c13326d61bb0c`.

## Changement

Le bridge accepte `--read-only-storage`. Ce mode exige une arborescence déjà préparée : `--root` contient `memory/persistent` et `memory/history/pending-delete`. Le fichier `memory/persistent/.write.lock` doit exister ; si `memory/persistent/threads` existe, son `.write.lock` doit aussi exister. Le démarrage les vérifie sans attente et chaque rappel les reprend. Une erreur de préflight empêche de lier le serveur ; une erreur ultérieure de rappel renvoie le diagnostic HTTP existant `RECALL_UNAVAILABLE`.

`FilesystemBackend(..., create_directories=False)` ne provisionne rien et exige des racines explicites. `ContextualRecall(..., read_only_locks=True)` utilise `exclusive_write(..., read_only=True)` : l'exclusivité est conservée, seul le descripteur du verrou est ouvert en lecture seule. Les valeurs par défaut restent inchangées. Cette option du backend n'interdit pas ses méthodes d'écriture : les permissions/montages du système doivent imposer la frontière.

Aucun verrou séparé : lecteurs et écrivains utilisent le même inode `.write.lock`, qui ne doit jamais être supprimé, remplacé ou recréé en fonctionnement. Le mode refuse les liens symboliques et fichiers non réguliers ; il contrôle l'identité avant et après acquisition. Un appel réentrant ne peut pas promouvoir un verrou acquis en lecture seule en verrou écrivain. La sortie sur erreur libère le descripteur/verrou.

## Périmètre et limites

Mode réservé à Linux sur stockage local ; autre plateforme refusée explicitement. Le [contrat Linux flock(2)](https://www.man7.org/linux/man-pages/man2/flock.2.html) permet un verrou exclusif sur un descripteur en lecture seule. NFS émule autrement les verrous et exige une ouverture en écriture pour l'exclusif ; NFS/CIFS et les options de montage ne sont pas qualifiés ici. Le code ne détecte pas le type de montage. Une recette du stockage cible est donc nécessaire avant activation.

La coordination reste coopérative : ni les contrôles d'inode ni les verrous ne protègent contre un acteur autorisé à remplacer les fichiers après acquisition. Les racines doivent rester de confiance. Ce lot ne déplace aucun verrou, n'initialise aucun compte, ne migre aucune donnée et ne modifie aucune unité systemd. Le cache du reranker reste un périmètre distinct, confié à Claude dans G262.

Les verrous existants doivent être préparés lors de l'initialisation contrôlée avec tous les lecteurs/écrivains arrêtés ; ne pas corriger un verrou manquant en supprimant ou recréant un fichier pendant le service. Les processus écrivains conservent l'ouverture historique en a+b et leurs permissions. Le montage readonly du bridge peut présenter le même inode que le montage writable du worker ; cette topologie réelle n'est pas testée ici.

## Preuves locales

`tests/test_readonly_storage_g263.py` : 25 réussis, 1 ignoré (UID root). Corpus entièrement synthétique. Tests avec refus EROFS des ouvertures en écriture et de mkdir, y compris sur répertoires existants ; le rappel historique échoue et le mode explicite réussit. Parcours simple et projet/dossier CURRENT ; empreintes des données conservées. Le refus EROFS est injecté, pas un vrai montage readonly.

Trois couples interprocessus réellement exécutés : lecteur/écrivain, écrivain/lecteur, lecteur/lecteur. Processus Python indépendants, acquisition non bloquante BUSY pendant le détenteur, acquisition après libération et lors d'un nouveau processus, inode et octets du verrou conservés. Fichier remplacé au retour de flock refusé ; liens, FIFO, répertoire, prérequis manquants, arguments non booléens, plateforme non supportée et promotion réentrante refusés. CLI reliée au mode et démarrage refusé avant ouverture du serveur si verrou absent. Rappel HTTP réel réussi puis 503 après suppression fautive du verrou, sans recréation.

Régression ciblée avec `-W error` : **117 réussis, 1 ignoré, 5 sous-tests**, 5,58 s. Modules : readonly G263, persistence_atomic, persistence_leaf_g249, contextual_recall, settled_read_phase, threads/test_serialization, memory_bridge, limits_g245, freshness_g245, write_deadline_g257, bridge_recall_lock_g259 et sondes Claude lock_g259. L'exclusion correspond au test chmod sous UID ordinaire : CI nécessaire. Aucun résultat de VM, de montage readonly réel ni de modèle revendiqué.

Qualification complète après publication : à consigner avec les SHA et journaux CI effectifs. Compte de service C187 toujours proposé ; dix tâches G262 restent attribuées à Claude, notamment contre-revue du verrou et préflight de l'UID.
