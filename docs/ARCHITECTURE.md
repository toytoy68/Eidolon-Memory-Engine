# Frontières actuelles du Memory Engine

État du dépôt au 2026-09-28. Les décisions ci-dessous concernent le code
présent ; leur adoption sur la VM 110 reste soumise à sauvegarde, inventaire et
tests. La source de vérité est le stockage en fichiers sous `memory/`, pas un
index Qdrant. La forme future des API et de la migration reste ouverte.

## Composants et droits d'écriture

| Composant | Lecture | Écriture actuelle | Règle de coexistence |
| --- | --- | --- | --- |
| `core/backend/FilesystemBackend` | `persistent/*.md`, `history/pending-delete/*.json`, Threads lors d'une suppression | Informations et demandes sous verrou ; suppression après contrôle des liens Thread | Seul écrivain nouveau des Informations core ; ne pas lancer le controller historique sur les mêmes fichiers. |
| `core/threads/ThreadStorage` | `persistent/threads/*.md` | Threads sous verrou, avec contrôle de révision | Les changements de statut doivent passer par le coordinateur d'Operations pour être récupérables. |
| `core/threads/ThreadInformationLinkService` | Information ciblée | Crée un Thread avec relation `CONCERNS` | Vérifie l'existence sous le verrou partagé de `persistent/` au moment de la création ; ne garantit pas que la cible restera présente après une suppression ultérieure. |
| `core/information/LinkedInformationDeletionService` | Backend partagé avec les Threads | Délègue l'approbation au backend | Façade de compatibilité ; la protection est appliquée aussi aux appels directs au backend. Les anciens CLI restent indépendants. |
| `core/operations/FilesystemThreadOperations` | Thread, Event et Operation | Journaux `thread-status-v1`, nouveau Thread ; ordre de verrous Thread → Operation → Event | Exécuter `recover` après redémarrage avant de reprendre les mutations. |
| `core/events/FilesystemEventRepository` | Events de son répertoire configuré | Nouveaux Events append-only | Le listing d'un dépôt n'agrège pas les autres sous-répertoires ni les Events anciens. |
| `services/memory-controller` | Working, Persistent, Reviews, anciens plans | YAML en `working/`, `persistent/`, `history/{events,reviews}/` et reçus JSON dans `history/operations/` | Écrivain historique direct, sans les verrous des dépôts core ; arrêter avant toute écriture core sur les mêmes données. |
| `services/memory-relations` | Informations Working, Reviews | Modifie Working ; crée Events et Reviews historiques | Même interdiction de concurrence ; son format Event ne correspond pas au format core. |
| `core/migration/{inventory,preflight}` | Signatures et métadonnées de fichiers | Aucune | Exécuter sur une copie sauvegardée. Ce ne sont pas des convertisseurs. |
| `core/monitoring/*` | Mesures, statuts, aperçus `.md` autorisés | Aucune | Le TDB peut lire pendant une écriture et afficher un état provisoire ; ne pas interpréter ses chiffres comme un snapshot atomique. |

Les autres anciens services lisent principalement les Informations YAML et
produisent des classifications ou plans. Leur comportement exact sur des
documents core 0.2 doit être validé avant de les réutiliser sur la même racine.
Le nouveau dispatcher de requêtes route actuellement les requêtes Thread ; il
ne constitue pas une API complète pour Information, Event ou l'interface web.

## Parcours de changement de statut Thread

Une commande avec identifiant d'opération et révision attendue prépare un plan
avec les états avant/après et un hash. Elle écrit l'état `APPLYING`, le nouveau
Thread et un Event déterministe, puis marque l'opération `COMMITTED`. En cas
d'interruption, `recover` reprend seulement si le Thread et l'Event correspondent
au plan. Un conflit est signalé sans écraser les données divergentes. Les
lecteurs peuvent voir un état intermédiaire entre ces fichiers.

Le CLI `python -m core.operations.cli` stocke ses journaux dans les
sous-répertoires `thread-status-v1` ; les reçus historiques Information dans
`history/operations/*.json` ne sont **pas** des opérations récupérables par ce
coordinateur.

## Avant la coexistence sur VM 110

1. Identifier les services et tâches planifiées qui écrivent actuellement ;
   arrêter leurs écritures le temps de la sauvegarde et de la validation.
2. Inventorier les données copiées (`docs/MIGRATION.md`) ; définir explicitement
   quels fichiers restent sous gestion ancienne ou nouvelle.
3. Ne démarrer qu'un chemin d'écriture par famille de données. Les anciens CLI
   doivent être adaptés ou retirés avant de partager une racine core 0.2.
4. Tester la reprise du journal Thread et le comportement applicatif sur copie.
5. Le TDB peut être servi en lecture seule sur le réseau local après validation
   de l'authentification et du port ; voir `docs/MONITORING.md`.

La conversion des données anciennes, les Events d'Information coordonnés et la
cohérence globale des lectures multi-fichiers restent à concevoir.
La création d'un Thread lié ne crée pas encore d'Event `CREATED` ; le scénario
intégré ne promet donc pas une traçabilité complète de sa création.
La suppression du backend prend les verrous `persistent/` puis `threads/`
pendant la vérification et l'approbation. Une demande de suppression peut rester
`PENDING_DELETE` si un lien existe. Cette protection couvre les appels directs
à `FilesystemBackend.approve_delete`, mais pas les écrivains historiques : ne
pas la présenter comme une garantie générale avant leur adaptation.

## Suppression interrompue

La suppression du backend retire actuellement le fichier Information puis
marque la demande `DELETED`. Une interruption entre ces deux écritures peut
laisser une demande `PENDING_DELETE` sans fichier. Sur une copie arrêtée :

```sh
python -m core.information.deletion_audit --root /chemin/vers/copie/du/moteur
```

L'audit signale les demandes malformées, `PENDING_DELETE` sans Information et
`DELETED` avec un fichier présent. Il ne lit pas le contenu des Informations,
n'écrit rien et ne répare pas la situation. Une réapparition du même identifiant
après suppression exige une analyse humaine ; le rapport n'en déduit pas la
cause. Un journal récupérable pour la suppression reste à concevoir.

## Audit des liens existants

Sur une copie de la racine du moteur, lancer :

```sh
python -m core.threads.link_audit --root /chemin/vers/copie/du/moteur
```

Cette commande lit les Threads et leurs relations `CONCERNS`, puis vérifie les
Informations ciblées. Elle rapporte des comptes et des chemins de Threads avec
des codes de raison, sans contenu des mémoires, et ne modifie aucun fichier.
Code retour 1 en cas d'anomalie. Elle accepte les documents core lisibles ; un
ancien front matter Information est signalé invalide jusqu'à migration. Le
résultat peut changer si un écrivain intervient pendant l'audit : utiliser une
copie arrêtée pour une décision de migration ou de suppression.
