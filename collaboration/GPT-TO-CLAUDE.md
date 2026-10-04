# GPT → Claude — missions du 4 octobre 2026

Demande directe de toytoy : étude du projet, répartition immédiate et poursuite.
Base publiée f3aaf3b. Ne pas présenter ces missions comme déjà exécutées.

## C1 — Relecture indépendante import et rappel (priorité 1)

Relire 10d68a2, 88050bc, b3ae58e, 7805b21 : sélection des branches/messages,
rejets des rôles système/outils/analyse, sauvegarde des originaux, collisions et
reprise import, passage exact et offsets, budgets, classement avant pagination.
Corpus synthétiques dans clone isolé ; pour tout défaut, reproduction minimale,
rouge sur la base et correctif proposé, sans modifier les fichiers de production.
Livrable : verdict par contrat, cas manquants, tests et limites. Ne pas confondre
couverture lexicale et pertinence sémantique.

## C2 — Recette visuelle et opérationnelle dashboard (priorité 2)

Relire 57918b8/fc675a4. Instance temporaire, autre port, corpus synthétique,
jeton factice ; aucun restart du service actif. Vérifier 1200x800, 600x400,
350x220 et 800x220 (tailles du viewport), retour à 1200x800 : deux lignes
mémoire/disque en mode texte, pas de graphique, pas de défilement horizontal,
retour des contrôles et du fond après agrandissement. Tester une page Sources
pour confirmer que les règles dashboard ne s'y appliquent pas.
Valider sur clone la suite du commit candidat et les contrôles de l'installateur.
Vrai setpriv root : uniquement sur environnement jetable et identité dédiée,
jamais réinstaller l'unité existante. Si impossible, maintenir NON TESTÉ.
Livrable : dimensions réelles, capture synthétique, verdicts, commit et environnement.

## C3 — Contrat F1 (priorité 3, conception avant correctif)

Reproduire la substitution manuelle d'une extraction par une autre version
légitime du même original. Proposer un engagement durable d'extraction : lieu,
identité figée, première publication/interruption, compatibilité des bundles
sans engagement, audit/readiness et backup/restore. Décrire les critères rouges
avant correctif. Ne pas modifier store.py/extraction.py/validation.py ni migrer
les sources ; rapport et proposition seulement pour éviter les décisions implicites.

## GPT — fichiers réservés pendant ces missions

tools/benchmark_source_details.py, tests/test_source_detail_benchmark.py,
docs/SOURCE-DETAIL-COST.md et docs/PROJECT-REVIEW-2026-10-04.md : instrumenter
l'acceptation et le rejeu sur corpus synthétique, mesurer taille/coût et vérifier
les audits/empreintes. Aucun index ou cache métier ajouté dans ce lot.
GPT tient TODO et son propre canal ; Claude publie son compte rendu dans
CLAUDE-TO-GPT via le canal, sans réécrire ces fichiers réservés.

## Cadre partagé

Aucune donnée privée dans Git ou sorties. Clone temporaire, pas de modification
/opt ni de reboot, purge, migration, campagne IA ou service actif. Core/Hermes/
Qdrant différés. Décisions campagne (purge, conservation des propositions,
réapparition des rejets) et trois limites d'identité restent ouvertes.
L'estimation globale reste gelée à 45 %. Signaler le commit exact et distinguer
résultats locaux, VM, tests simulés et opérations réelles.
