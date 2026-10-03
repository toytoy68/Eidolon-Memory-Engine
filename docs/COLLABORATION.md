# Collaboration asynchrone — Codex/GPT et Claude

Organisation demandée par toytoy le 2026-09-30. Codex poursuit le travail
autorisé ; Claude apporte des revues ponctuelles selon sa disponibilité.
Une revue non reçue n'est ni un accord ni un veto. Il n'y a pas de quota,
d'horaire ou de présence garantis par ce protocole.

## Canal actif GPT ↔ Claude

Depuis le 3 octobre 2026, les messages actifs courts sont dans
[collaboration/](../collaboration/README.md). ECHANGES.md conserve son historique
et les bilans des lots ; les demandes/réponses du nouveau canal sont archivées
séparément. Le [serveur MCP](COLLABORATION-MCP.md) permet à Claude de publier
uniquement sa réponse et son archive. Il ne lance aucun assistant. Son activation
HTTPS/OAuth et sa recette Claude Web restent distinctes de la livraison du code.

## Répartition des documents

- [ECHANGES.md](../ECHANGES.md) : questions, objections, preuves et réponses signées.
- [TODO-LIST.md](../TODO-LIST.md) : ordre de travail et statut réel des tâches.
- `docs/` et `schemas/` : contrats et décisions consolidés.
- Commits et tests : modifications exactes et preuves exécutables.

Ne pas transformer le fichier d'échanges en seconde TODO ou en copie complète
de la documentation. Référencer les tâches et commits. Pour un sujet terminé,
conserver la conclusion et ses preuves ; archiver les longs échanges dans
`docs/echanges/` si le volume le justifie, sans casser les liens.

## Début de session

1. Vérifier les instructions applicables, la branche, le commit et les
   modifications locales. Ne pas écraser le travail d'un autre intervenant.
2. Récupérer les références distantes si l'accès est disponible ; synchroniser
   un checkout propre par avance rapide. En cas de divergence, examiner le
   diff et préserver les changements, sans reset ou push forcé automatique.
3. Lire la reprise rapide, les sujets ouverts et les priorités du TODO.
4. Annoncer le lot pris en charge et son périmètre. Si un autre auteur travaille
   dessus, proposer une revue ou une tâche distincte ; une mention EN COURS
   est une indication, pas un verrou distribué.

Un assistant travaillant encore depuis un ZIP indique le nom de l'archive et
son commit de base s'il est connu ; il ne prétend pas être synchronisé avec Git.
Ne pas lui attribuer une réponse ou un test qui n'a pas été reçu.

## Travail et revue

Codex peut poursuivre les tâches autorisées sans attendre la prochaine session
de Claude. Regrouper les questions de revue à forte valeur : stockage, reprise,
formats, conflits et cohérence métier. Éviter de multiplier les petites demandes
qui consommeraient ses sessions disponibles.

Une revue propose : accord motivé, défaut reproductible, alternative avec
compromis, ou incertitude précisément délimitée. Un accord entre deux modèles
ne remplace pas un test. Mentionner séparément lecture du code, tests exécutés
par l'auteur, résultats rapportés et points non vérifiés sur VM/disque réel.

Les décisions déjà approuvées par toytoy restent la référence. Les choix
d'implémentation courants dans ce cadre ne nécessitent pas une nouvelle
approbation. Une contradiction avec ses contraintes ou un vrai choix métier
nouveau lui est présenté avec des options concrètes. Un problème bloquant
ne devient pas acceptable du seul fait de l'absence du relecteur.

Pour des modifications de code simultanées, utiliser des branches distinctes
depuis la base actuelle, par exemple `codex/t041-information-writes` et
`claude/review-t041`. Publier le commit ou la proposition de fusion à examiner.
L'intégrateur vérifie la base, le diff et les preuves avant fusion. Un auteur
travaillant seul peut poursuivre la branche autorisée après synchronisation.
Ne pas écraser les réponses précédentes lors de conflits sur ECHANGES.md.

## Fin de lot

Faire un commit cohérent, mettre à jour le statut TODO, référencer le résultat
dans ECHANGES.md et préciser ce qui reste ouvert. Publier selon l'autorisation
de la séance, puis vérifier que le contenu distant correspond. Une absence de
réponse Claude reste indiquée comme telle ; la clôture d'une implémentation
peut précéder sa revue indépendante, qui doit rester identifiable.

Les instructions de projet demeurent : pas de travail hors périmètre, pas de
micro-durcissements non demandés, preuve de test rouge sans la fonctionnalité
pour les changements exécutables, aucune étape VM comptée sans exécution et
aucune modification de l'estimation globale actuellement gelée.

## Message de reprise utilisable par toytoy

« Lis ECHANGES.md à la racine et les documents référencés. Vérifie le commit
actuel, puis prends un sujet disponible dans le périmètre autorisé. Indique
clairement tes constats, tes tests réellement exécutés et tes limites. Ajoute
ta réponse datée et signée, sans réécrire celle de l'autre intervenant. »

Le fichier ne lance ni ne réveille aucun assistant. L'accès au dépôt, le
démarrage d'une session et l'accès à la VM restent des capacités à constater.
