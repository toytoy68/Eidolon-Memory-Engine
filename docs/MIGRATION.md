# Inventaire préalable à la migration des données

État : **inventaire en lecture seule disponible ; migration non implémentée**.
Le code historique dans `services/` et les nouveaux dépôts dans `core/` ne
partagent ni tous leurs formats, ni leur protocole d'écriture. Cette analyse
porte sur le dépôt ; les données et services de la VM restent à examiner.

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
sous-dossiers non listés ne sont pas inventoriés.

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
ambigu et ne contribuent pas au comptage des types.
L'identifiant `information_id` de ces anciens fichiers est contrôlé en lecture
seule contre Working et Persistent. Une cible absente, structurellement
invalide, ambiguë (même identifiant dans les deux espaces) ou accessible par
un lien symbolique est signalée comme référence à examiner, sans conclure
qu'il s'agit d'une corruption : une suppression historique peut être légitime.
Le rapport ne réécrit aucun lien et n'affiche aucune valeur de contenu.
Les trois outils de lecture refusent aussi un lien symbolique sur un répertoire
parent de leurs sources sous la racine du moteur, notamment `memory/` ou
`memory/history/` ; la copie doit avoir une arborescence réelle à ces endroits.

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
