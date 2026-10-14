# G231 — Balayage canonique reprenable, 14 octobre 2026

Auteur : Codex/GPT. Base : `5d5c7b0702c9c5a9f0add9b4b464a208fb2e690b`.
Suite autorisée par toytoy à 21 h 08 Europe/Paris.

## Qualification du code publié

Révision Memory testée : `855a9eb325a306543afdf7a703fb8b37ec739c9b`.

| Validation | Résultat observé |
| --- | --- |
| [Suite Memory complète](https://github.com/toytoy68/Eidolon-Memory-Engine/actions/runs/38622854670) | **2386 tests et 12 sous-tests réussis**, 96,01 s |
| Worker expérimental, même workflow | **19 réussis**, 1,24 s ; contrat distinct du scanner/consommateur G230 |
| [Qdrant/worker/scanner ciblés](https://github.com/toytoy68/Eidolon-Memory-Engine/actions/runs/38622854503) | **131 réussis**, 9,20 s |

Les six échecs locaux passent sur le runner Linux ; aucun test n’a été masqué.
Les lots se chevauchent : ne pas additionner leurs comptes.

## Fonctionnement livré

`ReconciliationScan` inventorie les fichiers Information `*.md` au premier niveau
de la racine persistante pour retrouver les upserts
absents du journal. Il lit les preuves Qdrant et ajoute des intentions ; il n'écrit
pas de point et ne supprime rien. Le consommateur G230 conserve ses relectures et
ses contrôles avant indexation.

- Un checkpoint SQLite privé conserve la liste des identifiants, révisions et
  SHA-256 canoniques complets, le curseur, la génération Qdrant et les raisons de revue.
  Aucun corps Markdown n'est recopié dans ce checkpoint.
- L'inventaire utilise le lecteur par descripteur, sous le verrou des écrivains.
  Le contexte est lié à la racine physique, au journal physique, à l'alias,
  au modèle et au profil. Une réutilisation pour un autre contexte est refusée.
- Chaque page revalide le document, les droits et la génération avant l'ajout.
  Une intention identique encore en attente est réutilisée atomiquement ; une
  suppression en attente, une révision plus récente ou un digest contradictoire
  exige une revue. L'historique terminal n'empêche pas de réparer un point perdu.
- Le commit du journal précède le commit du curseur. Une interruption dans cet
  intervalle refait la lecture et retrouve la même intention, sans doublon.
- Une comparaison complète des inventaires initial et final détecte les ajouts,
  retraits et modifications derrière le curseur, y compris à révision identique.
  Une divergence impose un nouveau passage, sans jeter les intentions déjà enregistrées.
- La capacité de file est contrôlée dans la transaction du journal. À saturation,
  le curseur reste sur le document non enregistré ; le passage reprend après
  consommation ou revue de la file. Pas de troncature ni de clôture automatique.

## États et conduite du passage

| État | Signification et suite |
| --- | --- |
| RUNNING | Page traitée ; appeler de nouveau pour la suivante |
| VERIFYING | Toutes les lignes ont été examinées ; l'appel suivant vérifie l'inventaire complet |
| COMPLETE | Passage canonique terminé sans ligne de revue ; les intentions peuvent encore attendre le worker |
| REVIEW_REQUIRED | Passage terminé avec des refus/conflits consultables par `issues(limit=...)` |
| RESTART_REQUIRED | Source ou génération modifiée ; l'appel suivant démarre un nouveau passage |
| JOURNAL_FULL | Traiter/revoir la file, puis rappeler au même curseur |
| INDEX_UNAVAILABLE | Preuve indisponible ou invalide ; rappeler après résolution, sans effet Qdrant |
| INDEX_INCOMPATIBLE | Modèle configuré incompatible ; corriger le contexte avant toute suite |
| BUSY | Un écrivain possède le verrou ; rappeler plus tard |

Un passage terminé reste historique : `restart=True` demande explicitement le
passage périodique suivant. COMPLETE ne certifie ni un index entièrement synchronisé,
ni des droits permanents, ni une transaction distribuée. Les preuves de points sont
observées au moment de chaque page ; des modifications ultérieures de l'index
nécessitent le passage suivant.

## Budgets et coût assumé

Par défaut : 100 documents par page, au plus 100 intentions en attente admises par
ce producteur, 100 000 entrées de répertoire, 8 Mio par fichier, 256 Mio de sources
par inventaire. Les entrées non Markdown comptent dans le budget de répertoire.
Dépasser un budget refuse le traitement ; cela ne valide jamais un inventaire tronqué.

Les pages sont bornées, mais les captures initiale/finale parcourent toute la
collection autorisée sous verrou. Leur coût est proportionnel à sa taille ; la
mesure sur le corpus réel reste à faire. Des modifications continuelles peuvent
empêcher la fin d'un passage. Les écrivains canoniques, de droits et d'alias doivent
respecter la coordination commune. Un journal est affecté à une seule configuration
d’indexation active ; des modèles/alias servis indépendamment nécessitent des
journaux dédiés. Ce lot ne crée pas une file multi-index.

Le budget de file par défaut correspond au lot de 100 du worker G230. Si ce budget
est relevé, la limite du worker doit être ajustée explicitement, au maximum 999.
Une file remplie d'intentions nécessitant une revue ne se vide pas automatiquement.

## Preuves locales

- Trois tests rouges sans les nouvelles API, puis verts après implémentation.
- 146 tests ciblés réussis avec `-W error`, puis 33 cas propres au scanner réussis
  avec `-W error` après ajout d'une vérification du checkpoint. Comptes chevauchants.
- Reprise entre pages après reconstruction de l'objet depuis SQLite.
- Mort réelle d'un sous-processus après commit de l'intention et avant commit du
  curseur : journal intact, curseur précédent conservé, reprise sans doublon.
- Fichier ajouté/modifié derrière le curseur, modification à révision égale,
  suppression avant sa page, source modifiée pendant la lecture de l'index.
- File pleine puis vidée, droits retirés, génération remplacée avant/pendant la
  page, ancien point, point historique sans preuve, conflit de digest/journal.
- Deux scanners concurrents, contexte différent, limites d'entrées/octets,
  lien symbolique et checkpoint dont le curseur ou l'état final est incohérent.

Suite complète locale avant le dernier cas de checkpoint : **2379 tests et 12 sous-tests réussis, 6 échecs**, 95,92 s. Les six échecs sont les restrictions AF_UNIX/Manager déjà observées en G229/G230 ; aucun n’est masqué. La CI Linux a ensuite qualifié le code final publié (table ci-dessus).
Qdrant utilise ici son moteur local en mémoire ou sur disque, avec des vecteurs
synthétiques. Ce n'est pas une recette du serveur ni une mesure de pertinence.

## J2 restant

1. Inventaire inverse des points orphelins : absence canonique prouvée, réapparition
   et proposition de suppression sous revue. Ce lot parcourt les documents existants.
2. Orchestration périodique du scanner et du worker, ordonnanceur de reprise/revue,
   contrat historique complet des 19 scénarios et identité du découpeur.
3. Qualification serveur Qdrant, bascules/lecteurs concurrents, modèles réels et
   coût du verrou sur le corpus réel ; contre-revue indépendante puis recette VM/PC.

Aucun daemon activé, corpus réel modifié, déploiement VM ou fusion main.
