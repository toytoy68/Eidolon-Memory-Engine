# Budget du rappel sérialisé — T-047

`ContextualRecall.recall_payload`, également exposé par `RoutingExecutor`,
produit le texte exact transmis par un client : préfixe explicite, JSON compact
complet du RecallBundle, suffixe explicite. Les limites habituelles d’extraits
restent actives avant ce second budget. Le rappel existant reste inchangé.

```python
payload = executor.recall_payload(
    'measure', query_scope={'goal': 'efficiency'},
    max_payload_chars=8000,
    prefix='Sources avec réserves :\n', suffix='\nRéponds avec prudence.',
)
text_to_send = payload.text
assert len(text_to_send) <= 8000
```

Le JSON inclut les métadonnées, provenance, preuves, relations, temporalité,
statuts et needs_review. Si tout rentre, aucune source n’est écartée. Sinon le
rendu parcourt les éléments déjà sélectionnés dans leur ordre et conserve
chaque élément entier qui rentre avec les précédents ; un élément trop gros
n’empêche pas un suivant plus petit. Aucune réserve ni preuve n’est retirée
pour réduire la taille. PAYLOAD_BUDGET dans excluded_counts compte les éléments
écartés, en complément des exclusions du rappel. Le résultat Python expose
included_ids/omitted_ids pour le client. Les totaux d’extraits retenus sont
recalculés ; une réponse vide reste explicite. Si même l’en-tête et les
instructions fournies ne rentrent pas, la commande échoue sans tronquer le JSON.

`max_payload_tokens` exige un `payload_token_counter` explicite, déterministe,
retournant un entier positif ou nul. Le compteur reçoit chaque texte complet,
avec JSON et instructions ; le moteur ne somme pas des compteurs de champs.
Il est distinct du couple max_tokens/token_counter qui limite les extraits.
Aucun tokenizer implicite ou approximation de tokens n’est utilisé.

```sh
python -m core.routing.execution_cli --root RACINE recall-payload measure \
  --scope scope.json --max-payload-chars 8000
```

La CLI émet exactement payload.text, sans indentation ni nouvelle ligne ajoutée.
`--prefix` et `--suffix` sont comptés ; la CLI fournit un budget de caractères,
pas de tokenizer. Une erreur explicite BLOCKED a une sortie distincte du payload
réussi et n’est pas bornée par ce budget.

Le budget mesure des caractères Unicode Python, pas des octets UTF-8. Il couvre
payload.text, pas le conteneur Python RecallPayload, l’enveloppe HTTP, d’autres
messages système ou des instructions que le client ajouterait ensuite. Le client
doit transmettre exactement ce texte ou recompter son message final. Le rendu
considère seulement les éléments du bundle déjà borné, sans nouvelle recherche
ni garantie de sélection optimale pour un compteur non additif. Les réserves
et le contrôle de readiness du rappel restent actifs ; aucune donnée métier
n’est écrite. Les verrous techniques peuvent être initialisés.

Preuves du 03/10 : 36 nouveaux cas ; 24 rouges sur squelette après correction des
noms de champs d’une fixture, puis sept rouges API/CLI avant raccordement.
113 ciblés réussis en 0,44 s. JSON exact, Unicode, métadonnées volumineuses,
source suivante plus petite, réponse vide, header trop grand, cadrage, compteurs
non additifs/invalides, budgets d’extraits distincts, provenance/incertitude,
suppression en attente historique et garde readiness vérifiés. Retirer en mémoire
le budget caractères ou tokens produit un échec chacun. Corpus synthétiques ;
pas de tokenizer réel, client externe, corpus utilisateur ni coupure électrique
validés. [Suite VM](VM-TESTS-2026-10-02.md).
