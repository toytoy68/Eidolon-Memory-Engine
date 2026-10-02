# Inventaire préalable à la migration des données

État : **convertisseur explicite et vérification indépendante disponibles en
local ; correspondance métier non validée sur les données de la VM**.
Le code historique dans `services/` et les nouveaux dépôts dans `core/` ne
partagent ni tous leurs formats, ni leur protocole d'écriture. Cette analyse
porte sur le dépôt ; les données et services de la VM restent à examiner.

## Conversion sur une copie et contrôle après écriture

**Limite reproduite le 01/10 (A-03/T-021)** : une source mixte legacy/core
contenant un reçu DELETED peut être convertie sans rejet ; son reçu reste en
archive et ne réserve plus l'identité dans la destination. Les journaux,
Threads et reçus archivés ne sont pas importés comme états actifs. Il faut
un rejet explicite ou un import de ces invariants avant d'activer une telle
destination. Un rapport sans rejet et des hashes égaux ne prouvent pas la
continuité métier. Voir [l'audit](AUDIT-2026-10-01.md).

Après l'inventaire, le précontrôle et la simulation décrits plus bas, utiliser
deux dossiers **distincts** sur une copie arrêtée. La destination doit être
neuve ou contenir uniquement un rejeu identique :

```sh
python -B -m core.migration.converter --source /copie/historique --destination /copie/convertie
python -B -m core.migration.verification --source /copie/historique --destination /copie/convertie
```

Le convertisseur écrit les Informations compatibles dans la destination core,
les Events, Reviews, opérations et Working anciens sous `archive/`, et les
rejets dans `migration-report.json` avec une raison et une action suggérée.
Les Events et Reviews archivés restent des octets historiques, pas des objets
métier core. La vérification relit directement les sources, reconstruit le
document core attendu et compare les octets ; elle compare aussi toutes les
archives et confronte les comptes du rapport au résultat. Elle n'écrit rien,
affiche `ok`, les comptes et les anomalies, et sort avec le code 1 en cas de
rejet ou d'écart. Les données rejetées exigent une décision humaine, même si le
rapport les documente correctement. Aucun des deux outils ne doit être lancé
sur la racine active de la VM. Ce contrôle établit l'égalité technique des
copies suivant la correspondance actuelle ; il ne certifie pas la fidélité
sémantique de cette correspondance sur les données réelles.

Les sections historiques ci-dessous décrivent les capacités propres aux
outils d'inventaire, de précontrôle et de simulation ; leurs mentions d'une
conversion encore à décider restent des avertissements sur la politique métier.

## Inventaire sur une copie des données

Après la sauvegarde décrite dans `DEPLOYMENT.md`, exécuter sur une **copie** :

```sh
python -m core.migration.inventory --root /chemin/vers/copie/du/moteur
```

`--root` contient `memory/`. La commande ne crée pas de dossier, de verrou ni
de fichier. Elle classe les signatures des fichiers attendus et rend un JSON
avec leurs nombres et les chemins à examiner ; elle n'affiche aucun contenu de
mémoire. Code retour 1 si un chemin a une signature inconnue, un JSON illisible
ou un lien symbolique ; sinon 0. **Une signature reconnue ne prouve pas qu'un
document entier est valide.** Le scanner ne suit pas les liens symboliques
rencontrés dans les catégories inventoriées ; examiner aussi la structure de la
copie avant de l'utiliser. Les fichiers portant d'autres extensions et les
sous-dossiers non listés ne sont pas inventoriés. L'omission connue de
`memory/history/operations/thread-delete-v1` reste à corriger sous T-048.
Un JSON corrompu dans cette famille n'apparaît actuellement pas dans
`needs_review` ; compléter manuellement l'inventaire de la copie.

Pour un premier contrôle structurel des Informations historiques persistantes :

```sh
python -m core.migration.preflight --root /chemin/vers/copie/du/moteur
```

Ce second outil reste en lecture seule. Il vérifie la fermeture du front matter,
les clés YAML dupliquées, l'identité fichier/objet et les caractères admis par
le backend dans l'identifiant, la révision simple ou
`revision.number`, les valeurs des types/états/niveaux connus du modèle,
les types de `revision.is_revision` et `revision.previous_revision`, les champs
de premier niveau ou de révision inconnus, la forme des blocs de
métadonnées et relations, et la présence d'un corps. Il
signale aussi une révision précédente supérieure ou égale au numéro courant,
ou un indicateur `is_revision` contradictoire avec sa présence. Il ne déduit
pas une chronologie manquante. Il valide aussi la lecture et l'identité des
documents core reconnus avant de les
compter comme déjà présents, et liste les fichiers bloqués avec des
codes de raison, sans inclure le contenu. Code retour 1 en présence de blocages.
Un `legacy_candidate` signifie seulement **structure minimale analysable** :
la conversion, la validité métier, les références et la conservation de tous les
champs ne sont pas encore garanties. Aucun fichier n'est converti.

## Simulation de faisabilité en lecture seule

Sur une copie arrêtée, après inventaire et précontrôle :

```sh
python -m core.migration.simulation --root /chemin/vers/copie/du/moteur
```

Le rapport donne une proposition de correspondance champ par champ, les chemins
des Informations candidates ou bloquées et les nombres d'Events, Reviews et
Operations historiques. Il ne montre aucune valeur privée et n'écrit aucun
fichier. Une date YAML devenue un objet Python non sérialisable en JSON est
bloquée jusqu'à décision sur sa représentation. Les Events et Reviews sont
inventoriés, mais leur archivage ou conversion reste à décider.
Le rapport compte aussi les types d'Events historiques reconnus (notamment
`STORED` et `RELATION_ADDED`) et les Reviews `PENDING_REVIEW`/`RESOLVED`.
Il signale si l'identifiant interne d'un Event ou d'une Review ne correspond
pas au nom de son fichier ; les deux variantes historiques `id` et `review_id`
des Reviews sont reconnues, et une contradiction entre elles est signalée.
Les Events core 0.2 présents dans le répertoire historique ne sont comptés
qu'après validation du document entier et de son identité fichier/objet.
Un type ou statut inconnu est signalé par son chemin, sans recopier sa valeur
dans le rapport. Ce comptage aide à décider l'archivage ; il ne valide pas
encore la structure complète d'un Event ou d'une Review.
Pour les Events historiques sans front matter, les déclarations en double des
champs `event_id`, `event_type` et `information_id` sont signalées comme en-tête
ambigu et ne contribuent pas au comptage des types. Le séparateur `---` de fin
d'en-tête est requis avant de compter le type.
L'identifiant `information_id` de ces anciens fichiers est contrôlé en lecture
seule contre Working et Persistent. Une cible absente, structurellement
invalide, ambiguë (même identifiant dans les deux espaces) ou accessible par
un lien symbolique est signalée comme référence à examiner, sans conclure
qu'il s'agit d'une corruption : une suppression historique peut être légitime.
Un dossier Working ou Persistent lié est signalé comme référence dangereuse
même si le fichier demandé n'existe pas à l'emplacement visé.
Le rapport ne réécrit aucun lien et n'affiche aucune valeur de contenu.
Les trois outils de lecture refusent aussi un lien symbolique sur un répertoire
parent de leurs sources sous la racine du moteur, notamment `memory/` ou
`memory/history/` ; la copie doit avoir une arborescence réelle à ces endroits.
L'inventaire et le précontrôle refusent également un lien symbolique sur la
racine du moteur ou un de ses ancêtres ; la simulation utilise ce même
inventaire avant toute lecture.

Pour chaque candidate, l'outil construit maintenant un objet core **en mémoire**
et vérifie son aller-retour dans le format 0.2. Le corps après le front matter
est conservé dans cet aperçu, y compris ses fins de ligne ; une révision YAML
structurée conserve ses indicateurs dans `metadata.legacy_revision`. Cette
vérification établit la sérialisabilité technique de la proposition, sans
valider le sens métier des champs ou autoriser une conversion sur disque.
Les relations du front matter vers une cible absente, ambiguë ou déjà bloquée
font bloquer la candidate, y compris par propagation le long d'une chaîne de
références. Une relation textuelle trouvée dans le corps est signalée pour
revue : l'ancien CLI `memory-relations` pouvait y inscrire des données que la
liste YAML `relations` ne représente pas. L'outil ne réécrit ni ne déduit ces
relations. Un type de relation absent, inconnu ou de forme incorrecte exige
également une décision avant conversion.
La variante `RELATES_TO` dans une relation Information est bloquée pour revue :
le modèle Relation et l'ancien CLI utilisent `RELATED_TO`, tandis que
`RELATES_TO` reste un type possible dans le contrat des Events. La simulation
ne renomme aucun type automatiquement.
`INSTANCE_OF` figure dans `memory-relation.md` et dans l'ancien CLI, mais pas
dans la liste de `information.md` : la simulation signale
`relation_schema_mismatch_requires_policy` au lieu de déclarer le document
convertible. Il faut trancher ce désaccord de schéma avant une conversion ;
aucune relation n'est supprimée ni renommée par l'outil.
Inversement, des types tels que `CONFIRMS` ou `ASSOCIATED_WITH` figurent dans
`information.md` mais pas dans le modèle Relation historique. Ils reçoivent
`relation_schema_extension_requires_policy`, distinct d'un type totalement
inconnu. Ce classement expose le choix de contrat à faire sans présumer de la
sémantique d'une donnée ancienne.

**Une candidate n'est pas une conversion validée** : le rapport ne crée
pas de document converti et ne vérifie pas tous les sens métier, notamment
les références des relations et la politique d'historique des révisions.
La correspondance proposée ne doit pas être appliquée avant décision sur le
format cible et tests sur données anonymisées.

## Correspondance des fichiers constatée dans le code

Chemins relatifs à `MEMORY_ENGINE_ROOT` ; la variable peut modifier cette racine.

| Chemin | Écrivain historique | Nouveau lecteur/écrivain | Décision requise |
| --- | --- | --- | --- |
| `memory/working/*.md` | Controller : Information YAML à front matter ; relations modifie parfois ces fichiers | Aucun dépôt canonique pour ce format | Conserver ou transformer sans perdre le corps ni les métadonnées ; définir le sort des Working non promues. |
| `memory/persistent/*.md` | Controller : copie du YAML, révision simple ou structurée selon le flux | `FilesystemBackend` : Information Markdown/JSON 0.2, lecture du **format core 0.1** | Convertir explicitement les YAML : le core 0.1 n'est pas le front matter historique. Vérifier ID, révision, contenu et champs sans équivalent. |
| `memory/persistent/threads/*.md` | Aucun écrivain Thread ancien identifié dans `services/` | `ThreadStorage` : core 0.1/0.2 | Vérifier les données réelles avant toute conversion ; ne pas supposer que tous les fichiers sont core. |
| `memory/history/events/*.md` | Controller : Events YAML (`CREATED`, `STORED`, etc.) ; relations : autre présentation texte (`RELATION_ADDED`) | `FilesystemEventRepository` : Event Markdown/JSON 0.2 | Certains types/champs historiques n'ont pas d'équivalent direct (`STORED`, `RELATION_ADDED`, `state.initial`, `metadata_transition`, `CAUSED_BY_OPERATION`) ; établir la politique de conservation avant conversion. |
| `memory/history/reviews/*.md` | Controller et relations : Reviews YAML, structures différentes | Aucun dépôt Review nouveau | Conserver séparément et définir modèle/états avant migration. |
| `memory/history/operations/*.json` | Controller : reçu `EXECUTED` avec `result`, `information_id` et hash d'un plan | `FilesystemOperationRepository` attend une opération typée avec snapshots et statuts | Ne pas interpréter un reçu historique comme opération récupérable ; préserver ces reçus et éviter leur lecture par le nouveau dépôt. |
| `memory/history/{events,operations}/thread-status-v1/*` | Aucun | Journaux isolés du coordinateur Thread | Garder les journaux ensemble ; lancer `recover` après arrêt brutal avant toute écriture. |
| `memory/history/{events,operations}/thread-create-v1/*` | Aucun | Journaux de création liée récupérable | Garder les journaux ensemble ; lancer `recover-all` après interruption avant toute nouvelle écriture. |
| `memory/history/pending-delete/*.json` | Aucun identifié | Demandes de suppression du backend | Préserver avec les Informations, vérifier leur statut et révision avant reprise. |

Le router et le classifier lisent le front matter historique ; le validator
sémantique et le moteur de relations le lisent ou le modifient directement.
L'executor produit des plans mais laisse les écritures au controller. Les anciens
écrivains ne participent pas aux verrous des nouveaux dépôts. Même quand le
chemin coïncide, les lancer ensemble exposerait les données à des courses et à
des erreurs de lecture.

## Décisions à prendre avant tout convertisseur

1. Déterminer sur la VM les services actifs et toutes les données présentes ;
   inventorier sur copie et recenser les signatures inconnues.
2. Définir la correspondance champ par champ, notamment révision, provenance,
   dates, relations, contenu libre et statuts sans équivalent. Pour chaque perte
   potentielle, bloquer ou archiver l'original explicitement.
3. Décider quels Events restent en archive historique et quels Events peuvent
   devenir des objets du nouveau modèle sans déformer leur sens. Préserver IDs,
   ordre et liens entre entités ; ne pas fabriquer de transitions manquantes.
4. Concevoir une simulation produisant un rapport déterministe, un convertisseur
   idempotent sur copie, une vérification avant/après et une procédure de retour.
5. Tester sur des fixtures anonymisées représentatives, puis sur une copie de
   la VM, avant de modifier les données réelles.

Ne jamais effectuer une conversion automatique au démarrage. Ne pas lancer les
anciens CLI en écriture sur des données déjà converties au format 0.2.

## Refus préalable des sources mixtes — 01/10, lot du soir

`convert` inspecte pending-delete, operation-receipts et les sous-familles
operations avant de créer la destination. Tout enregistrement opérationnel,
même terminal, inconnu ou corrompu, exige une politique d’import dédiée.
Un lien dans ces chemins est refusé sans être suivi. Les répertoires vides et
les fichiers réguliers .write.lock ne constituent pas un état opérationnel.
Les anciens JSON reconnus legacy directement sous operations restent archivables.

En cas de blocage, `converted=0`, `blocked_before_writes=true` et les chemins
figurent dans `rejected`. Le CLI affiche le rapport et retourne 1 ; aucun fichier
rapport n’est écrit dans la destination, même si celle-ci existe déjà. Cette
garantie suppose une source arrêtée, comme toute la procédure de migration.
Elle ne rend pas atomiques les conversions legacy ordinaires avec rejets de
contenu. Aucun reçu n’est importé ni aucune opération exécutée.

Validation locale : 12 nouvelles régressions échouent avant le correctif,
47 tests de migration passent après. Import opérationnel et VM restent ouverts.

## Index dérivé de réservations — clarification après relecture du 02/10

`memory/derived/information-reservations-v1.json` est un index facultatif et
reconstructible, décrit dans [RESERVATION-INDEX.md](RESERVATION-INDEX.md).
`memory/derived/` n'est pas une catégorie de `inventory` : un fichier inconnu ou
incorrect placé uniquement à cet emplacement ne produit pas d'alerte de cet
inventaire. Un inventaire sans alerte ne certifie donc pas l'état de cet index.
Utiliser `core.information.cli index-status` pour son inspection spécifique.
Les écritures qui utilisent l'index contrôlent sa structure/checksum et les
octets des sources ; un index invalide est reconstruit, une source invalide bloque.

Pour une conversion que les précontrôles autorisent :

- Un fichier régulier sous `memory/derived/` est conservé octet pour octet sous
  `destination/archive/derived/` et compté dans `archived_other`.
- La vérification indépendante compare aussi cette archive à la source.
- Le convertisseur ne le copie pas dans `destination/memory/derived/`, ne le
  valide pas comme index et ne l'active ni ne le reconstruit automatiquement.
- Les liens et chemins non archivables suivent les rejets généraux du
  convertisseur ; cette archive n'est pas un import d'état opérationnel.

La présence de journaux/reçus opérationnels, même terminaux, conserve la priorité :
elle bloque la conversion avant toute écriture de destination, archive comprise.
Le cache ne permet pas de contourner ce refus. Après une migration/import
compatible, reconstruire un index neuf depuis les journaux **canoniques de la
destination**, avec `index-rebuild` ; ne pas promouvoir l'archive en index actif.
Un index reconstruit ne réimporte pas les journaux absents et ne restaure pas
leurs réservations. L'import opérationnel reste un travail distinct non livré.

Vérification de cette clarification sur fixture temporaire : Persistent vide,
un fichier dérivé synthétique, inventaire sans alerte, une archive exacte,
pas d'index actif en sortie, vérification indépendante OK et source inchangée.
Pas de changement du convertisseur ni de validation VM dans ce lot documentaire.

## Import DELETED livré le 02/10 après-midi

Un chemin dédié `core.migration.deleted_receipts` importe désormais les seuls
reçus terminaux DELETED entre arbres core compatibles et distincts. Aperçu sans
écriture, refus des conflits sur tout le lot, publication atomique par reçu et
reprise par relance ; l'identité supprimée reste réservée en destination.
Voir [le contrat et les commandes](DELETED-RECEIPT-IMPORT.md). Ce chemin ne copie
ni les Informations, ni les autres journaux/reçus, ni les Events/Threads/index.
PENDING_DELETE, APPLYING_DELETE et CANCELLED restent refusés. Le convertisseur
legacy conserve intégralement son refus préalable des sources mixtes ; l'import
opérationnel général et la validation VM ne sont pas livrés.

## Import terminal des reçus compactés Information — 03/10

Le chemin `core.migration.write_receipts` importe explicitement les reçus de rejeu
et leurs Events exacts entre arbres core arrêtés au même état canonique, sans
transférer les corps ni réexécuter les commandes. Audits FAILED conservés,
conflits vérifiés avant publication, Event puis reçu, reprise par relance.
[Contrat, commandes, interruption et limites](WRITE-RECEIPT-IMPORT.md).
Le convertisseur legacy reste fermé aux sources opérationnelles mixtes.

## Annulations de suppression transférables explicitement — 03/10

L'import DELETED reste strict par défaut. `--include-cancelled` transfère aussi
les décisions CANCELLED sur un canonique présent identique en source/destination,
sans réactiver ni approuver une suppression. Les états actifs restent refusés.
[Contrat et limites](DELETED-RECEIPT-IMPORT.md).
