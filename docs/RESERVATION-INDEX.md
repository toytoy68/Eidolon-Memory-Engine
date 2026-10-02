# Index reconstructible des réservations Information — T-049

Cet index facultatif évite de redécoder et revalider les anciens snapshots à
chaque écriture. Les journaux et reçus restent les sources de vérité. Aucun
format canonique n'est migré ; aucune base de données ni dépendance n'est ajoutée.

## Activation et inspection

Sur une copie de travail, avec les écrivains legacy arrêtés :

```sh
MEMORY_ENGINE_ROOT=/chemin/vers/copie python -B -m core.information.cli index-rebuild
MEMORY_ENGINE_ROOT=/chemin/vers/copie python -B -m core.information.cli index-status
```

`index-rebuild` prend les verrous Persistent → Operations, relit intégralement
les plans/reçus avec le lecteur strict, puis publie atomiquement :
`memory/derived/information-reservations-v1.json`. La réponse donne `entries`,
`validated` et `reused`. Cette commande active aussi l'utilisation de l'index
pour les nouveaux writers, y compris dans d'autres processus. L'API équivalente
est `FilesystemInformationWrites.rebuild_reservation_index()`.

`index-status` ne crée ni répertoire, ni verrou, ni fichier de précontrôle.
L'utiliser sur une copie arrêtée pour un constat stable. Résultats :

| Statut | Sens | Code CLI |
| --- | --- | ---: |
| DISABLED | Fichier absent, scans stricts habituels | 0 |
| CURRENT | Index lisible et mêmes octets/noms de journaux | 0 |
| STALE | Ensemble des fichiers ou contenu modifié | 1 |
| REBUILD_REQUIRED | Index invalide ou version inconnue | 1 |
| BLOCKED | Frontière symbolique ou erreur d'accès | 1 |

CURRENT décrit la fraîcheur de l'index, **pas la readiness globale** : des
intentions PREPARED/APPLYING/FAILED peuvent légitimement y être réservées.
`index-status` ne remplace ni les audits ni `readiness`/`recover-all`.

L'activation reste explicite. Sans fichier, les écritures conservent leur scan
strict précédent. Pour désactiver l'index, arrêter les écrivains puis retirer
ce seul fichier dérivé. Sa disparition ne supprime aucune réservation canonique.
Une reconstruction ultérieure réactive l'index. Aucun réglage VM n'est modifié
par cette livraison.

## Ce qui est vérifié à chaque utilisation

Sous les mêmes verrous que l'écriture, le moteur énumère tous les IDs de plans
et reçus Information et calcule le SHA-256 des **octets complets** de chaque
fichier présent. Une ligne stocke seulement :

- les deux empreintes plan/reçu, ou `null` pour le fichier absent ;
- l'identifiant de cible et l'identifiant d'Event réservé ;
- le fait que l'opération reste en attente de résolution.

Une paire d'empreintes identique autorise la réutilisation de la validation
antérieure. Une entrée nouvelle ou modifiée passe dans le lecteur strict
existant, y compris la cohérence plan/reçu. Ses empreintes sont reprises après
validation avant de mémoriser le résultat. Le moteur ne se fie ni à mtime, ni à
la taille, ni à un inode. Une modification de même taille avec date restaurée
est donc détectée. Les versions inconnues et les divergences restent bloquantes.

Les IDs ne peuvent contenir de séparateur de chemin ; les racines et fichiers
symboliques sont refusés. Un écrivain ne peut pas utiliser l'index sans les
verrous Persistent et Operations. Les mutations externes ignorant ces verrous
pendant un appel ne sont pas couvertes par le protocole.

L'index contient une version stricte et un checksum de sa représentation JSON
canonique complète. Syntaxe endommagée, checksum incorrect, champs invalides ou
version inconnue entraînent une **reconstruction complète** depuis les sources.
Aucun fragment d'index invalide n'est réutilisé. Une source elle-même invalide
bloque la commande, sans publier de nouvel index. Le checksum détecte les
altérations accidentelles ; ce n'est pas une signature contre un acteur capable
de falsifier volontairement l'index et de recalculer son checksum. Comme les
journaux, le répertoire dérivé doit rester sous le contrôle de l'application.

La version doit être incrémentée si les règles de validation du journal
changent : une validation ancienne ne doit pas contourner une nouvelle règle.
Les audits globaux n'utilisent jamais cet index pour éviter leurs validations.

## Publication, reprise et réservations

L'index est rafraîchi **avant** les contrôles nécessitant des réservations. Il
peut donc être en retard d'une commande ou d'un lot juste après leur succès :
c'est normal, les prochains appels le rafraîchissent. Un conflit ultérieur peut
laisser un index rafraîchi même si aucun effet canonique nouveau n'a été publié.
Cette maintenance dérivée ne représente pas un succès métier.

Chaque fichier modifié depuis le dernier rafraîchissement est revalidé. Un
processus interrompu après son intention, son Event ou son COMMITTED est donc
retrouvé, y compris par un autre processus. Si une publication d'index échoue,
la commande n'est pas commencée et peut être relancée. La publication utilise
le remplacement atomique durable existant ; une interruption après cette
publication mais avant l'écriture canonique ne réserve aucun effet fictif.

L'Event d'un reçu reste réservé si son fichier Event manque. PREPARED, APPLYING
et FAILED continuent à réserver la cible. Après reprise, le passage COMMITTED
est détecté et libère la cible. La compaction change la paire de sources,
revalide le reçu et conserve sa relecture obligatoire avant retrait du snapshot.
Un rejeu terminal après suppression ne recrée pas l'Information.

Les lots bornés utilisent la vue ainsi validée puis actualisent leurs
réservations en mémoire après chaque effet, selon [INFORMATION-BATCHES.md](INFORMATION-BATCHES.md).
Le dispatcher d'échéances en bénéficie automatiquement lorsque l'index est
activé. Les gardes de suppression, références, routage et révision sont inchangées.

Un index ne remplace pas un journal perdu : si des sources sont retirées
manuellement, leurs lignes sont retirées aussi. Il faut restaurer les journaux
depuis une sauvegarde pour restaurer leurs contraintes ; un cache dérivé ne
constitue pas une sauvegarde métier.

## Limites de coût et de confidentialité

Cette première version économise la validation répétée, **pas la lecture de
tous les fichiers**. Chaque utilisation reste O(N + octets de journaux) et
charge une vue O(N) en mémoire ; le JSON d'index est réécrit quand il change.
L'ingestion croissante reste quadratique à taille de lot fixe. Les lectures
physiques à froid, gros snapshots, pic RAM, durée des verrous et VM restent à
mesurer. Un gain de CPU local ne prouve pas un débit disque garanti.

Supprimer aussi l'énumération/lecture complète demanderait un protocole de
génération/invalidation partagé par tous les écrivains, avec contrôle des
éditions hors protocole. Ce changement n'est pas livré ici. Les lots restent
le premier moyen d'amortir les contrôles, l'index leur est complémentaire.

L'index ne contient pas les textes de snapshots ; il conserve des IDs et des
empreintes. Un texte court peut être testé par devinette. Il n'offre ni
chiffrement ni effacement physique ; sauvegardes/copies gardent leur propre
politique de rétention, comme les reçus existants.

## Mesure reproductible et preuves

```sh
python -B -m tools.benchmark_reservation_index --size 300 --incoming 50 \
  --histories live compact --output /tmp/reservation-index.json
```

Chaque point utilise un moteur temporaire distinct, avec 300 Informations
synthétiques initiales et 50 créations ou mises à jour. Historique live ou
compacté avant mesure ; commandes individuelles ou un lot. Préparation par
lots, compaction initiale et première construction de l'index sont exclues
du temps mesuré et rapportées séparément. L'index se rafraîchit ensuite dans
le temps mesuré. Tous les points utilisent le même code et les mêmes données.

Une mesure par point, Python 3.12.14, filesystem réchauffé, charge de l'hôte
non contrôlée. Aucun test lourd en parallèle pendant cette comparaison finale.
Les compteurs recensent les appels au lecteur strict et les ouvertures JSON
réussies **dans les journaux** : le hachage intégral est compté comme lecture,
mais les lectures/écritures du fichier d'index et les écritures canoniques ne
sont pas incluses dans ce compteur. Les temps englobent tout l'appel et son
instrumentation. Les audits finaux sont exclus ; chaque corpus vérifie les
objets canoniques attendus et un audit sans problème.

24 nouveaux cas dans `tests/test_reservation_index.py`. Couverture : sources
live/compactes, réutilisation par nouveau writer, reconstruction identique,
index perdu/corrompu/inconnu, Event toujours réservé malgré sa disparition,
modification de même taille/date restaurée, source inconnue ou divergente,
intentions et FAILED, reprise libérant les cibles, compaction, rejeu après
suppression, retrait canonique, symlinks, verrous et inspection sans écriture.
Trois arrêts réels de processus (code 74) après Event, COMMITTED ou publication
de l'index ; changement de journal par autre processus, deux lots concurrents,
CLI et dispatcher également couverts.

Retirer la réutilisation rend deux assertions de coût rouges ; retirer
l'identité des sources rend trois refus de corruption rouges ; retirer le
checksum permet de perdre une réservation Event et rend son test rouge.
Code restauré après chaque expérience. Suite complète : **1007 réussis,
cinq échecs Manager à la création de sockets avant scénario, 50,71 s**,
aucun désélectionné. Ces cinq tests restent à valider en VM ; les courses sans
Manager et arrêts de processus testés ici ne remplacent pas cette recette.

### Résultats locaux sur 300 entrées préexistantes

| Historique | 50 commandes | Sans index | Avec index |
| --- | --- | ---: | ---: |
| Snapshots | Créations individuelles | 4,861 s | 0,987 s |
| Snapshots | Créations en lot | 0,247 s | 0,243 s |
| Snapshots | Mises à jour individuelles | 4,769 s | 1,059 s |
| Snapshots | Mises à jour en lot | 0,278 s | 0,196 s |
| Reçus compactés | Créations individuelles | 4,086 s | 0,971 s |
| Reçus compactés | Créations en lot | 0,209 s | 0,208 s |
| Reçus compactés | Mises à jour individuelles | 4,058 s | 1,026 s |
| Reçus compactés | Mises à jour en lot | 0,228 s | 0,199 s |

[Rapport complet](benchmarks/reservation-index-2026-10-02.json), base `c3637f7`
avec index non encore commité, empreinte SHA-256 du code exécuté. L'empreinte
porte sur le JSON compact des couples triés `[chemin relatif, sha256(octets)]`
des fichiers Python de core.

Pour 50 commandes individuelles, appels au lecteur strict : **16 275 → 99** ;
scans de noms : **50 → 50** ; ouvertures JSON de journaux : **16 325 → 16 423**.
Les 98 lectures supplémentaires correspondent aux revalidations des 49 entrées
créées/modifiées depuis le dernier rafraîchissement. Le gain vient de la baisse
de décodage/validation, pas d'un nombre inférieur de fichiers ouverts.
Pour un lot : lecteur strict **350 → 50**, scans **1 → 1**, JSON **400 → 400**.

La construction initiale coûte ici environ **0,08 à 0,15 s**, hors des temps
comparés. Le gain de l'index est net sur les appels individuels (~4 à 5×),
mais négligeable pour les créations déjà en lot sur ce corpus. Les updates en
lot montrent un gain plus modeste et variable. Pour un unique lot, le coût
initial de construction peut dépasser le gain : conserver les lots pour les
imports et activer l'index surtout pour les écritures successives. Ces points
uniques ne permettent pas d'affirmer une différence de quelques millisecondes.
