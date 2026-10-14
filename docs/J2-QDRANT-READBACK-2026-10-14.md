# J2 — Qdrant read-back checkpoint (14 octobre 2026)

## Modification

- `qdrant_index.py` : `revision_for(information_id)` récupère un point précis et contrôle l'identifiant, le type, la provenance et la révision.
- `worker_upsert.py` : après un upsert, le worker exige la présence du point et la révision attendue ; sinon résultat `UNVERIFIED`. La relecture canonique et les permissions restent ensuite vérifiées.
- Tests de l'adaptateur, du worker et des doubles de test mis à jour.

## Résultats vérifiés

GitHub Actions Qdrant isolé run `38548231826`, commit `77a20f23b8bd3550a97002446df09b4a6db8cd7a` : **44 passed**, 0 failed. Suite Memory complète sur ce SHA encore en attente lors de la rédaction.

## Limites P0

1. Une révision seule ne prouve pas que le contenu de l'index correspond au digest canonique ; le payload Qdrant ne contient pas encore une empreinte de contenu vérifiable.
2. Aucun verrou transactionnel commun n'existe entre écrivain Markdown et worker.
3. Le journal n'est pas avancé par `worker_upsert` : l'indexation ne constitue pas une réconciliation complète.
4. Le contrat de 19 scénarios couvre `IndexWorker` expérimental ; il reste à adapter à ce chemin d'upsert réel.
5. Aucun test VM/PC ni Qdrant de production n'a été effectué.

## Priorité suivante

Ajouter une preuve d'empreinte canonique dans le payload Qdrant, la relire, puis coordonner les écritures Markdown et les transitions du journal. Ne pas activer de suppression automatique ni déployer avant recette.
