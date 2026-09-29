# Eidolon Global — concepts, idées et architecture future

Dernière mise à jour : 2026-09-29.

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

## Statut du document

Ce fichier est un **registre d'idées et de concepts**, pas une promesse de
fonctionnalités ni un ordre de développement. Lorsqu'un concept devient un
sous-projet réel, il doit recevoir sa propre spécification/roadmap dans le dépôt
approprié.

Les tâches propres au Memory Engine restent exclusivement dans `TODO-LIST.md`.
