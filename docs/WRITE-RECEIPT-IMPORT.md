# Import des reçus terminaux de rejeu Information — T-021/T-033

Ce chemin copie les reçus compactés `information-write-v1` et leurs Events
exacts entre deux arbres core arrêtés. Il conserve l'histoire des commandes et
les décisions humaines FAILED sans réexécuter une écriture Information.
Il ne convertit pas de corpus legacy et ne fusionne pas des contenus différents.

```sh
python -B -m core.migration.write_receipts \
  --source /copie-source --destination /destination
python -B -m core.migration.write_receipts \
  --source /copie-source --destination /destination --apply
```

API : `inspect_write_receipts(source, destination)` sans écriture ;
`import_write_receipts(source, destination)` pour publication explicite.
Le CLI renvoie 1 si BLOCKED et 0 pour READY/IMPORTED/UNCHANGED. Le JSON expose
IDs d'opération/Information/Event, révisions, SHA256 des fichiers et actions.
Sans `--apply`, aucun dossier, verrou ou rapport n'est créé.

Les deux arbres doivent contenir `memory/persistent/`, être distincts, sans
chevauchement ni ancêtre symbolique et avoir une readiness valide. Tous les
journaux d'écriture Information source doivent être compactés, sans coexistence
avec un snapshot complet. Les autres familles ne sont pas transférées par ce
chemin. Les sources, éditeurs et écrivains legacy/bas niveau doivent être arrêtés.
Les écrivains canoniques coopératifs destination partagent les verrous
Persistent → Operation → Event tenus par l'import.

Pour chaque reçu, l'Information canonique doit avoir les mêmes octets dans les
deux arbres et une révision au moins égale à celle du reçu. Si elle est absente,
les deux arbres doivent porter le même reçu DELETED exact. Importer ces
réservations séparément avec `core.migration.deleted_receipts` si nécessaire.
Aucun corps canonique, Thread, dossier ou index n'est copié. Une Information
absente sans réservation DELETED est refusée.

Les lecteurs stricts vérifient reçu, audit humain éventuel et Event. L'import
vérifie aussi cible, révision, type CREATED/UPDATED et lien CAUSED_BY vers la
commande. Un hash d'Event recalculé ne permet pas de masquer une identité métier
incohérente. Aucun Event ne peut être réservé par deux commandes candidates,
ni par une autre commande destination. Un journal complet destination de même
operation_id demande une compaction/revue séparée et est refusé ici.

Tous les candidats sont contrôlés avant publication, puis de nouveau sous
verrous. Une différence de contenu ou de présentation dans un Event/reçu déjà
présent bloque le lot entier avant la première écriture. Les objets déjà
identiques sont conservés, sans remplacement. Les octets source et l'audit
`manual_resolutions` sont préservés, y compris les champs optionnels stricts ;
aucun rapport de provenance n'est inséré dans un journal canonique.

Pour chaque paire, l'Event est publié durablement avant le reçu. Un arrêt entre
ces publications laisse un Event orphelin, sans reçu actif privé de son Event.
Un préfixe peut avoir été acquis : le lot n'est pas une transaction globale.
Relancer avec la même source arrêtée termine les manquants par comparaison
exacte. Les imports concurrents coopératifs sont sérialisés. Une relecture finale
exige tous les objets identiques et les contrôles toujours satisfaits.

Garder les écrivains métier destination arrêtés jusqu'au succès final, y compris
après une interruption. Le contrôle readiness ordinaire peut être vrai après
publication de l'Event seul : il ne connaît pas les reçus restant à importer.
Cette readiness ponctuelle ne vaut donc pas achèvement de l'import ni autorisation
de remettre un consommateur en service. Une commande sous le même operation_id
mais un Event différent pourrait sinon créer un conflit avec la relance.

Un arrêt avant le renommage peut laisser un fichier temporaire inconnu :
readiness bloque alors la relance, pour examen humain sans nettoyage automatique.
Un écrivain bas niveau ne partageant pas les verrous peut casser ces garanties ;
il doit rester arrêté. La source n'est jamais écrite, même pour un verrou.

Après import, le rejeu d'une ancienne commande renvoie son résultat terminal
sans remplacer une révision plus récente ni recréer une Information supprimée.
La décision humaine importée peut être rejouée avec les mêmes paramètres, selon
son contrat ; aucun nouvel ID de décision n'est créé par cet import.

Les reçus ne contiennent plus les snapshots de révision. L'import ne peut donc
reconstituer ni authentifier leur contenu historique : seules les empreintes,
les identités, les Events, l'état canonique actuel et l'audit déclaré sont
vérifiables. Utiliser une source connue et arrêtée. Ce chemin ne ferme pas
l'import général des Threads, opérations non compactées, CANCELLED ou parents.
Le convertisseur legacy continue de refuser les sources opérationnelles mixtes.


## T-021/T-033 — Import des reçus compactés Information, 3 octobre 2026

Base `5394e06`, vérifiée sur GitHub avant ce lot. Nouveau chemin explicite
`core.migration.write_receipts` : aperçu sans écriture et import des reçus
terminaux INFORMATION_CREATE/UPDATE avec leurs Events exacts, sans canonique,
Threads, index ni réexécution. Les deux arbres doivent être prêts et arrêtés ;
les journaux Information source doivent tous être compactés. Même canonique
actuel par octets et révision >= reçu, ou même réservation DELETED si absent.
L'import contrôle identité/révision/type/CAUSEDBY de l'Event, réservations et
conflits exacts avant publication, puis sous verrous Persistent/Operation/Event.
Il conserve les audits humains, et le rejeu ne remplace pas une révision plus
récente ni ne recrée une Information supprimée. Le convertisseur legacy conserve
son refus des sources mixtes ; aucune fusion générale introduite.

Event publié avant reçu ; arrêt entre les deux → Event orphelin, relance depuis
la même source arrêtée. Préfixe possible, aucune transaction globale ni rollback.
Résidu temporaire inconnu → refus readiness/reprise pour examen humain. Source
jamais écrite. Destination à garder arrêtée jusqu'au succès final, même si le
contrôle readiness peut être vrai sur un préfixe sans reçu manquant identifié.
Contrat : [WRITE-RECEIPT-IMPORT.md](WRITE-RECEIPT-IMPORT.md).

34 nouveaux tests : 23 échecs/5 réussites sur le squelette initial refusant
l'import, puis six cas supplémentaires (Event cohérent par digest mais métier
incorrect, révision canonique trop ancienne, arrêt avant renommage). Le cas de
révision canonique échoue avant ajout de sa garde, puis passe. Groupe ciblé :
**173 réussis en 5,56 s**. Trois arrêts réels code 74, deux importeurs concurrents,
revalidation sous verrous, aperçu sans écriture, audit FAILED conservé, conflits
sans préfixe, suppression/rejeu et fichiers exacts. Retirer publication ou garde
canonique en mémoire produit un échec chacun ; aucune substitution conservée.
Suite complète VM isolée hors sandbox : **1369 passed in 33.70s**, aucun échec,
saut ou désélection, Python `.venv` 3.13.5/pytest 9.1.1 ; journal
`/tmp/em-suite-pzRYrA/pytest.log`. Preuve sur base `5394e06` plus ce lot avant commit.
Corpus synthétique uniquement, aucun import dans la mémoire active, aucun corpus
réel ni coupure électrique. CANCELLED, Threads/actions/révisions et import
général restent ouverts ; estimations 45 % / 52,75 points inchangées.
