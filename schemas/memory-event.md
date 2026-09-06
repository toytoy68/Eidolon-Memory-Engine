# Eidolon Memory Event

Version: 0.1

Ce document définit le modèle d'un événement historique
lié à une information mémoire.

Un événement décrit une transition, une modification ou
une action significative concernant une information.

L'événement ne remplace jamais l'information originale.

---

# 1. Identity

```yaml
event_id: event-YYYYMMDD-00000
information_id: info-YYYYMMDD-00000
revision: 1
```

---

# 2. Event Type

```yaml
event_type:
```

Valeurs prévues :

- CREATED
- UPDATED
- VERIFIED
- REFUTED
- CONFLICT_DETECTED
- CONFLICT_RESOLVED
- REACTIVATED
- REVIEW_REQUESTED
- REVIEW_COMPLETED
- SUPERSEDED
- DEPRECATED
- ARCHIVED
- RESTORED
- DELETED

Une suppression définitive doit rester soumise aux règles
de validation et de conservation.

---

# 3. State Transition

```yaml
state_transition:
  before:
  after:
```

Les valeurs doivent correspondre aux états réellement observés.

Exemple :

```yaml
state_transition:
  before:
    epistemic_status: UNVERIFIED
    operational_state: ACTIVE
  after:
    epistemic_status: CONFIRMED
    operational_state: ACTIVE
```

---

# 4. Cause

```yaml
cause:
  type:
  description:
```

La cause peut être :

- NEW_INFORMATION
- USER_VALIDATION
- SYSTEM_VALIDATION
- ADMIN_VALIDATION
- CONTRADICTION
- TRIGGER
- TIME
- HARDWARE_CHANGE
- SOFTWARE_CHANGE
- MANUAL_ACTION
- OTHER

---

# 5. Evidence

```yaml
evidence:
  supporting: []
  contradicting: []
```

Les preuves doivent référencer des informations, événements,
documents, observations ou autres sources existantes.

---

# 6. Provenance

```yaml
provenance:
  source_type:
  source:
  actor:
  timestamp:
```

L'historique doit permettre de déterminer qui ou quoi a provoqué
la transition.

---

# 7. Validation

```yaml
validation:
  mode:
  status:
```

Modes possibles :

- AUTOMATIC
- HUMAN
- HYBRID

Statuts possibles :

- ACCEPTED
- REJECTED
- PENDING_REVIEW

Une transition douteuse doit pouvoir rester PENDING_REVIEW.

---

# 8. Relation

```yaml
relations:
  - type:
    target:
```

Les événements peuvent être reliés à d'autres événements ou
informations.

---

# 9. Principle

Un événement historique ne doit pas réécrire l'histoire.

Une nouvelle transition crée un nouvel événement.

L'information courante peut évoluer, mais son historique reste
append-only autant que possible.

