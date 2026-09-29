# Mesures synthétiques du backend fichier

Depuis la racine du dépôt :

```sh
PYTHONDONTWRITEBYTECODE=1 python -m scripts.benchmark_filesystem --count 15000
```

La commande crée des Informations artificielles dans un dossier temporaire,
mesure écriture, première page de 100, recherche d'un terme en fin de corpus et
construction du manifeste, puis supprime ce dossier. Elle n'utilise pas
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
