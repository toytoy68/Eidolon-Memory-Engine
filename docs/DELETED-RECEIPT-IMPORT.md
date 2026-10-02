# Import explicite des reçus terminaux de suppression — T-021/T-033

Un reçu `memory/history/pending-delete/<id>.json` à l'état DELETED réserve
l'identité d'une Information supprimée. Le perdre lors d'un transfert permettrait
à la destination de recréer cette identité. Ce premier import opérationnel
copie ces seuls reçus, octet pour octet, vers leur emplacement canonique actif.
Il ne supprime aucune Information et ne réexécute aucune ancienne commande.

## Commandes et portée

Sur une source core arrêtée et une destination initialisée, contenant chacune
`memory/persistent/` :

```sh
python -B -m core.migration.deleted_receipts \
  --source /copie-source --destination /destination
python -B -m core.migration.deleted_receipts \
  --source /copie-source --destination /destination --apply
```

Sans `--apply`, aucun fichier, répertoire ni verrou n'est créé. Le JSON décrit
les identités, révisions, IDs d'opération, empreintes SHA-256 et actions proposées
IMPORT/UNCHANGED. L'API correspondante est `inspect_deleted_receipts(source,
destination)` ; `import_deleted_receipts(source, destination)` réalise l'import.
Le CLI retourne 1 pour BLOCKED, 0 pour READY, IMPORTED ou UNCHANGED.

La destination doit être préparée séparément : l'import n'initialise pas un
nouveau moteur. La source doit rester arrêtée, y compris pendant une relance.
Arrêter aussi les écrivains legacy, éditeurs externes et écrivains de journaux
bas niveau en destination. Les écrivains canoniques coopératifs sont protégés
par les verrous Persistent puis Thread, lorsque ce répertoire existe.

Ce chemin ne remplace pas `core.migration.converter` : le convertisseur legacy
continue de refuser les sources mixtes opérationnelles. L'import requiert une
readiness valide dans les deux arbres. Il ne convertit pas de données legacy,
ne copie ni corps d'Information, ni Thread, ni Event, ni journal/reçu de commande,
ni index. Il ne restaure donc pas à lui seul l'historique de rejeu d'un moteur. Le
[chemin dédié Information](WRITE-RECEIPT-IMPORT.md) importe séparément les reçus
compactés de commande et leurs Events.

## Conditions et refus

Tous les candidats sont examinés avant la première publication. Le lot entier
est refusé si l'un d'eux ne convient pas :

- Arbres qui se chevauchent, répertoires invalides ou ancêtres symboliques.
- Readiness bloquée en source ou destination : FAILED, journal inconnu,
  corruption ou opération à reprendre, notamment APPLYING_DELETE.
- Entrée inconnue, sous-répertoire, lien symbolique ou reçu invalide dans le
  répertoire source ; seul un fichier régulier `.write.lock` y est ignoré.
- État autre que DELETED par défaut ; CANCELLED accepté uniquement avec
  `--include-cancelled`. PENDING_DELETE/APPLYING_DELETE restent refusés.
- Information canonique présente sous l'identité candidate dans l'un des arbres.
- Référence entrante Information/CONCERNS ou source illisible empêchant de
  vérifier ces références ; mêmes gardes que pour une suppression canonique.
- Snapshot d'écriture Information de cette identité encore non compacté.
- Reçu de destination différent, même si sa seule différence est de présentation.
  Un reçu déjà identique est reconnu comme importé ; rien n'est remplacé.

Le lecteur strict existant vérifie la forme et l'identité du reçu, son état,
sa révision et l'empreinte du contenu supprimé. Cette empreinte est conservée ;
le contenu étant absent, l'import ne peut pas la recalculer ni authentifier
l'histoire déclarée. Importer seulement des reçus issus d'une source connue.
Le résultat garantit la réservation d'identité dans cette destination, pas une
preuve d'effacement de toutes les copies externes ni une fusion générale de deux
historiques indépendants.

Un refus au précontrôle ne modifie aucun des deux arbres. Après acquisition
des verrous, l'import relit les sources et la destination : il ne fait pas
confiance à un aperçu antérieur. Un changement intervenu entre les deux contrôles
peut provoquer un refus ; les fichiers de verrou acquis peuvent alors exister.

## Publication et reprise

Chaque reçu est publié par fichier temporaire vidé sur disque, renommage atomique
et synchronisation du répertoire. Les octets d'origine sont préservés, y compris
CRLF ; les anciennes identités ne sont ni renumérotées ni révisées.
Une relecture finale exige que tous les reçus soient identiques en destination
et que les contrôles restent satisfaits avant d'annoncer IMPORTED.

Le lot n'est pas une transaction globale. Une panne d'E/S ou un arrêt du processus
peut laisser un préfixe de reçus déjà actifs. Relancer avec la même source arrêtée
termine les manquants sans réécrire les reçus acquis. Un conflit découvert à la
relance bloque le reste ; aucun rollback ou remplacement forcé n'est proposé.
L'API laisse remonter une erreur de publication ; le CLI signale BLOCKED et la
possibilité d'un préfixe acquis, avec invitation à relancer sur la même source.
Une limite est conservée : un arrêt avant le renommage peut laisser un fichier
temporaire inconnu. L'inventaire bloque alors la relance pour examen humain ;
l'import ne supprime ni n'adopte ce fichier automatiquement. Un deuxième arrêt
réel, injecté avant `os.replace`, vérifie ce refus sans altérer le résidu.

Le reçu importé est lui-même l'état durable : aucun journal d'import séparé
n'est nécessaire à cette reprise par comparaison exacte.

La source n'est jamais écrite, même pour un verrou. Une double lecture détecte
un reçu source modifié pendant son inspection ; elle ne remplace pas l'arrêt
des écrivains source. Deux imports coopératifs en destination sont sérialisés.
Les gardes existantes de `FilesystemBackend.store` et du service Information
refusent ensuite une nouvelle création sous l'identité importée.

## Preuves et limites

29 cas dans `tests/test_deleted_receipt_import.py` : aperçu sans écriture,
conservation exacte, réserve d'identité, rejeu, conflits sans publication,
PENDING/CANCELLED/APPLYING refusés, liens et corruption, snapshots non compactés,
absence de copie des Events/journaux/index, modification avant acquisition,
interruption par exception, arrêt réel code 74, deux processus concurrents sans
Manager et sorties CLI. Groupe ciblé avec migration et E-004 : **121 réussis, 4,03 s**. Désactiver la publication fait échouer un test ; omettre les gardes de
références en fait échouer deux. Ces mutations ne touchent que les processus de
preuve, jamais le code publié.

Suite complète avant le dernier cas de fichier temporaire : **1134 réussis,
5 échecs de sockets Manager avant scénario, 73,20 s** ; aucun désélectionné.
Le dernier cas a ensuite passé dans le groupe ciblé, sans changement du code.
Aucun test sur VM, disque réel en panne ou coupure électrique. Les reçus et
plans sont relus et les références rescannées par candidat : coût croissant
avec le corpus, sans promesse de gain de performance ni import massif validé.
Ces preuves historiques précèdent les extensions CANCELLED et reçus de commande
livrées le 03/10 ; les autres familles opérationnelles restent à traiter.

## Extension CANCELLED explicite — 3 octobre 2026

Ajouter `--include-cancelled` à l'aperçu et à `--apply` pour importer ensemble
les seuls états terminaux DELETED/CANCELLED. Les API `inspect_deleted_receipts`
et `import_deleted_receipts` acceptent le même argument mot-clé
`include_cancelled=True`. Sans cet argument, le comportement et la forme des
rapports restent ceux de l'import DELETED initial. En mode élargi, chaque ligne
porte aussi `status` pour distinguer réservation supprimée et décision annulée.

Pour CANCELLED, l'Information doit être présente, lisible, correctement nommée
et avoir exactement les mêmes octets en source/destination. Sa révision doit
être au moins celle de la demande annulée. Une révision plus récente est admise,
pour conserver une décision annulée suivie d'une édition. Aucun contenu,
révision, Thread, Event ou index n'est copié ni modifié par cet import.
Une modification directe du contenu sans changement de révision n'est pas
comparée à l'ancien contenu : le reçu CANCELLED n'en possède pas l'empreinte.
La source connue et l'égalité du canonique actuel restent nécessaires.

Les liens vivants ne sont pas effacés : l'annulation ne supprime rien.
Un reçu déjà différent en destination est refusé sans remplacement, même si
les deux états sont CANCELLED. Toute autre différence/absence canonique bloque
le lot entier avant publication ; mêmes contrôles répétés sous verrous.
Le rejeu de l'import est UNCHANGED seulement tant que les états contrôlés restent
identiques. Une édition explicite ultérieure peut rendre l'ancienne source
incompatible : ce refus ne remet pas en cause la décision déjà conservée.

La réservation CANCELLED importée reste reconnue par les écrivains normaux :
CREATE est refusé, UPDATE explicite reste possible ; l'approbation de l'ancienne
suppression est refusée. Une nouvelle demande de suppression est une commande
séparée, jamais fabriquée par l'import. PENDING_DELETE et APPLYING_DELETE ne
sont ni copiés ni approuvés. La publication/reprise par reçu durable reste la
même : préfixe possible, source arrêtée, aucun nettoyage de résidu inconnu.
Garder la destination arrêtée jusqu'au succès final de la relance.


## T-021/T-033 — Import explicite CANCELLED, 3 octobre 2026

Base `55e81ba`, vérifiée sur GitHub avant démarrage. `deleted_receipts` accepte
maintenant l'option explicite `--include-cancelled` (API `include_cancelled=True`)
pour transférer DELETED et CANCELLED terminaux. Par défaut, l'ancien comportement
DELETED seul et la forme des rapports sont conservés. En mode élargi, chaque
candidat indique son état. CANCELLED exige une Information canonique présente,
exacte par octets dans les deux arbres et de révision >= demande ; les liens
vivants restent intacts. Source/destination différentes ou receipt différent
refusés globalement avant publication, puis contrôle sous verrous et final.
Aucun contenu ni Event transféré, aucune suppression réactivée/approbation donnée.
CREATE reste refusé sur CANCELLED, UPDATE explicite autorisé ; la demande annulée
ne peut plus être approuvée. Ancien reçu conservé même après édition ultérieure ;
une relance contre une ancienne source divergente est refusée sans le remplacer.

18 nouveaux cas : 18 échecs initiaux (17 liés à l'option non livrée, un défaut
fixture de répertoire inconnu corrigé). **144 ciblés réussis en 4,96 s** après.
Préservation exacte, mode par défaut, lot DELETED/CANCELLED, liens, révision,
conflits sans publication, arrêt réel code 74, deux importeurs concurrents et CLI.
Substitutions en mémoire publication/garde canonique → un échec chacune.
Premier passage complet : un échec de cette fixture, 1386 réussis en 34,13 s ;
après correction, suite VM isolée hors sandbox : **1387 passed in 34.18s**, aucun
échec, saut ou désélection, Python `.venv` 3.13.5/pytest 9.1.1. Journal final
`/tmp/em-suite-XVdGSu/pytest.log` (premier : `/tmp/em-suite-U1A2zB/pytest.log`).
Preuve sur base `55e81ba` plus ce lot avant commit. Données synthétiques uniquement,
aucun import dans la mémoire active ni coupure électrique ; import des
Threads/actions/révisions, journaux complets et parents encore ouvert.
Estimations 45 % / 52,75 points inchangées.
