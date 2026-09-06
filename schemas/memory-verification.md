# Eidolon Memory Verification Model

Version: 0.1
Status: Draft

Ce document définit le modèle de référence pour la vérification
épistémique des objets Information Eidolon.

La vérification détermine l'état épistémique d'une information
à partir d'éléments de preuve et d'une procédure identifiable.

La confiance du modèle ne constitue pas une preuve.

---

# 1. Epistemic states

Les états épistémiques autorisés sont :

- UNKNOWN
- UNVERIFIED
- CONFIRMED
- REFUTED
- CONFLICTED
- SUPERSEDED

Ils décrivent le niveau actuel de validation de l'information.

L'état épistémique est distinct de :

- operational_state
- confidence
- importance
- valid_from
- valid_until

---

# 2. Verification result

Une opération de vérification peut produire :

```yaml
verification:
  result: CONFIRMED
  method: REPRODUCIBLE_TEST
  verified_at: 2026-08-10T15:30:00+02:00
  verifier: human
  reason: "Résultat confirmé par un test reproductible."
```

Le résultat doit appartenir aux états épistémiques autorisés.

---

# 3. Verification methods

Les méthodes possibles comprennent notamment :

- DIRECT_OBSERVATION
- MEASUREMENT
- EXPERIMENT
- REPRODUCIBLE_TEST
- DOCUMENTATION
- EXPLICIT_USER_CONFIRMATION
- INDEPENDENT_CORROBORATION
- ADMINISTRATIVE_REVIEW

Cette liste peut évoluer.

La méthode utilisée doit être conservée lorsque connue.

---

# 4. Evidence

Une vérification doit pouvoir référencer ses éléments de preuve.

Exemple :

```yaml
evidence:
  supporting:
    - info-YYYYMMDD-00001
  contradicting:
    - info-YYYYMMDD-00002
```

Une preuve peut être :

- une observation ;
- une mesure ;
- un événement ;
- un document ;
- une autre information ;
- une validation humaine.

La présence d'une preuve n'implique pas automatiquement
qu'elle soit suffisante pour confirmer une information.

---

# 5. CONFIRMED

`CONFIRMED` signifie qu'une procédure de vérification appropriée
a produit suffisamment d'éléments pour considérer l'information
comme validée dans son contexte.

Exemple :

```yaml
epistemic_status: CONFIRMED
verification:
  result: CONFIRMED
  method: REPRODUCIBLE_TEST
```

Une confirmation ne signifie pas que l'information est
universellement vraie ou éternelle.

Elle reste liée à son contexte et à sa validité temporelle.

---

# 6. REFUTED

`REFUTED` signifie qu'une procédure appropriée a établi que
l'information ne peut pas être considérée comme valide dans
le contexte concerné.

Une information réfutée ne doit pas être supprimée.

Elle reste disponible pour :

- l'historique ;
- l'analyse des erreurs ;
- la traçabilité ;
- la compréhension des hypothèses passées.

---

# 7. CONFLICTED

`CONFLICTED` indique que des éléments persistants incompatibles
existent et qu'aucune résolution suffisante n'a encore été établie.

Exemple :

```text
Information A
    CONTRADICTS
Information B
```

Cela ne signifie pas que A ou B est automatiquement fausse.

Le système doit conserver les deux informations et leur provenance.

Une Review peut être créée lorsque la résolution nécessite
une décision humaine.

---

# 8. SUPERSEDED

`SUPERSEDED` indique qu'une information a été remplacée
par une autre information plus récente ou plus appropriée.

La nouvelle information doit rester liée à l'ancienne par :

```yaml
type: SUPERSEDES
target: info-YYYYMMDD-00000
```

La donnée originale ne doit pas être supprimée.

La supersession est distincte de la réfutation.

Une information peut être superseded sans avoir été fausse.

---

# 9. Allowed transitions

Les transitions doivent être explicites.

Exemples courants :

```text
UNKNOWN
   |
   v
UNVERIFIED
   |
   +----> CONFIRMED
   |
   +----> REFUTED
   |
   +----> CONFLICTED
```

Puis :

```text
CONFIRMED ----> SUPERSEDED
REFUTED   ----> SUPERSEDED
CONFLICTED ----> CONFIRMED
CONFLICTED ----> REFUTED
```

Une transition doit produire un Event historique.

Aucune transition épistémique importante ne doit être silencieuse.

---

# 10. Review

Une transition peut nécessiter une Review lorsque :

- les preuves sont contradictoires ;
- le résultat est ambigu ;
- la décision a un impact important ;
- une confirmation humaine est explicitement requise ;
- une opération destructive ou irréversible est envisagée.

La Review reste un objet distinct de l'Information et de l'Event.

---

# 11. Provenance

Toute vérification significative doit conserver :

- méthode ;
- vérificateur ;
- date ;
- raison ;
- éléments de preuve lorsque disponibles.

La provenance originale de l'information doit être conservée.

Une vérification ajoute de la traçabilité ; elle ne remplace pas
la provenance initiale.

---

# 12. Temporal integration

La vérification utilise le modèle temporel.

Lorsqu'une vérification est effectuée :

```yaml
verified_at:
```

peut être renseigné.

Cela ne doit pas remplacer :

```yaml
created_at:
observed_at:
updated_at:
valid_from:
valid_until:
```

Les dimensions temporelles restent indépendantes.

---

# 13. Confidence

`confidence` est distinct de `epistemic_status`.

Exemple :

```yaml
epistemic_status: CONFIRMED
confidence: MEDIUM
```

Une information confirmée peut avoir une confiance différente
selon la nature de son contexte, sa portée ou ses limites.

Inversement :

```yaml
epistemic_status: UNVERIFIED
confidence: HIGH
```

peut représenter une information jugée plausible mais non vérifiée.

Le système ne doit jamais utiliser confidence comme substitut
à une vérification.

---

# 14. LLM verification

Une sortie LLM peut proposer :

- une hypothèse ;
- une interprétation ;
- une classification ;
- une piste de vérification ;
- une relation candidate.

Une sortie LLM ne doit pas automatiquement produire :

```yaml
epistemic_status: CONFIRMED
```

Une vérification automatisée par un LLM doit rester identifiable
comme telle et respecter les règles de vérification applicables.

---

# 15. Contradiction handling

Lorsqu'une nouvelle information contredit une information existante :

1. conserver les deux informations ;
2. conserver leur provenance ;
3. créer la relation `CONTRADICTS` ;
4. enregistrer l'événement ;
5. déterminer si un état `CONFLICTED` est nécessaire ;
6. créer une Review si une décision humaine est nécessaire.

Le système ne doit pas supprimer silencieusement l'information
précédente.

---

# 16. Source of truth

Les états et résultats de vérification sont persistés dans
les objets Information et les Events.

Les fichiers Markdown/textes restent la source de vérité.

Qdrant pourra indexer les états épistémiques et les métadonnées
de vérification, mais ne pourra pas devenir leur source unique.

---

# 17. Integrity rules

Le modèle impose :

- aucune confirmation sans procédure identifiable ;
- aucune réfutation sans justification suffisante ;
- aucune résolution silencieuse d'une contradiction ;
- aucune suppression automatique d'une information réfutée ;
- aucune conversion automatique de confidence en confirmation ;
- conservation de la provenance ;
- conservation des Events ;
- conservation des Reviews lorsque nécessaires ;
- traçabilité des transitions ;
- lisibilité sans Qdrant.

---

# 18. Future integration

Le Memory Controller pourra ultérieurement :

- valider les transitions ;
- enregistrer les résultats de vérification ;
- gérer les preuves ;
- créer automatiquement des relations `CONTRADICTS` candidates ;
- créer des Reviews lorsque nécessaire ;
- renseigner `verified_at` ;
- produire les Events correspondants ;
- empêcher les transitions interdites.

Ces fonctions ne sont pas implémentées par ce document.

