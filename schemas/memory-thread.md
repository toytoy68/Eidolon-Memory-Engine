# Eidolon Memory Thread Schema

Version: 0.1
Status: DESIGN
Component: Thread Manager

---

## 1. Purpose

Un Thread représente un sujet ouvert dans le temps.

Il peut représenter :

* un projet en cours ;
* une idée à développer ;
* une décision à prendre ;
* une action future ;
* un problème à résoudre ;
* un engagement en cours.

Un Thread conserve l'état courant du sujet et ses actions associées.

Le Thread ne remplace ni les Facts, ni les Events, ni les Decisions.

---

## 2. Architectural position

Le Thread Manager est responsable de la logique spécifique aux Threads.

```text
Memory Controller
        |
        v
Thread Manager
        |
        v
Memory Backend
        |
        v
FilesystemBackend
```

Le FilesystemBackend reste générique.

Il ne connaît pas la sémantique des Threads.

---

## 3. Identity

Chaque Thread possède un identifiant unique.

```yaml
id: thread-YYYYMMDD-HHMMSS-xxxxxxxx
type: THREAD
revision: 1
```

`id` est immuable.

`revision` augmente à chaque modification persistante du Thread.

---

## 4. Status

Les statuts principaux sont :

```text
PROPOSED
VALIDATED
IMPLEMENTATION
TESTING
COMPLETED
```

Les statuts secondaires sont :

```text
PAUSED
BLOCKED
CANCELLED
```

### Meaning

`PROPOSED`

Le sujet a été identifié mais n'est pas encore validé comme sujet actif.

`VALIDATED`

Le sujet a été explicitement reconnu comme Thread.

`IMPLEMENTATION`

Une réalisation ou action concrète est en cours.

`TESTING`

Le sujet est en phase de test ou de vérification.

`COMPLETED`

L'objectif du Thread est considéré comme atteint.

`PAUSED`

Le Thread reste ouvert mais aucune progression active n'est actuellement effectuée.

`BLOCKED`

La progression est empêchée par une dépendance, une information manquante ou un obstacle identifié.

`CANCELLED`

Le Thread ne doit plus être poursuivi.

---

## 5. Status transitions

Transitions normales :

```text
PROPOSED
    |
    v
VALIDATED
    |
    v
IMPLEMENTATION
    |
    v
TESTING
    |
    v
COMPLETED
```

Transitions de suspension :

```text
VALIDATED ─────► PAUSED
IMPLEMENTATION ─► PAUSED
TESTING ────────► PAUSED

PAUSED ─────────► VALIDATED
PAUSED ─────────► IMPLEMENTATION
PAUSED ─────────► TESTING
```

Blocage :

```text
VALIDATED ──────► BLOCKED
IMPLEMENTATION ─► BLOCKED
TESTING ────────► BLOCKED
```

Reprise :

```text
BLOCKED ─► VALIDATED
BLOCKED ─► IMPLEMENTATION
BLOCKED ─► TESTING
```

Annulation :

```text
PROPOSED ──────► CANCELLED
VALIDATED ─────► CANCELLED
IMPLEMENTATION ─► CANCELLED
PAUSED ─────────► CANCELLED
BLOCKED ────────► CANCELLED
```

Un Thread `COMPLETED` ou `CANCELLED` ne doit pas être réactivé silencieusement.

Une réouverture éventuelle devra créer une transition explicite et un Event historique.

---

## 6. Objective

L'objectif décrit ce que le Thread cherche à accomplir.

```yaml
objective: "Intégrer une mémoire dynamique des sujets ouverts."
```

L'objectif doit rester suffisamment stable pour permettre de déterminer si le Thread est terminé.

Une modification importante de l'objectif constitue une modification du Thread et doit donc augmenter sa revision.

---

## 7. Context

Le contexte fournit les informations nécessaires pour comprendre pourquoi le Thread existe.

```yaml
context:
  project: "Eidolon-Memory-Engine"
  domain: "MEMORY"
  description: "..."
```

Le contexte ne doit pas recopier les Facts ou Events.

Les informations existantes doivent être référencées par `relations`.

---

## 8. Actions

Un Thread peut contenir des actions.

```yaml
actions:
  - id: action-001
    description: "Définir le modèle Thread"
    status: COMPLETED

  - id: action-002
    description: "Implémenter Thread Manager"
    status: PLANNED
```

Statuts d'action v0.1 :

```text
PLANNED
IN_PROGRESS
COMPLETED
BLOCKED
CANCELLED
```

Une action appartient au Thread et ne constitue pas nécessairement une Information indépendante.

Une action importante nécessitant son propre historique pourra ultérieurement devenir une Information reliée au Thread.

---

## 9. Relations

Un Thread utilise le modèle de relations existant.

Exemple :

```yaml
relations:
  - type: RELATED_TO
    target: info-20260920-00001

  - type: DEPENDS_ON
    target: info-20260919-00012
```

Les relations peuvent pointer vers :

* Facts ;
* Events ;
* Decisions ;
* Questions ;
* Plans ;
* autres Threads ;
* autres objets Information.

Une relation ne constitue pas une preuve à elle seule.

Le Thread Manager ne doit pas modifier automatiquement l'état épistémique des objets reliés.

---

## 10. Temporal information

Un Thread conserve ses principales dates.

```yaml
time:
  created_at:
  updated_at:
  started_at:
  completed_at:
```

`created_at` est obligatoire.

`updated_at` est mis à jour lors de chaque modification persistante.

`started_at` est renseigné lors du passage vers un état actif de réalisation.

`completed_at` est renseigné lors du passage à `COMPLETED`.

Les dates historiques de changement d'état appartiennent aux Events.

---

## 11. Provenance

Le Thread conserve son origine.

```yaml
provenance:
  source_type:
  source:
  actor:
```

Exemples de `source_type` :

```text
USER_STATEMENT
SYSTEM_DETECTED
MEMORY_REVIEW
IMPORTED
OTHER
```

La provenance indique pourquoi le Thread existe.

---

## 12. Complete example

```yaml
---
id: thread-20260920-001200-a1b2c3d4
type: THREAD
revision: 1

status: PROPOSED

title: "Ajouter les Threads"

objective: "Intégrer une mémoire dynamique des sujets ouverts."

context:
  project: "Eidolon-Memory-Engine"
  domain: "MEMORY"
  description: "Ajouter une représentation persistante des sujets restant ouverts."

actions:
  - id: action-001
    description: "Définir le modèle Thread"
    status: COMPLETED

  - id: action-002
    description: "Définir les règles de cycle de vie"
    status: PLANNED

  - id: action-003
    description: "Implémenter Thread Manager"
    status: PLANNED

relations:
  - type: RELATED_TO
    target: info-example

time:
  created_at: 2026-09-20T00:12:00+02:00
  updated_at: 2026-09-20T00:12:00+02:00
  started_at:
  completed_at:

provenance:
  source_type: USER_STATEMENT
  source: "conversation"
  actor: "user"
---

# Thread

Ajouter les Threads au système Eidolon Memory Engine.
```

---

## 13. Invariants

Un Thread valide doit respecter les règles suivantes :

1. `id` est unique et immuable.

2. `type` est toujours `THREAD`.

3. `revision` est supérieure ou égale à 1.

4. `status` appartient à la liste des statuts autorisés.

5. `title` et `objective` sont obligatoires.

6. `created_at` est obligatoire.

7. `updated_at` ne peut pas être antérieur à `created_at`.

8. `completed_at` est obligatoire lorsque `status == COMPLETED`.

9. `completed_at` doit rester vide pour un Thread qui n'est pas `COMPLETED`.

10. Un Thread `CANCELLED` ne doit pas être modifié comme s'il était actif.

11. Une modification persistante du Thread augmente `revision`.

12. Les relations utilisent les types de relations existants.

13. Les actions possèdent un identifiant unique à l'intérieur du Thread.

14. Une action `COMPLETED` ne doit pas redevenir `PLANNED` sans transition explicite.

15. Une transition de statut doit produire un Event historique.

16. Le contenu du Thread reste lisible sans Qdrant.

17. Qdrant ne constitue jamais la source de vérité du Thread.

---

## 14. Thread versus Event

Le Thread représente l'état courant.

L'Event représente son historique.

Exemple :

```text
THREAD
status: TESTING
```

et :

```text
EVENT
event_type: STATUS_CHANGED

before:
  status: IMPLEMENTATION

after:
  status: TESTING
```

Le changement d'état ne doit donc pas écraser l'historique.

---

## 15. Thread versus Memory Plan

Le Thread et le Memory Plan sont deux concepts différents.

```text
Memory Plan
    contrat d'exécution interne
    Router → Executor

Thread
    mémoire persistante d'un sujet ouvert
    Controller → Thread Manager
```

Le Memory Plan n'est pas utilisé comme stockage des Threads.

---

## 16. Thread versus Action

Un Thread peut contenir plusieurs actions.

```text
THREAD
 ├── ACTION
 ├── ACTION
 └── ACTION
```

Une action simple reste embarquée dans le Thread.

Une action nécessitant une identité persistante, des relations, un historique propre ou un cycle de vie indépendant pourra ultérieurement devenir un objet Information.

Cette évolution n'est pas nécessaire en version 0.1.

---

## 17. Source of truth

Le fichier Markdown persistant constitue la source de vérité du Thread.

Les index et représentations dérivées sont reconstructibles.

```text
Thread Markdown
      |
      +----> Qdrant
      |
      +----> autres index
```

La perte d'un index ne doit pas entraîner la perte du Thread.

---

Status:

DESIGN
