# J2 — Verrouillage coopératif et vérification Qdrant

Date : 14 octobre 2026. Branche de développement uniquement.

## État confirmé

- Base antérieure `77a20f23b` : 2298 tests Memory, 19 scénarios worker expérimental et 44 tests Qdrant réussis.
- Nouveau chemin `worker_upsert` : vérifie l'identité d'embedding, la révision du point Qdrant via `revision_for`, puis relit la source canonique et les permissions avant ACKNOWLEDGED.
- Commits `5ce6df3`, `bc27e4e`, `24081e4` : option `canonical_root` pour maintenir `exclusive_write` durant la lecture, l'upsert, le read-back et la revérification. La CI Qdrant du commit `24081e4` : 46 tests réussis, run 38565669677.
- La suite Memory complète de ce commit reste à confirmer (run 38565669688 au moment de la rédaction).

## Limites de sécurité

1. Le verrou est **optionnel** : les appels sans `canonical_root` restent disponibles pour les tests, et ne doivent pas être utilisés comme chemin de production.
2. Seuls les écrivains utilisant `exclusive_write` sur la même racine coopèrent ; les modifications hors protocole ne sont pas couvertes.
3. Le verrou peut rester tenu pendant une opération Qdrant lente : prévoir un budget d'exécution et une stratégie de reprise avant production.
4. L'index et le journal SQLite ne sont pas dans une transaction commune ; un ACK incertain ne doit pas clôturer une intention.
5. Le worker expérimental `IndexWorker` et le chemin `worker_upsert` ne partagent pas encore tous les scénarios du contrat.
6. Pas de suppression automatique, aucune donnée réelle indexée, aucun déploiement VM.

## Suite prioritaire

- Valider la suite complète Memory sur SHA final.
- Tester concurrence interprocessus avec l'écrivain canonique et les interruptions Qdrant.
- Définir le journal de reprise pour les états STALE et UNVERIFIED.
- Raccorder Core ↔ Memory sur environnement isolé, puis recette VM/PC B01–B12.
