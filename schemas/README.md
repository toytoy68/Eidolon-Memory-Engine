# Eidolon Memory Schemas

Ce répertoire contient les modèles de référence utilisés
par le système mémoire Eidolon.

Les schémas ne contiennent pas de mémoire utilisateur.

Ils décrivent la structure que le futur Memory Controller
utilisera pour représenter les informations.

## Schéma principal

information.md

Il définit l'objet générique Information.

## Architecture

Les mécanismes mémoire définis dans memory_rules.md sont :

- Working Memory
- Episodic Memory
- Semantic Memory
- Associative Memory
- Procedural Memory
- Prospective Memory

Ces mécanismes sont conceptuels.

Ils ne nécessitent pas six stockages physiques indépendants.

## Source de vérité

Les données persistantes restent stockées dans des fichiers
humainement lisibles.

Qdrant sera ultérieurement utilisé comme index sémantique
reconstructible.

## Protection

Les schémas ne doivent pas être utilisés pour stocker
des données utilisateur ou des informations mémoire réelles.

Toute évolution importante doit rester cohérente avec :

/opt/eidolon/core/memory_rules.md
