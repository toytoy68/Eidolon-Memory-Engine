# Coût des validations de détails — 4 octobre 2026

## Protocole

`tools.benchmark_source_details` utilise uniquement des corpus synthétiques
créés puis supprimés dans des dossiers temporaires. Historiques vivants non
compactés et sans index ; Informations ordinaires sans ancien détail v1.
Chaque réplique est préparée par lots canoniques de 100, puis une source TXT
minuscule est ajoutée et extraite. Pas d'appel à l'IA locale.

Une nouvelle validation puis un rejeu avec variante d'espaces et autre acteur
sont mesurés. Le rejeu doit rendre exactement le premier résultat et préserver
les empreintes de tous les fichiers. Chaque point vérifie readiness, audit des
écritures, nombre d'Informations et égalité des Informations préexistantes.
Préparation, hashes et contrôles finaux sont hors chronométrage et compteurs.

```bash
.venv/bin/python -m tools.benchmark_source_details \
  --sizes 0 100 300 --replicas 3 \
  --output /tmp/source-details-new-report.json
```

Le rapport refuse un fichier de sortie existant. `--temp-parent` permet de
choisir un parent réel pour les corpus jetables ; aucun chemin de corpus
utilisateur n'est accepté. Identifier séparément le système de fichiers VM.

## Résultats locaux

Trois répliques indépendantes par taille, deux modes : **18 points PASS**.
Exécution GPT ici, Python 3.12.14, système de fichiers temporaire chaud ;
**pas une mesure VM ni une latence disque isolée**. Le rapport contient
les empreintes de l'outil et de validation.py et le commit de base local.
Ce commit local diffère du SHA publié, les publications étant faites par le
connecteur ; les empreintes identifient le code réellement exécuté.

| Informations avant validation | Mode | Médiane (s) | Ouvertures Markdown | Ouvertures JSON journal | Objets retournés par list |
| --- | --- | --- | --- | --- | --- |
| 0 | new | 0.0094 | 0 | 2 | 0 |
| 0 | replay_variant | 0.0070 | 3 | 4 | 0 |
| 100 | new | 0.0940 | 400 | 302 | 100 |
| 100 | replay_variant | 0.0597 | 303 | 204 | 0 |
| 300 | new | 0.2599 | 1200 | 902 | 300 |
| 300 | replay_variant | 0.1480 | 903 | 604 | 0 |

[Rapport détaillé](benchmarks/source-details-2026-10-04.json).
Les compteurs concernent des ouvertures réussies, pas des fichiers uniques
ni les octets. Ils comprennent readiness et le writer, pas seulement le scan
v1. Un contrôle des compteurs confirme les lectures JSON sur corpus non vide.

## Interprétation et suite

La nouvelle acceptation matérialise toutes les Informations pour chercher un
ancien détail v1 compatible. Le rejeu évite ce list, mais les contrôles globaux
restent proportionnels à l'historique : supprimer le scan v1 ne supprimerait
pas tout le coût. Aucun cache/index n'a été ajouté, aucun verrou/readiness
assoupli. Le coût total d'une ingestion séquentielle peut devenir quadratique ;
ces trois tailles ne constituent pas une preuve de complexité ou de débit réel.

Suite Claude après C1/C2 : rejouer cet outil sur clone isolé, tailles 0/100/300,
trois répliques, choisir un dossier temporaire ext4 si disponible, consigner
le FS et l'environnement. Ne pas extrapoler au corpus ChatGPT : ses archives
et cette validation de détails sont deux parcours distincts.

Avant optimisation : compléter par historiques compactés/indexés, détails v1
présents et concurrence, puis décider un objectif mesurable. F1 reste une
question d'engagement durable d'extraction, indépendante de ces mesures.

Validation locale : **58 tests ciblés verts**, dont cinq cas de l'outil :
corpus/audits/rejeu/compteurs et refus de paramètres invalides sans publication.

## Extension : compactage, index et compatibilité v1

Huit configurations indépendantes (live/compact × index désactivé/activé ×
nouvelle v2/v1 présente), tailles 0/100/300, trois répliques, deux opérations :
**144 points PASS**. Préparation par lots, compaction bornée et construction
initiale de l'index sont hors mesure. En mode compact, les antécédents sont
compactés ; la nouvelle validation v2 reste vivante pour son rejeu.

La v1 est publiée par le writer avec la commande historique sur source factice.
Les acceptations mesurées changent l'acteur et les espaces pour éviter le rejeu
exact historique et éprouver la recherche de compatibilité. Les deux appels
doivent retourner cette v1 sans changer aucune empreinte. Les Informations
ordinaires préexistantes et tous les audits sont vérifiés à chaque point.

Médianes locales, à 300 Informations ordinaires (plus une v1 quand présente) :

| Antécédents | Index | Premier appel | Premier (s) | Second (s) | Ouvertures Markdown premier / second |
| --- | --- | --- | --- | --- | --- |
| live | non | nouvelle v2 | 0.2351 | 0.1568 | 1200 / 903 |
| live | non | v1 présente | 0.1550 | 0.1561 | 1204 / 1204 |
| live | oui | nouvelle v2 | 0.1728 | 0.1525 | 1200 / 903 |
| live | oui | v1 présente | 0.1584 | 0.1533 | 1204 / 1204 |
| compact | non | nouvelle v2 | 0.1964 | 0.1313 | 1200 / 903 |
| compact | non | v1 présente | 0.1387 | 0.1364 | 1204 / 1204 |
| compact | oui | nouvelle v2 | 0.1630 | 0.1308 | 1200 / 903 |
| compact | oui | v1 présente | 0.1329 | 0.1333 | 1204 / 1204 |

[Rapport de matrice](benchmarks/source-details-matrix-2026-10-04.json).
L'index de réservations ne supprime ni les contrôles globaux de readiness ni la
recherche des anciens détails v1. Retrouver une v1 impose encore le scan lors
d'un nouvel appel variant : il n'existe pas de journal v2 pour cette variante.
Ces résultats ne justifient pas de modifier les garanties de reprise.

Options de l'outil : `--history compact`, `--reservation-index`, `--v1-match`.
Sans ces options, le protocole initial reste live/non indexé/nouvelle v2.
Les deux rapports représentent deux versions successives de l'outil ; leurs
empreintes respectives sont conservées. Ce ne sont pas des comparaisons
avant/après optimisation métier. Concurrence et corpus privé non mesurés.
