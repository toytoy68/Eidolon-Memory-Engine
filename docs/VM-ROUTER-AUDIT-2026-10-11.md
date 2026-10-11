# Audit initial du routeur VM — 11 octobre 2026

## Sources réellement lues
Lecture MCP sur Memory, racine tools : context_router_v3.py (SHA256 3d8ccad793dec2ffbebbef4f5a272afcf45365f861bd7616afb5cb3899049ad3) et test_router_v3.py (SHA256 0e7247479834f2c65e28e9812e185d2a2c1fcc3bc816e16953e52e8ba36d8754).
Aucun script de recherche exécuté sur la VM. Reproduction locale limitée aux constantes et fonctions de classification extraites par AST ; aucun import du backend, aucune lecture du corpus.

## Résultat reproductible
Classification originale reproduite : 27/30. Ce résultat ne mesure ni la pertinence documentaire, ni la provenance, ni la validité temporelle.
Trois divergences :
- « Quel GPU équipe le serveur d'inférence ? » : attendu general, obtenu factual. L'attendu general est discutable pour une question sur le matériel effectivement utilisé.
- « Quels composants sont encore à installer ? » : attendu general, obtenu documentary. Le mot installer suffit à déclencher un mode procédure malgré la demande d'inventaire.
- « Quel était le projet GPU initial ? » : attendu historical, obtenu general. Initial et était ne sont pas reconnus.

Contre-exemples supplémentaires effectivement exécutés localement :
- « Quelle est la configuration actuelle en 2026 ? » → historical.
- « Comment installer le premier agent ? » → historical.
- « Quel GPU utilisions-nous avant ? » → factual.
- « Quelle sera la configuration en 2027 ? » → historical.
Toutes les années sont traitées comme historiques, sans distinction présent/futur. Le mot premier prime sur la procédure, indépendamment de son rôle grammatical.

## Recherche et limites
Le routeur réordonne au plus 171 candidats obtenus par ContextualRecall ; ce n'est pas une recherche hybride ni un Cross-Encoder.
Le mode classifié n'est pas transmis à recall(). Dans la copie Git auditée, recall() utilise operational par défaut et exclut notamment SUPERSEDED et EXPIRED : si la VM emploie cette même implémentation, le routeur historique ne peut pas récupérer les références filtrées en amont. À confirmer sur la version VM avant correction.
Aucune date at ni query_scope n'est transmise. Le classement ajoute des bonus thématiques/types, sans valider lui-même la chronologie.
Les scores retournés dans item.score restent les scores du rappel initial, alors que l'ordre est déterminé par un nouveau score : l'explication du classement est incomplète.
Le benchmark affiche seulement deux identifiants par question ; aucune assertion sur les documents attendus ou interdits. Le nombre 171 est fixe : couverture et coût à vérifier lorsque le corpus grandit.

## Étape d'exécution à préparer
Une commande de benchmark identifiée et auditée, sans shell ni argv libres. Exécution sous utilisateur dédié, sur copie expérimentale du corpus, avec durée, ressources et taille de sortie bornées. Les lectures ContextualRecall peuvent créer des fichiers de verrouillage ; ne pas présenter l'exécution comme absolument sans écriture.
Une évaluation indépendante devra séparer classification, pertinence top-k, sources, actualité, abstention et latence. Les scripts hybrides et Cross-Encoder restent à inventorier et auditer.
