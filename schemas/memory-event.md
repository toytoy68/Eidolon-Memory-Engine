# Eidolon Memory Event

Version: 0.2

Ce document définit le modèle d'un événement historique
lié à une entité mémoire.

Un événement décrit une transition, une modification ou
une action significative concernant une Information ou un Thread.

L'événement ne remplace jamais l'entité originale.


---

# 1. Identity

```yaml
event_id: event-YYYYMMDD-HHMMSS-xxxxxxxx
information_id: info-YYYYMMDD-HHMMSS-xxxxxxxx
revision: 1
```

`information_id` et `thread_id` sont mutuellement exclusifs.

Un Event d'Information utilise `information_id`.

Un Event de Thread utilise `thread_id`.

Les deux ne doivent jamais être présents simultanément.

`revision` correspond à la révision de l'entité concernée au moment où l'Event est créé.


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

Pour les Threads :

- STATUS_CHANGED

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

Pour une Information, `before` et `after` décrivent les états
épistémique et opérationnel.

Pour un Thread, `before` et `after` décrivent le statut du Thread.

Exemple Thread :

```yaml
state_transition:
  before:
    status: IMPLEMENTATION
  after:
    status: TESTING
```

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


---

# 10. Thread Events

Les Threads utilisent les Events pour conserver leur historique.

Un Event de Thread utilise `thread_id` comme identifiant principal
et `STATUS_CHANGED` pour une transition de statut.

Exemple :

```yaml
event_id: event-20260920-002000-ab12cd34
thread_id: thread-20260920-001500-ef56gh78
revision: 4

event_type: STATUS_CHANGED

state_transition:
  before:
    status: IMPLEMENTATION
  after:
    status: TESTING

cause:
  type: MANUAL_ACTION
  description: "Passage du Thread en phase de test."

evidence:
  supporting: []
  contradicting: []

provenance:
  source_type: SYSTEM_GENERATED
  source: thread-manager
  actor: eidolon
  timestamp: 2026-09-20T00:20:00+02:00

validation:
  mode: AUTOMATIC
  status: ACCEPTED

relations:
  - type: CONCERNS
    target: thread-20260920-001500-ef56gh78

```
# Memory Event

Transition du Thread de IMPLEMENTATION vers TESTING.

---

# 11. Thread Revision

Lorsqu'un Thread change d'état :

1. Le Thread Manager valide la transition.
2. La révision du Thread est incrémentée.
3. Le nouvel état du Thread est déterminé.
4. Un Event historique correspondant est créé.
5. L'Event référence la nouvelle révision du Thread.

Exemple :

Thread revision 3
IMPLEMENTATION
        |
        | change_status()
        v
Thread revision 4
TESTING
        |
        +--> Event revision 4
             STATUS_CHANGED
             IMPLEMENTATION -> TESTING

L'Event et la nouvelle révision du Thread doivent rester cohérents.

---

# 12. Thread Principle

Un événement historique ne doit pas réécrire l'histoire.

Une nouvelle transition crée un nouvel événement.

L'état courant peut évoluer, mais son historique reste
append-only autant que possible.

Le Thread est la source de vérité de son état courant.

Les Events sont la source de vérité de son historique.

Les index ou systèmes de recherche, notamment Qdrant,
ne sont jamais la source de vérité des Events.


---

# 13. Compatibility

Les Events existants liés aux Informations restent valides.

L'ajout des Threads ne doit pas modifier le comportement
historique existant du Memory Controller.

Les deux domaines peuvent partager le même espace historique :

history/
└── events/
    ├── event-...md
    ├── event-...md
    └── event-...md

La distinction entre les domaines repose sur la présence
de `information_id` ou `thread_id`.
