# Mesures synthétiques du backend fichier

Pour les **écritures métier journalisées**, consulter le
[benchmark T-049](JOURNAL-SCAN-COST.md) et ses rapports avant/après du 01/10.
Il distingue create et create+compact, mesure 50/150/300 Informations et compte
les lectures de journaux. Ces coûts diffèrent de ceux des primitives backend
mesurées ci-dessous.

Depuis la racine du dépôt :

```sh
PYTHONDONTWRITEBYTECODE=1 python -m scripts.benchmark_filesystem --count 15000
```

La commande crée des Informations artificielles dans un dossier temporaire,
mesure écriture, première page de 100, recherche d'un terme en fin de corpus et
construction du manifeste, puis supprime ce dossier. La recherche est mesurée
avec le classement historique et le classement lexical optionnel. Elle n'utilise pas
`MEMORY_ENGINE_ROOT` ni les mémoires réelles. `--count` accepte 1 à 100 000.

Exécution locale dans l'environnement de développement du 29 septembre 2026,
15 000 fichiers synthétiques courts, un seul essai :

| Étape | Durée observée |
| --- | ---: |
| Création des 15 000 fichiers | 5,83 s |
| Première page de 100 | 0,13 s |
| Recherche sur tout le corpus | 0,94 s |
| Manifeste des 15 000 fichiers | 0,59 s |

Ce résultat ne prédit pas la VM Debian, son disque, la taille des données réelles,
les accès concurrents ni la pertinence des résultats. Refaire les mesures sur
une **copie** de données représentatives avant de choisir le découpage de
l'index et les budgets de latence d'Eidolon Core.

Nouvelle exécution locale le 29 septembre 2026, 15 000 fichiers synthétiques
courts, un seul essai : recherche historique 0,65 s, recherche
`lexical_v1` 0,64 s. Les deux trouvent le seul document contenant `needle`.
Ces temps ne mesurent ni la qualité du classement ni un corpus réel ; ils
indiquent seulement que le mode optionnel n'a pas augmenté le coût de ce
scénario synthétique dans cet environnement.

Un autre essai local du même jour a créé 15 000 fichiers synthétiques courts
avec 1 000 corps distincts répétés. L'audit de rétention et de validité a pris
3,70 s ; la prévisualisation des doublons exacts, 3,42 s pour 1 000 groupes.
Le pic suivi par `tracemalloc` pendant ces deux lectures était d'environ
15,9 Mio d'allocations Python, ce qui n'est **pas** une mesure de la RAM totale
du processus. Ces essais ont été effectués une seule fois, sur des textes
très courts et sans écrivain concurrent. Ils ne remplacent pas une mesure sur
une copie représentative de la VM.

Après l'ajout du contrôle des relations Information avant suppression, un
essai isolé sur 15 000 courts fichiers core sans relation a pris 0,43 s pour
approuver une suppression (scan des autres Informations inclus). C'est un seul
essai local, sans Thread lié, sans concurrence et sans matériel de la VM ; le
coût dépend du nombre et de la taille des fichiers.

Nouvelle exécution locale le 30 septembre 2026, toujours sur 15 000 fichiers
synthétiques courts après les contrôles supplémentaires du backend : écriture
3,75 s, première page de 100 en 0,104 s, recherche historique 0,617 s,
`lexical_v1` 0,593 s et manifeste 0,438 s. Une seule exécution ne permet pas
d'attribuer les différences aux changements de code ; le matériel et les
données de la VM restent à mesurer séparément.
