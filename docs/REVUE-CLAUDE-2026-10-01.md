# Revue de la contribution Claude du 01/10

Base : `0c89ce7`, code identique à `a779c9d`. Documents transmis par toytoy :
ECHANGES-2.md puis ECHANGES-1.md, ce dernier ajoutant la proposition de patch.
La réponse complète de Claude est conservée verbatim dans
[ECHANGES.md](../ECHANGES.md). Son accès en lecture est rapporté ; toytoy confirme
qu'il ne peut pas encore écrire dans le dépôt. Aucun accès VM constaté.

## Décision d'intégration

**Revue documentaire intégrée ; patch non intégré au code de la branche.**
La [proposition originale](reviews/claude-2026-10-01-proposal.patch) est conservée
comme pièce de revue, non appliquée dans `core/` ni `tests/`.
SHA-256 : `d78824d12f98c4df3c4d1b6176219e4b30b50dc61aad1a715c30121ffa239f08`.

Les corrections FAILED et reconnaissance de THREAD_DELETE sont utiles. Le
patch complet ne peut pas être repris tel quel : la lecture allégée des reçus
affaiblit un blocage existant, et le nouveau scanner est incomplet et traverse
un ancêtre symbolique. Ce sont des constats sur la proposition, pas de nouvelles
régressions publiées du moteur. Les correctifs restent dans T-048/T-021/T-049.

## Tests réellement exécutés par Codex

Patch appliqué dans un worktree détaché de `0c89ce7`, sans modifier le code du
checkout de travail. Vrai pytest 9.1.1, Python 3.12.14, conteneur Linux.

```sh
python -B -m pytest -q -p no:cacheprovider --tb=short
```

Résultat du **candidat** : **761 passed, 5 failed in 30.78s**, aucun désélectionné.
Les cinq échecs sont les mêmes sockets Manager interdites avant scénario métier
que dans l'audit de base. Ils ne sont pas validés. Le chiffre de 761 ne remplace
pas les 754 tests réussis de la branche puisque le patch n'y est pas intégré.

Retrait des sept modifications de modules, en conservant le nouveau fichier
de tests : **5 failed, 2 passed in 0.36s**. Quatre échecs sont des assertions
comportementales ; le cinquième est l'absence de `uncompacted_ids` (AttributeError),
pas une preuve de gain de performance. Après réapplication : **7 passed in 0.36s**.
L'aller-retour confirme le résultat annoncé par Claude avec le vrai pytest.

Les mesures 120 créations/compactions 10,19 → 2,09 s sont rapportées par Claude,
**non reproduites par Codex** dans cette revue. Les 619 tests de son substitut
ne sont pas assimilés à notre suite pytest. Aucune VM, coupure de courant,
donnée réelle ni validation complète de concurrence.

## Constats sur le patch

| Point | Vérification | Conclusion |
| --- | --- | --- |
| FAILED Thread | Nouveau test de statut rouge sans correction et vert avec ; lecture des trois recover | Correction pertinente ; ajouter preuve des trois familles et du code retour CLI avant livraison T-048 |
| THREAD_DELETE | Famille et type ajoutés ; test de JSON corrompu rouge/vert | Correction pertinente, mais ne rend pas l'inventaire exhaustif |
| Familles inconnues | Le test du répertoire directement sous operations passe | Fichier inconnu directement sous history et dossier imbriqué sous une famille connue restent invisibles |
| Ancêtre symbolique | La nouvelle fonction `unknown_history_entries` parcourt un history lié | Régression du parcours : vérifier tous les composants et ne suivre aucun lien, y compris lors du scan complémentaire |
| Reçu de version inconnue | Reçu compact modifié en version 999, puis nouvelle commande indépendante | Base : BLOCKED ; patch : ALLOWED. La lecture du seul event_id ne préserve pas les garanties actuelles |
| Migration | 50 legacy plus reçu à rejeter | 50 Informations créées avant le rejet ; refus signalé, destination partielle non activable automatiquement |
| Réservation Event perdu | Test existant `test_receipt_still_reserves_event_id_when_event_file_is_missing` inclus dans la suite | La version finale du patch conserve ce blocage ; l'idée initiale « Event présent suffit » ne convient pas |

### Lecture des reçus et complexité

`receipt_event_ids` lit et décode toujours **tous les fichiers JSON des reçus** ;
il ne valide qu'une partie de leur structure. Le coût d'une nouvelle commande
reste au moins O(nombre de reçus + opérations non compactées), hors taille
des contenus. Un gain de constante est plausible ; il ne faut pas le décrire
comme un passage général à O(opérations non compactées).

Un contrôle global au démarrage ne remplace pas automatiquement les garanties
du chemin d'écriture : il faudrait démontrer comment la validité reste connue
après mutations, interruptions et altérations. T-049 doit proposer un annuaire
reconstructible ou un mécanisme équivalent avec invalidation/reprise, ou garder
les validations tant que ce contrat n'est pas établi. Pas de nouvelle validation
générique demandée : préserver le comportement existant pendant l'optimisation.

### Portée du refus de migration

La correction ajoute des rejets et empêche de présenter ces reçus comme archives
migrées sans réserve. Elle **n'annule pas toute conversion avant écriture** et
n'installe aucun verrou empêchant d'utiliser la destination partielle. Ce n'est
pas forcément une régression : le convertisseur acceptait déjà des résultats
partiels. Le contrat et la procédure doivent dire qu'un rejet interdit la mise
en service. Si l'objectif devient un refus avant toute conversion d'une source
mixte, faire ce contrôle avant d'écrire les Informations.

Les reçus DELETED pourraient être importés à l'identique après validation,
absence de cible et contrôle des conflits, avec provenance dans un manifeste.
Cette proposition ne règle pas seule le rejeu des reçus compacts ni CANCELLED,
qui réserve aussi l'identité. La branche actuelle n'importe aucun de ces états.
Les journaux legacy archivables doivent rester distingués des familles core
actives ; ne pas bloquer aveuglément tout `operations/` historique.

## Apports d'architecture retenus, avec limites

- **T-048 :** distinguer attente légitime PENDING_DELETE et reprise non résolue.
  BLOCKED est un résultat de reprise, pas une valeur persistée d'OperationStatus.
  L'état APPLYING_DELETE doit être contrôlé même si son CLI de reprise est séparé.
  L'ordre proposé par Claude reste à tester sur les dépendances réelles ; un
  simple ordre linéaire ne prouve pas leur résolution.
- **FAILED :** prévoir une résolution humaine explicite, mais pas un simple
  bouton qui enlève le blocage. Examiner les effets déjà écrits, les liens,
  les réservations et le rejeu ; conserver la décision et ses preuves. Aucun
  nouvel état ABANDONED ni procédure de rollback implicitement approuvé.
- **Dérivés :** préférer le rapprochement par manifeste comme mécanisme de
  réparation ; la file durable reste utile pour les intentions/échéances.
  Les IDs/révisions permettent le suivi, et les hashes actuels détectent aussi
  les modifications directes sans changement de révision. Ne pas les enlever
  tant que ces accès restent possibles. Revalider après reconstruction.
- **Notes humaines :** conserver propriété, protection contre écrasement et
  sauvegarde ; une famille séparée avec révisions est une proposition à concevoir,
  pas une migration silencieuse des dossiers déjà produits.
- **Suppression :** vérifier les projections gérées par le moteur avant de
  déclarer l'effacement global terminé. Cela exige une phase de purge/reprise
  durable et un périmètre précis ; DELETED actuel ne garantit pas cet effacement.
  Ni les copies des clients, ni les sauvegardes, ni les notes humaines ne doivent
  être effacées implicitement par une reconstruction.
- **Liens Thread :** Persistent → Thread, puis journaux selon le contrat partagé.
  Tester le conflit avec suppression ; ne pas inverser cet ordre.
- **Plan/exécution :** figer entrées/révisions et version des règles, revalider
  l'applicabilité à l'exécution. Distinguer l'identité d'une intention et le hash
  de son contenu : deux demandes volontaires identiques ne sont pas forcément
  le rejeu de la même commande. L'identifiant dérivé du seul hash n'est pas adopté
  comme règle universelle.
- **T-050 :** archive de révisions optionnelle à examiner ; LONG_TERM/PERMANENT
  ne déclenchent pas automatiquement la conservation de chaque version. Prévoir
  publication/reprise et suppression cohérentes si cette option est retenue.
- **D2/D8 :** documenter aussi le hash non salé conservé dans les Events après
  suppression, sans promesse de confidentialité ni d'effacement.

E-001 reçoit une revue de lecture favorable, pas une certification. E-005 et
E-006 sont confirmés par les scripts rapportés de Claude et les reproductions
de notre audit. E-007 reçoit un accord d'orientation avec les réserves ci-dessus.
E-004 reste sans revue détaillée. Global 45 %, grille 52,75 points inchangés.

## Reproduire les réserves sur la proposition

Le [diagnostic associé](reviews/claude-2026-10-01-probes.md) contient le bloc
Python exécuté, à lancer sur la base puis le worktree portant le patch.
Ces expériences utilisent uniquement des répertoires temporaires synthétiques.
