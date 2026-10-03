# Mesures VM synthétiques du 3 octobre 2026

Ces mesures portent sur le commit `4a11c71`, Python 3.13.5, VM
`Eidolon-Memory` (quatre processeurs logiques disponibles). Les outils existants
sont exécutés séquentiellement, sans tests concurrents lancés par cette séance.
Les corpus jetables sont créés par TemporaryDirectory puis supprimés. Les
résultats/logs restent dans [benchmarks/vm-2026-10-03](benchmarks/vm-2026-10-03/environment.json).
Aucune donnée du moteur actif ni de la sauvegarde originale n’est utilisée.

Attention : `/tmp` est un montage **tmpfs** sur cette VM. Les premières mesures
quantifient le traitement des journaux et l’accès aux fichiers sur ce montage,
pas la latence du disque ext4 de la racine. L’instrumentation compte les
ouvertures de fichiers réussies, pas les lectures physiques. Les caches sont
chauds ; la charge extérieure de la VM n’est pas contrôlée. Aucune extrapolation
à un corpus réel, une durée de production ou un disque froid n’est justifiée.

## Protocole reproductible

Trois répétitions indépendantes des deux commandes suivantes, chacune recréant
son propre corpus avant chaque variante :

```sh
MEMORY_ENGINE_ROOT=/tmp/em-benchmark-unused PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python -B -m tools.benchmark_information_batches \
  --sizes 100 300 --incoming 25 --output /tmp/batches-run-1.json
MEMORY_ENGINE_ROOT=/tmp/em-benchmark-unused PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python -B -m tools.benchmark_reservation_index \
  --size 300 --incoming 25 --output /tmp/index-run-1.json
```

Comparer CREATE et UPDATE, commandes individuelles et lot de 25, journaux
complets et reçus compactés, index désactivé/activé. La préparation (création
et compaction du corpus) et la construction initiale de l’index sont chronométrées
séparément. Après chaque variante : égalité des objets canoniques attendus et
audit Information sans problème. Les audits finaux sont exclus des compteurs.

L’entretien utilise quatre corpus neufs (100/300 × live/compact), cinq Threads,
cinq échéances et trois passes de répétition à vide/rejeu par corpus :

```sh
MEMORY_ENGINE_ROOT=/tmp/em-benchmark-unused PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python -B -m tools.benchmark_maintenance \
  --sizes 100 300 --projects 5 --due-count 5 --repeats 3 \
  --output /tmp/maintenance.json
```

Chaque corpus vérifie les révisions/contenus exacts après cinq effets, le rejeu
sans effet supplémentaire, la readiness finale et la fraîcheur des dérivés.
Les Threads de fixture sont écrits directement hors mesure : cela ne mesure pas
le coût métier de leur création. Les médianes des passes à vide portent sur le
même corpus, alors que les répétitions des écritures utilisent des corpus neufs.

Les scopes historiques imprimés par les outils mentionnent « local / no VM ».
Les JSON conservés indiquent le contexte réellement observé et gardent le texte
original dans `original_scope`. Le manifeste conserve commandes, commit, hashes
du code et SHA256 des rapports/logs ; cette annotation ne transforme pas une
mesure synthétique en validation de données réelles.

## Limites opérationnelles

T-049 reste partiel : l’index réduit les validations mais conserve l’énumération
et la lecture des octets ; le coût cumulé croît avec les antécédents. Les coûts de
préparation et compaction ne doivent pas être cachés derrière le temps du lot.
Aucun seuil arbitraire d’ingestion intensive n’est déclaré satisfait.
Aucun service, corpus réel, client externe ou coupure électrique n’est validé.

## Résultats sur tmpfs

Médianes de trois corpus indépendants ; 300 antécédents, 25 CREATE.

| Historique | Mode | Index | Médiane | Étendue | Scans | Ouvertures JSON | Construction index |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| compact | batch | non | 0.077951 s | 0.076306–0.079594 s | 1 | 350 | 0.000000 s |
| compact | batch | oui | 0.046527 s | 0.045839–0.046878 s | 1 | 350 | 0.051705 s |
| compact | single | non | 1.111571 s | 1.090815–1.124918 s | 25 | 7850 | 0.000000 s |
| compact | single | oui | 0.275718 s | 0.270502–0.277109 s | 25 | 7898 | 0.050917 s |
| live | batch | non | 0.093317 s | 0.093274–0.093508 s | 1 | 350 | 0.000000 s |
| live | batch | oui | 0.045888 s | 0.045673–0.046036 s | 1 | 350 | 0.067736 s |
| live | single | non | 1.517871 s | 1.508333–1.538617 s | 25 | 7850 | 0.000000 s |
| live | single | oui | 0.275547 s | 0.272081–0.278580 s | 25 | 7898 | 0.067017 s |

Le lot strict passe de 25 scans à un seul. L’index déjà construit réduit les
validations ; il conserve les ouvertures pour comparer les octets et en ajoute
même sur les commandes individuelles (7 898 contre 7 850). Construire l’index
est un coût distinct : l’addition de ce coût peut annuler le gain du premier lot.
La préparation des 300 reçus compactés prend environ 15 s, loin devant le lot.
Les 84 mesures d’écriture ont toutes un audit sans problème et l’égalité exacte
des 100/125/300/325 objets attendus. [Détail et variations](benchmarks/vm-2026-10-03/summary.json).

| Entretien | Historique | À vide (médiane) | Cinq échéances | Rejeu (médiane) |
| ---: | --- | ---: | ---: | ---: |
| 100 | live | 0.091263 s | 0.271284 s | 0.095855 s |
| 300 | live | 0.251739 s | 0.727358 s | 0.257340 s |
| 100 | compact | 0.074446 s | 0.223001 s | 0.079134 s |
| 300 | compact | 0.203818 s | 0.581334 s | 0.209132 s |

Les quatre corpus terminent ready=true avec dérivés actuels et tous les objets
canoniques vérifiés. Chaque répétition à vide/rejeu n’ajoute aucun effet métier.
À 300, une passe à vide ouvre encore 1 230 JSON historiques et 2 135 Markdown
canoniques (100 : 430 et 735). Le partage des lectures n’élimine pas ce coût.
Ces observations ne valident pas une fréquence d’entretien en production.

## Extension : 1 000 antécédents et stockage ext4

Le lot suivant part de `08f0284`, confirmé sur GitHub avant démarrage ; le code
core est identique à celui des premières mesures. Trois répétitions indépendantes
mesurent 25 CREATE en batch, avec/sans index, pour live/compact : 1 000 antécédents
sur tmpfs, puis 300 sur le volume ext4 de la racine. Les corpus ext4 sont créés
sous un dossier `tmp/em-vm-bench-*` dédié de ce dépôt, puis supprimés ; aucune
lecture/écriture du répertoire mémoire actif n’a lieu.

Le point à 1 000 isole la croissance des scans ; le point ext4 distingue le
support de fichiers. Ce ne sont pas des mesures de lectures physiques du disque,
et les caches de l’hôte/hyperviseur ne sont pas contrôlés. Les compteurs portent
sur les ouvertures de fichiers et les validations logiques, comme précédemment.
La construction de l’index et la préparation sont toujours séparées.

Pour reproduire exactement les charges sélectionnées, utiliser l’API existante
`tools.benchmark_information_batches.run(size, 25, history, 'create', 'batch',
reservation_index=indexed)`, pour `history` dans `('live', 'compact')` et
`indexed` dans `(False, True)`, trois fois avec corpus neufs. `size=1000` utilise
le tempfile par défaut (/tmp tmpfs ici) ; pour `size=300` ext4, fournir un TMPDIR
neuf sous un parent ext4 avant le démarrage du Python. Le runner de cette séance
sélectionne uniquement CREATE/batch ; le CLI reservation-index mesure également
single et UPDATE, donc son ensemble de charges est plus large.

| Support / antécédents | Historique | Index | Médiane du lot | Étendue | Préparation | Construction index | JSON ouverts |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| ext4 / 300 | compact | non | 0.308451 s | 0.274893–0.322319 s | 21.465864 s | 0.000000 s | 350 |
| ext4 / 300 | compact | oui | 0.268084 s | 0.246138–0.269656 s | 21.318789 s | 0.063348 s | 350 |
| ext4 / 300 | live | non | 0.302016 s | 0.300534–0.311646 s | 3.142427 s | 0.000000 s | 350 |
| ext4 / 300 | live | oui | 0.251664 s | 0.249943–0.261616 s | 2.957146 s | 0.082497 s | 350 |
| tmpfs / 1000 | compact | non | 0.170881 s | 0.169221–0.172204 s | 154.829268 s | 0.000000 s | 1050 |
| tmpfs / 1000 | compact | oui | 0.062659 s | 0.062367–0.064456 s | 154.559687 s | 0.167541 s | 1050 |
| tmpfs / 1000 | live | non | 0.217938 s | 0.217900–0.219085 s | 2.249297 s | 0.000000 s | 1050 |
| tmpfs / 1000 | live | oui | 0.063263 s | 0.063187–0.065335 s | 2.222462 s | 0.219365 s | 1050 |

Les 24 points supplémentaires vérifient chacun les 1025 ou 325 objets exacts
et un audit sans problème. Le code core et les hashes des rapports/logs sont
contrôlés indépendamment ; les dossiers temporaires ext4 ont été supprimés.
[Manifeste de cette extension](benchmarks/vm-2026-10-03/extension-environment.json).

À 1000, le lot ouvre 1050 JSON contre 350 à 300. La compaction individuelle
de préparation atteint une médiane d’environ 155 s, contre environ 15 s à 300
sur tmpfs. Le lot seul reste inférieur à 0,22 s. Construire l’index avant le
premier lot coûte suffisamment pour dépasser le lot strict dans ces points.
Ces mesures orientent le prochain lot vers la compaction bornée et ses scans ;
elles ne livrent pas encore cette réduction.
