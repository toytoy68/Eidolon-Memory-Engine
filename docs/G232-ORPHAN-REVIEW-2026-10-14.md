# G232 — Inventaire inverse et revue des orphelins, 14 octobre 2026

Auteur : Codex/GPT. Suite autorisée par toytoy à 21 h 32 Europe/Paris.
Base Memory : `bef722294aa5ac7481e851218a18b8e743845a9c`.

## Qualification du code publié

Révision Memory testée : `e4d38ee3d4b56ec0a24ddec9939b2466ec5b9af4`.

| Validation | Résultat observé |
| --- | --- |
| [Memory complet](https://github.com/toytoy68/Eidolon-Memory-Engine/actions/runs/38625545805) | **2430 tests et 12 sous-tests réussis**, 98,74 s |
| Worker expérimental, même workflow | **19 réussis**, 1,16 s ; contrat distinct du scanner/consommateur |
| [Qdrant/worker/scanners ciblés](https://github.com/toytoy68/Eidolon-Memory-Engine/actions/runs/38625545759) | **175 tests réussis**, 7,61 s |

Les lots ciblés et complets se chevauchent ; leurs comptes ne s’additionnent pas.

## Livraison

`OrphanScan` parcourt les points Information de l’alias Qdrant géré, dans une
génération concrète. Un checkpoint SQLite privé conserve les observations et
le curseur dans la même transaction. Chaque appel traite une page bornée ; une
coupure avant commit refait toute la page, une coupure après commit reprend à
la suivante. Aucun corps Markdown ni vecteur n’est copié dans le checkpoint.

Le scanner ne produit ni intention DELETE ni appel de suppression. Les candidats
sont des observations destinées à une revue humaine ; aucun exécuteur ne les
accepte automatiquement. `review_page()` relit les conditions présentes plutôt
que de restituer comme valides les anciens verdicts du checkpoint.

## Contrôles

- `QdrantIndex.inventory_page()` parcourt la collection concrète sans filtre
  pouvant masquer un point étranger. Il ignore seulement le descripteur réservé.
  Identité UUID déterministe, type Information, révision, provenance et ordre du
  curseur sont contrôlés. Une page invalide est refusée intégralement ; son
  curseur n’avance pas. Les points historiques sans digest sont visibles mais
  ne deviennent pas candidats à la suppression.
- `CanonicalReader.proven_absent()` vérifie le nom exact via un descripteur de
  la racine, sans suivre les liens. Toute entrée, même répertoire, FIFO, lien
  pendant ou Markdown illisible, signifie présente. Seul ENOENT sur la feuille
  peut prouver son absence ; racine indisponible/remplacée, permissions et autres
  erreurs ne sont jamais converties en absence.
- Toute intention encore en attente pour l’identité bloque le candidat, même
  au-delà de la première page du journal. Un historique terminal ne suffit pas
  à bloquer une observation actuelle.
- Les droits `index.delete` doivent répondre exactement True avec le profil
  attendu. Ils sont revérifiés après lecture du point. Le point doit conserver
  sa révision, son SHA-256 canonique, son modèle et sa génération observés.
- Absence, droits, journal et point sont relus lors de la revue. Un document
  réapparu, un point modifié/retiré, des droits révoqués ou une nouvelle intention
  retirent le statut de candidat. Une bascule de génération impose un nouveau passage.
- Le checkpoint est lié à la racine et au journal physiques, à l’alias, au modèle
  et aux profils. Un journal, y compris via un lien physique, ne peut servir de
  checkpoint. Les deux scanners G231/G232 utilisent des fichiers distincts.

## API et états

```python
scan = OrphanScan(checkpoint, journal, canonical_root=root, index=index,
                  authorize=authorize, profile_id=profile,
                  expected_profile_id=expected_profile,
                  expected_model_id=model)
report = scan.run_page(limit=100)
review = scan.review_page(after=-1, limit=100)
# Pour continuer la revue : after=review.next_after, si non None.
# Pour un nouveau passage explicite : scan.run_page(restart=True).
```

| État du parcours | Conduite |
| --- | --- |
| RUNNING | Appeler de nouveau pour la page suivante |
| EXHAUSTED | Fin du curseur observée ; prochain passage avec `restart=True` |
| LIMIT_REACHED | Budget de points atteint ; aucune page tronquée/validée ; relever explicitement le budget ou revoir le périmètre |
| INDEX_UNAVAILABLE | Page entière à refaire ; aucune progression sur cette page |
| INDEX_INCOMPATIBLE | Modèle différent de celui attendu |
| RESTART_REQUIRED | Génération remplacée ; l’appel suivant recommence le passage |
| BUSY | Verrou canonique occupé ; réessayer plus tard |

La revue répond REVIEW et fournit des observations paginées : DELETE_CANDIDATE,
CANONICAL_PRESENT, ABSENCE_UNKNOWN, PENDING_JOURNAL, POINT_CHANGED,
PROVENANCE_MISSING ou FORBIDDEN. NOT_STARTED indique un checkpoint sans passage.
Les erreurs d’index/contexte/génération ne produisent aucune liste partielle de
candidats. `observed_candidates` est un compte historique du parcours ; seule
la revue relit la situation actuelle. Même une revue fraîche n’accorde pas un
droit durable de suppression.

## Budgets et limites

100 points au plus par appel par défaut, maximum 999 ; 100 000 observations par
checkpoint par défaut. Le descripteur compte dans la page Qdrant mais pas dans
les observations Information. Le journal garde son schéma existant.

Le scroll Qdrant n’est pas un instantané : une insertion derrière le curseur
peut attendre le prochain passage. EXHAUSTED ne certifie pas un inventaire global
immuable ni une synchronisation complète. Pour un inventaire exhaustif stable,
les écrivains de l’index doivent être coordonnés/arrêtés pendant le passage.

Les écrivains canoniques doivent respecter le verrou partagé ; ceux des droits
et de l’alias exigent aussi une coordination externe. Les observations ne sont
pas une transaction distribuée. Un futur exécuteur de suppression devra refaire
ses propres contrôles sous coordination, appliquer une décision de revue et
prouver l’effet sur le point exact. Il n’est pas livré ici.

Le verrou canonique couvre les lectures réseau d’une page. Leur latence et le
coût de recherche d’intentions sur un gros journal restent à mesurer. Les points
par passages et les collections étrangères ne sont pas pris en charge par ce
scanner Information ; une collection mélangée est refusée, pas nettoyée.

## Preuves exécutées

- Trois tests initialement rouges : API d’absence, inventaire et scanner absents.
- 185 tests ciblés réussis avec `-W error`, puis 44 tests propres au lot réussis
  après ajout du contrôle interdisant toute mutation index/journal. Comptes chevauchants.
- Markdown réel, SQLite réel, moteur Qdrant local en mémoire et sur disque ;
  vecteurs synthétiques, aucun téléchargement de modèle.
- Deux morts réelles de sous-processus (`os._exit(73)`), avant/après commit de la
  page ; réouverture du checkpoint et de Qdrant sur disque, reprise sans doublon.
- Réapparition pendant lecture, racine déplacée pendant contrôle, permissions,
  FIFO/liens, intention au-delà des 100 premières, révocation et bascule d’alias.
- Point remplacé à même révision, provenance historique, points étrangers,
  curseur répété/désordonné, page surdimensionnée, limite atteinte et concurrence.
- CI complète Memory et contrat Qdrant ciblé : réussis sur la révision publiée
  (table ci-dessus). Aucun test masqué ; les six restrictions AF_UNIX locales
  connues ne se reproduisent pas sur le runner Linux. Intégration Core suivie
  dans son bilan consolidé.

## Raccordement suivant — non implémenté dans G232

Le contrôleur devra conserver séparément les deux checkpoints et appeler des
étapes bornées, avec reprise différée hors verrou pour BUSY/INDEX_UNAVAILABLE.
Une intention récupérée passe d’abord à PUBLISHED : le worker G230 a besoin d’un
appel ultérieur pour l’indexer. DONE décrit un appel, pas une file synchronisée ;
les motifs `deferred` restent à traiter/revoir.

Point à résoudre avant activation : le worker actuel refuse une file dépassant
sa limite complète (TRUNCATED, maximum 999). La limite de 100 du scanner G231
évite de remplir davantage sa propre file, mais ne borne pas les autres
producteurs. Il faut donc qualifier la consommation paginée d’un arriéré et
l’absence de famine derrière des intentions à revoir, avant de brancher un
ordonnanceur. Augmenter simplement la limite ne résout pas un arriéré arbitraire.

Le contrôleur ne devra pas relancer `restart=True` à chaque étape, ni interpréter
EXHAUSTED/COMPLETE comme une permission de suppression. La revue des orphelins
reste distincte des upserts. Les horaires/inactivité d’exploitation seront
raccordés explicitement ; aucun cron ou service permanent n’est créé par ce lot.

## Suite J2

Orchestration des scans et du worker, politique de reprise/revue, contrat complet
historique et identité du découpeur. La suppression effective reste désactivée.
Serveur Qdrant, corpus et modèles réels, contention/latence puis recette VM/PC
et contre-revue indépendante restent à qualifier.

Aucun daemon activé, corpus réel modifié, déploiement VM ni fusion main.
