# Coût d’une passe d’entretien — T-049, mesures du 02/10

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

## Référence historique sur `43a1214`

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
aucun rapport `after` n’existait à cette étape ; les optimisations livrées
ensuite sont mesurées ci-dessous. Les six corpus ont passé leurs
contrôles sémantiques. La comparaison n’isole pas l’effet du cache ou de la
charge de l’hôte : elle indique un coût local, pas une causalité précise ni une
prévision VM.

À 300 Informations avec cinq projets, une passe inactive ouvre 7 890 JSON
d’historique et 5 490 Markdown canoniques. Les deux variantes ont les mêmes
comptes d’ouvertures : compacter réduit les données à décoder, pas le nombre de
scans. Les étapes reprise, dispatcher, dossiers, catalogue et vérification
relisent une partie des mêmes fichiers alors qu’aucun effet n’est nécessaire.

## Optimisation des passes

La sortie rapide et les phases de lecture partagées sont livrées dans ce lot :

- Quand aucune reprise ni échéance arrivée n’est connue, le moteur vérifie sous
  les verrous Persistent/Thread que dossiers et catalogue sont courants. Si oui,
  il retourne cette inspection complète et n’appelle pas les écrivains.
- Pendant la réparation des dérivés, un audit readiness complet réussi est
  partagé. Les dossiers n’effectuent plus leurs scans de journaux par projet
  après cet audit global plus strict. Les sources et leurs hashes restent lus.
- La vérification finale ouvre une **nouvelle** phase : elle réaudite les
  journaux, dossiers et catalogue depuis le disque. Elle ne reprend pas la
  preuve de l’étape de publication.

`settled_read_phase` est interne, limitée à un bloc synchrone détenant les
verrous canoniques. Le contexte est propre au thread/contexte, lié à une racine,
réinitialisé même sur exception, et n’enregistre que les audits réussis. Les
rapports rendus sont copiés ; l’appelant ne peut pas modifier la preuve partagée.
Une publication atomique dans Persistent ou history invalide la preuve avant
remplacement ; une écriture de dérivé ne l’invalide pas. Les chemins équivalents
avec `..` sont normalisés lexicalement, sans suivre un alias symbolique pour
réutiliser un audit. Aucun cache ne survit à la phase ou à la passe.

L’inspection autonome reste sans écriture et n’installe pas de cache partagé :
sans verrous, le moteur ne peut pas supposer que les journaux restent fixes.
Un rebuild isolé conserve ses propres gardes. Une nouvelle échéance, corruption
ou modification directe entre deux passes est relue ; les modifications
externes ignorant les verrous pendant une phase restent hors du contrat.

Les parcours à cinq échéances et à 25 échéances sont mesurés sur des corpus
neufs comparables, avec les mêmes contrôles de contenu/révision/readiness.
Les rapports `maintenance-optimization-*` et `maintenance-load-*` désignent
la base `5296cc8` et sa version modifiée avant commit ; leurs labels identifient
l’implémentation. Le script de benchmark est identique. Les médianes concernent
les trois passes inactives/rejeux ; les durées avec effets restent des mesures
uniques. Ne pas les transformer en débit garanti.

## Comparaison relancée sur la base `5296cc8`

Les durées ci-dessous proviennent d’une nouvelle référence mesurée, distincte
des premières valeurs sur `43a1214`. Un worktree séparé conserve la base inchangée.
Aucun test lourd ne tournait pendant les mesures finales optimisées ; certains
tests ciblés ont tourné pendant la référence initiale. Charge de l’hôte et caches
non contrôlés : les comptes de fichiers sont plus stables que les temps.

| Historique | Informations / projets | Inactive avant → après | Cinq échéances avant → après | Première reconstruction avant → après |
| --- | ---: | ---: | ---: | ---: |
| Snapshots | 50 / 5 | 0,525 → 0,079 s | 0,998 → 0,335 s | 1,035 → 0,271 s |
| Snapshots | 150 / 5 | 1,387 → 0,260 s | 2,403 → 1,018 s | 2,213 → 0,775 s |
| Snapshots | 300 / 5 | 2,691 → 0,375 s | 4,611 → 1,421 s | 4,480 → 1,393 s |
| Reçus compactés | 50 / 5 | 0,532 → 0,074 s | 0,909 → 0,292 s | 0,689 → 0,232 s |
| Reçus compactés | 150 / 5 | 1,336 → 0,193 s | 1,844 → 0,715 s | 2,254 → 0,552 s |
| Reçus compactés | 300 / 5 | 1,964 → 0,358 s | 3,380 → 1,558 s | 3,165 → 1,156 s |

Rapports complets : [référence](benchmarks/maintenance-optimization-before-2026-10-02.json),
[optimisé](benchmarks/maintenance-optimization-after-2026-10-02.json).
À 300/5, ouvertures JSON d’historique : **7 890 → 1 230** en passe inactive
(−84,4 %) et **13 180 → 4 605** pour cinq échéances (−65,1 %).

### Charge supplémentaire : 300 Informations, 25 projets, 25 échéances

```sh
python -B -m tools.benchmark_maintenance --sizes 300 --projects 25 \
  --due-count 25 --repeats 3 --history live --output /tmp/maintenance-load.json
```

| Passe | Avant | Après |
| --- | ---: | ---: |
| Première reconstruction | 16,744 s | 1,600 s |
| Inactive (médiane) | 8,168 s | 0,532 s |
| 25 échéances (un passage) | 18,843 s | 4,064 s |
| Rejeu inactif (médiane) | 7,399 s | 0,610 s |

Ouvertures JSON : **20250 → 1350** sans effet ; **46550 → 11275** avec 25 échéances.
Rapports : [référence en charge](benchmarks/maintenance-load-before-2026-10-02.json),
[optimisé en charge](benchmarks/maintenance-load-after-2026-10-02.json).
Les quatre rapports incluent une empreinte des sources core : SHA-256 du JSON
compact des couples triés `[chemin relatif, sha256(octets)]` des fichiers `.py`.
Tous les corpus vérifient l’égalité des Informations attendues, les révisions,
la readiness et les dérivés. Les écritures canoniques ne sont pas supprimées
pour obtenir ce gain.

## Validation

15 nouveaux cas, groupe ciblé de 52 réussis. Suite complète après correction :
**962 réussis, cinq échecs de sockets Manager avant scénario, 44,98 s** ; aucun
désélectionné. Cache borné à une phase et une racine, rapports non modifiables,
verrous exigés, invalider après publication, sortie sur exception, relecture
finale fraîche, correction directe et écrivain concurrent vérifiés. Le cas
chemin symbolique suivi de `..` est refusé avant toute réutilisation de preuve.
Les anciens tests de reprise, notes humaines, arrêts réels et courses restent
verts. Retirer partage/invalidation/fraîcheur donne 1 + 1 + 1 assertions rouges ;
code restauré. Sortie inactive rouge sur la base ; cas symbolique reproduit
rouge puis corrigé avant livraison. Aucun essai VM ou coupure physique.

## Limites et suite

La lecture reste linéaire en taille d’historique et dépend du nombre de projets.
Les opérations avec effets conservent leurs contrôles complets. La compaction
ne supprime pas l’obligation de lire et vérifier les reçus. `limit` ne borne
que les échéances exécutées, pas les audits ni le temps sous verrous.

Suite utile : mesurer les projets et les corpus réels séparément ; concevoir
un annuaire reconstructible et un protocole de détection de divergence avant
de remplacer les scans. Ces optimisations n’autorisent ni ingestion intensive ni
installation automatique d’un entretien récurrent.

## Lots bornés pour les échéances — base `72f4033`

Nouvelle comparaison avec le même script et les arguments 300 Informations,
25 projets, 25 échéances, trois répétitions inactives et historique live.
La base est conservée dans un worktree séparé ; la variante optimisée ajoute
[les lots Information](INFORMATION-BATCHES.md). Les deux rapports identifient
leur variante et le SHA-256 core avec la convention indiquée plus haut.

| Passe ou étape | Avant lots | Après lots |
| --- | ---: | ---: |
| Inactive (médiane de 3) | 0,509 s | 0,545 s |
| 25 échéances, passe entière (1 mesure) | 4,156 s | 1,770 s |
| Dispatcher seul dans cette passe | 3,134 s | 0,519 s |
| JSON d'historique ouverts, passe entière | 11 275 | 3 775 |
| Markdown canoniques ouverts, passe entière | 6 600 | 6 600 |

Les effets canoniques et leur contrôle final sont conservés. Chaque échéance
possède toujours son journal durable ; les réservations Information sont lues
une fois par tranche de 100 au plus et actualisées après chaque effet.
Aucun gain n'est attendu sur la passe inactive déjà optimisée. Le verrou
Persistent extérieur reste détenu pendant tout `run_due` et MaintenancePass ;
la tranche borne la réutilisation des réservations, pas la durée du verrou.

Rapports : [avant](benchmarks/maintenance-batches-before-2026-10-02.json),
[après](benchmarks/maintenance-batches-after-2026-10-02.json). Les contrôles
finaux confirment les 300 objets attendus, readiness prête et dérivés courants.
Des tests ciblés ont tourné au début de la préparation de la référence ; aucun
test lourd pendant la variante optimisée. Filesystem réchauffé, hôte non
contrôlé, un seul passage avec effets : aucune garantie de latence VM.

## Index de réservations facultatif

Les mesures d'entretien ci-dessus conservent les scans des réservations, avec
ou sans lots selon leur date. Le nouvel [index](RESERVATION-INDEX.md) est raccordé
au dispatcher mais n'a pas fait l'objet d'une nouvelle comparaison temporelle
de passe complète. Son gain mesuré concerne les écritures individuelles et
par lots. Les audits globaux et la vérification finale d'entretien restent
complets ; aucun gain additionnel de passe inactive n'est revendiqué.
