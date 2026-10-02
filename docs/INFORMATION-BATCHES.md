# Écritures Information par lots bornés — T-049

Le writer accepte maintenant `execute_batch(commands)` ; le CLI expose :

```sh
MEMORY_ENGINE_ROOT=/chemin/vers/copie python -B -m core.information.cli batch --input commandes.json
```

`commandes.json` contient un tableau JSON de **1 à 100 commandes**, avec des
identifiants et timestamps stables, conservé par l'appelant pour les relances :

```json
[
  {
    "kind": "CREATE",
    "memory": {"information_id": "observation-1", "revision": 1, "content": "Observation initiale"},
    "operation_id": "creation-1",
    "event_id": "event-creation-1",
    "actor": "operateur",
    "timestamp": "2026-10-02T07:00:00Z"
  },
  {
    "kind": "UPDATE",
    "memory": {"information_id": "observation-1", "revision": 1, "content": "Observation corrigée"},
    "previous_revision": 1,
    "operation_id": "correction-1",
    "event_id": "event-correction-1",
    "actor": "operateur",
    "timestamp": "2026-10-02T07:01:00Z"
  }
]
```

`memory` suit le modèle Memory existant, avec ses métadonnées et extensions.
UPDATE fournit l'objet complet à la révision attendue ; le writer produit la
révision suivante. L'exemple aboutit à la révision 2. Un champ omis reprend la
valeur par défaut du modèle : UPDATE n'est pas un patch partiel.

## Validation, progression et reprise

La liste est copiée par sérialisation JSON, puis sa forme, ses identifiants et
ses objets sont vérifiés avant le premier effet. Les contrôles dépendant de
l'état courant restent effectués au moment de chaque commande : révision,
réservation, suppression, routage et références. Chaque effet conserve son
propre journal Information, son Event et son protocole durable existants.

Succès : `status=COMPLETED`, `results` contient les résultats ordonnés avec
`index` et `operation_id`, `next_index=total`, `error=null`. Premier conflit ou
erreur métier/stockage attendue : `status=BLOCKED`, résultats du préfixe achevé,
`next_index` de la commande bloquée et `error` avec identifiant/type/raison.
Le CLI sort avec 0 ou 1 respectivement. Une liste structurellement invalide
lève une erreur dans l'API ; le CLI la rend BLOCKED sans progression.

**Le lot n'est pas une transaction atomique.** Le préfixe reste acquis et la
commande bloquée peut déjà avoir des effets durables. Une interruption brutale
ou une erreur inattendue peut empêcher tout résultat d'être retourné. Rejouer
la **liste entière avec exactement les mêmes commandes**, IDs et timestamps :
les journaux reconnaissent le préfixe et reprennent la commande interrompue.
`next_index` est une information de progression, pas un pointeur autorisant
à ignorer les effets partiels. Une commande changée avec un ancien operation_id
est refusée. Un rejeu terminal après suppression ne recrée pas l'Information.

Aucun journal parent ni file d'attente durable n'enregistre les commandes pas
encore commencées. `recover-all` reprend les intentions déjà enregistrées,
mais ne peut pas inventer la fin d'une liste perdue. L'appelant conserve cette
liste, qui contient les textes complets et peut retenir des données supprimées
plus tard ; la purge du moteur ne supprime pas ce fichier d'entrée.

## Un scan partagé sous verrous

Le lot prend les verrous Persistent → Operations → Events. Au premier effet,
le lecteur strict existant vérifie tous les plans/reçus Information et produit
les réservations. Une copie privée mutable conserve les cibles en attente et
les IDs d'Events. Chaque succès libère sa réservation de cible et ajoute son
Event réservé, même si son fichier disparaît ensuite. Une erreur ferme le
lot : aucune commande suivante ne peut utiliser une vue potentiellement périmée.

Versions inconnues, paire plan/reçu divergente et opérations FAILED gardent
leurs contraintes. Les processus coopérants attendent les mêmes verrous. Le
lot suivant recharge le disque ; aucun cache n'est conservé sur le writer.
La portée interne synchrone n'accepte pas de callback arbitraire, d'autre
writer ou de compaction intercalée. Les modifications externes ignorant les
verrous sont hors contrat, comme pour les commandes individuelles.

Ce scan est celui des **réservations Information**, pas un audit readiness
global. Les appels isolés ne deviennent pas une barrière de démarrage ; utiliser
le contrôle global existant avant exploitation. Les formats sur disque et le
protocole de compaction restent inchangés. Une reprise interne d'une compaction
inachevée peut demander ses lectures supplémentaires.

`LifecycleTriggers.run_due` utilise la même portée interne par tranches de 100
échéances sélectionnées. Le scan est paresseux : un lot entièrement STALE ou
SKIPPED n'initialise pas de journal enfant. L'ordre, le `limit`, les intentions
de déclencheurs et la reprise individuelle sont conservés. Le verrou Persistent
extérieur de `run_due`, et celui de MaintenancePass, restent détenus jusqu'à la
fin de leur appel : découper les réservations ne libère pas ce verrou entre
tranches. Aucun ordonnanceur système n'est installé.

## Coût et limites

La borne 100 limite le nombre de commandes par appel public ; elle ne borne
ni les octets des textes, ni la mémoire des réservations, ni la durée des scans
ou du verrou. Une petite taille de lot reste possible pour réduire les effets
par appel. Le lecteur conserve O(N) IDs d'Events. Un lot neuf fait un scan des
N entrées puis ses B écritures ; les gardes des autres familles restent actives.
L'ingestion croissante à taille B fixe conserve un terme O(N²/B) : c'est une
réduction des relectures, pas une preuve de passage à l'échelle illimité.

Mesures reproductibles et preuves ci-dessous ; aucun changement de base de
données n'est requis. Un annuaire reconstructible reste une étape distincte,
avec son protocole de divergence/reconstruction à établir.

## Mesures reproductibles du 02/10

```sh
python -B -m tools.benchmark_information_batches --sizes 0 100 300 \
  --incoming 50 --output /tmp/information-batches.json
```

Chaque point prépare un moteur temporaire distinct, avec le même historique
canonique créé par lots, éventuellement compacté avant mesure. Cette préparation
est exclue et son temps rapporté séparément. Les appels individuels et le lot
sont mesurés sur le même code, avec les mêmes objets/IDs : ce sont deux chemins
d'exécution, pas une comparaison de versions. Une seule mesure par point,
filesystem local réchauffé, Python 3.12.14 ; charge de l'hôte non contrôlée.
Aucun test lourd en parallèle. Les audits finaux et la comparaison intégrale
des objets attendus sont hors mesure. Les temps incluent l'instrumentation.

| Historique | Entrées préexistantes | 50 commandes | Individuelles | Un lot | Ouvertures JSON individuelles → lot |
| --- | ---: | --- | ---: | ---: | ---: |
| Snapshots | 0 | CREATE | 0,567 s | 0,162 s | 1 325 → 100 |
| Snapshots | 100 | CREATE | 2,033 s | 0,221 s | 6 325 → 200 |
| Snapshots | 300 | CREATE | 5,187 s | 0,321 s | 16 325 → 400 |
| Snapshots | 300 | UPDATE | 5,340 s | 0,333 s | 16 325 → 400 |
| Reçus compactés | 300 | CREATE | 3,890 s | 0,350 s | 16 325 → 400 |
| Reçus compactés | 300 | UPDATE | 4,063 s | 0,289 s | 16 325 → 400 |

Le nombre de scans de réservations passe de **50 à 1** à chaque point.
À 300 snapshots, le gain mesuré est d'environ 16× pour ces 50 créations ou
mises à jour. Ce n'est pas le débit total d'une ingestion projet ni une latence
garantie. Les ouvertures sont des lectures logiques réussies, pas des I/O
physiques. [Rapport complet](benchmarks/information-batches-2026-10-02.json),
avec tous les points compactés, temps de préparation, base Git `72f4033` et
empreinte du code core modifié avant commit. Cette empreinte est le SHA-256
du JSON compact des couples triés `[chemin relatif, sha256(octets)]` de core.

Le raccordement aux échéances réduit aussi la passe de 25 effets de 4,156 à
1,770 s sur 300 Informations/25 projets ; voir [MAINTENANCE-COST.md](MAINTENANCE-COST.md).
Aucun essai VM, corpus réel, disque froid ou coupure physique n'est couvert.

## Preuves comportementales

21 nouveaux cas dans `tests/test_information_batches.py` : créations/mises à
jour chaînées, rejeu sans nouvel effet, entrées live/compactes lues une fois,
Event perdu mais toujours réservé, reprise libérant la cible, FAILED et
réservations étrangères, version inconnue/paire divergente, relecture entre
lots, rejeu après suppression, arrêt au conflit, limites/forme avant effet,
PENDING_DELETE sans approbation, CLI et dispatcher en plusieurs tranches.
Deux arrêts réels de processus (code 74) après le second Event ou le second
COMMITTED vérifient la reprise du préfixe et de la fin. Deux processus
concurrents sans Manager vérifient le gagnant unique et l'absence d'effet dans
la fin du lot perdant.

Groupe ciblé : **102 réussis, 12,21 s**. Retirer le partage du scan rend rouges
les deux cas live/compact ; retirer l'ajout de réservation Event ou la
libération de cible après reprise donne 1 + 1 échec comportemental. Le code
est restauré après chaque expérience. Suite complète : **983 réussis, cinq échecs de sockets Manager avant scénario,
46,18 s**, aucun désélectionné. Ces cinq scénarios restent à valider en VM.

## Index facultatif ajouté ensuite

Après `index-rebuild`, la création de la vue initiale peut réutiliser les
validations d’entrées dont les octets sont identiques. L’énumération et le
hachage des sources restent complets, puis le lot actualise sa vue en mémoire
comme précédemment. Le protocole de reprise et les bornes sont inchangés.
Voir [RESERVATION-INDEX.md](RESERVATION-INDEX.md) ; les mesures ci-dessus
correspondent aux lots sans cet index facultatif.
