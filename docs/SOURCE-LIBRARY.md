# Sources conservées et détails IA à valider — T-051 / T-029

Demande de toytoy du 03/10/2026 après proposition Claude `4982014`. Le dashboard
peut ajouter un document source, conserver son original entier, figer son texte,
puis proposer des détails avec une IA locale. Seule une validation explicite
crée une Information. Qdrant, Hermes et Eidolon Core ne sont pas modifiés.

## Utilisation dans le dashboard

Le lien **Sources** ouvre la bibliothèque. Avec `--allow-source-upload`, choisir
un DOCX, PDF, TXT ou Markdown (1 octet à 10 Mio), saisir titre et auteur, puis
« Conserver la source ». Consulter la fiche ou télécharger l’original. Sans
l’option, le dashboard conserve ses accès en lecture seule ; aucun POST source
n’est accepté. L’authentification Basic existante protège aussi les originaux.
Les formulaires d’écriture exigent un jeton anti-CSRF du serveur.

Pour DOCX/TXT/Markdown, « Extraire le texte » publie une extraction figée, avec
paragraphes numérotés à partir de 1. Le DOCX couvre les paragraphes du document
principal, y compris ceux des tableaux ; images, notes, commentaires et en-têtes
séparés ne sont pas transcrits. TXT/Markdown exigent UTF-8 ; les lignes vides
restent numérotées. Les originaux PDF sont conservés/téléchargeables, mais leur
extraction texte n’est pas disponible dans ce premier lot. Aucun fichier n’est
exécuté, rendu comme HTML actif ou ouvert automatiquement par un programme tiers.

« Proposer des détails avec l’IA locale » analyse un passage explicite : au plus
20 paragraphes entiers / 6000 caractères, à partir du numéro choisi. Le prochain
numéro est affiché ; cela ne prétend pas avoir analysé tout le manuscrit. Un
paragraphe dépassant seul la borne doit être traité autrement, sans troncature
silencieuse de son texte. Au plus cinq détails par passage, avec citation exacte
et numéro ; réponse incorrecte ou citation absente du passage → refus sans
création d’Information. La présence d’une citation ne prouve pas la bonne
interprétation : relire et corriger les propositions.

**Valider ce détail dans la mémoire** crée une INTERPRETATION / UNVERIFIED par
le service Information journalisé. Le texte est modifiable avant validation.
La provenance conserve source/hash, extraction/hash/version, paragraphe,
citation, modèle/hash, proposition initiale et identité de validation. Le fait
qu’un humain accepte ne confirme pas une vérité ; un récit reste une source de
récit. Le champ auteur désigne l’auteur du document, pas l’auteur de la proposition.
Le temps stable de commande est celui d’émission du formulaire de revue,
explicitement nommé `review_form_issued_at`, pas une mesure de l’heure du clic.

Pour refuser un détail, ne pas le valider. Les propositions sont temporaires
au formulaire signé, pas une file durable. Elles expirent si le serveur est
redémarré ; recommencer l’analyse. Le même formulaire et détail validés sont
rejouables sans seconde écriture et sans résurrection après suppression. Une
nouvelle analyse/édition peut proposer une nouvelle Information ; aucune fusion
sémantique automatique ou suppression globale des sources n’est livrée.

## Stockage et conservation

`memory/sources/<SHA256>/original` conserve les octets exacts, sans réécriture.
`metadata.json` v1 porte source_id, sha256, taille, titre, auteur, nom original et
date. Un fichier identique est UNCHANGED et conserve sa première fiche ; un
manuscrit corrigé possède un autre SHA256 et ne déplace pas les anciennes
références. L’extraction facultative `extraction.json` v1 contient version de
parseur, hash source/texte et paragraphes ; elle est comparée à l’extraction de
l’original à chaque lecture de bundle. Elle ne change plus après publication.

Un original seul, sa fiche et l’extraction éventuelle sont des éléments de
sauvegarde. La copie core et la recette de restauration de l’arbre les conservent
sous `memory/`, hashes inclus ; ne pas copier seulement Persistent. Ne pas les
mettre dans Git. Leur suppression n’est jamais déduite d’une suppression
Information : retirer un détail garde sa source. Aucun effacement des sources,
sauvegardes ou copies clientes n’est revendiqué.

L’ajout prend Persistent → Sources, écrit un bundle `.pending-<SHA256>`, puis
publie par le renommage Linux NOREPLACE du transfert core. Un arrêt après
préparation complète est reprenable par le même original/titre/auteur ; la date
initiale est conservée. Readiness signale la préparation tant qu’elle n’est pas
publiée. Une préparation incomplète/divergente ou un fichier inconnu exige
examen humain, sans purge automatique. Deux ajouteurs coopératifs convergent.
Le processus de génération IA ne garde pas le verrou Persistent ; la validation
recontrôle readiness et les sources sous ce verrou avant la commande canonique.

Inventaire/readiness valident ces bundles ; altération d’original, de fiche ou
d’extraction bloque. `recover-all` ne publie pas une source à la place d’une
validation humaine ; relancer l’ajout exact après préparation complète. Le
convertisseur legacy refuse les sources préservées avant écriture destination :
aucune promotion/dégradation implicite d’un original en archive inactive.
Les scans relisent les sources et leurs textes, coût non optimisé ni mesuré sur
un corpus réel ; pas de garantie de latence ou d’ingestion intensive.

## CLI et lancement local

```bash
python -B -m core.sources.cli --root RACINE add --file manuscrit.docx --title "Mon manuscrit" --author "Auteur"
python -B -m core.sources.cli --root RACINE list
python -B -m core.sources.cli --root RACINE extract SHA256_SOURCE
python -B -m core.monitoring.dashboard --root RACINE --allow-source-upload --local-ai-model qwen3:0.6b
```

Le dashboard écoute par défaut sur **127.0.0.1:8766**, pour éviter le port 8765
réservé au MCP de collaboration. `EIDOLON_DASHBOARD_TOKEN` reste obligatoire.
Aucun service permanent dashboard ni nouvelle exposition réseau n’est installé.
Pour un accès hors machine, appliquer la politique HTTPS du guide MONITORING ;
Basic sur HTTP ne chiffre pas les documents ni le mot de passe.

## Petit modèle local choisi

Toytoy a choisi **Qwen3 0.6B Q4_K_M**, 522653767 octets téléchargés, digest
`7df6b6e09427a769808717c0a93cadc4ae99ed4eb8bf5ca557c90846becea435`.
Ollama 0.35.1 est préparé hors Git dans `tmp/local-ai/runtime/`, modèles dans
`tmp/local-ai/models/`. Le moteur dédié écoute sur **127.0.0.1:11435** ; il ne
réutilise ni ne modifie les modèles/services d’Eidolon Core. API locale seule,
proxy/redirect désactivés ; noms de modèles cloud refusés.

`scripts/run-source-ai.sh` lance ce runtime avec priorité CPU basse, une analyse
et un modèle à la fois, mode cloud désactivé et déchargement après usage. Chaque
appel demande un thread d’inférence, contexte 4096 et génération 512 tokens.
Ce sont des réglages de charge, **pas des quotas matériels ni une garantie de
zéro impact sur Eidolon Core**. Aucun ordonnanceur ni test conjoint Core n’est
installé. Le runtime est lancé manuellement dans cette séance, sans unité
systemd ni preuve de relance après arrêt de la VM. Ne pas lancer une seconde
instance sur le même port ; vérifier `/api/version` et `/api/ps` d’abord.

Test direct sur court récit synthétique : quatre propositions avec citations
exactes, 7,347 s, empreintes de la mémoire inchangées avant/après. Après réponse,
`/api/ps` vide ; daemon observé à 41088 ko RSS. Ce relevé ne mesure pas le pic
mémoire/CPU pendant l’inférence, ni la qualité sur le manuscrit réel.

Références : [modèle officiel](https://ollama.com/library/qwen3:0.6b),
[API génération](https://docs.ollama.com/api/generate),
[installation Linux officielle](https://docs.ollama.com/linux).
