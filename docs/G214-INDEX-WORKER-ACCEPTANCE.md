# G214 — Protocole de validation du worker de synchronisation

Date : 13 octobre 2026. Statut : contrat de réception, aucune exécution Qdrant activée.

## Pipeline obligatoire

1. **Planifier** : journal d'intentions et manifeste canonique vérifiés, état Qdrant observé, absence explicitement prouvée par ABSENT ; une clé manquante signifie INCONNU.
2. **Vérifier** : relire le fichier canonique au moment de l'action, comparer révision et empreinte, appliquer les permissions de profil et vérifier la version du découpeur et de l'embedding.
3. **Agir** : effectuer uniquement l'opération Qdrant autorisée, attendre l'accusé de réception, revalider l'état puis avancer le journal. Si l'issue est incertaine, ne pas annoncer un succès.
4. **Réconcilier** : comparer périodiquement les manifestes canoniques et l'index ; jamais de suppression aveugle d'une collection active.

## Politique de suppression

Aucune suppression automatique pendant la première recette. Une décision ENQUEUE_DELETE est seulement une proposition. Elle exige une absence canonique prouvée, les permissions adaptées et une vérification indépendante immédiatement avant l'effet. Une lecture échouée, un résultat tronqué ou un état inconnu bloque l'opération.

## Tests bloquants

- Crash après écriture d'intention, avant renommage canonique.
- Crash après renommage, avant publication.
- Crash après publication, avant écriture Qdrant.
- Crash après écriture Qdrant, avant accusé de réception.
- Deux workers concurrents, verrouillage et idempotence.
- Modification canonique pendant la génération des embeddings.
- Permissions de profil modifiées entre planification et action.
- Qdrant inaccessible ou accusé de réception perdu.
- Source non lue, supprimée ou remplacée par un lien symbolique.
- Changement de modèle d'embedding ou de version du découpeur.
- Journal tronqué et horloge système modifiée.
- Ancienne génération encore lue pendant une bascule.

## Critères de promotion

Aucune écriture Qdrant réelle tant que les tests isolés et la revue croisée n'ont pas validé les invariants. Recette VM après rétablissement MCP, avec sauvegarde vérifiée, environnement de test isolé et rollback documenté. Ne pas modifier les corpus d'évaluation figés.
