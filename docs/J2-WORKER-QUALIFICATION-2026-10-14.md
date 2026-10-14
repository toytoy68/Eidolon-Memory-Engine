# J2 — Qualification worker Memory (14 octobre 2026)

## Preuves de test

- GitHub Actions run `38538438365` sur `00d589b700a160c9f2e37a54a37caee766a557f9` : **2290 passed**, 12 sous-tests réussis ; contrat du worker expérimental : **19 passed**.
- Qdrant isolé run `38538220267` : **36 passed**, sur la même révision.
- Des commits ultérieurs ont ajouté les contrôles de changement canonique après écriture, de révocation des permissions et d'identité d'embedding de l'adaptateur. Ils exigent une nouvelle qualification sur leur SHA final.
- Ces résultats concernent des doubles de test et Qdrant en mémoire, pas la VM de production.

## Architecture du prototype

`CanonicalReader` lit le Markdown ; `worker_upsert.apply_upsert` vérifie révision, SHA-256, profil, autorisation et modèle, effectue un seul upsert, puis relit le canon et les droits. `worker_gate` est une preuve pure, pas une autorisation d'exécution. `QdrantIndex` maintient des index dérivés reconstruisibles. Les suppressions sont interdites.

## Limitations bloquantes pour production

1. Pas de verrou commun entre lecteur worker et écrivain canonique : une modification pendant l'upsert peut laisser un point obsolète ; le retour STALE exige réconciliation.
2. Pas de garantie transactionnelle entre l'accusé Qdrant, la relecture canonique et la transition du journal.
3. Le callback d'autorisation et le lecteur canonique doivent provenir de services de confiance et être liés à la bonne identité de profil.
4. Pas encore de vérification de read-back du point indexé après upsert dans le nouveau chemin `worker_upsert`.
5. Les 19 scénarios testent le worker expérimental `IndexWorker`, pas nécessairement le chemin `worker_upsert` contre Qdrant.
6. Le déploiement VM, la sauvegarde et la recette Core ↔ Memory ↔ PC restent à effectuer.

## Prochaines priorités

P0 : verrouillage partagé et idempotence ; preuve de read-back de l'index ; adaptation du contrat de 19 scénarios au chemin réel ; suites vertes sur SHA final. P1 : recette VM jetable, puis intégration Core.
