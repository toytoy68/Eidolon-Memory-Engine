# Annexe — détail des écritures Information coordonnées

Annexe de [DESIGN-INFORMATION-WRITES.md](DESIGN-INFORMATION-WRITES.md), texte
de référence. Importée de la proposition Claude `maj2`, revue puis harmonisée
avec les décisions D7, D8 et D9 validées par toytoy le 2026-09-30.

Statut au 01/10 : **service et compaction v1 implémentés et testés en local,
non validés sur VM**. Le contrat livré est décrit dans
[INFORMATION-WRITES.md](INFORMATION-WRITES.md) ; les sections ci-dessous
conservent la conception et ses limites initiales. Les formats précis et les signatures seront versionnés lors de
l'implémentation. Aucun test nouveau ni aucune validation VM n'est apporté par
ce document ; les estimations d'avancement restent inchangées.

## 1. Problème

Les parcours Thread **coordonnés** (création liée, statut, suppression) passent
par un journal d'Operation : snapshot immuable, hash du plan, états `PREPARED → APPLYING →
COMMITTED`, reprise idempotente. Création et statut produisent un Event
déterministe ; la suppression Thread ne produit pas d’Event métier. Les écritures Information
ne suivent pas ce modèle :

- `FilesystemBackend.store` et `update` écrivent le fichier sous le verrou
  `persistent_root`, sans Operation ni Event.
- Une interruption entre l'écriture et un Event éventuel laisserait un état non
  reconstructible : le fichier existe, l'historique n'en garde aucune trace.
- `ThreadStorage.create` et `update` restent appelables directement, sans
  Operation ni Event (reproduit lors de la revue du 2026-09-30) ; T-039 (suppression
  autorisée après un statut interrompu) est corrigé en local pour les journaux
  canoniques (`for_history`), non validé sur VM.
  Les Threads ont donc des mécanismes de reprise, mais leur usage systématique
  n'est pas garanti : cela reste une part de T-031.
- Seule la suppression Information dispose déjà d'un reçu (`APPLYING_DELETE`) et
  d'une reprise explicite.

## 2. Principes retenus (calqués sur les Threads)

1. Le fichier Information reste la source de vérité ; l'Operation est un
   journal technique, l'Event est le fait métier.
2. Le plan contient le **snapshot sérialisé complet** (avant/après), pas un
   delta : les valeurs à réappliquer sont figées. La reprise vérifie néanmoins
   les fichiers courants, les Events et les réservations de suppression.
3. `operation_id` et `event_id` sont fournis par l'appelant, valides avant
   toute écriture, et servent de clés d'idempotence : rejouer la même commande
   ne duplique ni fichier ni Event ; réutiliser un identifiant pour une
   commande différente lève `OperationConflict`.
4. L'Event est déterministe (fonction du plan), ce qui permet de le comparer à
   celui déjà sauvegardé après une interruption.
5. Aucun chemin de reprise implicite au démarrage : la reprise reste une
   commande explicite (cohérent avec T-015, à valider).

## 3. Nouveaux types

### OperationType

- `INFORMATION_CREATE`
- `INFORMATION_UPDATE`

La suppression garde son reçu actuel ; son alignement sur `OperationRecord`
est hors périmètre ici (**[DÉCISION D5]**).

### Plans (dataclasses frozen, comme `ThreadCreatePlan`)

| Plan | Champs |
| --- | --- |
| `InformationCreatePlan` | `event_id`, `after_state` (texte sérialisé, révision 1 pour une création métier) |
| `InformationUpdatePlan` | `event_id`, `before_state`, `after_state` (révision = précédente + 1) |

`OperationRecord.revision` reprend la convention existante :
`revision == previous_revision + 1`. Pour une création, `previous_revision`
vaut 0 et `revision` vaut 1 (**[DÉCISION D1, tranchée]** : révision 1 pour une nouvelle Information
métier. Un parcours d'**import** distinct conserve les révisions historiques
sans les ramener à 1 ; son contrat est à définir avec T-021.)

### Events

| Opération | `event_type` | Cible | `state_transition` |
| --- | --- | --- | --- |
| Création | `CREATED` | `information_id` | `before={}`, `after` = champs épistémiques et statut |
| Mise à jour | `UPDATED` | `information_id` | champs modifiés uniquement (avant/après) |

- Provenance : `source_type="SYSTEM_GENERATED"`, `source="information-service"`,
  `actor` fourni par l'appelant, `timestamp` = horodatage du snapshot.
- Relation `CAUSED_BY` vers `operation_id`, comme `thread-status-service`.
- `Event.__post_init__` accepte déjà `CREATED` et `UPDATED` avec
  `information_id` ; aucun changement du modèle Event n'est nécessaire.
- **[DÉCISION D2]** : le contenu de `state_transition` ne doit pas recopier le
  texte de l'Information (taille, données sensibles dans l'historique). Retenu :
  métadonnées et hash de contenu seulement. Attention : le snapshot complet du
  plan conserve malgré tout le texte dans l'Operation ; sa rétention doit être
  compatible avec les suppressions (transition récupérable vers un reçu compact une fois
  `COMMITTED`, décrite au §10 ; aucune suppression directe de champs).

## 4. Séquence d'écriture

Ordre cible commun : `persistent_root`, puis `threads_root` si les liens
Thread sont examinés, puis les journaux Operation/reçus dans un ordre fixe,
puis les Events si nécessaire. Le verrou Persistent doit être partagé par
création, modification, compaction et approbation de suppression, depuis les
contrôles jusqu'à leur publication durable. Le seul verrou du journal ne
suffit pas à coordonner ces familles. Réutiliser cet ordre dans les reprises ;
tester les acquisitions et la concurrence avant de revendiquer l'absence
d'interblocage. Aucun nouveau chemin n'acquiert Persistent après Thread.

Création :

1. Valider identifiants, forme (`_validate_memory_shape`), aller-retour de
   sérialisation, absence de reçu de suppression réservant l'identité.
2. Sous verrous : si l'Operation existe, comparer au plan attendu puis
   reprendre ; sinon vérifier qu'aucune Operation incomplète ne cible cet
   `information_id`.
3. Créer l'Operation `PREPARED` (plan + hash).
4. Passer en `APPLYING` (mise à jour de l'Operation).
5. Écrire le fichier s'il est absent ; s'il existe, il doit être égal au
   snapshot, sinon `OperationConflict`.
6. Sauvegarder l'Event s'il est absent ; s'il existe, il doit être égal à
   l'Event attendu.
7. Passer l'Operation en `COMMITTED`.

Mise à jour : mêmes étapes, avec contrôle de révision à l'étape 2 (fichier
courant == `before_state`) et, à l'étape 5, tolérance de `before_state` ou
`after_state` uniquement.

## 5. Reprise et cas d'interruption

| Interruption | État observé | Reprise |
| --- | --- | --- |
| Avant la création de l'Operation | rien | commande rejouable telle quelle |
| `PREPARED`, fichier inchangé | Operation seule | passe en `APPLYING`, écrit |
| `APPLYING`, fichier non écrit | Operation seule | écrit le fichier, puis Event |
| `APPLYING`, fichier écrit, pas d'Event | fichier == `after_state` | sauvegarde l'Event |
| Fichier écrit et Event sauvegardé | avant `COMMITTED` | marque `COMMITTED` |
| Fichier divergent des deux snapshots | corruption ou autre écrivain | `OperationConflict`, marqué bloqué, revue humaine |
| Identité supprimée pendant une opération inachevée | reçu `APPLYING_DELETE` ou `DELETED` | `OperationConflict`, pas de recréation |

Une commande `recover-all` distincte (ou une extension de
`core.operations.cli`) traite les Operations Information séparément des
Threads, avec rapport individuel des blocages, comme `recover()` actuel.

## 5bis. Conflits entre opérations (à respecter dès la première version)

Cette matrice décrit le **comportement cible du service coordonné** pour une
nouvelle commande ; elle ne prétend pas décrire les protections déjà présentes
dans toutes les primitives. Les rejeux d'une commande COMMITTED sont traités
séparément : ils rendent le résultat enregistré sans restaurer le fichier.

| État du reçu | Nouvelle création | Nouvelle modification | Suppression |
| --- | --- | --- | --- |
| Aucun reçu | Possible si cible absente et sans opération incompatible | Possible sur révision attendue et cible existante | Demande explicite, sous contrôle des liens et opérations |
| `PENDING_DELETE` | Refusée, identité réservée | Refusée jusqu'à annulation explicite (D7) | Rejeu identique de la demande ; approbation après compaction et contrôles |
| `APPLYING_DELETE` | Refusée | Refusée | Reprise explicite, sans nouvelle Operation métier |
| `DELETED` | Refusée, identité réservée | Refusée | Identité déjà supprimée ; ne pas rejouer ses écritures |
| `CANCELLED` | Refusée, identité conservée (D9) | Possible sur cible existante et révision attendue | Nouvelle demande possible |

**Code actuel :** `store` refuse une cible déjà présente puis, si elle est
absente, tout reçu de suppression existant, quel que soit son état. Ce
comportement reste inchangé. `update` ne consulte pas directement le reçu de
sa cible ; les refus de modification ci-dessus sont à implémenter. Une
annulation conserve normalement le fichier. `CANCELLED` sans fichier est une
incohérence à examiner, pas une permission de recréer automatiquement l'identité.
L'approbation actuelle n'est pas une API de rejeu de reçus déjà `DELETED`.

- Une suppression ne peut avancer tant qu'une Operation Information incomplète
  réserve sa cible ; les réservations Thread et les liens sont également examinés.
- Deux nouvelles Operations incomplètes sur la même identité sont refusées.
- La reprise autorisée continue son propre plan ; les commandes incompatibles
  restent bloquées jusqu'à sa terminaison ou résolution explicite.
- Même commande rejouée : aucune nouvelle révision ni Event supplémentaire.
- Le contrôle des plans restants et le passage à `APPLYING_DELETE` sont
  coordonnés sous le verrou Persistent partagé : aucune écriture ne peut
  intercaler un nouveau plan contenant le texte entre ces deux actions.

## 6. Coexistence et migration

- `store` et `update` font partie du contrat `MemoryBackend` et sont utilisés
  par `core/migration/converter.py`. **[DÉCISION D3, reformulée]** : ne pas les
  rendre privés par simple renommage. Réserver les écritures métier à un
  service coordonné, migrer les appelants par étapes, conserver les tests du
  stockage et ajouter ceux du service.
- Écrivains historiques (`services/*`) : le garde `core/migration/legacy_guard.py`
  reste la barrière ; le nouveau chemin ne les rend pas sûrs. Aucun démarrage sur
  fichiers historiques avant T-021.
- Les Informations déjà présentes n'ont pas d'Event `CREATED` rétroactif.
  **[DÉCISION D4, tranchée]** : pas de `CREATED` historiques fabriqués. Les
  archives existantes sont conservées ; au besoin, une trace d'import
  clairement identifiée et datée de la migration.

## 7. Plan de tests (à écrire avec le code)

Miroir de `tests/integration/` pour les Threads :

- interruption avant/après chaque étape du §4, puis reprise. Distinguer trois
  niveaux de preuve : exception simulée (rapide, dans la suite), arrêt de
  processus (`kill`), arrêt brutal de VM et coupure électrique du stockage
  physique. Un arrêt de VM ne prouve pas le dernier niveau ; aucune preuve
  de durabilité après coupure réelle n'est apportée ici ;
- reprise
  vérifiant : un seul fichier, un seul Event, Operation `COMMITTED` ;
- rejeu de la même commande : résultat identique, aucune écriture ;
- réutilisation d'`operation_id` ou d'`event_id` pour une autre commande ;
- conflit de révision, identité réservée par un reçu de suppression ;
- deux processus concurrents (à exécuter sur VM avec les cinq cas existants) ;
- test d'ordre des verrous face à la création liée et à la suppression ;
- non-régression : la suite existante inchangée (674 réussis, 5 de concurrence
  exclus d'après la séance du 30/09 ; non revérifié dans cet environnement), hors appelants de
  `store`/`update` migrés (D3).

## 8. Orientations retenues et limites

| Id | Sujet | Orientation |
| --- | --- | --- |
| D1 | Création imposée à la révision 1 ? | Oui pour le métier ; parcours d'import séparé |
| D2 | Contenu de `state_transition` | Métadonnées + hash ; définir la rétention du snapshot du plan |
| D3 | Sort de `store`/`update` directs | Service coordonné pour le métier ; migration des appelants par étapes |
| D4 | Events rétroactifs à la migration | Non ; trace d'import datée |
| D6 | Rapprocher `Memory` et Information | Mapping textuel explicitement étiqueté livré (T-040) ; limites décrites ci-dessous |
| D5 | Aligner la suppression Information sur `OperationRecord` | Journal plus tard ; conflits création/modification/suppression définis dès maintenant (§5bis) |
| D7 | Modifier pendant `PENDING_DELETE` | Annulation explicite requise avant nouvelle modification métier |
| D8 | Empreinte de commande | Conservée dans le reçu compact v1, sans garantie de confidentialité ni effacement implicite à la suppression |
| D9 | Identité après `CANCELLED` | Reste réservée ; modifier la cible existante, sans recréation automatique |

## 8bis. Cohérence avec les schémas et le modèle (vérifiée par lecture, 2026-09-30)

- **Deux modèles d'Information coexistent** (`Memory` stocké, `Information`
  du schéma). D6 est traitée par `core/information/mapping.py`, dans ses
  limites : il ne couvre que les Informations **textuelles explicitement
  étiquetées** (champ manquant → `KeyError`, étiquette inconnue →
  `ValueError`) ; les historiques non classés exigent une décision de
  migration. Les snapshots du plan doivent donc conserver le **`Memory`
  complet**, extensions comprises, et non la seule projection `Information`.
  Le `state_transition` des Events porte sur la projection.
- **Révision de l'Event.** `schemas/memory-event.md` : `revision` est la
  révision de l'entité au moment de l'Event. Cohérent avec §3 (révision du
  snapshot `after`).
- **Format des identifiants.** Le schéma Event illustre
  `event-YYYYMMDD-HHMMSS-xxxxxxxx` ; le dépôt Event et le dépôt Operation
  n'imposent que `[A-Za-z0-9._-]+`. Des identifiants déterministes fournis par
  l'appelant (§2) sont donc acceptés, à condition de documenter cette
  convention dans le schéma Event.
- **Relations.** `RELATED_TO` (Information) et `RELATES_TO` (Events) restent
  deux contrats distincts ; le service d'écriture ne doit normaliser ni l'un ni
  l'autre. Le backend accepte `target_id` ou `target` dans une relation : le
  snapshot du plan conserve la forme reçue.

## 10. Reçu compact et compaction (proposition pour D2, révisée)

Objectif : ne pas conserver indéfiniment le texte des Informations dans les
snapshots des Operations, sans perdre l'idempotence ni la détection de conflit.
`OperationRecord` exige aujourd'hui un plan pour chaque type : on **ne peut pas
simplement retirer le plan**. La compaction est donc un changement de format
versionné, pas une suppression de champ.

**Reçu compact** (`format_version`, lecteur qui refuse une version inconnue) :

| Champ | Contenu |
| --- | --- |
| `format_version` | entier, dès la première version |
| `status` | `COMMITTED`, état terminal |
| `operation_id`, `operation_type`, `target_id` | inchangés |
| `previous_revision`, `revision` | inchangés |
| `command_fingerprint` | voir ci-dessous |
| `plan_hash` | `execution_plan_hash` de l'Operation d'origine |
| `event_id` | Event produit |
| `result` | identité, révisions, `event_id` : résultat minimal rejoué |
| `compacted_at` | horodatage de la compaction |

**Transition récupérable** (famille de fichiers distincte, sous le verrou
Persistent puis les verrous des journaux concernés dans l’ordre commun) :

1. Vérifier les conditions (ci-dessous) sur l'Operation `COMMITTED`.
2. Publier durablement le reçu compact (écriture atomique + fsync du dossier).
3. Relire le reçu et vérifier qu'il correspond à l'Operation.
4. Seulement ensuite, retirer l'Operation d'origine (et son plan), puis
   synchroniser le répertoire d'origine (`fsync`) avant d'annoncer la fin.
5. Reprise : si Operation et reçu coexistent et correspondent → achever le
   retrait durable ; s'ils divergent → bloquer sans choisir automatiquement
   une version. Si seul un reçu valide existe → état final. Un reçu invalide
   sans Operation récupérable → blocage et revue humaine. Sans aucun fichier,
   on ne peut pas déduire qu'une ancienne opération a existé et disparu.
   Les lecteurs consultent les deux emplacements avant de décider ; une
   nouvelle commande ne doit pas contourner un reçu de la même identité
   d'opération. Une interruption avant publication du reçu laisse l'Operation
   d'origine comme source de reprise de la compaction.

**Conditions de compaction** (toutes requises) : Operation `COMMITTED` (jamais
`PREPARED`, `APPLYING` ni `FAILED`) ; Event présent et égal à l'attendu ; ni
Operation bloquée ni reçu `APPLYING_DELETE` sur l'identité ; commande
explicite, jamais au démarrage, avec rapport ; sauvegarde préalable si la
politique l'exige (à définir).

**Rejeu après compaction** : même `operation_id` et même empreinte → renvoyer
`result` sans écrire ; même `operation_id`, autre empreinte → `OperationConflict`.
L'état courant de l'Information n'est pas consulté.

**D8 validée — empreinte conservée en v1.** Conserver l'empreinte de la
commande normalisée pour reconnaître un rejeu et détecter un contenu différent,
y compris après suppression du fichier Information. Les champs volatils doivent
être figés ou exclus selon le contrat de commande, jamais régénérés au rejeu.
Une empreinte n'est ni un chiffrement ni une garantie d'effacement ; un contenu
court devinable peut rester testable. Les `plan_hash` et empreintes de contenu
des Events ont également cette limite. Aucun effacement automatique de ces
empreintes n'est décidé en v1 ; leur retrait futur exige un contrat explicite
sur les garanties de rejeu restantes.

Le HMAC n'est pas retenu pour cette première version. Une clé d'installation
partagée ne peut pas être détruite pour effacer une seule identité sans affecter
les autres reçus. L'ignorer pour une identité ne détruit pas sa capacité de
vérification. Un sel public tel que `operation_id` ne rend pas le texte secret.

**Suppression et compaction — ordre sans impasse.** Les deux règles « compacter
avant de valider la suppression » et « pas de compaction pendant
`APPLYING_DELETE` » ne sont compatibles que dans cet ordre :
1. À `PENDING_DELETE` (demande), compaction autorisée et requise pour les
   Operations `COMMITTED` de l'identité ;
2. le passage à `APPLYING_DELETE` est refusé tant qu'une Operation de cette
   identité porte encore un plan avec contenu. Ce contrôle et la publication
   durable de `APPLYING_DELETE` se font sans relâcher le verrou Persistent
   partagé avec tous les écrivains concernés ;
3. une fois en `APPLYING_DELETE`, aucune nouvelle Operation ni compaction ;
   l'interruption se reprend par la reprise de suppression existante ;
4. si une Operation de l'identité est bloquée, la suppression reste bloquée
   jusqu'à revue humaine (pas de purge forcée).
Une Operation `PREPARED`/`APPLYING` sur l'identité empêche la demande de
suppression d'avancer, conformément à la matrice de §5bis.

D7, D8 et D9 sont validées. Restent à spécifier pendant T-041/T-042 : schéma
sérialisé précis, normalisation de commande, durée de conservation des reçus,
politique des sauvegardes et protocole futur d'effacement des empreintes. Tant
que ce protocole n'existe pas, les reçus sont conservés même après suppression
de la cible. Les contrôles livrés le 01/10 sont référencés dans INFORMATION-WRITES.md.

## 11. Limites

Claude n'a pas exécuté de tests dans son environnement de rédaction. La revue
de cette annexe et son intégration sont documentaires ; la suite n'a pas été
relancée pour cette édition. Le dernier résultat du code inchangé reste 674
réussis et 5 exclus. Ce bilan initial précède le lot du 01/10 : ses tests du service et de la
compaction sont décrits dans INFORMATION-WRITES.md. Aucun essai VM revendiqué.

## 12. Précisions de la revue reçue le 2026-10-01

- La commande v1 distingue création/modification, identité, révision attendue,
  Memory complet (extensions comprises), event_id, acteur et horodatage explicite.
  operation_id sert de clé de recherche, hors empreinte. La canonicalisation
  JSON conserve les valeurs, trie les clés, conserve l'ordre des listes, utilise
  UTF-8 sans espaces de présentation et refuse les nombres non JSON. Aucun
  horodatage n'est régénéré au rejeu. La forme précise sera documentée avec le code.
- L'opération/reçu terminal est consulté et comparé à la commande avant les
  contrôles de nouvelle écriture (cible actuelle, réservation de suppression).
  Le rejeu rend un résultat minimal, sans restaurer un snapshot historique.
- Annuler PENDING_DELETE et modifier sont deux commandes distinctes, non une
  transaction. Une interruption entre elles conserve CANCELLED et l'Information
  inchangée ; une nouvelle suppression peut s'intercaler et bloquer la modification.
- Recovery, inventaire et audit doivent consulter journal et reçu ensemble. Une
  coexistence divergente bloque ; le reçu ne gagne jamais automatiquement.
- Une trace des acquisitions complète les tests d'interruption. Elle ne remplace
  ni les tests concurrents ni les essais de durabilité sur VM.
