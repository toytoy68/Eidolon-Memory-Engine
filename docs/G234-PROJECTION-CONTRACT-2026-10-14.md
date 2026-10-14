# G234 — Identité de projection et qualification du chemin réel

Auteur : Codex/GPT, 14 octobre 2026. Base : `26976e3de795b0cd184e3abbac3536517857cb50`.
Code publié : `274c3fc6ce95434f6fc759eb9a1cb4c6c211dabf`.

## Résultat et preuves

L'adaptateur Qdrant identifie explicitement sa projection ; le worker vérifie
la compatibilité persistée avant toute récupération du journal. 32 nouveaux cas
sur Markdown, SQLite et Qdrant local. Les 28 premiers échouaient avant la
fonctionnalité ; deux défauts complémentaires ont été reproduits séparément
(changement canon pendant autorisation et curseur avançant sur incompatibilité).

Après correction : **247 tests ciblés réussis**, 8,36 s, Python 3.12,
`-W error`. Un test historique injectant une erreur « après écriture » au deuxième
appel du lecteur a été corrigé pour déclencher après l'effet effectivement
observé, indépendamment du nombre de relectures. Son assertion est conservée.
Les 32 nouveaux cas sont inclus dans les 247, pas additionnels.
CI du code publié confirmée :

| Validation | Résultat |
| --- | --- |
| [Memory complet](https://github.com/toytoy68/Eidolon-Memory-Engine/actions/runs/38638977007) | **2502 tests et 12 sous-tests réussis**, 92,34 s |
| Worker expérimental, même workflow | **19 réussis**, 1,01 s ; interface historique avec doubles |
| [Qdrant et workers](https://github.com/toytoy68/Eidolon-Memory-Engine/actions/runs/38638976951) | **247 réussis**, 13,25 s |

Comptes chevauchants, non additionnés. Intégration Core épinglée sur ce SHA :
`833fea3d3041bf80a214045c4c7f8f64797c7d89`,
[run](https://github.com/toytoy68/Eidolon-Bootstrap-Framework/actions/runs/38639019833)
en cours lors de cette rédaction ; résultat consolidé dans PROJECT-STATUS Core.

## Identité persistée et incompatibilité

Le descripteur passe au **schéma 2**, avec
`projection_id="information-content-json-v1"`. Cette identité est fixe dans
l'implémentation : un point par Information, contenu chaîne inchangé ou JSON
trié, `ensure_ascii=False`, `allow_nan=False`, séparateurs Python par défaut.
Les poids et le prétraitement de l'embedding restent décrits par `embedding_id`.
Ce n'est **pas** un index de passages ; taille et chevauchement de découpeur ne
sont pas des options acceptées par cet adaptateur.

La projection est aussi inscrite dans les points vérifiés et contrôlée lors de
la relecture et de l'inventaire. Les points sans digest restent non vérifiés.
`IndexEvidence` reste lié à la génération dont l'adaptateur vérifie le descripteur ;
il n'est pas une preuve autonome portable entre adaptateurs/projections.
Les appels publics refusent un descripteur incompatible avant leur effet.
Les embeddings constituent une fenêtre possible de changement : upsert, requête
et publication du rebuild recontrôlent alors descripteur et génération.
Un rebuild interrompu peut conserver une génération intermédiaire non publiée.

`JournalUpsertWorker` exige désormais `active_generation()` sur son adaptateur.
Une incompatibilité persistée donne `INDEX_INCOMPATIBLE`, une panne de lecture
`INDEX_UNAVAILABLE`, y compris avant INTENT → PUBLISHED. La ligne qui rencontre
une incompatibilité en cours de page reste au curseur pour une future reprise.
Les scanners existants peuvent encore rapporter une erreur de descripteur comme
`INDEX_UNAVAILABLE` ; ils refusent l'action, sans diagnostic plus précis dans ce lot.

La relecture canonique après le callback d'autorisation empêche une écriture
périmée lorsqu'il change le document. Les contrôles après l'effet restent requis.
Ces observations ne sont pas une transaction distribuée : coordination externe
des écrivains de droits/alias et verrou coopératif du canon toujours nécessaires.

## Ancien index : reconstruction explicite, aucune migration silencieuse

Le schéma 1 est refusé, même avec `create=True`. Aucun descripteur ancien n'est
réétiqueté et aucune donnée existante n'est supprimée. Avant une future activation :

1. Arrêter/coordonner les écrivains du corpus et de l'index.
2. Créer un **nouvel alias isolé** via le nouvel adaptateur ; reconstruire depuis
   une capture canonique arrêtée, avec le modèle explicitement identifié.
3. Vérifier inventaire, comptage, permissions et relecture canonique ; reconstituer
   les preuves via le worker si nécessaire (le rebuild classique ne les fournit pas).
4. Raccorder explicitement l'hôte à cet alias et à de nouveaux checkpoints, après
   recette. Conserver l'ancien index et les anciens checkpoints pour diagnostic.

Cette procédure est préparatoire, non exécutée sur serveur/VM. Changer seulement
le champ `schema` ou copier les anciens points ne vaut pas reconstruction.

## Correspondance des 19 scénarios historiques

La recette inchangée `tests/claude_memory_eval/test_worker_reference_g214.py`
utilise toujours ses doubles et son interface expérimentale. Le nouveau chemin
utilise `JournalUpsertWorker`, le lecteur ancré, Qdrant local et les scanners.
Le tableau donne des preuves **d'invariants**, pas une compatibilité d'API.
Préfixes : J = `tests/test_worker_journal.py`, P = `tests/test_index_projection.py`,
O = `tests/test_orphan_scan.py`, M = `tests/test_index_maintenance.py`.
Les noms ci-dessous omettent uniquement le préfixe `test_`.

| N° | Scénario historique | Preuve du chemin réel et écart |
| --- | --- | --- |
| 1 | Nominal et rejeu | J `verified_upsert_advances_real_journal_and_replay_is_noop` |
| 2 | Canon illisible | J `unreadable_or_missing_canon_never_promotes_journal` ; aucune absence déduite |
| 3 | Absence et proposition de suppression | O `resumed_orphans_are_review_only_and_reappearance_invalidates` ; J `deletion_is_deferred_without_deleting_or_acknowledging`. Écart : revue distincte et toute intention DELETE en attente bloque la candidature ; pas de `proposed_deletions` dans le worker |
| 4 | Réapparition avant proposition | O `reappearance_during_point_read_prevents_candidate` |
| 5 | Arrêt après index avant journal | J `process_death_after_point_write_recovers_from_disk` : mort réelle, Qdrant sur disque, reprise sans embedding |
| 6 | Canon publié avant état PUBLISHED | J `interrupted_canonical_publication_recovers_in_two_rounds` ; état interrompu construit, pas une mort au renommage dans ce test |
| 7 | Arrêt avant renommage, grâce puis revue | P `missing_intent_before_publication_stays_for_review_at_any_age`. **Écart ouvert** : UNVERIFIED à tout âge ; pas de WAIT 600 s puis CLOSE_ABANDONED |
| 8 | Index indisponible puis retour | P `descriptor_outage_blocks_even_intent_recovery_then_recovers` ; J `index_read_failure_has_no_journal_effect` |
| 9 | Canon change entre décision et effet | P `canonical_change_inside_authorization_prevents_stale_effect` ; aucune écriture périmée |
| 10 | Deux révisions rapides | J `canon_changed_during_embedding_keeps_old_intent_pending` ; dernière indexée, ancienne en revue |
| 11 | Profil sans droits | J `rights_must_be_exactly_true` |
| 12 | Deuxième worker occupé | J `writer_lock_makes_other_worker_busy` et `writer_in_another_process_blocks_worker` |
| 13 | Accusé perdu | J `lost_ack_stays_pending_then_recovers_without_reembedding` |
| 14 | Canon change pendant calcul | J `canon_changed_during_embedding_keeps_old_intent_pending` ; journal non clôturé, point ancien possible puis réconcilié |
| 15 | Droits révoqués avant effet | P `rights_revoked_before_action_prevents_effect` |
| 16 | Modèle ou découpeur incompatible | P `incompatible_descriptor_stops_journal_before_any_effect` ; projection entière explicite, modèle altéré et `passage-v1` refusés |
| 17 | Journal tronqué | J `truncation_and_backwards_clock_refuse_before_effect` ; `run_once` refuse. API paginée distincte G233 pour les grands arriérés |
| 18 | Horloge en arrière | Même test J ; mode paginé reporte chaque ligne future, contrat distinct de `run_once` |
| 19 | Deux workers concurrents | J `two_workers_do_not_duplicate_the_effect` |

Autre **écart structurel ouvert** : le worker réel ne passe pas par
`preview_reconciliation` puis `worker_preflight.preflight`. Il applique ses gardes
par intention avec relectures et comparaison conditionnelle du journal. Aucun
adaptateur artificiel n'a été ajouté pour annoncer que les 19 tests historiques
qualifient ce pipeline. La contre-revue doit examiner et consolider ce contrat
réel, notamment les écarts 3 et 7, avant de clore « contrat complet ».

## Suite et limites

Relecture indépendante Claude lancée par toytoy ; demande et bases publiées dans
Core `collaboration/GPT-TO-CLAUDE.md`. Aucun résultat nouveau reçu à cette étape.
Restent : consolidation du contrat réel et décisions de revue, raccordement aux
mesures de l'hôte, index de passages éventuel, recette serveur Qdrant/corpus et
modèles réels, puis VM/PC. Aucune qualification réseau, sémantique ou coupure
électrique déduite de Qdrant local. Suppression et activation runtime inchangées.
