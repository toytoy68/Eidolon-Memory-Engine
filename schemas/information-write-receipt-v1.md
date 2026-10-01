# Reçu d'écriture Information v1

Format JSON terminal, famille
`memory/history/operation-receipts/information-write-v1/<operation_id>.json`.
Les plans avant compaction restent des OperationRecord dans la famille
`memory/history/operations/information-write-v1`.

| Champ obligatoire | Contrat |
| --- | --- |
| format_version | entier 1 ; version inconnue refusée |
| status | COMMITTED |
| operation_id | identité de commande, identique au nom de fichier |
| operation_type | INFORMATION_CREATE ou INFORMATION_UPDATE |
| target_id | information_id |
| previous_revision | 0 à la création, entier ≥ 1 à la modification |
| revision | previous_revision + 1 |
| event_id | Event initial, conservé |
| command_fingerprint | SHA-256 hexadécimal de la commande canonique v1 |
| plan_hash | execution_plan_hash du plan d'origine |
| event_sha256 | SHA-256 du dictionnaire Event complet, JSON canonique v1 |
| result | objet exact information_id, previous_revision, revision, event_id |
| compacted_at | date UTC de la première publication du reçu |

Les champs supplémentaires ne sont pas acceptés par le lecteur v1. Le résultat
répète les valeurs d'identité et de révision du reçu ; une contradiction est
refusée. Le reçu ne contient ni snapshot ni texte de l'Information. Les
empreintes ne rendent pas confidentiel un contenu devinable et ne constituent
pas une signature contre un tiers qui pourrait réécrire tous les fichiers.

La canonicalisation et les champs de commande sont définis dans
[INFORMATION-WRITES.md](../docs/INFORMATION-WRITES.md). Le hash Event permet à
l'audit de vérifier l'historique après retrait du snapshot. Le hash de plan
n'est pas reconstructible depuis le reçu seul ; il lie le reçu au plan pendant
la transition de compaction, sans prétendre conserver le contenu retiré.

Sous les verrous communs : publication atomique et synchronisée → relecture
et concordance avec le plan COMMITTED → retrait du plan → fsync du répertoire.
Un arrêt après publication conserve les deux objets ; la reprise retire le
plan seulement s'ils concordent. Un arrêt après retrait laisse le reçu pour
le rejeu ; répéter compact synchronise le répertoire de journal. Une divergence
bloque tous les lecteurs métier, jamais de priorité aveugle du reçu.

PENDING_DELETE permet la compaction ; APPLYING_DELETE la bloque. L'approbation
de suppression exige qu'aucun plan de la cible ne subsiste, sous le même verrou
Persistent tenu jusqu'à la publication du reçu APPLYING_DELETE. La rétention
des reçus est sans expiration en v1 ; les sauvegardes se gèrent séparément.
