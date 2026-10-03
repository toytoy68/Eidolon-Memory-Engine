# Eidolon Memory Engine

Moteur de mémoire en fichiers pour Eidolon. Les Informations et Threads sous
`memory/` sont la source de vérité ; un port d’index reconstructible et sa
référence sans dépendance externe existent. Le connecteur Qdrant reste différé.
La branche `refactor/architecture-v1` est en cours de
développement. Sa suite de tests passe sur la VM ; la recette sur données
réelles et le déploiement restent à valider.

## Point de départ

- [Échanges et reprise Codex/Claude](ECHANGES.md), avec le
  [mode de collaboration asynchrone](docs/COLLABORATION.md).
- [Architecture cible, état actualisé au 02/10](docs/ARCHITECTURE-CIBLE.md)
  et [conception des écritures Information](docs/DESIGN-INFORMATION-WRITES.md)
- [Dossiers Markdown de projet](docs/PROJECT-DOSSIERS.md) : reconstruction explicite,
  rapprochement global reprenable, sources/révisions et notes humaines conservées.
- [Index des réservations](docs/RESERVATION-INDEX.md) : reconstructible et activable
  par `index-rebuild`, réutilisation des validations après contrôle des octets.
  Sur 300 entrées : 50 créations individuelles 4,86 → 0,99 s ;
  en lot ~0,24 s avec ou sans index, sur cette comparaison locale.
- [Lots Information bornés](docs/INFORMATION-BATCHES.md) : 1 à 100 CREATE/UPDATE,
  scan partagé, arrêt au conflit et reprise par rejeu des commandes stables.
- [Écritures Information et compaction v1](docs/INFORMATION-WRITES.md) : API, CLI,
  reprise et audit ; livré en local, essais VM encore requis.
- [Résultats client NONE/REVIEW](docs/ROUTING-OUTCOMES.md) :
  évaluation sans écriture, revue explicite et prochaine étape avant exécution.
- [Rattachement d’une Information existante](docs/ROUTING-EXISTING-INFORMATION.md) :
  source canonique inchangée, lien/dossier récupérables, format 4 explicite.
- [Nouveau projet par routage](docs/ROUTING-NEW-PROJECT.md) : aperçu explicite,
  création journalisée, dossier et échéance ; format 3 compatible avec 1/2.
- [Contrat fonctionnel mémoire 0.1](schemas/memory-policy-v0.1.md) :
  correspondance Information/Memory et [planificateur contextuel v0.1](docs/MEMORY-ROUTING.md)
  testés ; dossiers actualisés dans le parcours qualifié, disponibilité et
  échéance intégrées avec le format 2 explicite.
- [Bilan transversal du 02/10](docs/AUDIT-2026-10-02.md) et [TODO active](TODO-LIST.md)
- [Architecture et frontières des écrivains](docs/ARCHITECTURE.md)
- [Inventaire et précontrôle de migration](docs/MIGRATION.md)
- [Import des reçus de rejeu Information](docs/WRITE-RECEIPT-IMPORT.md) :
  reçus compactés et Events exacts, audit humain conservé ; mêmes états canoniques,
  reprise par comparaison sans copie des corps ni fusion de contenus.
- [Import des reçus de suppression](docs/DELETED-RECEIPT-IMPORT.md) : DELETED
  conserve les identités supprimées ; CANCELLED explicite exige le même canonique.
  Aperçu sans écriture et reprise par relance.
- [Transfert d’un arbre core complet](docs/CORE-COPY.md) : destination neuve,
  octets et traces conservés, préparation reprenable, aucune commande exécutée.
- [Déploiement et sauvegarde](docs/DEPLOYMENT.md)
- [Résolution humaine des opérations Thread FAILED](docs/FAILED-STATUS-RESOLUTION.md) :
  aperçu, décision tracée et reprise du plan original, refus des divergences.
- [Reprise des opérations Thread](docs/THREAD_RECOVERY.md) et
  [cycle de vie/suppressions Information](docs/LIFECYCLE.md)
- [Première interface d'assemblage de contexte](docs/RETRIEVAL.md)
- [Manifeste de source pour un index dérivé](docs/INDEXING.md)
- [Compaction par lots bornés](docs/INFORMATION-COMPACTION-BATCHES.md) :
  reçus/audits conservés, un scan par lot de 100 au plus, reprise du préfixe.
- [Mesures VM synthétiques](docs/VM-PERFORMANCE-2026-10-03.md) : écritures,
  index/entretien sur tmpfs, lots sur ext4 et 1000 antécédents ;
  trois répétitions, latence physique du disque non mesurée.
- [Catalogue reconstructible](docs/INFORMATION-CATALOGUE.md) : découverte par
  métadonnées, filtres projet/disponibilité et refus d'une projection périmée.
- [Disponibilité et échéances durables](docs/LIFECYCLE-TRIGGERS.md) : changements
  explicites HIGH/INTERMEDIATE/LOW, réexamens, annulation et reprise idempotente.
- [Passe d’entretien explicite](docs/MAINTENANCE-PASS.md) : reprise, échéances,
  dossiers et catalogue enchaînés, reprise par relance et vérification finale.
- [Coût mesuré de l’entretien](docs/MAINTENANCE-COST.md) : 300 Informations,
  à 300 Informations/25 projets, passe inactive 8,17 → 0,53 s,
  25 échéances 18,84 → 4,06 s, puis 4,16 → 1,77 s avec les lots
  sur une nouvelle comparaison locale. 50 créations sur 300 entrées :
  5,19 → 0,32 s en lot ; [protocole et limites](docs/INFORMATION-BATCHES.md).
- [Mesures synthétiques et procédure de répétition](docs/PERFORMANCE.md)

Après une sauvegarde des données et l'arrêt des écrivains, les outils
`core.migration.inventory`, `core.migration.preflight`,
`core.threads.link_audit` et `core.information.deletion_audit` peuvent examiner
une **copie** en lecture seule. Ils prennent `--root` vers le dossier contenant
`memory/`. Aucune migration automatique n'est fournie.

Pour tester le dépôt sans toucher à la mémoire réelle :

```sh
python -m pip install -r requirements.txt -r requirements-dev.txt
MEMORY_ENGINE_ROOT="$(mktemp -d)" PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider
```

## État vérifié et reprise

Dernière suite complète directe sur VM le **03/10/2026** : **1516 réussis en
37,84 s**, Python `.venv` 3.13.5/pytest 9.1.1, aucun échec, saut ou désélection.
Base `2a50395` plus le rattachement d’Information existante ;
33 nouveaux cas, 182 ciblés réussis. Données synthétiques isolées, aucun service
installé ni journal réel résolu. [Preuve](docs/VM-TESTS-2026-10-02.md).

Suite complète exécutée par toytoy sur la VM `Eidolon-Memory` le 02/10/2026,
commit `ac4d739` : **1212 réussis en 28,89 s**, Python 3.13.5/pytest 9.1.1,
aucun échec ni test désélectionné. Les cinq tests de concurrence bloqués par
les sockets de Work passent également. Données de test temporaires isolées.
[Preuve rapportée et périmètre](docs/VM-TESTS-2026-10-02.md).

Correctif inventaire cron `9780473` : cinq tests inventaire réussis et
inventaire sudo vide confirmés par toytoy. Recette exécutée directement par
Codex le 03/10 depuis `.venv`, dans `/tmp/em-yZKsKq` hors sandbox : **neuf étapes
OK**, **5 tests concurrents réussis en 0,82 s** (40 désélectionnés par le filtre).
2448 fichiers sauvegardés/restaurés vérifiés par SHA256, source inchangée,
audits sans problème et `ready=true`. **Mémoire vide : aucune validation sur
corpus réel ni coupure électrique.** Inventaire sans sudo partiel (cron
inaccessible), contrôle sudo rapporté séparément. Rapports/logs archivés ;
[détails et limites](docs/VM-TESTS-2026-10-02.md).

Résultat antérieur dans Work : 1207 réussis, cinq blocages de sockets Manager
avant scénario, 75,62 s sous Python 3.12.14. Les audits sur copie des données réelles, les services et la coupure électrique
restent à vérifier ; ce résultat n'autorise pas à lui seul la mise en production.

Revue E-004 intégrée : REVIEW ne peut plus être contourné par UPDATE, les
valeurs multilignes ne forgent plus de sections de dossier, les propositions de
retrait exigent une cible cohérente et les échéances sont validées dès le plan.
71 cas supplémentaires. Claude a terminé sa relecture sur `3b2d7a0` et confirmé
F1–F4 par sondes ; les chiffres de suite complète restent ceux de Codex.
Suivi livré : raisons des plans REVIEW corrigées et blocage de `resolve()`
sur Thread corrompu vérifié par API/CLI (122 tests ciblés, quatre nouveaux cas).
Détails et limites dans [ECHANGES.md](ECHANGES.md).

La résolution FAILED couvre les créations liées, suppressions, statuts et éditions Thread (liens, actions,
titre/objectif/contexte) : aperçu,
auteur/motif explicites, trace et autorisation atomiques avant reprise.
Les écritures Information ont un
[parcours dédié](docs/FAILED-INFORMATION-RESOLUTION.md), avec trace conservée
dans les reçus compacts ; parents de routage et conflits restent bloqués.
Les anciens binaires refusent les journaux et reçus enrichis
avec cette trace ; détails dans [le contrat](docs/FAILED-STATUS-RESOLUTION.md).

Sur une copie arrêtée, `MEMORY_ENGINE_ROOT` désigne la racine contenant `memory/` :

```sh
python -B -m core.operations.cli readiness
python -B -m core.operations.cli recover-all
```

`readiness` contrôle les journaux et reçus en lecture seule. `recover-all`
**écrit** pour reprendre les opérations connues, y compris les suppressions
Information déjà approuvées en APPLYING_DELETE, puis relit l’état sur disque.
Le code de sortie vaut zéro seulement si `readiness.ready` est vrai.
FAILED, corruption, format inconnu ou divergence bloquent la reprise automatique ;
PENDING_DELETE valide reste une attente et n’est jamais approuvé automatiquement.
Consulter [STARTUP-READINESS.md](docs/STARTUP-READINESS.md) avant utilisation.
Ce contrôle ponctuel exige les écrivains arrêtés ; aucun service de démarrage
n’est encore installé sur la VM.

## Prochaines étapes

- Définir l’import opérationnel des sources mixtes. Le convertisseur refuse
  désormais leurs reçus/journaux avant toute écriture dans la destination ;
  il ne les archive plus silencieusement en perdant leurs contraintes actives.
- Étendre l’exécution des plans : le parcours qualifié STORE/UPDATE vers un
  projet existant ou explicitement nouveau et son dossier est livré avec reprise
  et rejeu ; NONE/REVIEW sont maintenant consommables sans mutation ; lieu/thème
  et résolution durable des revues restent ouverts. Voir
  [ROUTING-EXECUTION.md](docs/ROUTING-EXECUTION.md). Les commandes Thread
  restent décrites dans [THREAD-UPDATES.md](docs/THREAD-UPDATES.md).
- Définir l’ordonnancement de l’entretien : une passe explicite enchaîne maintenant
  reprise, échéances, dossiers et catalogue. Le rappel
  applique maintenant contexte/validité/statuts et expose sources et incertitudes ;
  voir [CONTEXTUAL-RECALL.md](docs/CONTEXTUAL-RECALL.md).
- Poursuivre T-049 avant ingestion intensive : les nouvelles écritures font
  un scan par commande individuelle ou par lot de 100 commandes au plus.
  Le dispatcher des échéances partage ce scan ; l’ingestion croissante à
  taille de lot fixe conserve un coût quadratique réduit. L’index facultatif
  évite maintenant les revalidations des journaux inchangés, tout en relisant
  leurs octets ; supprimer ces lectures exige un protocole supplémentaire.
  L’entretien évite maintenant les étapes inactives et partage les audits
  entre lecteurs sous verrous, avec relecture finale indépendante.
  [Mesures reproductibles](docs/JOURNAL-SCAN-COST.md) : 300 créations en 20,42 s
  contre 59,39 s sur le corpus synthétique local. Catalogue livré à la demande ;
  déclencheurs durables et réparation des dérivés assemblés dans une passe
  explicite. Ordonnancement système et traitement incrémental restent ouverts.

Le premier parcours Information → projet existant → dossier actualisé → rappel
contextualisé est livré pour les entrées explicitement qualifiées. Les autres
mutations peuvent laisser du retard, signalé au rappel qui utilise le canonique.
`python -B -m core.dossiers.cli --root RACINE reconcile` inspecte toutes les vues
sans écriture ; ajouter `--apply` répare celles qui manquent ou sont périmées,
y compris après suppression, en conservant les notes humaines. Une interruption
se reprend par relance. `preview --with-lifecycle` enregistre disponibilité et
échéance dans le parcours ; l’exécution des échéances reste explicite.
Les anciens services legacy constituent une pile distincte.
La [TODO active](TODO-LIST.md) précise les preuves, priorités et limites actuelles ;
les audits datés conservent leurs constats historiques.
