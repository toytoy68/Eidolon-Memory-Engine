# Coût d’une passe d’entretien — T-049, mesure du 02/10

## Expérience reproductible

```sh
python -B -m tools.benchmark_maintenance \
  --sizes 50 150 300 --projects 5 --due-count 5 --repeats 3 \
  --output /tmp/maintenance.json
```

Chaque point utilise un moteur temporaire distinct. Les N Informations courtes
synthétiques sont créées via le writer canonique avec leurs Events/journaux.
Deux variantes : journaux COMMITTED avec snapshots (`live`) et reçus compactés
(`compact`). Les cinq Threads de fixture sont créés directement dans le stockage,
avec N liens CONCERNS répartis entre eux ; ce n’est pas une mesure d’ingestion
projet. Cinq échéances REACTIVATE concernent cinq Informations distinctes.
Toute la préparation est exclue des temps de passes et rapportée séparément.

Mesures successives sur chaque moteur : inspection de dérivés manquants,
première reconstruction avant échéance, trois passes inactives avant échéance,
une passe avec cinq échéances arrivées, puis trois rejeux inactifs. Les temps
inactifs présentés sont les médianes ; les rapports conservent tous les
échantillons et les temps par étape. La passe avec effets n’est mesurée qu’une
fois par moteur : elle ne fournit pas une distribution de latence.

L’instrumentation compte les ouvertures de fichiers réussies en lecture via
Path.open : JSON d’historique, Markdown canonique et dérivés. Ce ne sont pas des
lectures physiques du disque. Les temps incluent le coût de l’instrumentation.
Les contrôles sémantiques finaux sont hors mesure : égalité complète des N
Informations attendues, révision +1 des cinq seules cibles, contenu/provenance/
vérité inchangés, readiness prête et dérivés courants. Chaque rejeu vérifie
l’absence de nouvel effet ou reconstruction.

Filesystem local réchauffé par la préparation, Python 3.12.14, charge de l’hôte
non contrôlée. Ni cache froid, ni corpus réel, ni VM, ni coupure de stockage.
Les corpus sont supprimés ; seuls les rapports JSON sont conservés.

## Résultats sur `43a1214`

| Historique | Informations | Passe inactive, médiane de 3 | Cinq échéances, 1 mesure | Rejeu inactif, médiane de 3 |
| --- | ---: | ---: | ---: | ---: |
| Snapshots COMMITTED | 50 | 0,588 s | 1,070 s | 0,649 s |
| Snapshots COMMITTED | 150 | 1,861 s | 3,070 s | 1,801 s |
| Snapshots COMMITTED | 300 | 3,270 s | 5,543 s | 3,306 s |
| Reçus compactés | 50 | 0,515 s | 0,878 s | 0,528 s |
| Reçus compactés | 150 | 1,261 s | 2,114 s | 1,312 s |
| Reçus compactés | 300 | 2,454 s | 4,139 s | 2,598 s |

[Rapport brut](benchmarks/maintenance-before-2026-10-02.json), produit avant la
nouvelle demande d’audit. `before` nomme une référence avant optimisation ;
aucun rapport `after` ni gain livré n’existe. Les six corpus ont passé leurs
contrôles sémantiques. La comparaison n’isole pas l’effet du cache ou de la
charge de l’hôte : elle indique un coût local, pas une causalité précise ni une
prévision VM.

À 300 Informations avec cinq projets, une passe inactive ouvre 7 890 JSON
d’historique et 5 490 Markdown canoniques. Les deux variantes ont les mêmes
comptes d’ouvertures : compacter réduit les données à décoder, pas le nombre de
scans. Les étapes reprise, dispatcher, dossiers, catalogue et vérification
relisent une partie des mêmes fichiers alors qu’aucun effet n’est nécessaire.

Piste **non implémentée** : vérifier sous verrous qu’aucune reprise, échéance
arrivée ou projection périmée ne subsiste, puis rendre ce snapshot vérifié sans
appeler les écrivains. Aucun cache entre passes ni lecteur de journal allégé
ne serait nécessaire. Il faudra mesurer le gain, préserver la détection des
éditions sans révision et vérifier les courses avant de livrer cette sortie
rapide. Deux essais préparatoires ont été mis de côté lors de la demande
d’audit ; ils ne font pas partie de la suite publiée.

## Limites et suite

La lecture reste linéaire en taille d’historique et dépend du nombre de projets.
Les opérations avec effets conservent leurs contrôles complets. La compaction
ne supprime pas l’obligation de lire et vérifier les reçus. `limit` ne borne
que les échéances exécutées, pas les audits ni le temps sous verrous.

Suite utile : mesurer les projets et les corpus réels séparément ; concevoir
un annuaire reconstructible et un protocole de détection de divergence avant
de remplacer les scans. Une éventuelle sortie rapide n’autoriserait ni ingestion intensive ni
installation automatique d’un entretien récurrent.
