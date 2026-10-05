# Présentation des installateurs Memory Engine

Les installateurs du dashboard et de Collaboration appliquent
[Eidolon Presentation Standard v1](../standards/EIDOLON-PRESENTATION-v1.md).
Ils partagent `deployment/presentation.sh` : identité ECT, devise, cadre,
sections, messages français et bilan. Les erreurs vont sur stderr ; les codes
de retour et les opérations d'installation restent ceux des composants.

## Examiner le style sans installer

Depuis le dépôt, sans sudo :

```sh
bash deployment/dashboard/install-dashboard-service.sh --presentation-preview
bash deployment/collaboration/install-vm.sh --presentation-preview
```

Ces modes s'arrêtent avant les contrôles système, écritures, authentification
ou appels réseau. Ils ne vérifient pas la machine et n'annoncent aucun succès
d'installation. Le helper Bash est sans effets à son chargement, sans effacement
d'écran et sans couleurs ANSI. Les caractères de contrôle des messages sont
neutralisés.

Le paquet généré par `tools.prepare_collaboration_deployment` inclut le helper
et son empreinte ; son aperçu fonctionne indépendamment du checkout source.
Un installateur copié seul doit conserver son helper voisin ; utiliser le
paquet pour Collaboration et le checkout complet pour le dashboard.

## Portée

Cette adoption concerne les deux installateurs et leurs en-têtes. Les outils
JSON, les formats mémoire, les pages du dashboard et les anciens modules
Python ne sont pas remaniés. Le standard copié depuis Core est conservé à
l'identique ; sa table d'adoption décrit son lot d'origine. Ce document décrit
l'adoption effective propre à Memory Engine.

L'installateur du dashboard reste une migration prévue pour la VM de toytoy,
avec son adresse, utilisateur et chemins actuels. Cette harmonisation ne le
transforme pas en installateur universel et ne doit pas être relancée sur une
unité déjà installée. Aucun déploiement VM n'est réalisé par ce lot.

## Validation

Les tests exécutent les aperçus avec des commandes système piégées, vérifient
l'autonomie du paquet et la neutralisation des caractères de contrôle. Les
tests existants vérifient toujours le rollback, l'absence de token dans argv,
les contrôles HTTP et les empreintes des paquets. L'installation réelle reste
à vérifier sur une cible autorisée.
