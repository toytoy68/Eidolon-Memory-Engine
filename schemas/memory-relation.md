# Eidolon Memory Relation Model

Version: 0.1
Status: Draft

Ce document définit le modèle de référence des relations
associatives entre objets Information Eidolon.

Les relations sont directionnelles.

Une relation ne constitue pas une preuve à elle seule.
Elle décrit un lien explicite entre deux informations.

---

# 1. Relation object

Une relation minimale possède :

```yaml
type: SUPPORTS
target: info-YYYYMMDD-00000
```

Le champ `target` désigne l'objet Information cible.

L'information source est l'objet dans lequel la relation est déclarée.

---

# 2. Relations autorisées

## SUPPORTS

L'information source apporte un élément favorable à l'information cible.

## CONTRADICTS

L'information source entre en contradiction avec l'information cible.

## DERIVED_FROM

L'information source a été dérivée de l'information cible.

## DEPENDS_ON

L'information source dépend de l'information cible.

## SUPERSEDES

L'information source remplace conceptuellement l'information cible.

L'information remplacée doit rester traçable.

## RELATED_TO

Les deux informations sont liées sans relation sémantique
plus spécifique actuellement établie.

## PART_OF

L'information source représente une partie de l'information cible.

## INSTANCE_OF

L'information source représente une instance d'un concept ou
d'une catégorie cible.

## CAUSED_BY

L'événement ou l'information source est attribué à la cause cible.

## FOLLOWS

L'information source intervient après l'information cible
dans une séquence temporelle ou causale explicitement connue.

---

# 3. Rules

Une relation :

- doit pointer vers un identifiant Information existant ou prévu ;
- doit conserver sa direction ;
- ne doit pas transformer automatiquement l'état épistémique ;
- ne constitue pas automatiquement une preuve ;
- doit rester lisible sans Qdrant ;
- doit être conservée lors d'une indexation ou d'une reconstruction ;
- doit rester traçable après archivage ou supersession.

---

# 4. Contradiction

`CONTRADICTS` ne signifie pas automatiquement que la source est vraie
ou que la cible est fausse.

Une contradiction doit pouvoir conduire à :

- une revue ;
- un état `CONFLICTED` ;
- une vérification ultérieure ;
- une résolution explicite ;
- ou une supersession.

Aucune résolution silencieuse ne doit être effectuée.

---

# 5. Supersession

`SUPERSEDES` ne doit pas supprimer la cible.

L'information précédente reste disponible pour l'historique
et la traçabilité.

La nouvelle information devient l'information active selon
les règles du Memory Controller.

---

# 6. Source of truth

Les relations sont stockées dans les objets Information
ou dans des fichiers texte/Markdown persistants.

Qdrant pourra indexer les relations ultérieurement.

Qdrant ne constitue pas la source de vérité des relations.

---

# 7. Example

```yaml
id: info-20260810-00001

relations:
  - type: SUPPORTS
    target: info-20260810-00002

  - type: DERIVED_FROM
    target: info-20260809-00015
```

Cet exemple décrit deux relations distinctes.

Il ne modifie pas à lui seul l'état épistémique des informations
concernées.

---

# 8. Future integration

Le Memory Controller pourra ultérieurement :

- valider les types de relations ;
- vérifier les cibles ;
- créer les relations ;
- enregistrer les transitions associées ;
- détecter les contradictions ;
- exploiter les relations lors du retrieval.

Ces fonctions ne sont pas implémentées par ce document.

