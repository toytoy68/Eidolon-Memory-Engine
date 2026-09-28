# Notes d'intégration Eidolon Core — idées et avertissements

Dernière mise à jour : 2026-09-28.

Ce document conserve des pistes issues de la veille technique et des discussions
d'architecture. **Ce ne sont pas des fonctionnalités promises ni des décisions
figées.** L'objectif est de ne pas perdre les idées utiles tout en protégeant le
périmètre du Memory Engine.

## Frontière fondamentale

- **Memory Engine sait ce qu'Eidolon sait** : informations, événements, relations,
  provenance, threads, historique et mémoire d'exécution utile.
- **Eidolon Core sait ce qu'Eidolon sait faire** : agents, skills, orchestration,
  outils, planification, politiques d'action et interactions avec le système.
- Le Memory Engine peut conserver la **mémoire d'un agent**, mais il ne doit pas
  héberger ni exécuter l'agent lui-même.
- Le Memory Engine peut mémoriser l'utilisation, les résultats, erreurs et versions
  d'un skill, mais le catalogue et le runtime des skills appartiennent au Core.
- Cette séparation doit permettre au Memory Engine de rester utilisable par un
  autre orchestrateur que Eidolon Core.

## Decision Engine / scoring spécialisé

Piste : utiliser côté Core un composant spécialisé dans les décisions courtes et
structurées plutôt qu'un LLM génératif pour chaque classification. Une seule passe
pourrait produire plusieurs scores, par exemple : pertinence de mémorisation,
classe mémoire, projet concerné, création/mise à jour d'un Thread, besoin de
validation ou archivage.

Le Memory Engine ne doit pas dépendre d'un modèle précis. Le futur contrat devrait
accepter des décisions structurées, leurs scores, la provenance du modèle et, si
nécessaire, les seuils/politiques utilisés.

## Agents, skills et orchestration

Piste d'architecture Core :

    Planner -> Workers -> Validator -> Reviewer

Les rôles peuvent utiliser des modèles différents ou plusieurs instances locales.
Les résultats intermédiaires intéressants peuvent être inscrits dans Memory Engine
avec provenance et liens vers le Thread concerné. Le Core reste responsable du
cycle de vie, des prompts, des outils et de l'exécution.

Un futur Skills Engine devrait séparer **connaissance** et **procédure** : connaître
un serveur dans Memory Engine n'implique pas savoir exécuter une maintenance. Les
procédures réutilisables et versionnées restent donc côté Core.

## AI-first et cadence

Une future interface EidolonOS peut utiliser Eidolon comme point d'entrée principal
et exposer applications, console, chat, vidéo, outils techniques et système comme
capacités. Le Memory Engine fournit contexte et historique ; il ne devient ni
bureau graphique ni gestionnaire d'applications.

Les tâches autonomes, déclencheurs et planifications périodiques appartiennent au
Core/Scheduler. Memory Engine peut fournir Threads, actions, états et événements
nécessaires au suivi et à la reprise.

## Policy / Safety Engine — avertissement important

Ne jamais concevoir le chemin d'exécution autonome comme :

    LLM -> shell root -> réseau / fichiers / machines

Cible à étudier côté Core :

    LLM -> Planner -> Policy Engine -> Permission Engine -> Sandbox
        -> Tool -> Validator -> Action

Les actions sensibles doivent pouvoir demander une autorisation explicite :
suppression/modification de données, modification réseau, communication externe,
export de données privées, flash firmware, changement kernel, arrêt
infrastructure, élévation de privilèges, etc.

La sandbox ne doit pas être considérée comme une garantie unique. Prévoir défense
en profondeur : permissions minimales, filtrage réseau/egress, isolation des
secrets, limites de ressources, journal d'audit, validation des paramètres et
contrôle du résultat. Memory Engine peut conserver les décisions d'autorisation,
preuves et événements nécessaires à l'audit.

## Modèles locaux et quantification

Piste de test pour l'infrastructure Eidolon : ne pas optimiser uniquement la taille
du modèle ou les tokens/s. Avec suffisamment de VRAM, préférer une quantification
qui conserve la qualité et réserver de la mémoire au contexte/KV cache. Les tests
doivent mesurer la qualité réelle sur les tâches Eidolon, la longueur de contexte,
la stabilité et le coût matériel, pas seulement les benchmarks QCM.

## Statut

Ces pistes doivent rester indépendantes des tâches de fiabilisation actuellement
prioritaires du Memory Engine. Elles seront converties en spécifications ou en
projets Core séparés uniquement après validation d'architecture.

## Référence à étudier : CasaOS / ZimaOS

Pour la future couche EidolonOS, en particulier **Duo**, étudier CasaOS et ZimaOS
avant de développer l'administration système et l'App Manager. L'objectif n'est
pas d'en faire une dépendance architecturale du Memory Engine ou du Core, mais
d'évaluer ce qui peut être réutilisé ou adapté au lieu d'être réinventé.

Points à examiner : modèle d'applications/conteneurs et catalogue, installation
simplifiée, dashboard et monitoring, gestion des services et du stockage, UX pour
un utilisateur non spécialiste, mécanismes de mise à jour et séparation entre
interface d'administration et OS sous-jacent.

Principe cible : **CasaOS/ZimaOS = références ou composants potentiels, pas
fondation imposée d'Eidolon**. Les besoins spécifiques à Eidolon (Core, Memory
Engine, agents, skills, Policy/Safety Engine, GPU/IA et robotique) doivent rester
modulaires et indépendants.
