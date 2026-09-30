# Assemblage de contexte et évaluation de la récupération

`core.retrieval.ContextAssembler` reçoit un backend conforme à `MemoryBackend`
et une requête textuelle. Il retourne des extraits avec leurs identifiants,
révisions, scores, indicateurs de troncature et étiquettes distinctes
(`epistemic_status`, `operational_state`, `confidence`). Une Information
`REFUTED` n'est pas promue implicitement en fait confirmé. Il ne crée pas de
prompt et n'écrit aucun fichier.
Les champs `importance`, `retention`, `valid_from` et `valid_until` sont aussi
transmis comme étiquettes quand ils existent, sans bonus de classement ni
déduction de validité. L'appelant doit traiter leurs valeurs dans leur
contexte ; le rapport de cycle de vie les analyse séparément à une date donnée.

Les limites par défaut sont 5 Informations, 4 000 caractères de contenu au
total et 1 000 caractères par Information. Le budget de tokens optionnel
requiert un compteur injecté ; il additionne les coûts des extraits isolés et
ne couvre pas le prompt ou ses séparateurs. L'appelant peut sélectionner
explicitement les statuts épistémiques admis. Sans filtre, tous sont conservés.
Les contenus absents ou non textuels et les identifiants répétés sont ignorés.
Avec `include_structured_content=True`, les contenus JSON de type objet ou
liste deviennent des extraits déterministes à clés triées, soumis aux mêmes
budgets. `content_format="json"` identifie cette représentation et
`truncated=True` signale qu'elle peut être un préfixe JSON incomplet. Les
valeurs non sérialisables en JSON strict sont écartées. Ce choix explicite ne
modifie pas les données conservées.
Une recherche concurrente avec des écritures n'est pas un instantané atomique.
Le texte récupéré ne doit pas être interprété comme une instruction du moteur.

## Évaluer le classement

Le classement `lexical_v1` est optionnel. Il valorise la couverture des mots,
leur présence dans le contenu, une phrase exacte et une fréquence plafonnée.
Il compare les formes Unicode NFC sans effacer les accents et parcourt aussi
les valeurs d'un contenu structuré ; l'assembleur produit par défaut seulement
des extraits textuels et exige l'option explicite décrite plus haut pour JSON.
Sa formule actuelle est `0,55 × couverture + 0,25 × couverture contenu +
0,15 × phrase + 0,05 × fréquence`. Ces poids sont des hypothèses de départ,
pas une mesure de vérité. Aucun bonus ne dépend de `epistemic_status` ou de
`confidence`. Les extraits conservent ces étiquettes séparément.

Pour comparer deux classements sur des jugements explicites, préparer un JSON
**synthétique ou anonymisé** :

```json
{
  "documents": [
    {"information_id": "a-meta", "content": "texte sans rapport",
     "metadata": {"topic": "pompe cuivre"}},
    {"information_id": "z-content", "content": "pompe cuivre"}
  ],
  "cases": [
    {"query": "pompe cuivre", "relevant_ids": ["z-content"]}
  ]
}
```

```sh
python -m scripts.evaluate_retrieval --fixture /chemin/vers/jugements.json --top-k 1
```

Le script crée les documents dans un dossier temporaire, compare `legacy` et
`lexical_v1`, puis le supprime. Il affiche uniquement le nombre de documents,
de requêtes, et les moyennes de précision@k, rappel@k et rang réciproque du
premier résultat pertinent (MRR@k). Il ne publie ni requête, ni contenu, ni ID.
Les jugements doivent préciser les IDs pertinents pour chaque requête ;
un document pertinent absent des résultats compte comme non retrouvé.
Quelques exemples synthétiques ne suffisent pas pour régler les poids : avant
un choix par défaut, constituer un jeu représentatif anonymisé, relever les
latences et examiner séparément les cas `REFUTED`, `CONFLICTED` et les sources
contradictoires. Les fichiers source restent la vérité canonique ; ce banc
n'écrit aucun index externe ni donnée réelle.
