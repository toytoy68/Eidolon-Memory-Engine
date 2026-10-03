# Import d'archives ChatGPT dans un corpus de test

Le lecteur importe une liste de conversations au format export ChatGPT. Il crée
une Information OBSERVATION/UNVERIFIED par conversation, avec ses messages texte
utilisateur/assistant et leurs identifiants, parents, rôles et dates.
Les variantes sont conservées avec leurs liens, sans les fusionner en dialogue.
Messages techniques, raisonnement interne et pièces multimédias non textuelles
ne sont pas proposés au rappel. Les fichiers originaux restent exacts.

Ce lot n'extrait pas de faits sémantiques, ne confirme pas les réponses de GPT,
ne crée pas de Threads et ne fournit pas de campagne IA durable. Le rappel sélectionne désormais un message par archive, selon la couverture des
termes, puis une fenêtre exacte maximisant les termes présents dans le budget caractères,
avec préférence pour les termes rapprochés (politique v2). excerpt_reference
porte conversation/message/nœud/parent/auteur/date et offsets caractères.
Le rappel classe les archives selon le passage borné avant pagination
(lexical_passage_v1), sans les métadonnées JSON dans les signaux lexicaux.
La recherche backend sans option passage_chars conserve lexical_v1 historique.
Les objets ordinaires gardent leur classement existant. Le budget utilisé pour
ce classement est min(max_item_chars,max_chars), avant consommation par les
autres résultats et avant réduction par budget tokens. Pas de recherche sémantique. La date du message
est une valeur Unix UTC conservée ; les dates absentes restent explicites.
Un budget très court peut couper le mot recherché. Les réserves et la provenance
restent transportées séparément et le budget payload couvre ces références. Les dates sont des dates d'archives, pas des dates de validité des
faits évoqués. Les textes sont des données, pas des consignes pour l'agent lecteur.

## Sur la VM

Synchroniser la branche sans écraser un checkout modifié :

```bash
cd /opt/eidolon-memory-engine
git status --short
git pull --ff-only origin refactor/architecture-v1
.venv/bin/python -m pytest -q tests/test_chatgpt_import.py
```

Déposer les cinq JSON dans un dossier privé hors du dépôt, par exemple
`/home/toytoy/eidolon-imports`. Puis lancer :

```bash
.venv/bin/python -m core.sources.chatgpt_import \
  --root /home/toytoy/eidolon-corpus-gpt-test \
  /home/toytoy/eidolon-imports/01.json \
  /home/toytoy/eidolon-imports/02.json \
  /home/toytoy/eidolon-imports/03.json \
  /home/toytoy/eidolon-imports/04.json \
  /home/toytoy/eidolon-imports/05.json
```

La destination doit être neuve ou porter le marqueur CHATGPT-TEST-CORPUS d'un
import précédent. Les créations utilisent FilesystemInformationWrites, Events
et journaux existants. Rejouer les mêmes fichiers conserve les identités et les
révisions. Une conversation modifiée possède une nouvelle identité ; aucune
réconciliation entre exports successifs n'est implémentée. Deux versions
contradictoires d'un même ID dans un lot sont refusées avant publication.

`memory/` porte les objets canoniques. `import-originals/` à la racine conserve
les exports : sauvegarder la racine complète pour inclure ces originaux.
La copie core limitée à memory/ ne les transporte pas. L'interface sources du
dashboard n'accepte pas encore ces JSON ; utiliser cette CLI dédiée.

## Validation

Quatre tests locaux : provenance/rôles/branches, exclusion du raisonnement,
rejeu sans doublon et octets originaux, refus de versions contradictoires,
refus d'une racine active. Validation VM non effectuée.

## Recette du rappel sur corpus réel

```bash
.venv/bin/python -m tools.check_chatgpt_recall \
  --root /home/toytoy/eidolon-corpus-gpt-test
```

Ne publie aucun texte privé. Contrôle exact des références, des offsets, des
réserves UNVERIFIED, des budgets, du cas sans résultat et des empreintes de la
racine entière (hors fichiers de verrou). La couverture lexicale n'est pas une
mesure de pertinence sémantique ; les synonymes et réponses attendues restent à
évaluer. Les fenêtres sont choisies avant l'éventuel budget tokens, qui peut
encore réduire la couverture finale.

Résultat VM communiqué par toytoy sur 88050bc (04/10) : quatre régressions vertes,
20/20 extraits contenant le terme avec références présentes ; 1,381–1,548 s.
Ce contrôle VM n'incluait pas la comparaison exacte de toutes les références.

## Recette VM en attente — nuit du 04/10

Toytoy n'a plus accès à la VM et a demandé de reporter les tests. La dernière
base effectivement vérifiée sur VM est 88050bc. b3ae58e (fenêtres v2) et les
correctifs suivants doivent être synchronisés et testés demain :

```bash
cd /opt/eidolon-memory-engine
git status --short
git pull --ff-only origin refactor/architecture-v1
.venv/bin/python -m pytest -q tests/test_chatgpt_passages.py tests/test_chatgpt_import.py
.venv/bin/python -m tools.check_chatgpt_recall \
  --root /home/toytoy/eidolon-corpus-gpt-test
```

Ne pas réimporter les données pour les corrections de rappel. Ne pas attribuer
les mesures cloud à la VM. Résultat attendu de la recette : status PASS,
unchanged et references_exact vrais. La couverture partielle de certains
résultats est explicitement affichée ; elle n'est pas une erreur de référence.
