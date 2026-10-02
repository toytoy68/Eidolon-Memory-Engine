# Catalogue reconstructible v1 — T-045

`core.indexing.catalogue.InformationCatalogue(root)` produit
`memory/catalogue/information-v1.json` depuis les Informations, les liens CONCERNS
des Threads et les reçus de suppression. Ce fichier dérivé peut être détruit puis
reconstruit à l'identique sur les mêmes sources. Il ne remplace pas IndexPort,
le rappel contextualisé ou les fichiers canoniques.

## Contrat et commandes

```sh
python -B -m core.indexing.catalogue_cli --root RACINE status
python -B -m core.indexing.catalogue_cli --root RACINE rebuild
python -B -m core.indexing.catalogue_cli --root RACINE query pompe --availability LOW
python -B -m core.indexing.catalogue_cli --root RACINE query --project-id refroidissement
```

API : `status()`, `rebuild()`, `query(text='', limit=20, project_id=None,
availability=None, epistemic_status=None)`. Les filtres sont exacts. Une recherche
vide liste les fiches ; une recherche textuelle utilise lexical_v1 sur leurs
métadonnées, avec score et explication. L'ordre est score décroissant puis ID.

Chaque fiche expose ID/révision/SHA-256, pointeur relatif vers le canonique,
type, nature déclarée, mots-clés, contexte, statut épistémique, état opérationnel,
rétention, disponibilité déclarée, temporalité complète, projets liés et état
de suppression. Le corps de l'Information et les extensions arbitraires ne sont
pas copiés. Les métadonnées peuvent elles-mêmes contenir du texte sensible et
ne sont pas bornées en taille. Aucun résumé ni mot-clé n'est inventé.

La disponibilité est `metadata.availability` lorsqu'elle est déclarée ; sinon
elle reste nulle. HIGH/INTERMEDIATE/LOW ne sont ni activés ni inférés depuis la
rétention. Une fiche LOW est aussi retrouvable que les autres. Les projets
proviennent des liens canoniques, pas d'une ressemblance lexicale.

## Fraîcheur et reprise

`status` ne crée aucun verrou ni fichier : copie arrêtée requise pour une lecture
stable. Il retourne MISSING, CURRENT, STALE ou CORRUPT. `rebuild` et `query`
tiennent Persistent → Thread lorsqu'il existe ; la publication prend ensuite
le verrou Catalogue. Les verrous techniques peuvent être créés par ces deux
appels, sans modification de canonique, Event ou journal.

La readiness doit être valide. Le digest intègre les fichiers Information,
Threads et reçus de suppression pertinents ; la comparaison porte aussi sur
l'intégralité de la projection attendue. Une édition directe sans augmentation
de révision est détectée. `query` refuse tout catalogue absent, périmé ou corrompu
et ne le répare jamais implicitement. Les résultats sont issus de la projection
canonique vérifiée ; aucun ancien extrait du catalogue n'est restitué.

Une demande PENDING_DELETE modifie la fraîcheur et exclut la fiche des recherches
après reconstruction. CANCELLED la rend à nouveau retrouvable. Après suppression
approuvée puis reconstruction, la fiche et ses anciens mots-clés disparaissent.
Avant reconstruction, l'ancien fichier peut encore contenir ses métadonnées,
mais l'API query le refuse. Ceci n'est pas une clôture globale de purge.

Le remplacement JSON est atomique et vérifié après publication. Une panne
avant publication laisse l'ancien état détectable ; après publication, une
relance constate CURRENT. Il n'y a pas de rejeu d'écriture canonique. Une
reconstruction explicite remplace également un catalogue corrompu, mais refuse
les chemins symboliques et les sources incohérentes.

Le CLI retourne 0 pour CURRENT/REBUILT/UNCHANGED, 1 pour MISSING/STALE/CORRUPT
ou un blocage. Il n'installe aucun job de rattrapage automatique.

## Limites assumées et preuves

Cette version fournit une découverte par métadonnées, pas une accélération
démontrée : la fraîcheur est vérifiée par scan complet avant toute recherche.
Les sources sont décodées pour construire les fiches mais leurs corps ne sont
ni indexés ici ni placés en contexte. Coût des scans/verrous à mesurer avant
un corpus important. Les éditeurs legacy doivent être arrêtés. Le classement
ne juge ni l'applicabilité temporelle ni la vérité : utiliser ContextualRecall
pour sélectionner des extraits opérationnels. Aucun connecteur Qdrant.

16 nouveaux cas dans `tests/test_information_catalogue.py` ; groupe catalogue/
manifeste/index : 28 réussis. Reconstruction identique après destruction,
correction/suppression sans anciens mots-clés, annulation, projets, édition
directe, corruption, readiness, deux interruptions par exception, arrêt réel
de processus, CLI, symlink et disponibilité non inférée. Retirer la barrière
de fraîcheur, le filtre PENDING_DELETE ou readiness donne 1 + 1 + 1 échec
comportemental ; code restauré. Pas de validation VM ni coupure électrique.

Depuis T-046, les fiches exposent aussi `recheck_required` ; tout changement
de disponibilité/revue invalide la projection et demande rebuild explicite.
