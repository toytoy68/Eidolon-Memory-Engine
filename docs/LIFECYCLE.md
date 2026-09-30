# Cycle de vie mémoire — premier audit en lecture seule

Les champs `retention` et `valid_until` répondent à deux questions
différentes. La rétention exprime une politique de conservation à définir ;
`valid_until` indique la fin déclarée d'une période d'applicabilité.
Une Information dont la période est terminée peut rester utile pour son
historique, une contradiction, une décision ou une recherche passée. Aucun de
ces champs ne déclenche une suppression.

Sur une copie arrêtée et sauvegardée de la racine du moteur :

```sh
python -m core.information.lifecycle_audit \
  --root /chemin/vers/copie \
  --at 2026-09-29T12:00:00+02:00
```

La date `--at` doit indiquer son fuseau. L'outil valide le manifeste de
source, refuse les liens symboliques sur le chemin de stockage, puis compare
l'empreinte de chaque fichier relu à celle du manifeste. Il rend seulement les
nombres de politiques de rétention déclarées (`missing` et `invalid` inclus),
les nombres de périodes `ended`, `not_started`, `within_known_bounds`, `unknown`
ou `invalid`, l'heure
de référence et l'empreinte globale. Il n'affiche pas de contenu ni d'ID et
n'écrit pas de fichier. Ce contrôle n'est pas un instantané atomique si un
autre processus modifie la copie pendant l'exécution.
La table `retention_by_applicability` croise aussi ces deux déclarations : elle
permet de distinguer, par exemple, une mémoire `PERMANENT` dont la période
est `ended` d'une mémoire temporaire encore dans ses bornes. Chaque document
compte une seule fois dans cette table ; aucune case ne déclenche une action.
La table `epistemic_by_applicability` croise séparément le statut épistémique
déclaré (`missing` et `invalid` inclus) avec la même période. Elle permet
d'examiner les souvenirs réfutés ou conflictuels sans confondre fin de validité
et preuve de fausseté, et sans modifier le classement de recherche.
L'outil compare `valid_from` et `valid_until` avec `--at` ; il signale une
période contradictoire ou une date sans fuseau comme `invalid`. Une seule borne
connue peut suffire à `within_known_bounds`, ce qui ne prouve pas que
l'Information est vraie ou applicable dans tous les contextes.
Le rapport compte également les groupes de contenus textuels **exactement**
identiques et le nombre de documents qu'ils réunissent. Les empreintes de
contenu restent internes au calcul et ne sont pas affichées. Un contenu
identique peut représenter plusieurs observations ou provenances : ce comptage
ne conclut pas qu'une fusion est correcte et ne modifie aucune relation.
Pour une revue locale explicite, l'API Python
`preview_exact_duplicates(persistent_root)` dans
`core.information.consolidation` renvoie les IDs de chaque groupe de corps
identiques et les noms des champs divergents (`revision`, `metadata`,
`provenance`, `temporal`, `verification`, `relations`). Elle vérifie la source
contre le manifeste et n'écrit rien. Les IDs ne sont pas inclus dans la sortie
de la commande d'audit ; traiter la prévisualisation Python comme une donnée
potentiellement privée. Des textes identiques avec des statuts ou provenances
différents restent des Informations distinctes jusqu'à décision explicite.

Avant une consolidation ou un oubli, il faudra décider explicitement :
comment conserver provenance et preuves, comment traiter les relations et
révisions, comment identifier les contradictions, quelle archive restaurable
produire, qui peut autoriser une suppression et comment la reprendre après
interruption. Les valeurs `TEMPORARY` ou `DISPOSABLE` ne suffisent pas à elles
seules à décider une date de suppression.
L'approbation core d'une suppression refuse désormais une Information ciblée
par une relation structurée d'une autre Information, sous le verrou du stockage
Persistent. Les relations ambiguës, documents illisibles et liens symboliques
bloquent également la suppression. Le scanner ne déduit pas des références
textuelles cachées dans un corps libre ; la migration historique et ses
relations textuelles restent à examiner avant déploiement.
Une relation sortante du document supprimé, y compris vers lui-même, disparaît
avec ce document ; elle ne bloque donc pas sa propre suppression. Les autres
Informations sont inspectées avant le retrait.
La reprise d'un reçu `APPLYING_DELETE` refait ce contrôle. Si une relation vers
la cible apparaît après un retrait interrompu, le reçu reste bloqué pour revue
humaine au lieu d'être déclaré terminé. Les écrivains directs actuels ne
valident pas encore toutes les cibles lors de leur création ; cette frontière
reste à traiter avant une ouverture aux agents.
Une écriture core refuse désormais une relation structurée vers l'identité
d'une Information déjà retirée et réservée par un reçu de suppression. Si la
cible existe encore pendant une demande en attente, le lien est autorisé et
l'approbation de la suppression est bloquée par le contrôle des relations.
Les références dans le corps libre et les anciens écrivains ne sont pas
couverts par ce contrôle.
L'audit des reçus signale `cancelled_without_information` si une annulation a
perdu sa cible. Pour `PENDING_DELETE`, il distingue
`pending_without_information`, `invalid_information` et
`pending_revision_conflict` ; ces résultats sont des blocages à examiner,
jamais des réparations automatiques.

Sur une copie arrêtée, un inventaire distinct aide à mesurer cette frontière :

```sh
python -m core.information.relation_audit --root /chemin/vers/copie
```

Il vérifie les Informations core et leur empreinte, puis compte les relations
vers une Information présente, vers le document lui-même, vers une cible
**externe ou absente**, ainsi que les cibles invalides ou contradictoires.
Une cible externe peut désigner un objet non Information ; le rapport ne la
qualifie donc pas automatiquement de lien cassé. Il ne révèle ni ID, ni texte
et ne modifie aucun document.
