# G232 — Inventaire inverse et revue des orphelins, 14 octobre 2026

Auteur : Codex/GPT. Suite autorisée par toytoy à 21 h 32 Europe/Paris.
Base Memory : `bef722294aa5ac7481e851218a18b8e743845a9c`.

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
- CI complète Memory, contrat Qdrant ciblé et intégration Core : à confirmer
  sur les révisions publiées. Les limitations AF_UNIX locales connues ne sont
  pas assimilées à des échecs du runner Linux.

## Suite J2

Orchestration des scans et du worker, politique de reprise/revue, contrat complet
historique et identité du découpeur. La suppression effective reste désactivée.
Serveur Qdrant, corpus et modèles réels, contention/latence puis recette VM/PC
et contre-revue indépendante restent à qualifier.

Aucun daemon activé, corpus réel modifié, déploiement VM ni fusion main.
