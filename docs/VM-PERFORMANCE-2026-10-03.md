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
