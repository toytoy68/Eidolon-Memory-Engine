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
les clés YAML dupliquées, l'identité fichier/objet, la révision simple ou
`revision.number`, trois champs d'état de base et la présence d'un corps. Il
compte les documents core déjà présents et liste les fichiers bloqués avec des
codes de raison, sans inclure le contenu. Code retour 1 en présence de blocages.
Un `legacy_candidate` signifie seulement **structure minimale analysable** :
la conversion, la validité métier, les références et la conservation de tous les
champs ne sont pas encore garanties. Aucun fichier n'est converti.

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
