# Écritures Information coordonnées v1

Implémentation T-041 : `core/information/writes.py`. Les fichiers Information
restent canoniques. Le service journalise création/modification et leur Event ;
il ne fait ni classification, ni import historique, ni appel LLM.

## API et commande

`FilesystemInformationWrites(backend)` utilise obligatoirement les journaux
canoniques `history/operations/information-write-v1` et
`history/events/information-write-v1` du backend. `create(memory, operation_id=…,
event_id=…, actor=…, timestamp=…)` impose révision 1 ; `update` ajoute
`previous_revision` et attend un Memory portant cette révision, puis alloue +1.
Les deux renvoient `{information_id, previous_revision, revision, event_id}`.
Le Memory original reste inchangé. Il peut contenir des extensions et un contenu
structuré ; aucune projection textuelle ne lui est appliquée.

```sh
MEMORY_ENGINE_ROOT=/chemin/reel python -B -m core.information.cli create \
  --input command.json --operation-id create-001 --event-id event-001 \
  --actor toytoy --timestamp 2026-10-01T05:00:00Z
MEMORY_ENGINE_ROOT=/chemin/reel python -B -m core.information.cli update \
  --input updated.json --previous-revision 1 \
  --operation-id update-001 --event-id event-002 \
  --actor toytoy --timestamp 2026-10-01T05:01:00Z
MEMORY_ENGINE_ROOT=/chemin/reel python -B -m core.information.cli recover
```

Les fichiers JSON d'entrée représentent le dataclass `core.backend.models.Memory`
au complet. L'import historique conserve son API/backend et ses révisions ;
il ne fabrique pas d'Events CREATED rétroactifs. `core.operations.cli recover-all`
inclut le groupe `information-writes`. La reprise reste explicite.

## Commande stable et Event

L'empreinte SHA-256 v1 porte sur l'objet JSON : `format_version=1`,
`operation_type`, `previous_revision`, `memory` (Memory après, révision allouée
incluse), `event_id`, `actor`, `timestamp`. JSON UTF-8, clés triées, séparateurs
`,` et `:`, sans espace décoratif, sans ASCII escaping ni nombres non finis.
Les chaînes Unicode et les listes ne sont pas normalisées ; leur valeur/ordre
exact fait partie de la commande. `operation_id` est la clé, hors empreinte.
Changer la révision du Memory envoyé au rejeu n'est pas autorisé : renvoyer
la commande originale. Date et acteur sont fournis, jamais régénérés.

Le plan conserve le Memory complet après et, pour update, avant. Son hash
couvre aussi l'identité d'opération. L'Event contient uniquement les six champs
de classement connus et une empreinte du contenu. Les métadonnées libres,
preuves, contexte et texte ne sont pas recopiés dans l'Event. Un état épistémique
absent y est représenté par null, pas par CONFIRMED. Lors d'un update, les
champs changés sont inclus et les états épistémique/opérationnel sont gardés
comme contexte pour respecter le contrat Event existant. Un changement uniquement
dans une extension produit néanmoins un Event UPDATED à la nouvelle révision.

## Conflits et reprise

Verrous : Persistent → journal Information → Events. Les appels ne prennent
pas le verrou Thread. Les plans sont PREPARED puis APPLYING puis COMMITTED.
La reprise accepte seulement le snapshot avant ou après ; un Event différent,
un plan altéré ou un fichier divergent bloque sans écraser la donnée.
Un rejeu COMMITTED retourne son résultat avant d'examiner l'état actuel de la
cible ; il ne restaure jamais le fichier. Un operation_id réutilisé pour une
commande différente est refusé. Un Event est réservé dès PREPARED.

Une demande de suppression attend les opérations incomplètes de sa cible ou
qui créent un lien vers elle. Son approbation exige la compaction des plans de
la cible, y compris COMMITTED. PENDING_DELETE bloque un nouvel update ; annuler
puis modifier sont deux commandes distinctes. CANCELLED réserve encore l'identité
mais permet de modifier la cible existante. Aucune annulation automatique.

## Limites et preuve

Les primitives backend store/update restent publiques pour l'import et les tests
bas niveau. Elles ne sont pas devenues des chemins métier coordonnés ; la migration
de tous leurs appelants reste T-031. Les anciens services ne sont pas raccordés.
Le verrou et les garanties supposent que les écrivains coopèrent ; un outil qui
réécrit directement un fichier peut provoquer un blocage de reprise.

Tests : `tests/test_information_writes.py` et
`tests/integration/test_information_write_crash.py` (arrêt de processus par
`os._exit`, cinq frontières pour création et modification). Le test de suppression
échoue si son raccordement est retiré. Aucun essai VM ni coupure de stockage réel.
La compaction est le lot T-042, nécessaire avant d'approuver une suppression ayant
un plan d'écriture conservé.

## Compaction récupérable T-042

```sh
MEMORY_ENGINE_ROOT=/chemin/reel python -B -m core.information.cli compact create-001
python -B -m core.information.write_audit --root /copie-arretee
```

La commande compact traite un seul identifiant explicite. Elle vérifie l'Event
et les opérations en attente, écrit un reçu versionné dans
`history/operation-receipts/information-write-v1`, le relit, compare tous les
champs avec l'Operation, puis retire durablement le plan. Le verrou journal
Information couvre également les reçus ; l'ordre reste Persistent → journal
Information → Events. Les nouveaux répertoires de reçus et le répertoire du
journal sont synchronisés sur POSIX. Windows n'a pas cette même garantie de
fsync de répertoire ; aucun test Windows n'est revendiqué.

Un reçu et un plan concordants décrivent COMPACTING ; recovery termine le
retrait. Un reçu seul décrit COMPACTED. Toute divergence ou version inconnue
bloque. Le rejeu de commande lit ces deux emplacements avant les contrôles
sur la cible ; il ne modifie aucun fichier métier. Le résultat minimal du reçu
n'est pas une copie de l'Information ni une preuve de sa présence actuelle.

Le lecteur partagé `InformationWriteJournal` est utilisé par service, reprise,
compaction, garde de suppression et audit. L'inventaire de formats inclut cet
audit logique ; la recette VM ajoute `audit_information_writes`. Les audits
ne créent aucun dossier ni verrou et doivent tourner sur une copie arrêtée
pour un résultat stable. COMPACTING appelle une reprise explicite, signalée
par l'audit. Les familles Thread conservent leur propre format.

Le schéma exact est dans [information-write-receipt-v1.md](../schemas/information-write-receipt-v1.md).
D8 : les empreintes restent conservées après suppression ; un contenu court
peut être testé par devinette. Il n'y a ni chiffrement ni garantie d'effacement
physique. Dossiers de sauvegarde, archives et snapshots du système de fichiers
peuvent conserver des copies anciennes ; la commande ne les purge pas.
Les reçus sont conservés sans expiration dans cette v1. Aucun ordonnanceur de
compaction, rétention automatique ou effacement des empreintes n'est ajouté.

## Histoire après compaction

Le [lot T-049](JOURNAL-SCAN-COST.md) réduit les trois scans par nouvelle écriture
à un seul, par vue de réservations validée locale à la commande sous verrous.
Les reçus restent strictement validés et la compaction relit sa publication.
Aucun cache n'est réutilisé entre commandes ; le coût reste linéaire par écriture.

La compaction retire les snapshots avant/après. Le reçu et l'Event permettent
la traçabilité/reprise, pas la reconstruction intégrale des anciens textes.
Conserver les observations historiques nécessaires comme Informations distinctes
reliées ; une archive de révisions demanderait une politique séparée (T-050).
