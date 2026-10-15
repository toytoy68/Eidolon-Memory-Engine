# G242 — Fraîcheur explicite du rappel, 15 octobre 2026

Base Memory : 587d4a9b50357401d9150c46d977b2d72648835a. Auteur : Codex/GPT.

Le rappel sémantique relisait les candidats mais ne signalait pas les documents
ajoutés après reconstruction. La sonde Claude G201 Q2 a échoué avec --runxfail
avant modification ; ses assertions sont conservées, son marqueur retiré.

## Contrat livré

`RecallBundle.index_status` est nul en rappel lexical. Pour un index :

| État | Signification |
| --- | --- |
| INDEX_SNAPSHOT_MATCH | Le digest complet de la reconstruction concorde avec le canon observé sous verrou coopératif. Ce n'est ni une garantie de pertinence ni un verrou de génération durable. |
| INDEX_STALE | Le digest du canon diffère : ajout, correction, suppression ou modification à révision identique. |
| INDEX_UNVERIFIED | Pas de snapshot fourni, digest invalidé par indexation incrémentale, ou vérification canonique incomplète. Aucune absence de document n'est déduite. |

Le motif, la génération et les digests observés sont exposés au niveau du bundle,
même sans candidat. Le rendu JSON complet conserve ce diagnostic, y compris
lorsque son budget retire les extraits. Les erreurs réseau et incompatibilités
continuent à interrompre le rappel, sans repli lexical silencieux.

`QdrantIndex.query_snapshot` complète `query`, qui conserve sa signature et sa
liste de résultats. Descripteur et génération sont revérifiés après la requête ;
un changement constaté est refusé. Un changement pendant la dernière lecture
du descripteur est également détecté (scénario rouge puis vert).

`ManifestBudget` : 10 000 entrées de répertoire, 8 Mio par fichier et 32 Mio de
sources au total par défaut ; réglage explicite par l'hôte via
`ContextualRecall(..., freshness_budget=ManifestBudget(...))`. Lecture ancrée
sans liens, budget restant appliqué avant chaque fichier, aucun digest partiel,
second inventaire des noms. Aucune écriture de mémoire, journal ou index.

## Preuves et limites

34 nouveaux tests : ajouts, mutations/révisions, suppression, index vide,
absence de capacité snapshot, limites exactes/dépassements, configuration,
JSON et courses de descripteur/génération. 31 premiers cas rouges avant code
(dont un cas de lien repris pour respecter le blocage existant de readiness).
141 tests ciblés réussis avec `-W error`, 2 xfail inchangés (passages et rétention).
CI complète à confirmer après publication.

Les budgets portent sur la **nouvelle lecture diagnostique**, pas sur l'ensemble
du rappel : readiness et les lectures existantes des candidats gardent leurs
propres limites. Ce n'est pas une borne RSS ni un timeout réseau. Une comparaison
complète coûte O(taille du corpus) sous verrou et devient inconnue au-delà du
budget. Les écritures non coopératives ne bénéficient pas d'un snapshot atomique
multi-fichiers. Le contrat d'un seul écrivain Qdrant coordonné demeure requis.
Aucun seuil d'ancienneté S1 choisi ; la tâche Claude reste distincte. Pas de
modèle sémantique, corpus privé, VM ou production activés.
