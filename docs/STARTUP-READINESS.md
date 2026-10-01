# Contrôle explicite de démarrage — T-048

Livré en local le 01/10/2026, sans installation d'un service ni essai VM.
Le contrôle exige un arbre arrêté, sans écrivain concurrent. Il ne fournit pas
de verrou global durable ni d'autorisation valable après une nouvelle écriture.

## Commandes

Avec `MEMORY_ENGINE_ROOT` pointant sur une copie arrêtée :

```sh
python -B -m core.operations.cli readiness
python -B -m core.operations.cli recover-all
```

`readiness` ne crée ni répertoire ni verrou. Il lit les journaux Thread
création/statut/suppression, le journal commun Information (plan et reçu), les
reçus de suppression, et l'inventaire des formats. Il retourne `ready`, `issues`
avec chemin/raison/caractère reprenable, `records` sans snapshots et le périmètre
du contrôle. Code 0 seulement si `ready` est vrai.

Les familles enregistrées ne possèdent que leurs fichiers directs. Tout fichier
inconnu, sous-famille inconnue ou lien dans `memory/history` nécessite une revue ;
le scan ne descend pas dans un lien symbolique. Les fichiers de verrou
`.write.lock` des dépôts enregistrés sont reconnus. Un temporaire abandonné
n'est pas ignoré. `archive/` est inactif et n'est pas exécuté. Les opérations
legacy non versionnées exigent une migration, même si leur format est reconnu.

| État | Décision |
| --- | --- |
| Thread/Information PREPARED ou APPLYING | Reprise explicite nécessaire |
| Plan/reçu Information concordants, compaction interrompue | Reprise de la compaction nécessaire |
| FAILED, format inconnu, corruption, plan/reçu divergents | Bloqué pour revue humaine, sans abandon implicite |
| PENDING_DELETE valide | Attente d'approbation normale, aucune suppression déclenchée |
| APPLYING_DELETE | Suppression déjà approuvée à reprendre |
| CANCELLED ou DELETED cohérent | Aucun travail de suppression à exécuter |

`recover-all` refuse de lancer une reprise automatique si le contrôle initial
trouve un problème non reprenable. Sinon il appelle création/statut/suppression
Thread, écritures Information puis suppressions Information. Il relit ensuite
l'état sur disque. Un rapport de coordinateur vide ou optimiste ne vaut jamais
succès à lui seul. Si des dépendances subsistent, il recommence tant que l'état
progresse, au maximum nombre initial d'anomalies + 1 passes. Sans progrès il
rend le problème à l'opérateur ; il ne tourne pas indéfiniment.

Le JSON conserve les quatre groupes antérieurs et ajoute
`information-deletions`, `passes`, `readiness`. Les résultats Information déjà
terminés restent affichés comme COMMITTED, même sans reprise (`passes: 0`).
Les consommateurs doivent lire `readiness.ready`, sans supposer que toutes les
valeurs du premier niveau sont des dictionnaires d'opérations. Le contrôle final
fait autorité pour le code de sortie. Les commandes de reprise d'une seule
famille restent disponibles et ne valent pas contrôle global.

La recette `tools.vm_acceptance` ajoute `startup_readiness` après les audits sur
la restauration. Elle reste en lecture seule et n'appelle jamais `recover-all`.

## Preuves et limites

`tests/test_startup_readiness.py` ajoute 21 cas : trois familles FAILED et
PREPARED, relecture indépendante des rapports de reprise, journal de suppression
corrompu, cinq chemins inconnus, trois ancêtres symboliques, archives/verrous,
suppression en attente puis interrompue, écriture Information/compaction, CLI
non nul et recette incapable de déclarer OK un Thread FAILED.

Preuves négatives réellement exécutées : restaurer l'omission de FAILED donne
3 échecs ; restaurer l'inventaire antérieur en donne 6 ; retirer la reprise des
suppressions Information en donne 1 ; déclarer le succès depuis les résultats
des coordinateurs au lieu de la relecture finale en donne 1. Changements remis
en place après chaque essai. Ce sont des assertions comportementales.

Suite complète après correction : **775 réussis, 5 échecs d’environnement,
35,46 s**, pytest 9.1.1 / Python 3.12.14, aucun désélectionné. Les cinq erreurs
Manager sont des refus de socket avant le scénario métier.

Les nouvelles interruptions de ce lot sont des exceptions simulées. Les tests
existants d'arrêt de processus sont conservés. Aucun arrêt VM, coupure physique,
disque de production ni combinaison de dépendances issue de données réelles
n'a été testé. La recette contient un test avec concurrence simulée : ce test
prouve la propagation du KO, pas les cinq scénarios concurrents.

La résolution humaine durable d'un FAILED reste à concevoir : vérifier les
effets partiels et réservations avant toute décision, conserver sa trace.
Aucun état ABANDONED ni commande de déblocage aveugle n'est ajouté. Ce contrôle
ne remplace pas les audits métier de relations/lifecycle ni l'assemblage futur
de tous les écrivains via une façade unique.

## Extension du lot projet du soir

La famille `thread-update-v1` (THREAD_UPDATE) est maintenant inventoriée et
contrôlée. `recover-all` ajoute le groupe `thread-updates`, repris entre les
statuts et les suppressions Thread. Une mutation non terminée bloque les
mutations concurrentes du même Thread et réserve les liens de ses snapshots.
La relecture finale reste la seule autorité pour le code de sortie. Voir
[THREAD-UPDATES.md](THREAD-UPDATES.md) pour les preuves et limites.
