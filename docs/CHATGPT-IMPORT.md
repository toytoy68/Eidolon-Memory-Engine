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

## Importeur v2 — revue C1 du 4 octobre 2026

Les nouveaux imports portent `chatgpt-archive-v2` et des identifiants
`gpt-conversation-v2-…`. Ils excluent les appels d'outil (recipient différent de
all), les messages visuellement cachés et les contenus code. Rôles système,
outils, raisonnement et multimédia non textuel restent exclus. Les entrées
malformées sont refusées ; la CLI retourne BLOCKED avec code 1, sans traceback
pour les erreurs attendues.

Validation A5-03 du 05/10 : pour les messages texte retenus, `content.parts`
doit être une liste. Une chaîne, un objet, `null`, un nombre ou un booléen
provoque un refus explicite avant création de la destination ou publication
d'un élément du lot. Dans une liste multimodale, les chaînes sont conservées
dans leur ordre et les objets non textuels restent ignorés. Un champ absent
reste équivalent à une liste vide. Aucun ancien contenu n'est réécrit.

**Le corpus existant /home/toytoy/eidolon-corpus-gpt-test reste en v1.** Il est
rappelable avec références exactes, sans réécriture ni purge. Un import v2 y est
refusé avant publication pour éviter de doubler les archives. La garde couvre
les fichiers Information et les opérations/reçus v1, y compris après suppression
ou interruption, et est revérifiée sous verrou Persistent pour la publication.
Les fichiers originaux sont inchangés ; aucune réimport réelle n'a été effectuée.

La revue Claude rapporte 153 appels d'outil sur 11 484 messages v1, répartis dans
42 conversations du corpus réel (comptage seul, empreintes inchangées). Ces
messages techniques restent dans les anciennes archives : le correctif v2
n'est pas une migration ni un filtre rétroactif de leur rappel.

Pour un futur import v2, utiliser une racine neuve distincte, par exemple
/home/toytoy/eidolon-corpus-gpt-v2-test. Ce choix conserve le corpus précédent
et ne constitue pas une demande de réimport immédiate.
Une reprise d'import v1 inachevé nécessite le producteur v1 compatible sur un
clone isolé ou une procédure explicitement décidée ; le nouveau CLI ne mélange
pas les versions pour contourner le blocage.

Les accents décomposés sont reconnus dans les passages, avec offsets calculés
sur le texte original : le texte des archives n'est pas normalisé/réécrit.
Les deux versions d'archive utilisent le classement des passages bornés.

Limites caractérisées par C1 : deux versions divergentes d'une conversation
sont refusées dans un même lot ; des imports successifs peuvent conserver deux
archives et rappeler le même message deux fois. Les passages commencent au
terme trouvé sans contexte à gauche ; limite de 32 Mio par fichier inchangée.
Aucune pertinence sémantique déduite de la couverture lexicale.

## Sur la VM

Synchroniser la branche sans écraser un checkout modifié :

```bash
cd /opt/eidolon-memory-engine
git status --short
git pull --ff-only origin refactor/architecture-v1
.venv/bin/python -m pytest -q tests/test_chatgpt_import.py
```

Déposer les cinq JSON dans un dossier privé hors du dépôt, par exemple
`/home/toytoy/eidolon-imports`. Pour une **racine v2 neuve**, lancer :

```bash
.venv/bin/python -m core.sources.chatgpt_import \
  --root /home/toytoy/eidolon-corpus-gpt-v2-test \
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

## Résultat VM reçu le 04/10

Validation directe de toytoy sur /opt au commit 9819d6b : **1824 tests verts
en 44,25 s, MCP inclus**. Rappel réel PASS, références exactes, corpus inchangé ;
1,290–1,376 s par requête. Pertinence sémantique non évaluée. Le redémarrage
et le rendu du dashboard restent à vérifier. Cette preuve complète le rapport
Claude ci-dessous et remplace l’état ancien du checkout /opt.


Claude Code rapporte sur 9819d6b : 1809 tests verts hors 15 MCP, 136 ciblés
verts et deux rappels réels PASS, références exactes et corpus inchangé.
Temps par requête : 1,298–1,381 s. [Rapport, provenance et limites](VM-VALIDATION-2026-10-04.md).
Le service actif reste 88050bc ; la recette navigateur reste à faire.
Les indications de non-validation ci-dessous décrivent l’état avant ce rapport.

## Recette VM en attente — nuit du 04/10

Toytoy n'a plus accès à la VM et a demandé de reporter les tests. La dernière
base effectivement vérifiée sur VM est 88050bc. b3ae58e (fenêtres v2) et les
correctifs suivants doivent être synchronisés et testés demain :

```bash
cd /opt/eidolon-memory-engine
git status --short
git pull --ff-only origin refactor/architecture-v1
.venv/bin/python -m pytest -q \
  tests/test_chatgpt_passages.py tests/test_chatgpt_import.py \
  tests/test_write_receipt_import.py tests/test_write_receipt_import_concurrency.py \
  tests/test_legacy_writer_guard.py tests/test_legacy_history_guard.py \
  tests/test_source_detail_identity.py tests/test_source_ai.py \
  tests/test_monitoring_dashboard.py
.venv/bin/python -m tools.check_chatgpt_recall \
  --root /home/toytoy/eidolon-corpus-gpt-test
```

Ne pas réimporter les données pour les corrections de rappel. Ne pas attribuer
les mesures cloud à la VM. Résultat attendu de la recette : status PASS,
unchanged et references_exact vrais. La couverture partielle de certains
résultats est explicitement affichée ; elle n'est pas une erreur de référence.

Les tests supplémentaires couvrent l’attente des imports concurrents de reçus
et le blocage des anciens outils d’écriture lorsque seul l’historique core
subsiste. Ces corrections restent NON TESTÉES VM. Aucun transfert ni aucune
suppression de données ne sont nécessaires pour cette recette.

D7/D9 ajoutés à la reprise : les tests vérifient l’identité des détails et le
libellé Europe/Paris. Compléter ensuite par une visite du tableau de bord sur
mobile ; les tests de rendu local ne constituent pas une recette navigateur.
