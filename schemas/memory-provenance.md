# Eidolon Memory Provenance Model

Version: 0.1
Status: Draft

Ce document définit le modèle de référence de provenance
pour les objets Information Eidolon.

La provenance décrit l'origine d'une information.
Elle ne constitue pas, à elle seule, une preuve de vérité.

---

# 1. Purpose

Toute information persistante doit conserver autant que possible
la trace de son origine.

Eidolon doit pouvoir répondre :

- d'où vient cette information ?
- qui ou quoi l'a produite ?
- quand a-t-elle été produite ou observée ?
- dans quel contexte ?
- comment a-t-elle été vérifiée ?
- quelles informations ou sources la soutiennent ?

---

# 2. Provenance object

Une provenance minimale peut contenir :

```yaml
provenance:
  source_type: USER_STATEMENT
  source: "test-manual"
  author:
  originating_conversation:
  project:
  observed_at:
  verification_method:
```

Les champs inconnus restent vides ou absents.

Une information ne doit pas recevoir artificiellement une provenance
qui n'existe pas.

---

# 3. Source type

Les valeurs courantes peuvent inclure :

- USER_STATEMENT
- SYSTEM_GENERATED
- DIRECT_OBSERVATION
- MEASUREMENT
- EXPERIMENT
- DOCUMENTATION
- EXTERNAL_SOURCE
- TOOL_OUTPUT
- MODEL_OUTPUT
- IMPORTED_DATA

Cette liste peut évoluer.

Une nouvelle source_type doit rester sémantiquement explicite.

---

# 4. Source

`source` identifie la source immédiate de l'information.

Exemples :

```yaml
source: "test-manual"
```

```yaml
source: "nvidia-smi"
```

```yaml
source: "NVIDIA documentation"
```

```yaml
source: "conversation-20260810"
```

La source doit être aussi précise que possible sans inventer
d'identifiant ou de référence.

---

# 5. Author

`author` identifie l'auteur humain ou le système à l'origine
de l'information lorsqu'il est connu.

Exemple :

```yaml
author: "toytoy"
```

Pour une information générée par Eidolon :

```yaml
author: "eidolon"
```

Cela n'implique pas que l'information soit vraie.

---

# 6. Originating context

Le contexte d'origine peut comprendre :

```yaml
originating_conversation:
project:
domain:
mode:
```

Le contexte aide à interpréter l'information sans modifier
son contenu sémantique.

---

# 7. Temporal provenance

La provenance peut conserver plusieurs temps distincts :

```yaml
created_at:
observed_at:
verified_at:
updated_at:
```

Ces champs ne sont pas interchangeables.

`created_at` indique la création de l'objet Information.

`observed_at` indique quand le fait ou l'observation a eu lieu.

`verified_at` indique quand une vérification a été effectuée.

`updated_at` indique quand l'objet Information a été modifié.

---

# 8. Verification provenance

Une vérification doit pouvoir conserver sa méthode.

Exemple :

```yaml
verification:
  method: REPRODUCIBLE_TEST
  verified_at: 2026-08-10T12:00:00+02:00
  verifier: human
  result: CONFIRMED
```

La vérification doit rester distincte de la confiance.

Une information ne devient pas `CONFIRMED` simplement parce que
le modèle lui attribue une confiance élevée.

---

# 9. Evidence links

Les éléments de preuve peuvent être référencés explicitement :

```yaml
evidence:
  supporting:
    - info-YYYYMMDD-00001
  contradicting:
    - info-YYYYMMDD-00002
```

Ces références complètent les relations définies dans
`memory-relation.md`.

Elles ne doivent pas être utilisées pour masquer une contradiction.

---

# 10. Generated information

Une information produite par un LLM ou par Eidolon doit conserver
une provenance explicite :

```yaml
source_type: MODEL_OUTPUT
source: eidolon
author: eidolon
```

Une information générée automatiquement reste non vérifiée
tant qu'aucune validation appropriée n'a été effectuée.

La provenance ne transforme jamais automatiquement
`MODEL_OUTPUT` en `CONFIRMED`.

---

# 11. External sources

Une source externe doit rester identifiable lorsque cela est possible.

Exemples de métadonnées :

```yaml
source:
author:
published_at:
retrieved_at:
reference:
```

Les données externes doivent conserver leur origine.

La copie locale d'un document ne doit pas effacer sa provenance.

---

# 12. Provenance and relations

La provenance et les relations répondent à des questions différentes.

La provenance répond :

"Quelle est l'origine de cette information ?"

Une relation répond :

"Comment cette information est-elle liée à une autre ?"

Les deux mécanismes doivent rester distincts.

---

# 13. Provenance and epistemic status

La provenance ne détermine pas automatiquement l'état épistémique.

Exemples :

```yaml
source_type: USER_STATEMENT
epistemic_status: UNVERIFIED
```

```yaml
source_type: DOCUMENTATION
epistemic_status: UNVERIFIED
```

```yaml
source_type: DIRECT_OBSERVATION
epistemic_status: CONFIRMED
```

La transition vers `CONFIRMED` doit dépendre de la procédure
de vérification applicable.

---

# 14. Source of truth

La provenance est stockée dans les objets Information
et dans les fichiers persistants.

Les fichiers Markdown/textes constituent la source de vérité.

Un index ou une base vectorielle peut reproduire ces métadonnées,
mais ne doit pas devenir leur unique stockage.

Qdrant pourra ultérieurement indexer la provenance.

---

# 15. Integrity rules

La provenance :

- ne doit pas être inventée ;
- ne doit pas être silencieusement réécrite ;
- doit rester associée à l'information concernée ;
- doit être conservée lors d'une révision ;
- doit rester traçable après archivage ;
- ne doit pas être confondue avec la preuve ;
- ne doit pas déterminer seule la vérité ;
- doit rester lisible sans Qdrant.

---

# 16. Future integration

Le Memory Controller pourra ultérieurement :

- valider les champs de provenance ;
- enrichir la provenance avec des événements vérifiables ;
- enregistrer les méthodes de vérification ;
- lier les preuves aux informations ;
- exploiter la provenance lors du retrieval ;
- préserver la provenance lors des migrations et consolidations.

Ces fonctions ne sont pas implémentées par ce document.

