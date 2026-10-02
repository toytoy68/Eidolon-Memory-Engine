# Passe d’entretien explicite — T-044 / T-045 / T-046

Lot du 02/10/2026. Une commande assemble la reprise des journaux, les échéances
arrivées, le rapprochement des dossiers et la reconstruction du catalogue.
Elle ne lance aucun service et ne choisit aucun horaire, fenêtre ou critère
d’occupation. Les fichiers canoniques restent la source de vérité.

## API et commandes

`MaintenancePass(root).inspect(at=…)` examine sans écrire : readiness, échéances
arrivées/futures, dossiers et catalogue. `work_pending` distingue un travail
visible d’une copie déjà à jour. Le statut READY signifie que l’inspection n’a
rencontré aucun blocage ; il ne signifie pas que toutes les échéances sont
traitées. Une reprise nécessaire rend l’inspection BLOCKED. L’inspection est
ponctuelle, à utiliser sur copie arrêtée pour une vue stable.

`MaintenancePass(root).run(at=…, query_scope={}, limit=100)` effectue une passe
explicite. La racine Persistent doit exister. Le temps fourni nécessite un
fuseau ; il n’est jamais remplacé par l’horloge locale. Le contexte décrit les
conditions **actuelles** d’exécution, pas celles observées autrefois. Son absence
laisse le contexte inconnu : aucune localisation ou confirmation n’est inventée.
Une REACTIVATE sans contexte applicable devient un réexamen, suivant le contrat
[LIFECYCLE-TRIGGERS.md](LIFECYCLE-TRIGGERS.md).

```sh
python -B -m core.maintenance.cli --root RACINE inspect --at 2026-10-03T08:00:00Z
python -B -m core.maintenance.cli --root RACINE run \
  --at 2026-10-03T08:00:00Z --scope contexte-actuel.json --limit 20
```

Le JSON de contexte est le même objet `query_scope` que pour le dispatcher.
Le CLI renvoie 1 pour BLOCKED, 0 sinon. PARTIAL signifie qu’une passe bornée a
réussi mais qu’il reste des échéances arrivées ; relancer pour les suivantes.
COMPLETED signifie qu’il ne reste aucune échéance arrivée **au temps fourni**
et que les dérivés gérés sont à jour. Des échéances futures peuvent subsister.

## Ordre, reprise et résultat

1. Lire readiness. Corruption, FAILED et formats inconnus bloquent sans reprise.
2. Prendre les verrous Persistent puis Thread et reprendre les journaux connus.
   La readiness relue doit être prête avant de poursuivre.
3. Traiter au plus `limit` échéances avec le dispatcher existant. Les effets
   utilisent ses journaux et ses révisions attendues ; STALE/SKIPPED sont des
   issues normales explicites, pas des confirmations implicites.
4. Rapprocher les dossiers gérés, en préservant les notes humaines. Une frontière
   endommagée exige une correction explicite, jamais une réparation devinée.
5. Reconstruire le catalogue seulement s’il diffère du canonique courant.
6. Relire readiness, échéances, dossiers et catalogue sur disque. Un faux succès
   annoncé par un composant ne suffit pas à rendre la passe réussie.

Le rapport contient `stage`, `recovery`, `triggers`, `dossiers`, `catalogue` et
`verification`. `readiness` au premier niveau décrit l’état initial ; celui de
`verification` décrit l’état final. Les résultats de déclencheurs sont résumés
par identité, statut et raison, sans corps d’Information.

Aucun nouveau journal parent n’est nécessaire : les enfants acquittent les effets
canoniques ; les manifests révèlent les projections restant à refaire. Relancer
la passe après exception ou arrêt de processus converge. La reprise d’un parent
de routage précède le déclenchement de son échéance ; une échéance déjà appliquée
mais non acquittée est terminée par la reprise globale, sans nouvelle révision.

Ce n’est **pas** une transaction atomique de tout le lot. Si une publication de
dossier est bloquée après un effet canonique, cet effet reste acquis, le rapport
indique BLOCKED à l’étape dossiers et la prochaine passe termine les dérivés.
Les journaux individuels restent la référence si le processus meurt avant de
rendre son rapport. Les verrous sont coopératifs, les écrivains legacy doivent
rester arrêtés. Deux passes concurrentes coopératives produisent un seul effet.

## Limites de charge et de politique

`limit` borne uniquement le dispatch des échéances. La reprise globale, les
scans de journaux, le rapprochement et la reconstruction restent complets ;
aucune borne de latence ou de mémoire n’est promise. Les verrous Persistent et
Thread sont gardés pendant la passe. Mesurer ce coût sous T-049 avant exploitation
intensive ; un entretien incrémental par lots reste à concevoir.

La passe ne confirme pas une vérité, n’approuve pas PENDING_DELETE et ne supprime
pas sur le seul critère d’âge. Une suppression déjà approuvée peut être reprise
par recover-all. Les dérivés gérés reflètent ensuite l’absence canonique, mais
les notes humaines restent conservées ; aucune clôture globale de purge ou
suppression des copies externes n’est revendiquée.

Restent ouverts : récurrence, occupation/inactivité, fenêtre horaire, décision
sur le profil quotidien/hebdomadaire, ordonnanceur système et validation VM.

## Preuves locales

20 nouveaux cas dans `tests/test_maintenance_pass.py` : inspection sans écriture,
parcours avec effets puis dérivés courants, replay inchangé, backlog borné,
contexte inconnu, refus de corruption, frontière humaine endommagée, faux succès
rejeté après relecture, reprise du routage et d’un effet interrompu, attente de
suppression et retrait d’une ancienne projection après suppression approuvée.
Quatre interruptions par exception, deux arrêts réels de processus code 74 et
deux travailleurs concurrents sans Manager. Les preuves négatives et le résultat
global sont consignés dans ECHANGES.md. Aucune VM ni coupure physique testée.
