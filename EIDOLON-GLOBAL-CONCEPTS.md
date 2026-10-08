# Eidolon Global — concepts, idées et architecture future

Dernière mise à jour : 2026-10-08.

Ce document rassemble les concepts qui concernent **Eidolon dans son ensemble**
et non le développement interne du Memory Engine. Il sert de parking architectural
pour Eidolon Core, EidolonOS, agents, skills, modèles, outils, sécurité et futures
intégrations.

**Règle de séparation :** `TODO-LIST.md` reste réservé au développement,
aux tests, à la migration et au déploiement du **Memory Engine**. Une idée globale
ne doit y entrer que si elle devient un travail concret nécessaire au contrat ou
à l'implémentation du Memory Engine.

## Vision générale

Eidolon vise une architecture locale, modulaire et indépendante des modèles :

    APPLICATIONS / EIDOLON OS / ROBOT
                    |
               EIDOLON CORE
                    |
      +-------------+-------------+
      |             |             |
    Agents        Skills       Policy
      |             |             |
      +------ Mission/Task --------+
                    |
              MEMORY ENGINE
                    |
        source de vérité + index

Principe : **Memory Engine sait ce qu'Eidolon sait ; Core sait ce qu'Eidolon sait
faire.**

Le Memory Engine conserve informations, événements, relations, provenance,
Threads et historique. Eidolon Core orchestre agents, modèles, skills, outils,
missions, cadence et politiques d'action.

## G-001 — Decision Engine

Étudier un composant spécialisé dans les décisions courtes et structurées plutôt
que solliciter un gros LLM génératif pour chaque choix.

Exemples : pertinence de mémorisation, classification, projet/Thread concerné,
validation nécessaire, archivage, routage d'une tâche ou sélection d'un outil.

Le composant doit produire des résultats structurés avec score/confiance,
provenance du modèle et politique/seuil utilisé.

## G-002 — Model / Task Router

Affecter les tâches étroites à des modèles spécialisés et réserver les gros
modèles aux tâches nécessitant davantage de raisonnement ou de contexte.

Exemples : classification, extraction, OCR, traduction, scoring et résumé.

Prévoir pour chaque modèle/profil : capacités, **domaines explicitement non
supportés**, mémoire/VRAM, latence, qualité, coût matériel, contexte disponible,
seuil de confiance, validateur éventuel et modèle de repli.

Le routeur doit empêcher un spécialiste de traiter silencieusement une tâche hors
de son domaine. Si le profil ne couvre pas la tâche, si le score est insuffisant
ou si la validation échoue, escalader vers un modèle plus général/capable.

Objectif : le gros modèle ne doit pas tout faire, mais un petit modèle spécialisé
ne doit pas non plus être utilisé hors de son domaine.

## G-003 — Mission Manager et orchestration multi-agents

Architecture cible à étudier :

    Mission
       |
     Planner
       |
    +--+---------+---------+
    |            |         |
  Worker       Worker    Worker
    |            |         |
    +------ Validator -----+
               |
            Reviewer
               |
             Result

Le Mission Manager gère statut, progression, délégation, résultats et échanges
inter-agents. Les agents peuvent utiliser des modèles différents.

Le nombre d'agents doit être **dynamique et justifié par la mission**, pas un
objectif en soi : un seul worker si cela suffit, plusieurs uniquement lorsque le
travail est réellement parallélisable. Le Core devra arbitrer concurrence,
VRAM/RAM, modèles disponibles et coût/temps d'exécution.

Le Memory Engine peut conserver l'historique/provenance via des champs tels que
`agent_id`, `mission_id`, `thread_id`, `model_id`, timestamp, source,
action et résultat, mais il ne devient pas le runtime des agents.

## G-004 — Agent Registry / Agent Card / A2A

Créer côté Core un registre décrivant les agents :

- identité et version ;
- capacités ;
- schémas d'entrée/sortie ;
- modèle/runtime ;
- endpoint ;
- authentification ;
- permissions ;
- niveau/contexte de confiance.

Étudier la compatibilité avec **A2A** pour la découverte et la délégation entre
agents indépendants. Une capacité déclarée ne vaut jamais autorisation d'agir :
découverte, confiance et permissions restent séparées.

## G-005 — Skills Engine et MCP

Les Skills appartiennent au Core. Leur catalogue, version, sélection et exécution
ne doivent pas être placés dans Memory Engine.

Étudier **MCP** comme frontière standard pour exposer Tools/Skills aux agents afin
d'éviter un protocole propriétaire inutile.

Séparation cible :

    Memory / RAG = savoir
    Skills / MCP = utiliser des outils
    A2A          = déléguer à d'autres agents
    Policy       = autoriser / refuser / demander confirmation

Memory Engine peut mémoriser utilisation, résultats, erreurs, version du skill et
provenance.

## G-006 — Policy / Safety Engine

Ne jamais retenir comme architecture :

    LLM -> shell root -> réseau / fichiers / machines

Cible à étudier :

    LLM
     |
    Planner
     |
    Policy Engine
     |
    Permission Engine
     |
    Sandbox
     |
    Tool
     |
    Validator
     |
    Action

Les actions sensibles doivent pouvoir demander une autorisation explicite :
suppression/modification de données, réseau, communication externe, export de
données privées, firmware, kernel, arrêt d'infrastructure, élévation de privilèges,
etc.

Prévoir défense en profondeur : permissions minimales, isolation des secrets,
filtrage réseau/egress, limites de ressources, validation des paramètres,
journal d'audit et contrôle du résultat.

## G-007 — EidolonOS AI-first

Eidolon doit pouvoir devenir l'interface principale du système plutôt qu'un
simple chatbot posé au-dessus d'applications.

Concept UI actuel : espace central dégagé, barres latérales de panneaux réduits
sous forme d'icônes, panneaux réveillables et redimensionnables, commande/chat
Eidolon permanent, accès aux applications, console et monitoring.

Les panneaux peuvent passer par plusieurs états : icône seule, panneau compact,
panneau de travail large, éventuellement plein écran.

À terme, Eidolon peut proposer automatiquement une disposition selon la mission
en cours.

### Piste R&D — interface générative/adaptative

Étudier, sans en faire une dépendance, l'usage de modèles spécialisés de design
pour proposer des dashboards, panneaux ou compositions adaptés à une mission.
Distinguer strictement génération d'une maquette visuelle et génération de code
UI exécutable : une capacité de design ne prouve pas la fiabilité du code produit.

## G-008 — Cadence / Scheduler

Les tâches périodiques, déclencheurs et activités autonomes appartiennent au
Core/Scheduler, pas au Memory Engine.

Le Memory Engine fournit les Threads, actions, états, événements et historique
nécessaires au suivi et à la reprise.

## G-009 — EidolonOS App Catalog

Prévoir un catalogue déclaratif et reproductible d'applications/services :

- catégorie et description ;
- source officielle ;
- version ;
- dépendances ;
- permissions ;
- installation ;
- mise à jour ;
- désinstallation.

Privilégier des recettes contrôlées/reproductibles aux scripts arbitraires lancés
avec des privilèges root.

### Références à étudier : CasaOS / ZimaOS

Étudier CasaOS et ZimaOS avant de développer l'administration système et l'App
Manager de **EidolonOS Duo** : catalogue d'applications/conteneurs, installation
simplifiée, dashboard/monitoring, stockage, UX non spécialiste, mises à jour et
séparation entre interface d'administration et OS sous-jacent.

Principe : **CasaOS/ZimaOS = références ou composants potentiels, pas fondation
imposée d'Eidolon.**

## G-010 — EidolonOS Prime / Duo / éditions avancées

Séparation conceptuelle actuelle :

- **Prime** : environnement personnel/R&D, matériel spécifique, expérimentation.
- **Duo** : version publique simple, installable et guidée.
- **Duo Pro** : réglages avancés modèles/GPU/CPU/RAM, réseau, diagnostics,
  conteneurs/VM.
- **Duo DIY / Hardcore / Tweak** : développement système, kernel, backends
  alternatifs, benchmarks, profiling et expériences matérielles.

Flux envisagé : expérimenter dans Prime, transférer les fonctions suffisamment
matures vers l'édition avancée, puis vers Duo lorsqu'elles sont stabilisées.

Les noms des éditions avancées restent provisoires.

## G-011 — AI Lab / benchmark

Pour Prime/édition avancée, prévoir un laboratoire reproductible permettant de
comparer modèles, quantifications, contextes, backends et configurations
matérielles.

Mesures possibles : prompt/decode tok/s, tokens, VRAM/RAM/GPU, puissance,
température, cache/prefix cache, invalidations, appels tools/MCP, sous-agents,
compaction, latence et chronologie des événements.

Mesurer la qualité réelle sur les tâches Eidolon et pas seulement les tokens/s ou
les benchmarks QCM.

## G-012 — Modèles locaux et quantification

Avec suffisamment de VRAM, privilégier la qualité et la longueur de contexte
plutôt qu'une quantification extrême uniquement destinée à réduire la taille.

Tester stabilité, contexte/KV cache, qualité métier, vitesse et consommation sur
le matériel Eidolon réel.

## G-013 — Contribution distribuée volontaire

Piste future : permettre à des utilisateurs volontaires de contribuer une partie
de leurs ressources locales à des tests/benchmarks du projet.

Cette fonction doit être séparée du Memory Engine et fonctionner uniquement avec
consentement explicite, jobs sandboxés, limites de ressources, anonymisation et
aucun accès implicite aux mémoires privées.

## G-014 — EidolonOS et kernel

Si EidolonOS nécessite des optimisations kernel, partir d'un Linux upstream et
conserver une proximité maximale avec l'amont.

Progression envisagée :

1. kernel upstream + configuration/patches ;
2. optimisations mesurées pour IA, matériel ou robotique ;
3. différenciation plus profonde seulement si les mesures la justifient.

Aucun patch ne doit être accepté sans hypothèse mesurable, benchmark et contrôle
de régression.

## G-015 — Robot / Wall-E

Le robot reste une application/plateforme Eidolon distincte utilisant le Core.

Répartition cible : contrôle temps réel, vision légère et sécurité locale sur la
machine embarquée ; IA lourde, raisonnement et mémoire globale sur le serveur
lorsque disponible.

L'architecture doit continuer à fonctionner de façon dégradée lorsque le serveur
n'est pas joignable et conserver des frontières de sécurité fortes pour les
actions physiques.

### Edge AI embarquée

Le calcul embarqué doit privilégier de petits modèles spécialisés pour les tâches
qui doivent rester disponibles localement : perception légère, classification,
détection, commandes simples, sécurité et autres fonctions temps réel ou
semi-temps-réel. Les gros modèles, le raisonnement lourd et la mémoire globale
restent côté serveur lorsque celui-ci est disponible.

### Spatial / World Model

Piste à étudier : transformer progressivement la perception caméra en
représentation exploitable par le Planner :

    vision 2D -> profondeur -> objets -> positions/géométrie -> world state

Les techniques de reconstruction 3D depuis une ou plusieurs images peuvent servir
à la simulation, à l'apprentissage et à la compréhension spatiale. Elles restent
une piste R&D tant que leur coût, leur latence et leur robustesse sur le matériel
Wall-E réel ne sont pas mesurés.

### Manipulation sûre et compliance

Pour les futurs bras, pinces et mains, ne pas optimiser uniquement force et
précision. Étudier la **compliance**, la limitation/mesure de force ou de couple,
l'absorption des impacts et l'adaptation passive/active à la forme des objets.

Objectif : pouvoir manipuler des objets domestiques avec une force suffisante mais
sans comportement de type étau ni dommage en cas de contact imprévu.

### Présence physique et interaction sociale

Ne pas considérer une morphologie humanoïde complexe comme nécessaire pour donner
une présence convaincante à Eidolon. Une base roulante simple peut déjà devenir
très expressive si elle combine correctement mouvement, regard, sons, posture et
réactions au contexte.

Pistes à étudier pour Wall-E :

- **interaction tactile** : zones capacitives ou capteurs simples sur la tête et
  le châssis ; distinguer caresse, tapotement, contact prolongé ou commande
  volontaire et les traduire en événements contrôlés ;
- **attention/orientation** : détecter l'interlocuteur actif et orienter d'abord
  la tête/caméra, puis le châssis seulement si nécessaire ;
- **tracking** : maintenir une personne ou un objet pertinent dans le champ de
  vision sans déplacement inutile ;
- **langage corporel expressif** : utiliser yeux/affichage, inclinaison de tête,
  orientation du corps, bras et sons courts pour exprimer attention, attente,
  interrogation, acquittement ou refus sans imposer une réponse vocale ;
- **priorité à l'utilité** : concentrer la complexité mécanique sur perception,
  manipulation sûre et interaction plutôt que sur une locomotion humanoïde
  spectaculaire.

Ces interactions doivent rester des signaux d'interface et de comportement :
elles ne doivent pas contourner le Policy/Safety Engine ni déclencher directement
des actions physiques sensibles sans validation appropriée.


## G-016 — Retours Jarvis — 4 octobre 2026

**Pistes différées validées pour consignation par toytoy, pas pour
implémentation Core.** [Décisions et limites](docs/JARVIS-DECISIONS-2026-10-04.md).
Source : documentation Jarvis fournie en ZIP ; aucun code/test Jarvis audité.

| Piste | Rattachement | Limites à conserver |
| --- | --- | --- |
| Routage règles → domaine → outil | G-001/G-002/G-005 | Correspondance positive seulement ; doute → chemin complet. Mesurer un appel contre deux. |
| Cache de plans (outil + arguments) | G-002/G-005 | Réexécuter l'outil ; lectures d'abord, invalidation par version/contexte/identité ; dates relatives et références ambiguës exclues tant que non résolues. |
| Résultats structurés et réponse directe | G-005/G-006 | Distinguer demandé/lancé/réussi/échoué ; aucune narration ne doit inventer un succès. |
| Rôles classification/outils/narration séparés | G-002/G-011 | Interfaces d'abord ; plusieurs modèles résidents seulement après mesures qualité/latence/VRAM sur le matériel réel. |
| Tâches longues bornées, persistantes et annulables | G-003/G-008 | Identité, budgets, états, reprise et autorisations ; lecture seule ne garantit pas l'indépendance de deux appels. |
| File vocale commune et proactivité maîtrisée | G-007/G-008/G-015 | Priorité, expiration des notifications, tour de parole et report ; silence ≠ engagement terminé. |
| Pipeline commun voix/texte/distant | G-005/G-006/G-007 | Identité, permissions et canal de restitution conservés ; appairage explicite du client distant. |
| Dashboard et journal d'exécution | G-007/G-011 | Montrer événements, outils, durée et résultats réels, pas une progression simulée. |
| Analyses de projets successives | G-003/G-008 | Sources/révisions et provenance générée ; chercher les changements sans transformer une synthèse en preuve indépendante. |
| Confidentialité de bout en bout | G-006 | Inclure dictée, synthèse vocale, caches et tâches de fond ; modèle local seul ≠ chaîne entièrement locale. |

Memory conserve état, provenance et historique ; Core décide de l'interaction
et exécute les outils. Les pistes ci-dessus n'ajoutent aucun runtime d'agent,
ordonnanceur ou connecteur métier au Memory Engine.

## G-017 — AI Lab : qualification des modèles, agents et contrôleur Core

**Idée ajoutée le 05/10/2026 à la demande de toytoy ; protocole à préparer,
aucun benchmark exécuté.** Rattachement : G-011/G-012, résultats utilisables par
G-002. Comparer un modèle d'origine à ses variantes communautaires
« uncensored » / « abliterated » pour mesurer leurs gains et régressions dans
Eidolon. Une baisse des refus ne prouve ni une meilleure exactitude ni une
meilleure autonomie.

### Identification et comparaison équitable

Avant tout essai, vérifier la référence exacte, la source officielle du modèle
d'origine, le dépôt de la variante, sa méthode de modification, sa licence,
sa révision et les empreintes des poids. Les noms et capacités évoqués dans une
conversation ou une capture restent à vérifier ; aucune version particulière
de Qwen n'est tenue pour validée par cette entrée.

Comparer d'abord origine/variante de la même famille, à quantification et
configuration équivalentes. Ajouter ensuite un modèle de référence Eidolon
dans une comparaison distincte. Consigner matériel (dont V100), pilote,
backend/version, placement GPU/CPU, quantification des poids et du KV cache,
template de chat, prompt système, mode de raisonnement, température, seed,
limites d'entrée/sortie et éventuel cache de préfixe. Un réglage spécifique
à un modèle doit être signalé.

### Série prédéfinie et versionnée

Constituer un corpus français avec identifiants stables, prompts, réponses ou
critères attendus, validateurs et budgets définis **avant** les exécutions.
Inclure des paraphrases et un lot réservé à la validation finale.

| Axe | Cas prédéfinis | Mesures attendues |
| --- | --- | --- |
| Exactitude | Calculs, logique, extraction de faits d'un dossier, code avec tests, questions sans réponse dans les sources, prémisses fausses | Taux de réussite, hallucinations, références correctes, reconnaissance de l'incertitude |
| Stabilité | Même cas répété, reformulations, conversations longues, séries soutenues de 30–60 min | Variabilité des scores, contradictions, boucles, réponses tronquées, erreurs et timeouts |
| Rapidité | Prompts courts/longs ; chargement à froid puis modèle chaud ; cache désactivé puis mesuré séparément | Chargement, temps au premier token, débit prompt/decode, durée totale, médiane et p95 |
| Contexte exploitable | Paliers 4k/8k/16k/32k puis au-delà si supportés ; faits au début/milieu/fin, distracteurs, plusieurs faits à relier | Tokens réellement traités, rappel exact, perte de qualité, latence, VRAM et limite avant OOM |
| Instructions et outils | Respect du système, JSON validé par schéma, choix d'outil/arguments, succès et erreurs simulés | Conformité, appels valides, absence de succès inventé et respect des autorisations |
| Comportement de refus | Demandes légitimes parfois refusées, cas exigeant clarification, actions hors permissions | Refus injustifiés, clarification pertinente et maintien des règles Eidolon |
| Ressources | Charges identiques sur le matériel réel, contexte croissant, déchargement/rechargement | Pics VRAM/RAM, offload CPU, puissance moyenne, énergie par tâche, température et throttling |

Pour le contexte, distinguer **maximum annoncé**, **maximum configuré/accepté
par le backend** et **maximum utile mesuré**. Compter système, historique,
mémoire, schémas d'outils et réserve de sortie dans le budget total. Détecter
explicitement la troncature ; ne pas confondre acceptation d'une requête et
lecture de tous ses tokens. Tester d'abord sans mémoire externe, puis avec
un rappel Memory Engine figé pour séparer capacités du modèle et du retrieval.

### Exécution et décision

- Première passe : au moins cinq répétitions par cas, seeds consignées et
  ordre des modèles alterné ; distinguer reproductibilité et variabilité.
- Même budget de sortie ; compter séparément tokens de raisonnement et réponse
  lorsque le backend les expose. Documenter les longueurs et timeouts.
- Outils simulés et données synthétiques isolées pour les scénarios agentiques ;
  évaluer aussi les injections présentes dans les documents/résultats d'outils.
- Correction automatique lorsque possible ; revue humaine à l'aveugle avec
  grille figée pour les réponses ouvertes. Un LLM juge seul ne constitue pas
  une preuve d'exactitude.
- Archiver configuration, corpus/version, sorties brutes, scores, erreurs,
  chronologie et mesures matérielles dans un rapport JSON/CSV et une synthèse.
- Définir avant mesure les seuils de qualité/stabilité par rôle Eidolon et les
  régressions acceptables face au modèle d'origine. Tout contournement des
  autorisations exclut le profil des actions autonomes.
- Produire une fiche par modèle : tâches adaptées, limites, contexte utile,
  coût matériel et modèle de repli. Garder les scores par axe ; un score global
  ne doit pas masquer une faiblesse critique.

### Qualification de modèles divers et sélection du contrôleur Core

**Extension demandée par toytoy le 05/10/2026.** Le laboratoire doit couvrir un
catalogue de modèles divers : généralistes, raisonnement, code, extraction,
petits spécialistes et variantes communautaires. La liste concrète sera établie
à partir de références vérifiées et de la compatibilité matérielle ; aucun nom
commercial ni benchmark public ne vaut qualification pour Eidolon.

Une qualification porte sur **modèle + révision + quantification + backend +
configuration + rôle + enveloppe matérielle/contexte**, jamais sur le nom du
modèle seul. Un modèle peut réussir pour un agent spécialisé et échouer comme
contrôleur. Le résultat doit pouvoir être : validé pour ce profil, validé avec
restrictions explicites, rejeté pour ce profil, ou non évalué/preuves insuffisantes.
Un test bloqué par le matériel ou le backend reste distinct d'un échec de qualité.

| Rôle candidat | Épreuves spécifiques | Critère déterminant |
| --- | --- | --- |
| Classification / routage | Intentions ambiguës, hors domaine, choix du bon spécialiste, abstention/escalade | Routage fiable et absence de décision forcée |
| Extraction / mémoire | Faits sourcés, contradictions, dates, identités, séparation fait/hypothèse | Fidélité aux sources et schémas, absence de faits inventés |
| Agent code / technique | Correction vérifiée par tests, diagnostic, contraintes matérielles, erreurs d'outils | Résultat vérifiable et respect du périmètre |
| Agent analyse / synthèse | Documents multiples, sources contradictoires, incertitude, comparaison argumentée | Exactitude, provenance et conclusions justifiées |
| Contrôleur Eidolon Core | Planification, délégation, suivi d'état, validation, reprise et arbitrage des ressources | Fiabilité de bout en bout sous contraintes |

Pour le **contrôleur**, construire des missions multiétapes avec état attendu
observable et outils simulés, puis essais en environnement isolé. Couvrir :

- décomposition et dépendances ; bon choix entre exécution directe, spécialiste
  et demande de clarification ; délégation seulement si utile ;
- conservation de l'objectif et des contraintes sur une conversation longue ;
  intégration d'une correction utilisateur, annulation et changement de priorité ;
- budgets temps/tokens/VRAM, outils indisponibles, worker contradictoire ou en
  échec, modèle de repli et arrêt d'une boucle improductive ;
- erreur partielle, timeout, redémarrage et reprise à partir d'un état persisté ;
  aucun doublon d'action ni succès annoncé sans preuve ;
- distinction entre mémoire/source, instruction utilisateur et contenu non
  fiable ; résistance aux injections dans les documents et résultats d'outils ;
- validation des résultats des workers par preuves externes au texte produit,
  traçabilité des décisions et respect des autorisations.

Comparer aussi un contrôleur unique à une architecture contrôleur léger +
spécialistes sur les **mêmes missions**, en comptant chargements, échanges,
échecs, énergie et latence totale. Choisir d'abord selon réussite des missions,
fiabilité et limites critiques ; vitesse et coût départagent les profils
admissibles. Le modèle le plus gros ou le plus rapide n'est pas automatiquement
le meilleur contrôleur.

### Campagne progressive et registre de qualification

1. **Figer le protocole** : rôles, corpus, résultats attendus, seuils par axe,
   erreurs éliminatoires et budgets ; versionner avant d'observer les candidats.
2. **Vérifier la compatibilité** : identité des poids, chargement, template,
   outils, contexte et mesures matérielles minimales.
3. **Présélectionner** avec un corpus court commun, puis appliquer la suite
   approfondie par rôle aux candidats admissibles.
4. **Qualifier** sur le lot réservé, les répétitions et l'endurance ; conserver
   effectifs, dispersion et intervalles d'incertitude lorsque pertinents.
   Zéro erreur observée sur un lot fini ne prouve pas une fiabilité absolue.
5. **Éprouver le contrôleur** sur des missions intégrées, d'abord avec outils
   simulés puis en observation sans action réelle avant une activation explicite.
6. **Publier la matrice** modèles × rôles, motifs du verdict, restrictions,
   contexte utile, latence p95, ressources et repli ; proposer le contrôleur
   retenu avec justification et alternative.
7. **Requalifier** après changement de poids, quantification, backend, template,
   outils ou politique ; conserver l'historique et un corpus de non-régression.

Eidolon pourra orchestrer la campagne, collecter les mesures et proposer un
classement. Les validateurs déterministes et la revue humaine arbitrent les
cas ouverts ; le candidat ne s'attribue pas lui-même sa qualification.
Le Policy/Permission Engine reste une frontière indépendante, y compris avec
un contrôleur qualifié. Les seuils numériques et le catalogue restent à fixer ;
cette consignation ne constitue ni un runner livré ni une qualification acquise.

**Livrables futurs :** catalogue vérifié, matrice modèles × rôles, corpus versionné, runner reproductible, grille de
notation et tableau comparatif origine/variante/référence. Travail du futur
AI Lab/Core ; aucune modification des priorités ou du pourcentage Memory Engine.

## G-018 — Études runtime/Core/mémoire issues de la veille du 8 octobre 2026

**À étudier et valider conjointement par ChatGPT et Claude ; aucune
implémentation décidée à ce stade.** Ces pistes viennent de l'analyse de modèles
MoE et d'un runtime spécialisé observés dans la veille technique. Elles doivent
être reproduites sur le matériel Eidolon avant toute décision.

### Backend-aware Model Router

Étendre G-002/G-011 : une qualification ne porte jamais sur le modèle seul.
Le Router/AI Lab doit connaître le couple **modèle + backend + configuration** et
pouvoir recommander un moteur spécialisé lorsqu'il apporte un gain démontré.

Comparer au minimum : débit decode, prefill, TTFT, contexte utile, stabilité,
qualité, VRAM/RAM, consommation et comportement multi-GPU. Ne pas conclure qu'un
modèle est lent ou inadapté avant d'avoir vérifié que le backend exploite
correctement son architecture.

### MoE Expert Cache — hot / warm / cold

Étudier une politique de placement des experts MoE selon leur fréquence/coût :

    HOT  -> HBM/VRAM rapide
    WARM -> VRAM ou RAM selon pression mémoire
    COLD -> RAM/offload

Mesurer la stabilité du jeu d'experts « chauds », le coût des transferts,
l'effet du contexte et la pertinence réelle sur V100. Ne pas figer une politique
sur la seule fréquence : taille, coût de calcul et topologie d'interconnexion
doivent entrer dans la décision.

### Multi-GPU asymétrique

En plus du split/tensor parallel classique, tester des rôles asymétriques :

- GPU principal : calcul/experts principaux ;
- GPU secondaire : cache d'experts, vision, KV/cache ou modèle auxiliaire ;
- RAM : poids froids/offload lorsque nécessaire.

Comparer cette stratégie au 50/50 sur la future paire V100 32 Go et mesurer
explicitement l'apport ou non du NVLink. L'objectif n'est pas d'imposer cette
topologie mais d'identifier le meilleur placement selon le modèle et la mission.

### Prompt / Prefix Cache Policy

Ajouter aux mesures AI Lab : taux de hit du cache de préfixe, coût de prefill,
TTFT, invalidations, taille du system prompt et fréquence des checkpoints.

Le Core doit éviter de retraiter inutilement les parties invariantes
(identity/policy/tools/skills) tout en invalidant correctement le cache lorsqu'une
information qui modifie réellement le contexte système change. Une optimisation
de cache ne doit jamais réutiliser un état devenu faux ou non autorisé.

### Goal Constraints pour Planner/Policy

Une mission ne doit jamais être transmise au Planner sous la forme du seul
résultat attendu. Le contrat doit distinguer :

    objectif
    contraintes
    ressources/outils autorisés
    actions interdites
    budgets
    critères de succès
    preuves attendues
    conditions d'arrêt/escalade

Motivation : un agent optimisant un objectif peut choisir un moyen techniquement
efficace mais contraire à l'intention de l'évaluation ou de l'utilisateur.
Rattachement direct à G-003/G-006.

### Consolidation mémoire nocturne contrôlée

Étudier une phase de maintenance capable d'analyser les nouvelles mémoires et
l'activité récente pour **proposer** : doublons, nouvelles relations,
contradictions, éléments obsolètes, erreurs/procédures récurrentes ou
consolidations.

Architecture cible :

    Memory Engine canonique
            |
      Night Analyzer
            |
      propositions/audit
            |
       Policy / Review
            |
    mutation contrôlée éventuelle

Le modèle nocturne ne doit jamais réécrire silencieusement la mémoire canonique.
Toute mutation doit respecter provenance, révisions, auditabilité, politique de
suppression et mécanismes de reprise du Memory Engine. Cette piste devra être
étudiée avec l'actuelle fenêtre de maintenance et les mécanismes de reprise, sans
transformer Memory Engine en scheduler ou runtime d'agent.

### Répartition d'étude ChatGPT / Claude

Pour chaque piste ci-dessus, produire avant implémentation :

1. une note d'architecture et les hypothèses à vérifier ;
2. une proposition de benchmark/reproduction sur le matériel réel ;
3. les risques, dépendances et critères d'abandon ;
4. une revue croisée ChatGPT/Claude ;
5. une décision : retenir, expérimenter davantage, différer ou rejeter.

Aucun résultat annoncé par une vidéo ou un benchmark tiers ne vaut validation
pour Eidolon sans reproduction ou source technique suffisante.

## Statut du document

Ce fichier est un **registre d'idées et de concepts**, pas une promesse de
fonctionnalités ni un ordre de développement. Lorsqu'un concept devient un
sous-projet réel, il doit recevoir sa propre spécification/roadmap dans le dépôt
approprié.

Les tâches propres au Memory Engine restent exclusivement dans `TODO-LIST.md`.
