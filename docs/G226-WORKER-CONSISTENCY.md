# G226 — Worker J2 : cohérence après écriture et conditions de promotion

Date : 14 octobre 2026. Statut : tests isolés, aucun déploiement.

## Résultat

- Le worker `apply_upsert` vérifie maintenant à nouveau le document canonique et les permissions **après** l'accusé d'écriture de l'index.
- Si la révision, l'empreinte ou les droits changent, il renvoie `STALE` plutôt que `ACKNOWLEDGED`.
- Si la relecture échoue après écriture, l'exception remonte : état incertain, sans succès annoncé et sans nouvelle tentative automatique.
- Aucun chemin de suppression n'est ajouté.

## Limite de sécurité importante

La double relecture **ne fournit pas d'atomicité**. Le canonique peut encore changer entre les contrôles ; un autre worker peut intervenir, et le client Qdrant peut perdre un accusé. Le déploiement exige un verrou partagé avec les écrivains canoniques, une vérification d'index en lecture après écriture, un contrôle des versions du modèle/du découpeur et un protocole de reprise du journal. Le booléen `verified` n'est pas une autorisation.

## Prochaines priorités

1. Valider la CI complète Memory et Qdrant sur SHA final G226.
2. Introduire un contrat explicite de verrouillage entre writers et worker, puis des tests multiprocessus.
3. Vérifier les 19 scénarios worker sur la version réellement raccordée, pas uniquement l'expérimentale.
4. Relecture Qdrant après upsert avant toute transition INDEXED du journal.
5. Recette VM/PC B01–B12 après rétablissement MCP et sauvegardes.

Pas de fusion main ni d'activation de service.
