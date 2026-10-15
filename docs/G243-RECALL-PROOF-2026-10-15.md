# G243 — Preuve des candidats au rappel, 15 octobre 2026

Base : Memory f029c9a1bd1b16916d4d03b9ca2dba75019bf62e (G242). Codex/GPT.

## Défaut et correction

Un Markdown modifié sans incrément de révision pouvait encore utiliser le score
sémantique de ses anciens octets. Le texte relu était actuel, mais le lien entre
ce texte et le vecteur n'était pas vérifié. Nouveau cas rouge reproduit.

Qdrant renvoie maintenant l'empreinte canonique et la génération de ses points
prouvés. Une preuve partielle, mal formée, d'un autre modèle, d'une autre
projection ou génération interrompt la requête. Un index déclarant une
reconstruction complète exige ces preuves ; leur suppression totale ne permet
pas de revenir silencieusement au mode historique sans preuve.

Le rappel compare l'empreinte aux octets canoniques relus par `CanonicalReader`
sous le verrou coopératif. Dérive : exclusion `INDEX_DIGEST_MISMATCH`. Lecture
impossible ou au-delà du budget par fichier : `INDEX_CANONICAL_UNVERIFIED`.
Les autres candidats restent utilisables. Les métadonnées de la preuve sont
conservées dans le classement de l'extrait. Un changement entre la lecture du
backend et la lecture prouvée est également refusé.

Les anciens upserts sans preuve restent compatibles, explicitement
`INDEX_UNVERIFIED` ; les doubles de test génériques sans empreinte gardent leur
contrat de relecture/révision. Il ne s'agit pas d'une migration silencieuse.
Le budget par fichier G242 s'applique aussi à cette nouvelle lecture de preuve ;
les budgets de diagnostic complet et de candidats sont distincts. Les anciennes
lectures backend/readiness ne deviennent pas globalement bornées dans ce lot.

## Validation

13 nouveaux cas isolés, dont 10 échecs au premier passage avant correctif et
un onzième défaut détecté ensuite (suppression de toutes les preuves).
154 tests ciblés réussis avec `-W error`, 2 xfail connus inchangés.
Trois scénarios supplémentaires sur serveur HTTP : état vide/périmé/reconstruit
avec redémarrage, dérive à révision égale puis reconstruction, preuve corrompue.
Ils sont explicitement ignorés localement faute de binaire et ajoutés à la CI
serveur dédiée. Résultats CI de ce lot à confirmer.

G242 : CI Qdrant ciblée et serveur réussies au moment de cette publication ;
suite complète encore en cours. Aucun corpus privé, modèle sémantique ou VM.

Premier passage serveur : 15 réussis et 3 échecs de harnais (client Qdrant 1.15.1
sans protocole context manager). Les trois nouveaux scénarios n'avaient donc pas
encore exécuté leurs assertions. Fermeture corrigée avec contextlib.closing ;
aucune modification applicative. CI ciblée G243 : 406 réussis +1 xfail Q2.
G242 confirmé complet : 2673 réussis, 15 ignorés, 4 xfail, 12 sous-tests ;
52 worker, 393 ciblés +1 xfail, 15 serveur. Comptes chevauchants.
