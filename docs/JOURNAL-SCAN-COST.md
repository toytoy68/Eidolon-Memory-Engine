# Coût des scans de journaux — T-049, réduction locale

## Changement initial livré

Les chiffres ci-dessous documentent le premier lot. Depuis le 02/10,
[les lots bornés](INFORMATION-BATCHES.md) partagent aussi ce scan entre 1 à 100
commandes sous verrous et dans le dispatcher des échéances. Les commandes
individuelles conservent le fonctionnement décrit ici sans index. Un
[index de réservations facultatif](RESERVATION-INDEX.md) permet maintenant
de réutiliser la validation après contrôle intégral des octets. Les chiffres
historiques ci-dessous ne mesurent pas cet index.

Une nouvelle écriture métier Information faisait trois parcours complets de
son journal : écriture en attente sur la cible, réservation d'Event, puis
nouvelle recherche pendant la reprise interne. Elle n'en fait plus qu'un.
`InformationWriteJournal.reservations()` valide chaque plan/reçu via le lecteur
complet existant, puis conserve seulement les IDs d'Events et les IDs des
opérations non COMMITTED par cible.

La vue immuable `JournalReservations` est construite sous les verrous
Persistent → Operations → Events, utilisée pour les trois vérifications et
abandonnée avant leur libération. Entre sa création et sa dernière utilisation,
la seule nouvelle opération est celle de la commande en cours, exclue du
contrôle de sa propre cible. Ni cache sur le writer ou le processus, ni fichier
d'index supplémentaire. Aucun texte de snapshot n'est conservé dans la vue.

Une reprise explicite reconstruit ses réservations depuis le disque. La
compaction garde son scan et la relecture/comparaison du reçu publié **avant**
de retirer le snapshot. Audits, suppression, Threads et routage conservent leurs
lecteurs. La vue n'est pas un objet à conserver ou passer entre commandes ;
les méthodes internes supposent les verrous des points d'entrée métier.

## Garanties conservées

- Tous les reçus sont validés : champs, version exacte, types, révisions,
  empreintes et résultat. Une version 999 bloque aussi une commande sans lien
  avec le reçu concerné. Aucune lecture JSON allégée permissive.
- Si plan et reçu coexistent, leur cohérence est intégralement vérifiée.
- Le reçu réserve l'Event même si le fichier Event manque.
- PREPARED/APPLYING/FAILED réservent leurs cibles. Les opérations ajoutées par
  un autre processus sont relues avant la commande suivante.
- Rejeux compacts, interruptions, suppressions et gardes de références gardent
  leurs contrats. Le format des données est inchangé.

Les écrivains legacy et les modifications externes ignorant les verrous
restent à arrêter.

## Mesure reproductible

```sh
python -B -m tools.benchmark_information_writes \
  --sizes 50 150 300 --label current --output /tmp/journal-current.json
```

Deux corpus temporaires neufs : create, puis create+compact après chaque
création. Informations courtes synthétiques, IDs/Event distincts, mêmes
annotations et date déclarée. Après chaque corpus : égalité des 300 objets
canoniques et audit sans problème. L'instrumentation compte les appels au
lecteur partagé, les scans complets et les ouvertures JSON de journaux réussies
en lecture ; audits finaux exclus des compteurs. Les données temporaires sont
supprimées. Aucune donnée réelle touchée.

Base mesurée : `2d21739`. Après : même base avec le changement de ce lot, avant
son commit. Les deux rapports portent donc la même base Git ; leurs labels
identifient le code testé. Pour comparer à nouveau, exécuter **le même script**
depuis un worktree arrêté de la base, avec `PYTHONPATH=.` et le chemin absolu du
script ; puis depuis la version modifiée. Garder environnement et tailles
identiques. Script fourni dans ce lot.

Résultats locaux Python 3.12.14, un passage par variante :

| Charge cumulée | Nombre | Avant | Après | Scans avant → après | Lectures JSON avant → après |
| --- | ---: | ---: | ---: | ---: | ---: |
| Création | 50 | 2,01 s | 0,75 s | 150 → 50 | 3 825 → 1 325 |
| Création | 150 | 16,65 s | 5,57 s | 450 → 150 | 33 975 → 11 475 |
| Création | 300 | 59,39 s | 20,42 s | 900 → 300 | 135 450 → 45 450 |
| Création + compaction | 50 | 1,89 s | 1,35 s | 200 → 100 | 5 250 → 2 750 |
| Création + compaction | 150 | 14,70 s | 8,23 s | 600 → 300 | 45 750 → 23 250 |
| Création + compaction | 300 | 57,11 s | 30,01 s | 1 200 → 600 | 181 500 → 91 500 |

Rapports exacts : [avant](benchmarks/journal-scans-before-2026-10-01.json),
[après](benchmarks/journal-scans-after-2026-10-01.json). À 300, environ 2,91×
plus rapide pour create et 1,90× pour create+compact. Les comptes de lectures
expliquent le gain ; ces durées ponctuelles ne promettent pas une latence.
Des tests ciblés ont tourné pendant une partie du passage de référence ; charge
de l'hôte non contrôlée. Aucun disque froid ni VM mesurés.

## Preuves et limites restantes

8 nouveaux cas `tests/test_journal_scan_cost.py` : un scan/une lecture des
antécédents par création, plans ou reçus ; version inconnue après utilisation du
même writer ; paire divergente ; Event réservé ; opération posée par un autre
processus ; deux créateurs concurrents ; reprise et rejeu après compaction.
Groupe écritures/compaction/Thread/routage : 69 cas existants réussis ; nouveaux
cas : 8 réussis. Retirer la réutilisation donne 2 échecs sur les comptes d'I/O ;
retirer les réservations cible ou Event donne 1 + 1 échec comportemental.
Code restauré après les expériences. Suite complète finale : **883 réussis,
5 échecs de sockets Manager avant scénario, 51,84 s**, Python 3.12.14/pytest 9.1.1,
aucun désélectionné. Pas de validation VM.

**T-049 reste partiel pour l'ingestion intensive.** Une commande relit toujours
N entrées : l'ingestion croissante reste quadratique. La vue contient O(N) IDs
d'Events en mémoire ; aucun pic RAM mesuré. Les audits, dossiers, catalogue et
intentions de routage gardent leurs scans. Un annuaire incrémental reconstructible
demandera son protocole de divergence/reconstruction, concurrence et reprise
avant de remplacer ces relectures. Aucun objectif VM arbitraire ni autorisation
d'ingestion intensive ne découle du benchmark.

## Mesures directes sur VM du 03/10

Le commit `4a11c71` a maintenant une comparaison directe sur Eidolon-Memory :
84 mesures d’écriture, trois répétitions indépendantes, et quatre corpus
entretenus avec cinq échéances/rejeu. [Rapport et données brutes](VM-PERFORMANCE-2026-10-03.md).
300 antécédents/25 créations : médianes 1,518 s seules, 0,093 s en lot,
0,046 s en lot indexé hors construction de l’index. Attention : `/tmp` est tmpfs ;
ni latence disque physique, ni corpus réel, ni autorisation d’ingestion intensive.
L’index conserve les lectures d’octets ; l’entretien à vide conserve ses scans.
