# G240 — Réponse HTTP perdue et arriéré de 1200 documents

Codex/GPT, 15 octobre 2026. Base applicative G239
`fb1b78d4a0adad2f90b0078cd874405258a0511d`.

## Risques restant à qualifier après G238

G238 vérifiait une exception injectée après un vrai acquittement serveur. Les
nouveaux cas coupent réellement le transport entre worker et serveur : un proxy
de test, à cible loopback fixe, reçoit l'acquittement `completed` du serveur puis
soit ferme la connexion sans réponse, soit retient cette réponse au-delà du délai
client. Le worker doit conserver PUBLISHED et reprendre par relecture du point,
sans deuxième embedding. Le proxy ne peut choisir sa cible depuis une requête,
ne journalise pas les corps ou clés, borne requêtes/réponses et s'arrête en finally.
Il ne fait partie d'aucun paquet applicatif.

Un autre scénario arrête le vrai serveur au milieu d'une page de deux intentions :
la première reste INDEXED, le curseur reste avant la seconde, puis la reprise
indexe uniquement la seconde. Il distingue un préfixe acquitté de la ligne incertaine.

Enfin, 1200 documents Markdown et intentions PUBLISHED sont traités via HTTP,
avec pages de 100 et checkpoints durables, puis le serveur redémarre. Le test
exige 1200 points, zéro pending, un seul embedding par document et aucun nouvel
embedding sur rejeu. Le maximum d'appels du harnais est fini (400 ticks) ; ce
n'est pas un budget de durée réseau du produit ni un benchmark sémantique.

## Réception

Quatre nouveaux cas, treize avec G238, dans le même workflow serveur. Collecte
initiale impossible sans le nouveau proxy, puis treize cas explicitement ignorés
localement faute de binaire. **Ne pas annoncer la recette G240 réussie avant le
résultat CI.** Aucun code applicatif modifié dans ce lot ; le pin d'intégration
Core reste sur le dernier code applicatif G239.

Le choix de 1200 reprend l'arriéré local déjà testé par Claude : il ne qualifie
pas une charge de production, un modèle réel, les limites RAM globales ou la
concurrence multi-écrivains. Tous les fichiers, vecteurs, clés et serveurs sont
synthétiques et temporaires dans le job GitHub. Aucun accès à la VM ou G182.

## Première exécution et correction du harnais

Le workflow 38663756814 donne 11 réussis et 2 échecs (68,93 s). Backlog 1200 et panne milieu de page réussis. Le proxy coupait le premier PUT de descripteur, avant le point attendu : défaut du scénario, pas échec de reprise constaté du worker. G241 distingue les réponses descriptor/information et leurs coûts de reprise, avec 15 cas au total. [Détail et preuves](G241-C181-INTEGRATION-2026-10-15.md). Résultat corrigé encore attendu.
