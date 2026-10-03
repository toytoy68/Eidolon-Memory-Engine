# Rappel contextualisé v0.1 — T-047, première tranche

`ContextualRecall(backend).recall(...)`, également disponible via
`RoutingExecutor.recall`, relie le classement lexical aux règles de contexte et
de temps. Il lit les fichiers canoniques ; aucun dossier Markdown périmé n’est
utilisé comme source de texte. La qualification et les conditions sont explicites,
sans inférence sémantique depuis le texte ni découverte automatique des conflits.

## Profil versionné

Paramètres : requête, query_scope (objet), at (instant explicite avec fuseau ou
absent), mode (`operational` par défaut ou `historical`), project_id facultatif,
limites d’extraits et compteur de tokens facultatif. Les conditions utilisent
l’applicability du planner : MATCH, UNKNOWN, OUT_OF_SCOPE, EXPIRED ou UNRESOLVED.
Un instant absent ne fait pas disparaître une borne de validité : elle donne
UNKNOWN. Un contexte absent n’est pas universel.

| Situation | Mode operational | Mode historical |
| --- | --- | --- |
| Expirée / contexte incompatible | Exclue avec compteur de raison | Incluse avec étiquette et needs_review |
| REFUTED / SUPERSEDED | Exclue avec compteur de raison | Incluse sans changement de statut |
| UNKNOWN / UNVERIFIED | Incluse, needs_review=true | Même avertissement |
| CONFLICTED dans le contexte correspondant | UNRESOLVED, needs_review=true | Même avertissement |
| Suppression en attente PENDING_DELETE | Exclue | Incluse avec pending_deletion et needs_review |
| MATCH et CONFIRMED, sans suppression en attente | Incluse | Incluse |
| Moteur avec état de reprise bloquant | Refus global | Refus global |

Ce tableau est un **profil de rappel explicite**, pas une modification des règles
de vérité ou de rétention. Les filtres du ContextAssembler historique restent
inchangés par défaut. Aucun statut n’est promu automatiquement. needs_review
signale une réserve au consommateur ; ce booléen ne constitue pas une décision
autonome de validation ou une permission d’agir.

Le mode historique retrouve les objets canoniques encore conservés, pas toutes
les anciennes versions remplacées ni les contenus supprimés. L’historique
intégral des révisions reste T-050. Le statut opérationnel (PLANNED, COMPLETED,
etc.) est transmis mais n’est pas transformé implicitement en statut épistémique.

## Résultat et budgets

Chaque extrait contient identité/révision, contenu, score et raisons de classement,
troncature, statut épistémique, état opérationnel, confiance, applicability,
needs_review, selection_reasons, provenance, contexte, temporalité, vérification
et relations. Le résultat indique la version de profil et des compteurs
excluded_counts sur les candidats effectivement examinés, pas sur tout le corpus.

Les exclusions s’appliquent **avant** les budgets, et la pagination continue même
si les 100 premiers candidats sont tous exclus. Les limites de caractères et
les tokens comptés concernent les extraits seuls : métadonnées, sérialisation,
instructions et prompt complet ne sont pas compris. Le client conserve donc
la responsabilité de son budget final. Les corps JSON restent optionnels et
peuvent être tronqués comme dans ContextAssembler.

Avec project_id, seuls les liens CONCERNS effectivement persistés du Thread
sont admis. dossier_status indique CURRENT, STALE ou MISSING. Une vue STALE
n’est pas reconstruite pendant le rappel ; la dernière Information canonique
est utilisée. Les notes humaines du dossier ne sont pas ingérées implicitement.

## Cohérence et coût

Le rappel prend les verrous coopératifs Persistent puis Thread s’il existe,
contrôle readiness, recherche, recontrôle chaque candidat contre son objet
canonique et assemble le résultat. freshness=CANONICAL_AT_READ décrit cette
lecture, pas une garantie permanente après retour. Un ancien résultat de
recherche différent du canonique est exclu comme STALE_CANDIDATE. Les écrivains
externes qui ignorent les verrous restent hors garantie.

Aucun objet métier, dossier, reçu ou journal n’est écrit. Les fichiers techniques
.write.lock peuvent être initialisés. Le contrôle global peut refuser une requête
à cause d’une opération sans rapport avec son sujet : choix conservateur de
cette première version. Le scan des journaux et le verrou de lecture peuvent
coûter cher en volume ; T-049 et les mesures VM restent requis avant ingestion
intensive. Aucun résultat de latence réelle n’est revendiqué.

## CLI et démonstration

Après le parcours décrit dans ROUTING-EXECUTION.md, scope.json contient par exemple
`{"goal":"efficiency"}` :

```sh
python -B -m core.routing.execution_cli --root RACINE recall "measure" \
  --scope scope.json --at 2026-10-01T18:30:00Z --project-id project
```

Ajouter `--mode historical` pour la recherche historique explicite. Le CLI
retourne un code non nul si la reprise du moteur n’est pas résolue.

## Preuves et restant

15 nouveaux cas couvrent expirations/contextes, REFUTED/SUPERSEDED, conflit,
contexte inconnu, provenance/preuves, budget après filtrage, pagination après
101 exclusions, demande de suppression, ancien résultat de recherche, CLI et
parcours complet avec correction/notes/dossier périmé. Trois retraits temporaires
(filtre, readiness, needs_review) produisent respectivement 1, 1 et 3 échecs
comportementaux ; code restauré ensuite.

Restant : corpus représentatif/anonymisé et qualité/latence mesurées, politiques
plus fines, recherche sémantique et catalogue, déclencheurs, adaptateurs clients
réels. Aucun accès VM, client Hermes/Eidolon Core ou Qdrant livré dans ce lot.

Suite complète finale : 842 réussis, cinq échecs sockets Manager avant scénario,
55,32 s ; groupe ciblé rappel/assembleur/parcours : 65 réussis. Aucune exclusion.

## Disponibilité et réexamen — ajout T-046

Le filtre optionnel `availability` accepte HIGH/INTERMEDIATE/LOW avant budget.
Le résultat expose le niveau déclaré. Un `recheck_required` impose needs_review
et une raison explicite, même pour CONFIRMED/MATCH. Ces champs ne remplacent
ni contexte ni temporalité. Voir [LIFECYCLE-TRIGGERS.md](LIFECYCLE-TRIGGERS.md).

## Mesures VM synthétiques du 03/10

Le commit `ecd83d1` est mesuré sur six corpus neufs 300/1000/3000 × live/compact,
huit scénarios avec réponses connues et trois requêtes par corpus chaud :
144 requêtes conformes, objets/révisions/review flags/hash/readiness vérifiés.
[Protocole, chiffres et limites](VM-RECALL-2026-10-03.md). `/tmp` tmpfs ; aucune
pertinence/latence sur corpus réel, production ou client externe n’est validée.
Le coût des scans globaux reste visible malgré le petit nombre de résultats.
