# Coût de l’entretien après correction des verrous — 3 octobre 2026

Comparaison VM : code antérieur `e49caa7` extrait avec git archive dans un
répertoire isolé contre `b7ebdb4` (correctif `208a6ee`). Python 3.13.5,
corpus synthétiques temporaires sur tmpfs, fichiers chauds, cinq projets et
cinq échéances. Trois passes inactives puis trois rejeux par corpus ; un passage
avec effets par corpus, donc aucune médiane ni conclusion de gain sur ce dernier.
Préparation différente et indépendante pour les deux versions et chaque variante.
L’instrumentation compte les ouvertures Path.open réussies, pas les I/O physiques.

| Informations | Historique | Inactif avant (s) | Inactif après (s) | JSON historiques ouverts | Cinq échéances avant → après (s) |
| --- | --- | --- | --- | --- | --- |
| 100 | live | 0.092103 | 0.052598 | 430 → 220 | 0.276693 → 0.270463 |
| 100 | compact | 0.074418 | 0.044124 | 430 → 220 | 0.222227 → 0.224996 |
| 300 | live | 0.256671 | 0.148833 | 1230 → 620 | 0.733867 → 0.738454 |
| 300 | compact | 0.207244 | 0.118216 | 1230 → 620 | 0.586440 → 0.586182 |

À 300 Informations, les Markdown canoniques ouverts passent de 2135 à 1830,
les lectures dérivées restent à 6. La baisse provient du retrait d’un inventaire
initial redondant ; les autres scans, le catalogue et les dossiers restent
complets. Les coûts d’écriture avec échéances ne montrent pas de gain mesurable
sur cette comparaison limitée. La complexité globale n’est pas supprimée.

Chaque benchmark vérifie les 100/300 objets canoniques, les révisions attendues,
les cinq effets puis l’absence de second effet, la readiness finale et les dérivés
courants. Aucun corpus utilisateur ni appel IA, aucun entretien du roman. Pas
de garantie de latence sous charge Core, de disque froid/physique ni de coupure.

Reproduction : `run.py RACINE_CODE SHA_SORTIE FICHIER_JSON [100|300]` avec
l’environnement Python du projet ; le script réutilise le benchmark versionné.
Les variantes live/compact et trois répétitions sont fixées. Les fichiers JSON
contiennent les échantillons et contrôles ; manifest.json protège leurs octets.
