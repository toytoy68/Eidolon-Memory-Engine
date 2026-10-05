# Eidolon Presentation Standard v1

Référence commune établie le 05/10/2026 à la demande de toytoy, à partir des
fichiers `01-system.sh`, `02-nvidia.sh` et `03-docker.sh` du Bootstrap
(`main` au commit `9cc70cc`). Elle couvre les en-têtes source et la présentation
console des installations, diagnostics et commandes interactives Eidolon.

Ce document est autonome et peut être copié dans chaque dépôt Eidolon sous
`standards/EIDOLON-PRESENTATION-v1.md`. C'est la référence à fournir aux agents,
quel que soit leur fournisseur. Les fichiers voisins cités dans ce dépôt sont
des compléments ; les modèles essentiels sont également inclus ci-dessous.

## Consigne à transmettre à un agent

> Avant toute création ou modification d'un en-tête source, d'un affichage CLI
> humain ou d'un parcours d'installation Eidolon, lis et applique
> `standards/EIDOLON-PRESENTATION-v1.md`. Réutilise la présentation commune du
> composant, préserve le JSON et les codes de retour, et ne déduis jamais une
> réussite d'un simple message affiché. N'harmonise pas d'autres dépôts ou
> installateurs sans que le travail demandé porte sur eux. Si le standard est
> absent, signale-le plutôt que d'inventer une identité graphique différente.

Ajouter cette consigne au `AGENTS.md` existant sans remplacer ses autres règles.
Si l'outil ne consulte pas ce fichier, fournir la consigne et ce document dans
ses instructions de projet. Un document publié dans un dépôt n'est pas
automatiquement connu des agents travaillant dans un autre.

## Identité commune

| Champ | Valeur |
| --- | --- |
| Organisation | Eidolon Core Technologies |
| Sigle | ECT |
| Devise | Local AI • Modular • Reliable • Reproducible |
| Produit | Eidolon Bootstrap Framework / Eidolon Core / Eidolon Memory Engine |
| Standard de présentation | Eidolon Presentation Standard v1 |

Ces noms reprennent les constantes existantes. Ne pas les remplacer par
« Eidolon Corporation ». Le nom d'affichage n'affirme aucun statut juridique.
La version du produit et celle du standard sont distinctes.

## Conventions déjà présentes et écarts constatés

- En-tête source encadré de commentaires `=`, métadonnées alignées ; groupes
  de code introduits par des commentaires `-` et titres explicites.
- Bannière console de 57 caractères, cadre `#`, nom du produit et du composant.
- Sections entourées de lignes `=` de 57 caractères.
- Messages `[INFO]`, `[OK]`, `[ATTENTION]`, `[ERREUR]`, texte français.
- Présentation des opérations prévues, contexte de la machine, bilan et suite.
- Aucun code couleur ANSI dans ces trois scripts. Le standard v1 reste lisible
  en monochrome, dans un terminal ou dans un journal redirigé.

Les constantes ECT/devise existent dans 01-system et 03-docker, mais ne sont
pas affichées dans leur bannière. 02-nvidia emploie le même cadre mais ne déclare
pas ces constantes. 03-docker encapsule son accueil dans `header()`, tandis
que 01 et 02 l'affichent au niveau principal. Il existe donc un style commun,
pas encore une implémentation partagée intégralement conforme.

## En-tête des fichiers source

Pour les nouveaux fichiers : Projet, Organisation, Fichier, Description,
Standard. Un shebang éventuel reste à la première ligne. Conserver les mentions
de licence existantes. Version/Statut peuvent compléter l'en-tête des installateurs ;
ne pas dupliquer la version Python du paquet dans chacun de ses modules.

Les modèles [`templates/source-header.py.txt`](../templates/source-header.py.txt)
et [`templates/source-header.sh.txt`](../templates/source-header.sh.txt) sont
des fragments, **pas des installateurs exécutables**. Remplacer leurs champs
avant usage. Pas d'obligation de multiplier les séparateurs dans les petits
modules ; leurs responsabilités et fonctions doivent rester faciles à lire.

Modèle Python autonome :

```python
# ==========================================================
# Projet      : <Eidolon Core / Eidolon Memory Engine>
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : <nom_du_module.py>
# Description : <responsabilité du module>
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""<Contrat du module et limites utiles.>"""
```

Modèle Bash autonome :

```bash
#!/usr/bin/env bash

# ==========================================================
# Projet      : <Eidolon Bootstrap Framework / composant>
# Organisation: Eidolon Core Technologies (ECT)
# Script      : <nom_du_script.sh>
# Version     : <version du composant>
# Description : <opérations réellement effectuées>
# Statut      : <statut réel>
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

readonly COMPANY_NAME="Eidolon Core Technologies"
readonly COMPANY_SHORT="ECT"
readonly COMPANY_MOTTO="Local AI • Modular • Reliable • Reproducible"
```

Ces métadonnées documentent le fichier ; elles ne remplacent pas ses imports,
sa gestion d'erreurs, ses validations ni les règles d'exécution du composant.

## Accueil d'une installation

Ordre commun :

1. Cadre contenant produit et composant ; identité ECT et devise juste dessous.
2. Version du composant, statut réel et mode (installation, simulation, diagnostic).
3. « Ce script va : » et liste des effets réellement prévus.
4. Contexte utile : machine, utilisateur cible, date, destination. Ne jamais
   afficher secret, token ou variable d'environnement complète.
5. Vérifications puis confirmation si le parcours d'installation la requiert.
6. Sections d'exécution, vérifications des résultats, résumé et prochaine étape.

N'afficher que les champs pertinents : un aperçu de style n'invente ni machine
cible ni destination d'installation. Le nom du produit reste propre au composant,
l'identité et les conventions sont communes. Les intitulés statiques du cadre
doivent tenir dans sa largeur ; les chemins et résultats longs restent hors cadre.

## Messages et signification

| Préfixe | Signification |
| --- | --- |
| `[INFO]` | Information, opération prévue/en cours, résultat non encore vérifié |
| `[OK]` | Vérification effectivement réussie, avec un périmètre explicite |
| `[ATTENTION]` | Réserve, blocage, revue requise, effet inconnu ou annulation |
| `[ERREUR]` | Échec constaté avec diagnostic |

La couche d'affichage n'exécute pas de commande, ne décide pas des permissions,
ne transforme pas un résultat non vérifié en succès, et n'appelle pas `exit`.
La logique métier choisit l'arrêt et le code de retour. Un installateur ne doit
pas annoncer « tout installé » parce que l'affichage du bilan s'est terminé.

Ne pas effacer l'écran par défaut : conserver l'historique de diagnostic. Une
éventuelle option interactive `clear` devra être explicite. Les données externes
doivent être rendues comme du texte ; neutraliser les caractères de contrôle.

## Sortie humaine et sortie machine

Les bannières concernent le mode humain. Une sortie JSON ne contient ni
bannière, ni progression décorative, ni séquence ANSI. Conserver les codes de
retour et la sémantique des champs. Les diagnostics applicatifs vont sur stderr.
L'option explicite Core est `--format human` ; JSON reste le défaut compatible.
Les confirmations/permissions restent indépendantes du choix d'affichage.

## Adoption et séparation des composants

| Composant | État au 05/10 après ce lot |
| --- | --- |
| Eidolon Core | En-têtes des modules normalisés ; rendu humain mutualisé dans `eidolon_core.presentation`, aperçu et CLI intégrés |
| Bootstrap 01/02/03 | Référence historique lue, scripts inchangés et non exécutés ; harmonisation de leurs fonctions à traiter dans un lot Bootstrap |
| Memory Engine | Adoption future à coordonner avec sa session ; aucun fichier modifié ici |
| Futurs installateurs Eidolon | Appliquer ce standard dès leur création |

Le standard est commun ; son code Python n'est pas une dépendance obligatoire
des installateurs Bash. Une future bibliothèque d'affichage Bash devra rester
pure et être testable sans `source` d'un installateur à effets. Pas de réécriture
automatique de tous les dépôts ni de nouvel installateur système dans ce lot.

## Aperçu reproductible

Depuis `eidolon-core/` :

```sh
PYTHONPATH=src python -m eidolon_core --format human presentation-preview
PYTHONPATH=src python -m eidolon_core --format human --state /tmp/eidolon-core-demo demo
```

La première commande ne crée ni mission ni dossier d'état et n'installe rien.
La seconde exécute la démonstration synthétique existante et affiche ses résultats
avec le style commun. Le standard doit être revu lors d'un changement volontaire
d'identité ou de format, pas modifié implicitement par chaque composant.

## Vérification avant livraison

- Identité/devise exactes, produit et version réels ; bannière et sections communes.
- En-tête conforme pour les nouveaux fichiers concernés.
- Aucun succès fictif, aucune modification des permissions ou codes de retour.
- Sortie machine propre, diagnostics séparés, caractères de contrôle neutralisés.
- Exécution d'un aperçu ou d'une commande sans effet pour examiner le rendu.
- Adoption des autres dépôts annoncée comme différée tant qu'elle n'a pas été faite.

Une copie locale du standard doit garder son numéro de version. Toute évolution
commune doit être explicite et répercutée dans les copies ; ce document ne met
pas en place de synchronisation automatique entre dépôts.
