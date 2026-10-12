# G202 — Indexation des passages et synchronisation durable

Date : 12/10/2026. Statut : contrat technique à implémenter et qualifier, **pas une fonctionnalité activée**.
Sources : contre-revue Claude C166 / patch 0007 et décisions G201.

## Constats
- QdrantIndex actuel produit un point par Information entière ; les archives de conversations n'ont pas de références de passage et sont donc exclues du mode index.
- Les résultats Qdrant sont des candidats : le Markdown canonique est relu avant toute citation.
- Une mutation canonique après reconstruction n'est pas automatiquement synchronisée. Le digest du snapshot peut devenir invalide ; ne pas prétendre à une couverture complète.
- Les scores d'embeddings synthétiques ne permettent pas de fixer un seuil d'abstention fiable.

## Architecture proposée
1. Découpage déterministe des documents canoniques en passages bornés avec chevauchement configurable ; ne pas couper les métadonnées de provenance.
2. Identité de passage stable par document, révision, version du découpeur et plage canonique ; empreinte du texte. La référence doit permettre de relire exactement le passage d'origine.
3. Qdrant conserve seulement des identifiants et métadonnées minimales (pas le texte privé), avec embedding_id incluant poids et prétraitement.
4. Recherche renvoie les candidats de passage ; Core/Memory relisent la source, vérifient identité, empreinte, version et droits avant de citer.
5. Toute modification canonique génère un événement durable dans une boîte de sortie transactionnelle, sans appeler Qdrant pendant l'écriture de la source.
6. Worker idempotent applique upsert/delete de passages ; progression, erreur et retard sont exposés. Reprise après interruption sans double effet.
7. Réconciliation compare manifeste canonique et index, puis reconstruit une génération isolée si nécessaire ; bascule atomique après validation. Anciennes générations conservées jusqu'à vérification de leur non-utilisation.
8. Modes explicites : INDEX_CURRENT, INDEX_PENDING, INDEX_STALE, INDEX_UNAVAILABLE. Aucun fallback lexical silencieux ; mode lexical explicite possible selon politique.
9. Abstention : calibrer sur jeu de développement distinct des 40 questions finales ; inclure négatifs, paraphrases et cas sans réponse. Relever rappel, précision et faux positifs par modèle d'embedding.

## Tests de réception
- Une archive longue est retrouvée par un passage précis et une citation canonique valide.
- Passage modifié ou supprimé : ancien candidat rejeté.
- Nouveau document avant indexation : INDEX_PENDING visible.
- Panne Qdrant : INDEX_UNAVAILABLE, aucune réussite inventée.
- Crash après écriture canonique et avant indexation : événement récupéré et appliqué une seule fois.
- Changement d'embedding_id : incompatibilité explicite et reconstruction requise.
- Deux générations et bascule : aucune référence orpheline utilisée.
- Question hors sujet : abstention calibrée sans masquer des faits pertinents.
- Test de rétention : aucune suppression d'une collection encore référencée.

## Frontières et ordre
Memory Engine possède le journal, les références de passages, le contrôle canonique et la synchronisation.
Core consomme les résultats et leur état de fraîcheur ; il ne modifie pas les index directement.
Qdrant reste reconstruisible. Ne pas modifier les références G182 ou les corpus figés.
Ordre : patch sondes 0007 après revue → passages → outbox → worker → calibration → recette sur corpus réel.
