# Contrat du diagnostic de rappel indexé

Eidolon Memory Engine — contrat G242/G243/G250/G251, 15 octobre 2026.
Ce document décrit l'API livrée ; le [bilan de qualification](G251-SESSION-2026-10-15.md) identifie les sources et les preuves.

## Deux informations distinctes

`RecallBundle.items` contient les extraits canoniques retenus dans le budget de contexte. `RecallBundle.index_status` décrit l'index observé et sa comparaison au canon. Une liste vide ne prouve pas l'absence de souvenirs. Le rappel lexical laisse `index_status` à `None` ; les consommateurs anciens peuvent omettre le champ.

| État et motif | Ce qui a été établi | Interprétation pour l'hôte |
| --- | --- | --- |
| `INDEX_SNAPSHOT_MATCH` / `FULL_SOURCE_DIGEST_MATCH` | Le digest complet de reconstruction correspond au canon observé sous verrou coopératif. | Présenter les extraits retenus ; aucune garantie de pertinence ou d'exhaustivité. |
| `INDEX_STALE` / `FULL_SOURCE_DIGEST_MISMATCH` | Le canon diffère du digest de reconstruction. | Signaler que des changements peuvent manquer à l'index, même avec zéro extrait. |
| `INDEX_UNVERIFIED` / `SNAPSHOT_NOT_SUPPORTED` | Le fournisseur ne fournit pas l'observation facultative `query_snapshot`. | Conserver explicitement l'incertitude. |
| `INDEX_UNVERIFIED` / `NO_FULL_SOURCE_DIGEST` | La génération observée n'a pas de digest global exploitable, notamment après une mise à jour incrémentale. | Ne pas assimiler cela à une panne ni à un index périmé prouvé. |
| `INDEX_UNVERIFIED` / `CANONICAL_CHECK_INCOMPLETE` | Le digest global n'a pas pu être vérifié, par exemple à cause du budget ou d'une source illisible. | Signaler que la mise à jour complète n'a pas pu être vérifiée. |

Le diagnostic contient aussi `generation`, `source_digest` et `canonical_digest` quand ils sont connus. Une concordance exige deux digests identiques ; un état périmé exige deux digests différents. Le contrat Core valide ces combinaisons. La génération est une observation, pas une réservation durable.

## Provenance des candidats

Les candidats issus d'une reconstruction Qdrant portent une preuve du modèle, de la projection, de la génération et des octets canoniques. Le lecteur relit les octets sous le verrou du rappel. Une modification à révision inchangée est ainsi détectée.

| Compteur d'exclusion | Conséquence |
| --- | --- |
| `INDEX_MISSING_CANONICAL` | Identité canonique absente, extrait écarté. |
| `INDEX_REVISION_MISMATCH` | Révision du candidat différente du canon, extrait écarté. |
| `INDEX_DIGEST_MISMATCH` | Preuve différente des octets relus, ou objet canonique divergent, extrait écarté. |
| `INDEX_CANONICAL_UNVERIFIED` | Relecture de preuve impossible ou hors budget par fichier, extrait écarté. |
| `INDEX_PASSAGE_MISSING` / `INDEX_PASSAGE_UNRESOLVED` | L'archive ne fournit pas de passage canonique valide, extrait écarté. |

Une ligne refusée n'efface pas les candidats sains. Une erreur réseau ou un index incompatible interrompt le rappel ; aucun repli lexical silencieux n'est déclenché. Les anciens points sans preuve globale restent explicitement non vérifiés, selon le contrat de l'adaptateur.

## Budgets et coût

L'hôte peut fournir `freshness_budget=ManifestBudget(...)` à `ContextualRecall` : 10 000 entrées de répertoire, 8 Mio par fichier et 32 Mio cumulés par défaut. Tous les noms de répertoire comptent dans le premier budget. Le budget restant est appliqué avant chaque lecture ; aucun digest partiel n'est accepté. La limite par fichier sert aussi à la preuve des candidats.

Cette comparaison complète est O(taille du corpus) et se déroule sous verrou coopératif. Un dépassement du budget global produit un diagnostic inconnu ; il ne retire pas à lui seul un candidat dont la preuve individuelle est valide. Les anciennes lectures du backend, la RSS et la durée d'embedding ne sont pas bornées par cette option. Les écrivains externes ne respectant pas le verrou ne bénéficient pas d'un snapshot atomique.

## Transmission à Core et décisions restantes

Le pont transporte `index_status` dans le résultat JSON. Core le valide avant usage. Le dialogue transmet le diagnostic avec la mémoire et son contexte visible indique `memory_index` seulement si cette mémoire a effectivement été envoyée au modèle. Un index périmé ou non vérifié rend ce contexte partiel, même sans extrait. Le modèle reçoit l'instruction de ne pas déduire une absence de souvenir d'un rappel vide ; cela ne constitue pas un essai sur modèle réel.

Le point d'entrée du bridge reste lexical par défaut. L'hôte doit construire explicitement le fournisseur indexé, choisir ses budgets et sa politique de maintenance. Aucun diagnostic de lecture ne lance une reconstruction, une suppression ou un service.

L'évaluateur pur `evaluate_lag` est complémentaire : il reçoit un seuil obligatoire fourni par l'hôte et les intentions en attente. Avec `AGE_UNKNOWN`, l'âge maximal reste `None`, tandis que `lagging` compte les retards connus comme borne inférieure. Ce résultat ne remplace ni le diagnostic de couverture ci-dessus ni l'ancien `worker_status`.
