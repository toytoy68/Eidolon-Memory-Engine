# Échanges de travail — Memory Engine

Ce fichier permet une revue asynchrone entre toytoy, Codex/GPT et Claude.
Il ne déclenche aucune session ni aucun accès automatique au dépôt ou à la VM.
Mode d'emploi : [COLLABORATION.md](docs/COLLABORATION.md).

## Reprise rapide

État constaté le 2026-09-30, sur `refactor/architecture-v1` au commit
`0f45070`. Toujours vérifier la branche et le commit actuels avant de travailler.

- But : mémoire autonome, contextuelle et traçable ; fichiers canoniques,
  dossiers Markdown vivants, trois niveaux de disponibilité. Voir le
  [bilan fonctionnel](docs/MEMORY-ARCHITECTURE-2026-09-30.md).
- T-040 : contrat fonctionnel v0.1 et mapping textuel Information/Memory livrés.
  Les 14 scénarios sont des attendus ; aucun router core ne les exécute encore.
- T-039 : suppression Thread implicite raccordée aux trois journaux canoniques,
  corrigée localement. T-031 reste partiel : des écritures directes subsistent.
- Prochain lot : T-041/T-042, écritures Information coordonnées et reçus
  compacts. Leur [conception](docs/DESIGN-INFORMATION-WRITES.md) et son
  [annexe](docs/DESIGN-INFORMATION-WRITES-DETAIL.md) sont documentées, non implémentées.
- D7/D8/D9 validées par toytoy : annuler PENDING_DELETE avant nouvelle
  modification métier ; conserver l'empreinte dans le reçu v1 sans garantie
  de confidentialité ; conserver l'identité après CANCELLED.
- Dernière suite réellement exécutée : **674 réussis, 5 exclus**, pytest 9.1.1,
  sur le code publié dans `b967bf4`. Ce résultat vient de la séance Codex ;
  ce n'est pas une exécution indépendante de Claude ni une validation VM.
- Accès Claude au dépôt et accès VM annoncés par toytoy pour le weekend,
  **pas encore constatés**. Aucun résultat VM disponible.
- Estimation globale gelée à 45 %, grille à 50,75 points. Pas de hausse pour
  une discussion ou un accord entre assistants. Pas de travail sur Eidolon
  Core, Hermes, Qdrant ni de nouvelle série de micro-durcissements.

## Sujets à relire lors d'une prochaine session disponible

| Sujet | Priorité | État | Référence | Attendu |
| --- | --- | --- | --- | --- |
| E-001 | Haute | PROPOSÉ — revue non bloquante pour le travail autorisé | T-041/T-042, `0f45070` | Revue du format de commande/reçu et des interruptions |
| E-002 | Moyenne | PROPOSÉ — aucune revue Claude reçue | T-040/T-039, `b01ed9f` et `b967bf4` | Revue indépendante des deux lots déjà livrés |
| E-003 | Haute avant mise en service | EN ATTENTE D'ACCÈS VM | T-010 à T-015/T-021/T-032 | Rapport réel, commit testé et limites d'environnement |

### E-001 — Écritures et reçus compacts

**Entrée du 2026-09-30 — Codex/GPT.** Base lue : `0f45070`.
Question de revue proposée à Claude, lorsqu'une session sera disponible :
la représentation précise des commandes et reçus permet-elle de conserver
l'idempotence après compaction, évolution puis suppression de la cible ?

Points à contrôler sur la future implémentation : snapshot du Memory complet,
résultat minimal stable, ordre des verrous, publication durable du reçu,
retrait durable du plan, coexistence divergente bloquée, absence de résurrection.
Les décisions D7–D9 sont déjà validées : ne pas les rouvrir sans nouvel élément.
Si l'implémentation a avancé, relever son commit et examiner le diff depuis
`0f45070` ; ne pas commenter une ancienne version comme si elle était actuelle.

**Prochaine action Codex :** poursuivre le lot P1 autorisé et déposer les
références de commits et preuves. **Réponse Claude :** aucune à ce jour.

### E-002 — Vérification indépendante des derniers lots

**Entrée du 2026-09-30 — Codex/GPT.** Proposer une revue ciblée de
`core/information/mapping.py`, `tests/test_information_mapping.py` et de
`test_implicit_storage_delete_waits_for_other_family_recovery` dans
`tests/test_thread_deletion_recovery.py`.

Preuves déjà obtenues : aller-retour identique sur 500 candidats synthétiques,
préservation des extensions après édition persistée, blocage de suppression
après interruption création/statut puis succès après reprise. Retirer les
changements rend les tests concernés rouges. Voir le
[rapport de séance](docs/SESSION-2026-09-30-CONTRACT.md).

**Attendu :** observation appuyée sur code/test, ou limites de lecture si pytest
reste indisponible. **Réponse Claude :** aucune à ce jour.

### E-003 — Recette sur copie VM

**Entrée du 2026-09-30 — Codex/GPT.** L'accès annoncé ne constitue pas une
validation. Sur une copie arrêtée, exécuter la recette dans un dossier de
travail explicite distinct, selon le rapport de séance et les procédures de
déploiement. Garder l'inventaire réel des écrivains, la restauration par hash,
les cinq résultats de concurrence et les audits, avec leurs KO éventuels.

**Attendu :** commit exact, commande, versions, rapport et anomalies constatées,
sans données privées ni secrets dans Git. Un arrêt de VM et une coupure
physique du stockage sont des expériences différentes. **Résultat :** non testé.

## Modèle pour un nouveau sujet

Copier le modèle ci-dessous en attribuant un ID E-xxx libre après synchronisation.

```text
E-xxx — Titre
État : PROPOSÉ / EN COURS / À RELIRE / DÉCIDÉ / CLOS / BLOQUÉ
Auteur et date :
Branche et commit examinés :
Tâche TODO associée :
Question ou problème :
Proposition et compromis :
Preuves exécutées (commande, résultat, environnement) :
Non testé / simple lecture / résultat rapporté par un autre :
Réponse datée et signée (à ajouter sans remplacer la proposition) :
Décision et autorité de décision :
Commit d'implémentation et documentation consolidée :
Prochaine action et responsable, ou disponibilité à confirmer :
```
