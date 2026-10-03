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

## Parcours allégé des passages — 3 octobre 2026

Les paragraphes vides sont masqués dans le texte et ignorés dans la limite des
20 paragraphes transmis au modèle. Les numéros d’origine et l’extraction figée
restent inchangés ; les citations continuent de pointer vers le paragraphe réel.
Un bouton « Analyser le passage suivant » reprend au prochain paragraphe non
vide, en conservant les limites 6000 caractères et un appel local à la fois.
Une fin entièrement vide est signalée sans charger le modèle. Un paragraphe
non vide dépassant seul la limite reste refusé, sans découpage implicite.

Les brouillons restent temporaires : valider les détails souhaités avant de
quitter leur page. Ce bouton ne valide rien, ne traite pas tout le manuscrit et
n’installe aucune analyse automatique. La file durable fait l’objet d’une
proposition séparée demandée à Claude. Quatre nouveaux cas rouges avant le lot,
45 tests sources/IA/HTTP réussis après correction.

## Erreurs d’analyse lisibles

Les erreurs attendues du modèle sont maintenant distinguées : analyse occupée
(HTTP 409), moteur indisponible ou modèle absent (503), réponse inexploitable,
citation non appuyée ou paragraphe trop long (422). Une page française conserve
le lien vers le texte pour reprendre. Elle n’affiche ni la réponse brute du
modèle ni le contenu fautif ; aucune proposition rejetée n’est enregistrée.
Les erreurs de formulaire restent distinctes (400). LocalAIError reste une
sous-classe de ValueError pour les appelants existants. Deux parcours HTTP rouges
avant le lot, 32 tests dashboard/IA ciblés verts après correction, sans appel
au modèle réel ni écriture du corpus utilisateur pendant ces tests.

## Lecture paginée du texte

Le texte extrait est présenté par pages de 40 paragraphes non vides. Les liens
précédent/suivant sont disponibles avant et après la page. Le formulaire IA est
placé avant le texte et commence par défaut au premier paragraphe visible de la
page choisie ; son numéro reste modifiable. Les références originales ne sont
jamais renumérotées. Version et empreinte sont disponibles dans un volet séparé.

Une page de lecture n’est pas un lot d’analyse : l’IA conserve sa limite de
20 paragraphes/6000 caractères, puis indique le passage suivant. Naviguer dans
le texte ne lance aucune IA et n’écrit aucune donnée. Aucun texte non vide est
signalé explicitement. Un test HTTP rouge avant le lot couvre deux pages,
numéros source avec vides intercalés, formulaire en haut, pages invalides/refus
des paramètres dupliqués et absence d’écriture. **51 tests ciblés verts**.

## Correction de la signature de validation (revue Claude D1)

La clé de signature HMAC est désormais un secret de 32 octets propre au serveur,
distinct du jeton CSRF rendu dans les formulaires et jamais envoyé au navigateur.
Connaître le jeton CSRF ne permet donc plus d’inventer une proposition portant
une fausse provenance modèle. Les citations vides, non textuelles ou de plus de
2000 caractères sont refusées avant toute écriture. Les signatures expirent au
redémarrage comme auparavant. Les contrôles du snapshot, de citation exacte et
du rejeu sans résurrection restent en place.

Défaut confirmé sur corpus factice : 4 cas rouges (formulaire forgé, citation
vide et deux types non textuels), 1 cas espaces déjà rejeté. **56 ciblés verts**
après correction. Signature privée et pagination activées sur la VM ; GET pages
1 et 2 du roman répondent 200 sans analyse ni validation automatique.

## Bibliothèque disponible après interruption (revue Claude D2/D3)

L’interface utilise une inspection en lecture seule qui sépare sources valides,
préparations complètes en attente et anomalies par lot. Une préparation ou un
fichier temporaire laissé dans une autre source ne masque plus toute la page.
Les audits/readiness et l’API list stricte conservent leurs refus ; une anomalie
n’est pas rendue utilisable et peut toujours bloquer les écritures en mémoire.

Une préparation complète expose sa fiche et un formulaire prérempli : sélectionner
le même original avec les mêmes nom, titre et auteur reprend la publication et
conserve la date initiale. La présence d’autres anomalies peut empêcher cette
reprise ; elles doivent être vérifiées séparément. Un lot incomplet ou un temporaire
d’extraction est signalé pour vérification, sans lecture de contenu invalide,
suppression/purge ou réparation implicite. Deux parcours HTTP rouges avant le lot,
**58 ciblés verts**, reprise réelle et conservation de date testées sur corpus
factice ; source valide accessible et readiness toujours bloquante en cas d’anomalie.

## Versions d’extraction figées (revue Claude D5)

Chaque lecture d’une extraction publiée reproduit son texte avec le pilote
correspondant au champ extractor enregistré, et non avec l’extracteur par défaut
pour les nouveaux documents. Les pilotes `utf8-lines-v1` et `docx-paragraph-v1`
conservent leurs règles antérieures ; toute nouvelle règle doit recevoir un
nouveau nom/version et être ajoutée au registre. Les formats sont vérifiés par
version ; une version inconnue ou incompatible reste bloquante.

L’extraction continue d’être comparée à l’original : cette séparation ne rend
pas valable un texte falsifié dont l’empreinte aurait été recalculée. Aucun
snapshot existant n’est migré ni réécrit et les versions par défaut n’ont pas
changé dans ce lot. Un cas rouge reproduit l’évolution de l’extracteur courant
avec suppression des vides ; l’extraction v1/readiness restent maintenant valides
sans écriture. **65 ciblés verts**, contrôles de falsification inclus. Conserver
les anciens pilotes est une obligation lors des évolutions ultérieures.

## Nouveaux pilotes DOCX/TXT v2 (D4/D11)

Les nouvelles extractions DOCX utilisent `docx-paragraph-v2` : une seule branche
AlternateContent est retenue (premier Choice, sinon Fallback) et les paragraphes
imbriqués ne sont plus agrégés dans le texte de leur paragraphe porteur. Les zones
de texte apparaissent donc une fois. Le parcours reste structurel dans
word/document.xml, sans prétendre reproduire la mise en page Word ni évaluer
les capacités visuelles de chaque branche.

Les nouvelles extractions TXT/Markdown utilisent `utf8-lines-v2` : limites de
ligne LF, CRLF et CR uniquement. Saut de page et séparateur Unicode U+2028 restent
dans leur ligne et ne créent plus de faux numéros. Le dernier terminateur de
ligne conserve le comportement antérieur (pas de ligne vide ajoutée pour lui).

Les pilotes v1 restent dans le registre et leurs snapshots sont vérifiés par
ces pilotes. Aucun snapshot existant, notamment celui du roman, n’est réécrit ;
extract sur une source déjà extraite renvoie toujours UNCHANGED. Quatre nouveaux
cas rouges avant le lot vérifient doublon DOCX, lignes TXT et conservation v1 ;
**73 ciblés verts**, contrôles de falsification et sauvegarde sources inclus.
