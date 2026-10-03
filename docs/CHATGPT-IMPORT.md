# Import d'archives ChatGPT dans un corpus de test

Le lecteur importe une liste de conversations au format export ChatGPT. Il crée
une Information OBSERVATION/UNVERIFIED par conversation, avec ses messages texte
utilisateur/assistant et leurs identifiants, parents, rôles et dates.
Les variantes sont conservées avec leurs liens, sans les fusionner en dialogue.
Messages techniques, raisonnement interne et pièces multimédias non textuelles
ne sont pas proposés au rappel. Les fichiers originaux restent exacts.

Ce lot n'extrait pas de faits sémantiques, ne confirme pas les réponses de GPT,
ne crée pas de Threads et ne fournit pas de campagne IA durable. Les archives
entières peuvent dépasser les budgets du rappel : la recherche par passage reste
à construire. Les dates sont des dates d'archives, pas des dates de validité des
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
