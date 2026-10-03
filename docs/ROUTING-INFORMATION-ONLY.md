# Routage explicite d’une Information sans dossier

Le format 5 complète T-043 : `preview_information(memory, context)` fige un
plan STORE/UPDATE qualifié sans association projet, lieu ou thème. L’aperçu
n’écrit rien et ne crée aucun répertoire. `assess` propose PREVIEW_INFORMATION ;
ce résultat n’est pas une autorisation d’écriture ni une preuve de readiness.

```sh
python -m core.routing.execution_cli --root /chemin/moteur preview-information \
  --memory /chemin/information.json --context /chemin/contexte.json
python -m core.routing.execution_cli --root /chemin/moteur execute \
  --plan /chemin/plan.json --intent-id choix-explicite --actor humain \
  --timestamp 2026-10-03T01:00:00Z
```

La qualification et les règles sont explicites. STORE exige une identité
absente et une révision 1 ; UPDATE exige une cible/révision identique et un
snapshot canonique inchangé. Le moteur refuse les demandes de revue, NONE,
associations ou dossiers demandés, retraits observés et conflits non résolus.
Le corps, la provenance, la temporalité et le statut épistémique restent ceux
fournis ; disponibilité et besoin de revérification proviennent du profil
expliqué. Une échéance REACTIVATE est enregistrée après l’écriture, pour la
révision résultante. Son effet reste une commande ultérieure explicite : une
Information UNVERIFIED conduit à RECHECK, sans promotion de vérité.

L’intention durable possède les identités Information concernées jusqu’à
l’acquittement du déclencheur. Elle ne réserve aucun Thread. Les écritures
partagent l’ordre des verrous existant, sans fabriquer de répertoire Thread.
Les identités enfants et Events sont stables. Les snapshots sont relus à
l’exécution puis lors de la reprise ; l’historique enfant justifie une source
éventuellement déjà publiée. La reprise globale accepte ce format et fonctionne
sur un arbre dépourvu de Threads. Les inconnus/échecs non résolus bloquent les
nouvelles écritures avant création de l’intention parent.

Le reçu COMMITTED conserve empreinte et résultat compact, sans corps ni snapshot :
`information={id,revision}`, `project=null`, `projection_digest=null`,
`deferred=[]`, `lifecycle={availability,trigger_id}`. Une relance identique rend
ce reçu, même après compaction puis suppression explicite de la source ; elle
ne la recrée pas. Réutiliser l’intention avec un autre plan est refusé. Inventaire,
readiness et copie complète core comprennent routing_execution_v5.

Preuves du 03/10 : 30 nouveaux tests, 25 rouges sur le squelette ; interruptions
aux trois frontières, deux sorties réelles de processus, deux exécutants
concurrents, UPDATE/stale/pending-delete, reçu corrompu, rejeu après suppression,
copie/rejeu et CLI sans initialisation à l’aperçu. Suppression en mémoire du
contrôle de snapshot ou de l’application de disponibilité : un échec observé
pour chacun. Les branches lieu/thème et la file de revue durable restent ouvertes.
Corpus synthétiques isolés ; aucun client externe, service actif, corpus réel
ou coupure électrique validé. [Suite VM](VM-TESTS-2026-10-02.md).
