# Consignes pour les agents — Eidolon Memory Engine

## Identité et présentation communes

Avant de créer/modifier un en-tête source, une CLI destinée à l'utilisateur ou
un parcours d'installation, lire et appliquer
[Eidolon Presentation Standard v1](standards/EIDOLON-PRESENTATION-v1.md).

- Identité exacte : **Eidolon Core Technologies (ECT)**.
- Devise exacte : **Local AI • Modular • Reliable • Reproducible**.
- Nom du produit de ce dépôt : **Eidolon Memory Engine**.
- Utiliser les modèles d'en-tête du standard pour les nouveaux fichiers source ;
  ils sont également disponibles dans `templates/source-header.py.txt` et
  `templates/source-header.sh.txt`.
- Réutiliser les fonctions d'affichage communes du composant lorsqu'elles
  existent ; éviter une nouvelle bannière par commande. Les installateurs
  Bash partagent `deployment/presentation.sh`.
- Une sortie JSON reste strictement exploitable par machine ; réserver la
  décoration au mode humain. Conserver les statuts et codes de retour.
- `[OK]` exige une vérification réelle. L'affichage ne donne jamais une permission
  et ne prouve pas à lui seul une installation ou une exécution.

## Portée de cette adoption

Standard copié à la demande de toytoy le 05/10/2026 depuis
`toytoy68/Eidolon-Bootstrap-Framework`, branche `feat/eidolon-core-v0.1`,
commit `f34391687f14cd1b1734c25eef6f47dad5fd91f5`. Document et modèles identiques
à cette version de référence. Les mises à jour entre dépôts restent explicites.

Les commandes d'aperçu du standard concernent le sous-projet Eidolon Core du
dépôt source ; elles ne sont pas des commandes d'installation de Memory Engine.
La copie de ce standard ne signifie pas que les interfaces existantes ont déjà
été harmonisées.

Le standard ne demande pas de réécrire globalement les fichiers existants.
Harmoniser les composants dans des lots explicites sans altérer leur logique
métier. Ne pas exécuter ou `source` un installateur pour examiner sa présentation.
Les contrats mémoire, écritures coordonnées et règles de reprise restent
indépendants de l'affichage et doivent être préservés.
