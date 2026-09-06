# Eidolon Memory Temporal Model

Version: 0.1
Status: Draft

Ce document définit le modèle de référence pour la temporalité
des objets Information Eidolon.

Les différents champs temporels décrivent des événements distincts.
Ils ne doivent pas être confondus.

---

# 1. Temporal dimensions

Une information peut posséder plusieurs dimensions temporelles :

```yaml
created_at:
observed_at:
verified_at:
updated_at:
valid_from:
valid_until:
```

Chaque champ possède une signification propre.

---

# 2. created_at

`created_at` indique le moment où l'objet Information a été créé
dans le système Eidolon.

Exemple :

```yaml
created_at: 2026-08-10T15:30:00+02:00
```

Il ne signifie pas nécessairement que l'événement décrit
s'est produit à cette date.

---

# 3. observed_at

`observed_at` indique le moment où le phénomène, l'événement
ou l'état décrit par l'information a été observé.

Exemple :

```yaml
created_at: 2026-08-10T15:30:00+02:00
observed_at: 2026-08-10T14:55:00+02:00
```

Une observation peut donc être enregistrée après le moment
où elle s'est produite.

---

# 4. verified_at

`verified_at` indique le moment où une procédure de vérification
a produit son résultat.

Exemple :

```yaml
verified_at: 2026-08-11T09:20:00+02:00
```

La vérification est distincte de la création de l'information.

---

# 5. updated_at

`updated_at` indique le moment où l'objet Information a subi
une modification.

Il ne remplace pas `created_at`.

Une révision conserve l'identité de l'information tout en
modifiant sa représentation actuelle.

---

# 6. valid_from

`valid_from` indique le début connu ou supposé de la période
pendant laquelle l'information est considérée comme applicable.

Exemple :

```yaml
valid_from: 2026-08-01T00:00:00+02:00
```

Cette valeur décrit la validité de l'information, pas sa date
d'enregistrement.

---

# 7. valid_until

`valid_until` indique la fin connue de la période de validité.

Exemple :

```yaml
valid_until: 2026-08-31T23:59:59+02:00
```

Une information sans `valid_until` peut rester applicable
jusqu'à preuve du contraire ou jusqu'à une transition explicite.

---

# 8. Unknown temporal values

Une date inconnue ne doit pas être inventée.

Si une valeur temporelle n'est pas connue :

- le champ peut être absent ;
- le champ peut rester vide ;
- une information qualitative peut être conservée séparément.

Eidolon ne doit pas transformer une estimation en date exacte
sans l'indiquer.

---

# 9. Relative time

Les expressions relatives telles que :

- aujourd'hui
- hier
- demain
- récemment
- bientôt

doivent être interprétées dans leur contexte temporel.

Lorsqu'une date exacte peut être établie, elle peut être ajoutée
comme donnée dérivée, sans effacer la formulation originale.

---

# 10. Temporal uncertainty

Une information temporelle peut être incertaine.

Exemple :

```yaml
observed_at:
temporal_confidence: LOW
```

L'incertitude temporelle ne doit pas être confondue avec
l'état épistémique global de l'information.

---

# 11. Event time versus information time

Eidolon doit distinguer :

- le moment où quelque chose se produit ;
- le moment où Eidolon l'observe ;
- le moment où Eidolon crée l'objet ;
- le moment où Eidolon le vérifie ;
- le moment où l'objet est modifié.

Ces temps peuvent être différents.

---

# 12. Temporal validity and supersession

Une nouvelle information peut superséder une information précédente
sans que l'ancienne soit supprimée.

Exemple :

```text
Information A
valid_until = 2026-08-10

Information B
valid_from = 2026-08-11
SUPERSEDES -> Information A
```

La supersession est une relation explicite.

Elle ne doit pas effacer l'historique.

---

# 13. Temporal validity and epistemic status

La validité temporelle ne détermine pas automatiquement
la vérité d'une information.

Une information peut être :

```yaml
epistemic_status: CONFIRMED
valid_until: 2026-12-31T23:59:59+01:00
```

ou :

```yaml
epistemic_status: UNVERIFIED
valid_from: 2026-08-10T00:00:00+02:00
```

Les deux dimensions restent indépendantes.

---

# 14. Time zones

Les timestamps complets doivent conserver leur information
de fuseau horaire ou utiliser une représentation UTC explicite.

Exemple :

```yaml
created_at: 2026-08-10T15:30:00+02:00
```

ou :

```yaml
created_at: 2026-08-10T13:30:00Z
```

Une date locale sans contexte ne doit pas être interprétée
comme un instant universel sans information supplémentaire.

---

# 15. Source of truth

Les données temporelles sont conservées dans les objets
Information et les événements persistants.

Les fichiers Markdown/textes constituent la source de vérité.

Un index peut reproduire les timestamps pour le retrieval,
mais ne doit pas devenir leur unique stockage.

Qdrant pourra ultérieurement indexer les champs temporels.

---

# 16. Integrity rules

Le modèle temporel impose les règles suivantes :

- ne pas inventer une date inconnue ;
- ne pas confondre date de création et date d'observation ;
- ne pas confondre date de vérification et date de validité ;
- conserver les révisions ;
- conserver l'historique des transitions ;
- préserver les fuseaux horaires lorsque disponibles ;
- ne pas utiliser la temporalité seule comme preuve de vérité ;
- conserver les anciennes informations après supersession.

---

# 17. Future integration

Le Memory Controller pourra ultérieurement :

- valider les champs temporels ;
- renseigner `updated_at` lors des révisions ;
- enregistrer `verified_at` lors des vérifications ;
- exploiter `valid_from` et `valid_until` lors du retrieval ;
- détecter les informations temporellement périmées ;
- relier la temporalité aux Events ;
- exploiter la temporalité dans les mécanismes de mémoire prospective.

Ces fonctions ne sont pas implémentées par ce document.

