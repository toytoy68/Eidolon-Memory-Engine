# Compaction Information par lots bornés

`FilesystemInformationWrites.compact_batch(operation_ids)` compacte explicitement
une liste ordonnée de **1 à 100 identités distinctes**. Le CLI accepte un tableau
JSON de ces identités :

```sh
MEMORY_ENGINE_ROOT=RACINE_ARRETEE python -B -m core.information.cli \
  compact-batch --input operation-ids.json
```

Les champs/versions des journaux et reçus restent identiques. L’opération ne
modifie aucun corps canonique, Event ou révision et n’exécute pas de suppression.
L’audit humain FAILED est conservé dans le reçu. Le rejeu des commandes d’origine
reste exact après modification ou suppression ultérieure, sans résurrection.

Le lot gèle sa liste puis garde les verrous Persistent → Operations → Events
jusqu’au résultat. Un scan strict des réservations est partagé entre les
compactions qui retirent un journal complet ; il valide les formats et paires
journal/reçu comme auparavant. La compaction COMMITTED ne change ni les cibles
en attente, ni les réservations d’Events : cette vue reste donc valable sous les
verrous. Elle n’est ni stockée sur le writer ni réutilisée au lot suivant.
L’index facultatif conserve sa validation d’octets ; il n’est pas activé par le lot.

Chaque opération conserve ses vérifications propres : statut COMMITTED, absence
d’opération Information en attente sur sa cible, état de suppression compatible,
Event exact, publication durable du reçu, **relecture/comparaison du reçu avant
retrait du seul snapshot complet**, puis fsync du répertoire de journaux.
Une relance dont toutes les identités ont déjà un reçu ne nécessite pas de scan
global, comme la compaction individuelle ; elle synchronise les retraits déjà
faits et retourne les résultats existants. Ce rejeu n’est pas un audit global.

COMPLETED retourne `results`, `next_index=total` et `error=null`. BLOCKED signale
la première identité refusée et conserve les résultats du préfixe. Les opérations
suivantes ne sont pas traitées. Les entrées syntaxiquement invalides sont refusées
avant publication. Le CLI retourne un code non nul si le lot bloque.

Le lot **n’est pas atomique**, ne crée pas de file durable et ne choisit pas une
politique de rétention. Le caller conserve sa liste et relance la même commande
après interruption/revue ; les reçus du préfixe sont rejoués sans nouveau contenu.
Une compaction concurrente attend les verrous. Les écrivains externes/legacy qui
ignorent ces verrous restent à arrêter. La borne de 100 limite la durée du verrou,
sans démontrer une latence maximale.

## Preuves

26 nouveaux cas : scan unique, limites/identités invalides, préfixe bloqué,
réservations fraîches au lot suivant, audit humain conservé, Event réservé même
absent, création/mise à jour puis suppression/rejeu, relecture du reçu corrompu,
mutation de la liste du caller, trois vrais arrêts de processus, deux compacteurs
concurrents et CLI. Groupe ciblé 124 tests réussis ; suite VM 1483 réussis.
Retirer le partage du scan ou la comparaison de publication provoque un échec
chacun dans les tests comportementaux ; code du dépôt inchangé durant ces essais.

## Mesure reproductible

`tools.benchmark_information_compaction` recrée des corpus neufs pour single et
batch, et sépare la préparation du temps de compaction. Il compte scans et
lectures, puis vérifie les valeurs canoniques, chaque reçu, l’absence de corps
dans les reçus et le rejeu exact des commandes. Exemple :

```sh
MEMORY_ENGINE_ROOT=/tmp/em-measure PYTHONDONTWRITEBYTECODE=1 \
  python -B -m tools.benchmark_information_compaction \
  --sizes 1000 --repeats 3 --output /tmp/compaction.json
```

`--temp-parent DOSSIER_TEMPORAIRE_EXISTANT` permet de choisir le support ; ne pas
utiliser le répertoire mémoire actif comme parent. Les corpus sont supprimés.
L’instrumentation porte sur les ouvertures de fichiers, pas l’I/O physique.
Le résultat garde les temps de seeding, de compaction et de leur somme ; les
contrôles finaux sont exclus des compteurs. Les chiffres exacts observés sur VM
et leurs limites sont consignés dans [le rapport de performance](VM-PERFORMANCE-2026-10-03.md).

Aucun corpus réel, service actif, rétention automatique ou coupure électrique
n’est validé par ce lot. L’ingestion et la compaction croissantes conservent un
coût linéaire par lot sur les antécédents, donc quadratique à borne fixe sur une
séquence croissante. Ce changement réduit ce coût sans l’éliminer.
