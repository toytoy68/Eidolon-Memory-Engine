# Eidolon Information Object

Version: 0.1

Ce document définit le modèle générique d'une information
persistante Eidolon.

Une même information peut participer à plusieurs mécanismes
mémoire.

La structure physique des fichiers ne doit pas être confondue
avec les mécanismes cognitifs définis dans memory_rules.md.

---

# 1. Identity

Identité stable de l'information.

```yaml
id: info-YYYYMMDD-00000
revision: 1
```

---

# 2. Content

Contenu humainement lisible de l'information.

```yaml
content: |
  Contenu de l'information.
```

Le contenu doit rester lisible sans Qdrant, embedding ou
autre service externe.

---

# 3. Type

Type principal de l'information.

Valeurs autorisées :

- FACT
- OBSERVATION
- EVENT
- HYPOTHESIS
- PREDICTION
- INTERPRETATION
- QUESTION
- DECISION
- CONSTRAINT
- PREFERENCE
- CONCEPT
- PROCEDURE

---

# 4. Epistemic Status

État de validation de l'information.

```yaml
epistemic_status: UNVERIFIED
```

Valeurs autorisées :

- UNKNOWN
- UNVERIFIED
- CONFIRMED
- REFUTED
- CONFLICTED
- SUPERSEDED

L'état épistémique ne doit jamais être déduit uniquement de
la formulation ou de la confiance du modèle.

---

# 5. Operational State

État opérationnel de l'information.

```yaml
operational_state: ACTIVE
```

Valeurs autorisées :

- ACTIVE
- PLANNED
- PENDING_REVIEW
- CANCELLED
- COMPLETED
- DEPRECATED

L'état opérationnel est distinct de l'état épistémique.

---

# 6. Confidence

Niveau de confiance actuel.

```yaml
confidence: MEDIUM
```

Valeurs autorisées :

- LOW
- MEDIUM
- HIGH

La confiance ne constitue pas une preuve.

Une information peut avoir une confiance élevée tout en restant
UNVERIFIED.

---

# 7. Importance

Importance future de l'information.

```yaml
importance: NORMAL
```

Valeurs autorisées :

- EPHEMERAL
- LOW
- NORMAL
- HIGH
- CRITICAL

Importance et vérité sont indépendantes.

---

# 8. Context

Contexte nécessaire à l'interprétation.

```yaml
context:
  mode: PROJECT
  project:
  domain:
  session:
  environment:
  hardware:
  software_version:
```

Modes possibles :

- CHATBOT
- PROJECT
- ADMIN
- MAINTENANCE
- RESEARCH
- SYSTEM

Domaines possibles :

- TECHNICAL
- PERSONAL
- ENVIRONMENTAL
- PROJECT
- GENERAL

Plusieurs domaines peuvent être associés à une même information.

---

# 9. Provenance

Origine de l'information.

```yaml
provenance:
  source_type:
  source:
  author:
  date:
  conversation:
  document:
  event:
```

Sources possibles :

- USER_STATEMENT
- DIRECT_OBSERVATION
- COMMAND_OUTPUT
- LOG
- FILE
- DOCUMENTATION
- EXTERNAL_SOURCE
- MODEL_INFERENCE
- SYSTEM_GENERATED
- DERIVED

La provenance indique l'origine.

Elle ne constitue pas automatiquement une preuve.

---

# 10. Evidence

Éléments permettant de soutenir ou de contredire l'information.

```yaml
evidence:
  supporting: []
  contradicting: []
```

Les éléments doivent pouvoir référencer leur source ou leur
événement d'origine.

Une information sans preuve peut rester conservée comme
hypothèse, prédiction ou information non vérifiée.

---

# 11. Time

Informations temporelles.

```yaml
time:
  created_at:
  observed_at:
  verified_at:
  updated_at:
  valid_from:
  valid_until:
```

Toutes les dates ne sont pas obligatoires.

Elles ne doivent être ajoutées que lorsqu'elles ont un sens.

---

# 12. Relations

Relations avec d'autres informations.

```yaml
relations:
  - type:
    target:
```

Types autorisés :

- RELATES_TO
- CONCERNS
- DERIVED_FROM
- SUPPORTS
- CONTRADICTS
- CONFIRMS
- REFUTES
- DEPENDS_ON
- REQUIRES
- USES
- PRODUCES
- CAUSES
- CAUSED_BY
- PRECEDES
- FOLLOWS
- REPLACES
- SUPERSEDES
- PART_OF
- BELONGS_TO
- ASSOCIATED_WITH

Les relations doivent conserver leur signification.

---

# 13. Triggers

Déclencheurs permettant de réactiver une information.

```yaml
triggers: []
```

Ils sont principalement utilisés par la mémoire prospective.

Types possibles :

- DATE
- TIME
- EVENT
- HARDWARE_CHANGE
- SOFTWARE_CHANGE
- NEW_INFORMATION
- CONTRADICTION
- THRESHOLD
- USER_ACTION
- PROJECT_STATE
- MANUAL_REVIEW

Un trigger ne doit pas déclencher automatiquement une opération
destructive.

---

# 14. Retention

Politique de conservation.

```yaml
retention: NORMAL
```

Valeurs autorisées :

- PERMANENT
- LONG_TERM
- NORMAL
- TEMPORARY
- DISPOSABLE

La rétention est indépendante de la vérité et de l'importance.

---

# 15. Example

Exemple d'information complète.

```yaml
id: info-20260810-00001
revision: 1

type: HYPOTHESIS

epistemic_status: UNVERIFIED
operational_state: ACTIVE

confidence: MEDIUM
importance: HIGH

context:
  mode: PROJECT
  project: Eidolon
  domain:
    - TECHNICAL
    - PROJECT
  session: 20260810

provenance:
  source_type: MODEL_INFERENCE
  source: benchmark-analysis

evidence:
  supporting:
    - episode-20260809-004
  contradicting: []

time:
  created_at: 2026-08-10T00:00:00+02:00

relations:
  - type: CONCERNS
    target: v100-32gb

triggers:
  - type: HARDWARE_CHANGE
    event: second_v100_installed

retention: LONG_TERM
```

## Hypothèse

Une seconde V100 32 Go pourrait réduire fortement
l'offload CPU sur certains modèles de grande taille.

## État

Cette hypothèse n'est pas encore vérifiée.

## Vérification prévue

Réaliser un benchmark après installation de la seconde V100.

## Résultat

À compléter après vérification.

Cet exemple est uniquement un modèle.
Il ne constitue pas une information réelle de la mémoire.

---

# 16. Source of Truth

Les fichiers Markdown et texte contenant les informations
persistantes constituent la source de vérité.

Qdrant pourra ultérieurement indexer ces informations.

La perte de Qdrant ne doit pas entraîner la perte de la mémoire.

Le contenu doit donc toujours pouvoir être reconstruit depuis
les fichiers persistants.

---

# 17. Relation avec memory_rules.md

Ce schéma implémente les règles définies dans :

/opt/eidolon/core/memory_rules.md

En cas de contradiction entre le schéma et les règles mémoire,
la définition de memory_rules.md doit être revue avant toute
modification du schéma.

Ce fichier ne constitue pas une base de données.

Il constitue un modèle de référence pour le futur
Memory Controller.
