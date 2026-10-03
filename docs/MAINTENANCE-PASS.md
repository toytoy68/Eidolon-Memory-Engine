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
réussi mais qu’il reste des échéances arrivées ou des dossiers à reconstruire
avec la limite optionnelle ci-dessous ; relancer pour les suivants.
COMPLETED signifie qu’il ne reste aucune échéance arrivée **au temps fourni**
et que les dérivés gérés sont à jour. Des échéances futures peuvent subsister.

## Ordre, reprise et résultat

1. Lire readiness. Corruption, FAILED et formats inconnus bloquent sans reprise.
   Sans reprise ni échéance arrivée, une inspection complète sous verrous permet
   une sortie immédiate si tous les dérivés sont déjà courants. Aucun écrivain
   métier n’est alors appelé ; `recovery` reste nul.
2. Prendre les verrous Persistent puis Thread et reprendre les journaux connus.
   La readiness relue doit être prête avant de poursuivre.
3. Traiter au plus `limit` échéances avec le dispatcher existant. Les effets
   utilisent ses journaux et ses révisions attendues ; STALE/SKIPPED sont des
   issues normales explicites, pas des confirmations implicites.
4. Rapprocher les dossiers gérés, en préservant les notes humaines. Une frontière
   endommagée exige une correction explicite, jamais une réparation devinée.
5. Reconstruire le catalogue seulement s’il diffère du canonique courant.
6. Relire readiness, échéances, dossiers et catalogue dans une nouvelle phase
   de lecture sur disque. Un faux succès
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
rendre son rapport. Dans les phases de réparation et de lecture finale, un audit complet réussi
est partagé entre les lecteurs ; aucun scan simplifié ni cache inter-passes.
Une publication canonique invalide la preuve. La lecture finale effectue son
propre audit frais. Voir [MAINTENANCE-COST.md](MAINTENANCE-COST.md).

Les verrous sont coopératifs, les écrivains legacy doivent
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

## Échéances regroupées — 02/10

Le dispatcher partage désormais le scan strict des réservations Information
par tranches de 100 échéances au plus. Les intentions et journaux enfants
restent individuels et reprenables. `limit` conserve son sens ; les verrous
Persistent/Thread extérieurs restent détenus pendant la passe entière.
Aucun audit global, contrôle de révision ou contrôle final n’est supprimé.
Voir [INFORMATION-BATCHES.md](INFORMATION-BATCHES.md) et les mesures comparées
dans [MAINTENANCE-COST.md](MAINTENANCE-COST.md).

## Publications de dossiers bornées — 03/10

`DossierReconciler.apply(limit=1…100)` et
`core.dossiers.cli … reconcile --apply --limit 20` reconstruisent au plus ce
nombre de dossiers, dans l’ordre des identités. Sans limite, le comportement
complet précédent reste inchangé. L’inspection reste complète et sans écriture.
La corruption d’un dossier hors du premier lot bloque toute publication.

`MaintenancePass.run(…, dossier_limit=20)` et
`core.maintenance.cli … run --at DATE --dossier-limit 20` raccordent cette
borne à la passe. `limit` / `--limit` continuent de borner les seules échéances.
Le résultat dossiers expose `remaining_count` après publication ; PARTIAL
signale les vues encore MISSING/STALE/ORPHANED. Le CLI renvoie 0 pour ce progrès
partiel, 1 pour BLOCKED. La vérification finale fraîche conserve le backlog
visible et interdit COMPLETED tant que les dossiers ou échéances restent dus.

Relancer la même commande découvre le travail restant depuis les sources et
les régions générées, sans nouvelle file durable. Une interruption après une
publication ne la rejoue pas si elle est courante. Notes humaines préservées,
vues orphelines nettoyées sans recréer le Thread ; deux travailleurs coopératifs
sérialisent leurs publications sous les mêmes verrous.

Cette borne limite les publications, pas les scans, la reprise globale, le
catalogue, la mémoire ou la durée des verrous. Aucun ordonnanceur installé,
aucune fenêtre ou politique d’occupation choisie. Les dérivés peuvent rester
périmés entre passes ; ne pas interpréter PARTIAL comme une mise à jour complète.
Preuves synthétiques : tests/test_dossier_batches.py ; résultats dans ECHANGES.md.

## Report explicite si un écrivain canonique est occupé — T-046

`MaintenancePass.run(…, if_idle=True)` et `run … --if-idle` tentent les verrous
Persistent puis Thread sans attente. Sans l’option, les appels continuent
d’attendre suivant le protocole existant. Si un autre thread/processus détient
l’un de ces verrous, la passe rend `status=DEFERRED`,
`reason=CANONICAL_WRITER_BUSY`, `stage=locks`, sans reprendre de journal,
déclencher d’échéance ou publier de dérivé. Le CLI renvoie 0 : report volontaire,
pas réussite de l’entretien. Relancer plus tard avec temps/contexte actualisés.

Avec cette option, la readiness initiale est lue seulement après acquisition
des deux verrous, pour éviter de diagnostiquer des journaux en cours d’écriture.
Un état FAILED/corrompu découvert une fois les verrous libres reste BLOCKED.
Une erreur de chemin/permission n’est pas assimilée à un écrivain occupé.
Un verrou déjà détenu par le même thread reste réentrant. Si le second verrou
est occupé, le premier est libéré avant de rendre DEFERRED.

L’option ne lit ni charge CPU, ni sessions SSH, ni activité utilisateur. Elle
ne choisit aucun horaire et ne programme aucune relance. Elle couvre seulement
les écrivains coopératifs de ces racines : un écrivain legacy ignorant les
verrous n’est pas détecté. Des verrous internes de journaux, dossiers ou
catalogue peuvent encore faire attendre une passe ayant obtenu les verrous
canoniques ; aucune limite globale de durée n’est promise. Un fichier de verrou
technique peut être créé, mais aucun contenu métier n’est modifié par le report.

Compatible avec `dossier_limit` et le backlog PARTIAL. Validation Linux par
processus concurrents ; branche Windows du verrou non validée sur une VM Windows.
Tests : tests/test_maintenance_if_idle.py ; preuves et limites dans ECHANGES.md.
