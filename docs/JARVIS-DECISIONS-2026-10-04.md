# Décisions Jarvis → Eidolon — 4 octobre 2026

## Autorité et périmètre

Cadrage validé explicitement par toytoy le **4 octobre 2026 à 18 h 01
(Europe/Paris)**, après analyse GPT et revue Claude relayée par toytoy.
Cette validation autorise la consignation documentaire ; ce lot ne livre
aucune implémentation, migration, analyse IA ni campagne sur données privées.

Source : `jarvis-console-technique.zip`, documentation « JARVIS — Console
technique » du 4 octobre 2026, provenant de
https://claude.ai/artifact/VXdfprHLytQLDvEmCNfMUF.
Le ZIP contient documentation, HTML et captures, pas le code ni les tests.
Les performances et fonctions Jarvis sont des déclarations documentées,
pas des résultats vérifiés ici ; certaines captures sont simulées.

Base documentaire relue : `5a5eea7`, branche `refactor/architecture-v1`.
Aucun changement de l'estimation gelée **45 % / 52,75 points**.

## J-01 — Trois destinations, gel Core maintenu

1. Memory Engine : validations métier prévues et campagne ciblée sur un
   petit corpus réel, dans les lots existants T-047/T-051.
2. Interface de revue : prolonger Sources pour comprendre et corriger les
   propositions et leurs références, en lien avec T-029/T-051.
3. Core : conserver les idées dans
   [EIDOLON-GLOBAL-CONCEPTS.md](../EIDOLON-GLOBAL-CONCEPTS.md#g-016--retours-jarvis--4-octobre-2026),
   comme pistes différées, sans lever le gel ni changer l'ordre prioritaire.

Le dossier `core/` de ce dépôt contient aussi le code du Memory Engine :
son nom ne désigne pas une autorisation de travailler sur Eidolon Core.

Le dépôt documente déjà des imports/rappels réels et leurs contrôles de
références. La campagne ci-dessous est une **première campagne ciblée de
validation sémantique de ces cas**, pas le premier usage de données réelles
ni une remise à zéro des preuves existantes.

## J-02 — Proposition sans décision : attente sans expiration automatique

Règle métier validée pour la future file durable : une proposition sans
décision reste en attente. Son ancienneté ou l'absence de réponse ne valent
ni acceptation, ni rejet, ni abandon, ni motif de suppression automatique.
Aucun statut « expiré » n'est décidé par ce lot.

Prévoir dans la revue : ancienneté visible, tri, filtres par source, ancienneté
et type, et accès à la provenance. Ces fonctions doivent permettre de traiter
une file croissante sans modifier le contenu ou le statut par simple filtrage.

Séparer trois dimensions : ancienneté, décision sur le contenu, droit de
relancer. Espacer/suspendre une notification ne tranche pas la proposition.
Le mécanisme de relance appartient aux pistes Core ; il n'est pas implémenté ici.

Les règles existantes de purge des brouillons déjà décidés et de conservation
des empreintes ne sont pas étendues aux propositions sans décision. Une
acceptation humaine ne transforme pas automatiquement une interprétation en
vérité confirmée. Aucun nouveau mécanisme de purge n'est autorisé dans ce lot.

**Écart actuel explicite :** [SOURCE-LIBRARY.md](SOURCE-LIBRARY.md) décrit des
propositions temporaires portées par des formulaires signés, invalidés au
redémarrage. La décision ne rend pas ces formulaires persistants. La future
file devra conserver la proposition indépendamment de l'expiration technique
d'une signature et revalider les sources avant acceptation. Conservation
durable, tri et filtres restent à implémenter et vérifier.

## J-03 — Petit corpus réel, attentes explicites avant exécution

Point d'entrée retenu : dossier de sources existant. Choisir un petit ensemble
de conversations concernant **un seul projet**, avec corrections, engagements
et dates relatives. Le sous-ensemble exact et ses références restent à choisir ;
aucune lecture de corpus privé ni sélection effective n'a été réalisée dans ce lot.

Conserver les références exactes aux messages et leur chronologie. Ne pas
convertir silencieusement une archive ChatGPT en texte en perdant dates/rôles :
le parcours Sources du dashboard et l'import ChatGPT CLI ont des capacités
distinctes à respecter. Aucun réimport ou migration n'est lancé par cette décision.

Écrire les résultats attendus à la main avant la campagne, puis examiner :

| Cas | Attente |
| --- | --- |
| « hier » après minuit local | Calcul à partir du message et du fuseau d'origine, pas de l'heure d'import |
| « mardi » ambigu | Ambiguïté conservée ou clarification ; pas de précision inventée |
| Correction ultérieure d'une information | Provenance des deux énoncés conservée ; correction prise en compte sans confirmation automatique |
| Engagement sans preuve de fin | Aucun achèvement/abandon déduit du silence |
| Proposition sans décision | Attente conservée dans la cible durable ; absence de support signalée dans l'état actuel |

Sur une copie isolée, vérifier compréhension, références, restitution et effets
éventuels autorisés. Distinguer observation d'un comportement actuel, capacité
manquante et résultat attendu futur ; ne pas déclarer ces scénarios PASS avant
exécution. Ne pas publier les conversations privées dans Git.

## J-04 — Dates relatives : référence par message et hypothèses traçables

- Garder l'horodatage UTC original, l'expression source et sa référence exacte.
- Utiliser la date/heure du **message concerné**, pas uniquement celle de la
  conversation, qui peut s'étendre sur plusieurs jours.
- Convertir dans le fuseau IANA d'origine avant le calcul calendaire.
- Si le fuseau est inconnu, `Europe/Paris` peut être proposé/configuré comme
  hypothèse d'import explicite. Ne jamais le présenter comme extrait de la
  source, ni appliquer un décalage UTC fixe ; gérer été/hiver.
- Conserver référence, fuseau et origine/hypothèse du fuseau, interprétation,
  résultat résolu et incertitude. Ne pas inventer une heure pour une date seule.
- Séparer date d'observation, d'enregistrement et de validité ; le calcul de
  « hier » ne doit pas écraser ces distinctions ni réécrire les originaux.
- Le code effectue le calcul ; l'ambiguïté linguistique demeure visible si la
  référence ne permet pas de trancher.

Claude rapporte avoir constaté la conservation des dates de conversation et
messages dans `core/sources/chatgpt_import.py`, sans résolution de « hier »/
« mardi » et sans fuseau d'origine. Ces constats sont **rapportés**, pas
revérifiés par lecture du code dans cette consignation documentaire.

## J-05 — Absence de résultat et provenance

Un raccourci sans correspondance signifie qu'il ne sait pas répondre, pas
qu'aucun outil n'est nécessaire. Une recherche mémoire vide ne prouve ni la
fausseté d'un fait ni l'absence réelle d'un engagement.

Conserver la distinction source originale / fait extrait / synthèse générée.
Une analyse produite ne doit pas se transformer en preuve indépendante par
réindexations successives. Aucun changement du contrat RAG ou de Qdrant ici.

## Vérification de ce lot

Documentation uniquement : cohérence des liens, préservation des contenus
existants et publication distante contrôlées. Aucun test logiciel nouveau,
aucune suite pytest ou recette VM exécutée pour cette édition.
