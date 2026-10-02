# Résolution humaine des écritures Information FAILED

Sur une copie arrêtée, ce parcours permet de reprendre uniquement le plan
original INFORMATION_CREATE ou INFORMATION_UPDATE de `information-write-v1`.
Il ne remplace pas le contenu, n'abandonne pas l'opération et ne décide aucun
statut de vérité. La qualification, les extensions, les IDs, le hash du plan,
la révision et l'Event original restent inchangés.

## Revue et décision

```sh
python -B -m core.information.failed_resolution --root /copie \
  preview operation-id > /hors-copie/revue.json

python -B -m core.information.failed_resolution --root /copie \
  retry --review /hors-copie/revue.json \
  --resolution-id decision-unique --actor toytoy \
  --reason "Cause examinée, effets cohérents, reprise du plan original autorisée" \
  --timestamp 2026-10-03T01:00:00+02:00
```

API : `review_failed_information(root, operation_id)` et
`retry_failed_information(root, review, *, resolution_id, actor, reason, timestamp)`.
Le CLI renvoie 1 et BLOCKED au refus, 0 pour une revue ou un résultat COMMITTED.
L'aperçu n'écrit aucun fichier ni dossier ; la redirection shell est explicite.
Il montre la cible, le type de commande, les révisions, les empreintes du plan
et du journal FAILED, les effets encore nécessaires et l'historique des décisions.
Les snapshots complets sont dans le journal source ; garder la revue hors des
journaux canoniques. La revue seule n'autorise rien.

## Gardes et reprise

L'Information courante doit être absente pour CREATE ou exactement le snapshot
avant/après pour UPDATE. Dans les deux cas, le résultat exact déjà écrit est
accepté. L'Event doit être absent ou exactement l'effet prévu ; un Event présent
sans l'Information après est refusé. Plan, empreinte de commande et snapshots
sont revalidés par les lecteurs ordinaires. Les réservations Information/Event,
les reçus de suppression et les relations vers des identités supprimées gardent
leurs restrictions. Un reçu CANCELLED permet UPDATE, conformément au coordinateur,
mais ne libère pas une identité pour CREATE.

Les FAILED indépendants de cette famille peuvent être résolus un par un.
Une autre famille FAILED, une opération indépendante PREPARED/APPLYING, une
compaction interrompue, un parent de routage non terminé ou une source inconnue
ou corrompue bloque l'autorisation. Ce parcours ne contourne aucun parent.

Sous verrous Persistent → Operation → Event, la revue est recalculée et comparée
avec celle approuvée. Changer les seuls octets FAILED la périme aussi. Une seule
publication atomique du journal ajoute `manual_resolutions` (action
RETRY_INFORMATION_WRITE_V1, décision, auteur, motif, date avec fuseau et empreintes)
et passe FAILED à APPLYING. Le dépôt générique interdit toujours les sorties de
FAILED et la modification de cet historique. Le coordinateur reprend alors le
plan original ; le hash du plan et l'empreinte de commande excluent cette trace.

Un arrêt avant publication laisse FAILED sans décision ; après publication,
APPLYING et trace sont durables et `recover-all` peut terminer selon ses gardes.
Une même décision rejouée ne publie pas de seconde autorisation. Si la reprise
échoue et est déclarée FAILED à nouveau, une nouvelle revue et un nouvel ID de
décision sont requis ; l'historique précédent reste conservé.

## Compaction et compatibilité

La compaction copie l'historique d'autorisation dans le reçu terminal, avant
retrait durable du seul snapshot. La validation de l'audit est commune au
journal et au reçu. En coexistence journal/reçu, l'historique doit être identique ;
une divergence interdit le retrait. Le reçu ne contient aucun snapshot de contenu.
Les auteurs et motifs sont les métadonnées explicites fournies par l'opérateur.

Après compaction, seule une décision déjà enregistrée avec exactement la même
revue et les mêmes paramètres peut rendre le résultat terminal. Aucun nouvel
ID de décision n'est accordé à une opération compactée. Le rejeu reste sans
écriture Information/Event, même si l'Information a été supprimée depuis.

Le champ `manual_resolutions` est optionnel strict : les journaux et reçus anciens
sans trace conservent leur forme et restent lisibles. Les anciennes versions
qui ne connaissent pas ce champ/action refusent les objets enrichis. Ne pas
supprimer la trace pour permettre un retour à un ancien lecteur. Les IDs,
auteurs et empreintes sont déclaratifs, sans authentification ni signature.
Une édition malveillante peut supprimer entièrement une trace d'un reçu isolé ;
la validation de format ne peut pas prouver son histoire antérieure. Une décision
supprimée ne peut cependant plus être rejouée par cette API.

Aucun abandon automatique, aucune réparation forcée de divergence et aucun
nettoyage des fichiers inconnus après panne. Les parents de routage, les conflits
réels et la migration opérationnelle générale restent ouverts. Les sources et
écrivains directs/legacy doivent rester arrêtés ; aucun service n'est installé.


## T-048 — Reprise humaine des écritures Information FAILED, 3 octobre 2026

Base `dcbdf1c`, vérifiée sur GitHub avant démarrage. Nouveau parcours
`core.information.failed_resolution` : revue sans écriture puis décision explicite
pour INFORMATION_CREATE/UPDATE. Le lecteur normal revalide snapshots/hash/empreinte ;
la revue contrôle les effets présents, réservations Information/Event, reçus de
suppression et relations vers identités supprimées. Event sans état après,
divergence, revue périmée, autre famille non résolue et parent non terminé bloqués.
Les FAILED Information indépendants se résolvent un par un ; aucun abandon.

Publication atomique RETRY_INFORMATION_WRITE_V1 et APPLYING, puis coordinateur
normal. Le hash du plan et les IDs restent inchangés. La trace stricte est copiée
dans le reçu compact avant retrait du snapshot ; journal/reçu divergents bloquent
la compaction. Les anciens reçus sans trace restent identiques et lisibles ;
les anciens binaires refusent les journaux/reçus enrichis. Le rejeu de la décision
sur reçu compact conserve le résultat sans recréer l'Information supprimée ;
aucune nouvelle décision n'est accordée après compaction. Contrat :
ce document.

58 nouveaux tests : 49 premiers rouges avant implémentation sur un squelette
refusant explicitement le parcours, puis neuf cas supplémentaires de dépendances,
audit et compaction. **295 ciblés réussis en 7,29 s**. Six arrêts réels code 74
(CREATE/UPDATE × trois frontières), deux scénarios à deux processus concurrents,
compaction interrompue, trace divergente, suppression puis rejeu, seconde décision,
CANCELLED et relations réservées couverts. Substitutions en mémoire : revue figée,
autorisation sans trace, compaction retirant la trace → un échec chacune ;
aucune substitution conservée dans le code.

Suite complète isolée hors sandbox sur VM : **1335 passed in 32.13s**,
aucun échec, saut ou désélection, Python `.venv` 3.13.5/pytest 9.1.1.
Journal `/tmp/em-suite-rmKyis/pytest.log`. Preuve sur base `dcbdf1c` plus ce lot
avant commit. Sources actives/sauvegardes intactes ; données synthétiques uniquement,
aucune reprise humaine de journaux réels, service ou coupure électrique validés.
Parents de routage, divergences/abandon et import opérationnel général ouverts.
Estimations 45 % / 52,75 points inchangées.
