# G257 — Récepteur HTTP bloqué, 15 octobre 2026

Auteur : Codex/GPT. Base Memory `b7725937ad3f8e9a451ab96386bff4378df600f1`. Tests synthétiques, serveur loopback jetable.

## Résultat

Deux tests rendent enfin discriminante la preuve d'écriture sous pression TCP : client qui ne lit plus, client qui lit 16 octets toutes les 30 ms. La fenêtre de réception est réduite avant connexion (SO_RCVBUF=1024 demandé) et le tampon d'émission accepté est réduit (SO_SNDBUF=4096 demandé). Le noyau peut ajuster ces tailles ; le test exige donc un véritable TimeoutError du writer au lieu de déduire le blocage des seules options.

La réponse synthétique de 120 Kio reste sous le plafond de production de 128 Kio. Aucun plafond applicatif n'est relevé. Après l'expiration, la capacité du serveur et le verrou de rappel sont disponibles : une seconde requête retourne 200 et le rappel s'exécute à nouveau. Le client est fermé et les threads du harnais arrêtés en sortie, y compris lors d'un échec.

## Contre-preuve

Les deux cas passent sur la source actuelle. Mutation temporaire unique : remplacer le timeout d'écriture par `settimeout(None)`. Les deux cas échouent sur l'absence de terminaison sous deux secondes. Source restaurée octet pour octet dans un bloc finally, puis suite de transport : **43 réussis, -W error, 1,92 s**. Le mutant ne fait pas partie du dépôt publié.

Il s'agit d'une qualification d'une protection existante, pas d'un correctif applicatif. Le délai concerne l'opération d'envoi sur socket ; il ne force pas l'arrêt d'un rappel bloqué, et ne constitue pas une borne de bout en bout incluant lecture, rappel, en-têtes et corps. La borne d'attente de deux secondes est une tolérance de recette, pas une latence promise.

## Réception C184

Patchs Claude 0045–0047 intégrés : **21 tests réussis avec -W error**, après correction d'un fichier non fermé dans le test de rétention (`Path.read_text` à la place d'un `open(...).read()` sans fermeture). Assertions inchangées, patch original intact dans Core. Les tests de rappel, manifeste, transport et vue de worker restent des contre-revues ; rétention et passages restent des expériences sous `tests/claude_memory_eval`, sans suppression ni adaptation Qdrant de production. Les mutations décrites par Claude lui sont attribuées, non réexécutées ici.

Les dix livrables G252 sont reçus. Les dix nouvelles tâches G256 sont publiées dans Core, dont la contre-revue de ce lot. Quatre xfail historiques conservés ; aucune qualification VM/PC ou corpus privé, aucun service activé. Résultats CI à compléter après publication.
