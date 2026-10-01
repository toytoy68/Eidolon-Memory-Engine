# Dossiers Markdown de projet v1 — T-044

`core.dossiers.projects.ProjectDossiers` construit un fichier
`memory/dossiers/<thread_id>.md` depuis un Thread existant et les Informations
qu'il référence explicitement par CONCERNS. La vue contient objectif,
récapitulatif sourcé, décisions déclarées, questions, actions, mots-clés,
contenu, contexte, provenance et dates. Chaque source porte identité et révision.
Aucun résumé interprétatif par LLM ni rapprochement par mots-clés n'est utilisé.

## Utilisation explicite

```sh
python -B -m core.dossiers.cli --root /chemin/reel resolve info-1
python -B -m core.dossiers.cli --root /chemin/reel rebuild thread-cooling
python -B -m core.dossiers.cli --root /chemin/reel status thread-cooling
```

La création d'un dossier est automatique **à l'appel de rebuild pour un Thread
existant** ; elle ne crée pas de Thread ni de liaison. Utiliser auparavant le
service de création liée pour un nouveau projet. Zéro liaison donne UNASSIGNED,
plusieurs liaisons donnent REVIEW. `resolve --selected-thread …` exige une
liaison existante et résout explicitement le choix ; il n'en invente aucune.
Les dossiers de lieu et de thème ne sont pas couverts par cette première vue.

## Texte humain et texte calculé

Le bloc entre les marqueurs MEMORY-ENGINE GENERATED est reconstructible.
Tout texte avant/après est préservé exactement lors d'une mise à jour, notamment
la section « Notes humaines (non ingérées) ». Ces notes ne deviennent pas
implicitement des Informations validées. Pour une décision canonique, passer
par le service Information et la lier au Thread. Sauvegarder le fichier dossier
si ses notes humaines doivent être conservées : cette partie n'est pas
reconstructible à partir des seules Informations.

Ne pas modifier les marqueurs. Une structure endommagée bloque la régénération
sans écraser les notes. Modifier le bloc généré le rend périmé et ces modifications
seront remplacées lors du prochain rebuild ; éditer les sources pour les pérenniser.

## Fraîcheur, reprise et suppression

Le résumé est déterministe et embarque un digest des fichiers sources, en plus
des références/révisions affichées. `status` compare aussi le bloc généré attendu :
CURRENT, STALE ou MISSING. `status` et `resolve` n'écrivent aucun fichier ; faire
les audits sur copie arrêtée pour une lecture stable. Les erreurs de source
invalide sont bloquantes, pas une permission de recopier l'ancienne vue.

`rebuild` tient Persistent → Thread → Dossiers et publie le Markdown atomiquement.
Une opération Information/Thread en attente bloque la projection. Deux appels
identiques laissent les octets inchangés. Les éditeurs externes ne partageant pas
ces verrous doivent être fermés pendant rebuild ; la préservation des notes
n'est pas une fusion concurrente d'éditeurs arbitraires.

Quand le Thread source a disparu, un rebuild du dossier existant retire son
ancien bloc calculé et affiche l'absence de source, tout en conservant les notes.
Une Information liée absente est signalée sans recopier son ancien contenu.
**Aucune invalidation automatique ni purge globale n'est encore raccordée aux
écritures/suppressions.** Un dossier non reconstruit peut donc garder une ancienne
copie : ne pas le consommer sans contrôle de fraîcheur et ne pas compter la
suppression canonique comme effacement des dossiers/notes/sauvegardes.
Le raccordement automatique, le traitement des vues après suppression et les
vues de lieu/thème restent la partie ouverte de T-044 ; l'ordonnancement relève
ensuite de T-046.

## Preuves

Huit tests dans `tests/test_project_dossiers.py` : sources/actions, rejeu
identique, correction propagée et notes intactes, ambiguïté, disparition du
Thread, marqueurs endommagés, opération incomplète, contenu contenant un marqueur
et CLI en lecture seule (les scénarios sont regroupés dans certains tests).
Supprimer la préservation des notes fait échouer le test de mise à jour.
Aucune validation VM ni édition concurrente par outil externe.
