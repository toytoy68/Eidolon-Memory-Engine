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
python -B -m core.dossiers.cli --root /chemin/reel reconcile
python -B -m core.dossiers.cli --root /chemin/reel reconcile --apply
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
Le parcours qualifié T-043 actualise son dossier. Pour les autres commandes,
le rapprochement global décrit ci-dessous répare le retard à la demande.
Un dossier non reconstruit peut garder une ancienne copie : ne pas le consommer
sans contrôle de fraîcheur et ne pas compter la suppression canonique comme
effacement des dossiers/notes/sauvegardes. Aucun ordonnanceur n'est installé.

## Rapprochement global — T-044, tranche du 01/10 au soir

`DossierReconciler(dossiers).inspect()` et le CLI `reconcile` ne créent ni
répertoire, ni verrou, ni fichier. Ils contrôlent la readiness et examinent
l'union des Threads présents et des dossiers `.md` présents dans la sortie
configurée. Cela retrouve aussi les vues dont le Thread a été supprimé.
Le rapport contient les IDs/révisions et SHA-256 de chaque dépendance, les
absences explicites et le digest de source. Ce manifeste est recalculé ; aucune
copie de contenu ni cache persistant ne devient une autorité supplémentaire.
Une modification directe sans augmentation de révision est donc détectée.

| État d'une vue | Sens |
| --- | --- |
| MISSING | Thread présent, dossier à créer |
| STALE | Bloc généré différent de celui attendu depuis les sources courantes |
| ORPHANED | Thread absent, ancien bloc généré à remplacer par l'avis d'absence |
| CURRENT | Bloc généré conforme, y compris l'avis d'un Thread déjà retiré |
| UNMANAGED | Markdown sans marqueur et sans Thread homonyme ; ignoré |
| BLOCKED | Source illisible, marqueurs endommagés ou collision avec un fichier humain |

Le bilan vaut CLEAN, DRIFT ou BLOCKED. Une readiness bloquante interrompt
l'examen avant toute réparation. Un fichier humain homonyme d'un projet n'est
jamais adopté implicitement. Une vue gérée utilise les deux marqueurs réservés ;
un seul marqueur n'est pas interprété comme une simple note. Les autres sorties
configurées, sous-répertoires et copies externes ne sont pas parcourus.

`apply()` / `reconcile --apply` reprend un scan complet sous verrous
Persistent → Thread (si présent) → Dossiers. Les blocages découverts sont
rapportés avant toute publication de vue. Chaque dossier à réparer est écrit
atomiquement ; les autres restent inchangés. Les zones humaines avant/après le
bloc conservent leurs caractères et leurs fins de ligne, y compris CRLF.
L'application **ne réutilise pas un ancien rapport** : une source modifiée après
l'inspection est relue. Après publication, un nouveau contrôle confirme CLEAN ;
le résultat vaut RECONCILED si des vues ont changé. Le CLI retourne 1 pour DRIFT
ou BLOCKED, 0 pour CLEAN/RECONCILED.

Une interruption peut laisser une partie des dossiers actualisés. Relancer la
même commande suffit : les vues restantes sont retrouvées par comparaison des
fichiers, sans rejouer les commandes canoniques, leurs Events ni leurs reçus.
Le lot entier n'est pas une transaction atomique. Une erreur de publication
ne transforme pas les réparations précédentes en échec canonique.

Après UNLINK/suppression d'Information ou suppression de Thread, les anciens
extraits **de la zone générée** disparaissent lors du rapprochement réussi.
Les notes humaines ne sont ni effacées ni automatiquement ingérées. CLEAN ne
certifie donc pas une purge globale de l'information : notes, autres sorties,
sauvegardes et copies échappent à cette portée. La clôture globale de purge,
l'édition humaine coopérative et les vues lieu/thème restent ouvertes.

Les écrivains legacy et les éditeurs externes doivent rester arrêtés. Le scan
sans écriture est ponctuel ; seule l'application tient les verrous coopératifs.
Les scans complets, répétés par les projections, peuvent être coûteux et garder
les verrous longtemps : optimisation T-049 avant ingestion intensive. Aucun
service automatique, minuterie ou ordonnanceur T-046 ajouté.

## Preuves

Huit tests dans `tests/test_project_dossiers.py` : sources/actions, rejeu
identique, correction propagée et notes intactes, ambiguïté, disparition du
Thread, marqueurs endommagés, opération incomplète, contenu contenant un marqueur
et CLI en lecture seule (les scénarios sont regroupés dans certains tests).
Supprimer la préservation des notes fait échouer le test de mise à jour.
Aucune validation VM ni édition concurrente par outil externe.

17 cas supplémentaires dans `tests/test_dossier_reconciliation.py` : manifeste
sans écriture, deux projets dépendants, correction et CRLF conservés, liens,
suppression, édition directe sans révision, frontière endommagée, fichier humain,
reprise canonique préalable, deux interruptions par exception, arrêt réel de
processus, CLI, lien symbolique, objectif/action, journal inconnu et deux
réparateurs concurrents sans Manager. Groupe ciblé : 69 réussis.
Retirer temporairement le rafraîchissement, la préservation des notes ou la
barrière readiness provoque respectivement 1 + 1 + 1 échec d'assertion ; code
restauré. Aucun résultat VM, corpus réel ou coupure électrique.
Suite complète du lot : **859 réussis, 5 échecs de sockets Manager**, 50,08 s,
Python 3.12.14/pytest 9.1.1, aucun désélectionné. Les cinq scénarios bloqués
avant leur logique métier restent à valider sur la VM.
