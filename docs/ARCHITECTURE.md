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
| `core/operations/FilesystemLinkedThreadCreation` | Information, Thread, Event et Operation | Journal `thread-create-v1`, Thread lié et Event `CREATED` | Prend les verrous Persistent → Thread → Operation → Event ; reprendre avec `recover-creations` avant d'autres mutations. |
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

### Décision provisoire pour les anciens écrivains

Conserver `memory-controller` uniquement pour les données historiques YAML
tant que la migration n'est pas décidée. Ses commandes `execute` et `update`
sur Persistent Memory prennent désormais le verrou du nouveau backend et
refusent une racine contenant des Informations core, des Threads core ou des
journaux d'opérations Thread. Ce contrôle protège contre une cohabitation
accidentelle déjà visible ; il ne transforme pas ses Events/Reviews YAML en
Events core ni ne répare les écritures historiques interrompues.

`memory-relations` écrit dans Working Memory et produit des Events/Reviews
historiques : sa commande `add` refuse maintenant les sources hors de
`memory/working/*.md` et prend le verrou de ce répertoire. Le conserver
uniquement sur une racine historique isolée. Le controller historique partage
désormais le verrou Working lors des commandes `ingest`, `update` d'un fichier
Working et `review`. Ses commandes `update` et `review` refusent aussi les
chemins hors de leurs répertoires respectifs. Leurs Events/Reviews ne forment
toujours pas une transaction atomique. Les
CLI classifier, router, executor et semantic-validator sont essentiellement
lecteurs/producteurs de plans ; les adapter après choix du format cible.
Avant une mise en service core, arrêter les écrivains historiques, migrer ou
archiver leurs données sur une copie, puis rediriger les usages nécessaires vers
les services core journalisés. Une détection de fichiers ne suffit pas à
autoriser deux piles actives sur la même racine.

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

La création liée récupérable passe par `FilesystemLinkedThreadCreation.create`
via `ThreadService.create_linked` ou le CLI
`python -m core.operations.cli create-linked` :
elle prépare un snapshot et un journal dans `thread-create-v1`, puis écrit le
Thread et son Event `CREATED`. Après interruption, exécuter
`python -m core.operations.cli recover-all` : la commande reprend les créations,
puis les changements de statut, et renvoie un code non nul si un journal reste
bloqué. Les commandes `recover-creations` et `recover` restent disponibles pour
chaque famille. Un Thread ou Event divergent bloque la
reprise sans écrasement. La création directe via `ThreadInformationLinkService`
reste disponible mais n'écrit ni journal ni Event ; les autres chemins de
création restent à adapter.
`ThreadService.recover_all` fournit le même ordre de reprise aux appelants
Python lorsque les deux coordinateurs lui sont injectés.
L'écriture directe de `ThreadStorage.create` prend maintenant les verrous
`persistent/` puis `threads/` et vérifie que chaque cible `CONCERNS` est une
Information core lisible au même identifiant. `ThreadStorage.update` refuse
de changer les cibles `CONCERNS` directement. Cela protège les liens contre
une suppression concurrente, mais une création directe reste dépourvue de
journal et d'Event : les applications doivent utiliser le coordinateur de
création pour obtenir une reprise complète.
Le CLI de changement de statut vérifie les journaux de création en attente et
refuse la mutation du Thread concerné avant `recover-creations`. Les appels
Python qui construisent `FilesystemThreadOperations` doivent lui passer le
dépôt d'opérations de création pour bénéficier du même contrôle.

Exemple sur une racine core isolée (l'Information cible doit déjà exister) :

```sh
python -m core.operations.cli create-linked thread-1 info-1 \
  --title "Examen" --objective "Vérifier info-1" \
  --created-at "2026-09-28T08:00:00+02:00" \
  --operation-id creation-thread-1
```

Rejouer la même commande exige les mêmes champs et la même date ; un identifiant
d'opération réutilisé avec un autre contenu est refusé.

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
Seul le nouveau chemin de création journalisée produit un Event `CREATED` ;
les lecteurs d'un répertoire Event n'agrègent pas les sous-répertoires.
La suppression du backend prend les verrous `persistent/` puis `threads/`
pendant la vérification et l'approbation. Une demande de suppression peut rester
`PENDING_DELETE` si un lien existe. Cette protection couvre les appels directs
à `FilesystemBackend.approve_delete` ; elle bloque aussi une relation `CONCERNS`
sans cible fiable ou avec deux cibles contradictoires. Elle ne couvre pas les
écrivains historiques : ne pas la présenter comme une garantie générale avant
leur adaptation.

## Suppression interrompue

La suppression du backend inscrit `APPLYING_DELETE` avec une empreinte SHA-256
du fichier avant de le retirer, puis marque la demande `DELETED`. Un nouvel
appel `approve_delete` avec le même identifiant d'opération reprend une demande
`APPLYING_DELETE`, sous les verrous et après contrôle des liens Thread. Si le
fichier existe encore, son empreinte doit correspondre ; s'il est absent, le
reçu est finalisé. Une annulation ou une nouvelle demande ne peut pas remplacer
une opération commencée. La reprise est explicite, jamais automatique.

Les anciennes demandes `PENDING_DELETE` sans fichier restent ambiguës et ne
sont pas reprises. Le journal ne protège pas contre les écrivains historiques
qui ignorent ces verrous, ni contre une recréation externe avec les mêmes octets.

La demande en attente n'est plus remplacée par une autre demande ; un rejeu
identique est accepté sans écriture. Une demande `CANCELLED` peut toutefois être
remplacée par une nouvelle demande sur le même identifiant : ce fichier n'est
pas un historique complet des décisions. L'approbation et l'annulation refusent
un reçu dont l'identité Information ne correspond pas au fichier demandé.

Sur une copie arrêtée :

```sh
python -m core.information.deletion_audit --root /chemin/vers/copie/du/moteur
```

Une commande distincte affiche le même audit par défaut et peut reprendre
explicitement les **seuls** reçus `APPLYING_DELETE` après sauvegarde, sur une
racine arrêtée :

```sh
python -m core.information.deletion_recovery --root /chemin/vers/copie/du/moteur --apply
```

Chaque reçu est repris via `FilesystemBackend.approve_delete`, sous ses verrous
et avec les contrôles de liens et d'empreinte. Le rapport liste les reprises et
les blocages ; une nouvelle exécution ignore les reçus déjà `DELETED`. Les
anciens `PENDING_DELETE` sans fichier ne sont jamais finalisés par déduction.

L'audit signale les demandes `APPLYING_DELETE` à reprendre, les demandes
malformées, `PENDING_DELETE` sans Information et
`DELETED` avec un fichier présent. Il ne lit pas le contenu des Informations,
n'écrit rien et ne répare pas la situation. Une réapparition du même identifiant
après suppression exige une analyse humaine ; le rapport n'en déduit pas la
cause.

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
