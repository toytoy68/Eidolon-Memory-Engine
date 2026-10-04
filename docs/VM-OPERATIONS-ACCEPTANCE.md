# Recette d'exploitation à préparer — 4 octobre 2026

Cette recette complète les tests de code ; elle n'a pas été exécutée par GPT.
Base et empreintes doivent être enregistrées avant chaque essai. Les dossiers
actifs `/opt/eidolon-memory-engine` et les corpus privés ne sont pas des cibles
pour les étapes synthétiques. Aucun reboot ou restart actif n'est demandé à
Claude dans ses missions actuelles.

## 1. Contrôle sans changement

Relever hostname, Python, commit du clone, état Git, système de fichiers du
répertoire temporaire, état enabled/active et MainPID du dashboard. Ne pas
imprimer l'environnement, les jetons ou les fichiers de conversation.

Le commit du checkout seul ne prouve pas le code chargé par le processus.
Conserver la date de lancement et la dernière relance connue. Vérifier les
commandes sudo exactes sans pager prévues dans MONITORING ; les variantes ne
sont pas automatiquement autorisées par la règle sudo installée.

## 2. Restauration synthétique hors service

Dans un clone isolé du commit candidat, créer un corpus factice comprenant :

- un original TXT et son extraction figée ;
- une Information acceptée avec référence de source et son Event ;
- une opération reprise puis rejouée ;
- au moins un reçu compacté et une Information supprimée avec reçu conservé.

Utiliser les commandes canoniques existantes et les fixtures de recette, pas
une édition manuelle des journaux. Arrêter tout écrivain de ce corpus avant
copie. Faire un manifeste chemin/empreinte, conserver les octets des originaux,
extraire l'archive dans un autre dossier neuf et comparer tous les fichiers.
Ne pas inclure l'environnement d'authentification du service dans cette archive.

Exécuter ensuite sur cette copie arrêtée :

```bash
.venv/bin/python -m tools.vm_acceptance \
  --source /CHEMIN/COPIE-SYNTHETIQUE-ARRETEE \
  --workdir /CHEMIN/RAPPORT-NEUF-SEPARE
```

Critères : manifeste identique immédiatement après restauration, aucune issue
aux audits, readiness vraie, référence exacte et résultat de rejeu identique,
aucune résurrection de l'Information supprimée. La recette peut créer des
artefacts de travail dans workdir : comparer la source avant/après et ne pas
confondre son état avec celui de la copie dérivée par les exercices.

### Sous-recette synthétique exécutable

`tools.check_source_restore` réalise un contrôle plus étroit sans accepter de
racine utilisateur : original TXT, extraction figée, détail conservé, détail
supprimé, reçus compactés, archive TAR et restauration dans un dossier neuf.
Il vérifie manifeste complet, original/extraction, référence exacte, audits et
rejeu des deux commandes sans écriture ni résurrection. Les corpus et l'archive
sont jetables ; seul le rapport statistique est conservé.

```bash
.venv/bin/python -m tools.check_source_restore \
  --output /tmp/source-restore-new-report.json
```

Exécuté ici : PASS, 14 fichiers ; [rapport](benchmarks/source-restore-2026-10-04.json).
Quatre tests passent, dont trois archives volontairement incomplètes (extraction,
original ou reçus manquants), rejetées avant le rejeu. Cela ne valide pas encore
l'opération reprise interrompue, une restauration privée, le sandbox systemd
ou le reboot. Cette sous-recette complète les étapes ci-dessus, sans les remplacer.

Une restauration réelle de sauvegarde utilisateur reste une étape distincte :
utiliser une copie arrêtée, privée, sans publier son contenu ni son manifeste
détaillé ; seuls comptes et empreinte globale dans le compte rendu.

## 3. Upload sous cloisonnement systemd

Le test HTTP synthétique existant vérifie le handler, pas le sandbox systemd.
Pour éprouver le cloisonnement, préparer une **unité temporaire distincte**
avec les mêmes protections que deployment/dashboard/eidolon-dashboard.service :
User/Group toytoy, UMask, NoNewPrivileges, PrivateTmp, ProtectSystem,
ProtectHome, ProtectKernelTunables et ProtectControlGroups.

Différences nécessaires et explicites : nom d'unité, WorkingDirectory/code du
clone, racine synthétique, écoute 127.0.0.1 sur port libre différent de 8765/8766,
EnvironmentFile à jeton factice, journal temporaire. Pas d'IA locale. Vérifier
l'unité avec systemd-analyze avant démarrage. Consigner ces différences : elles
limitent la preuve à la configuration testée.

Avec PrivateTmp, un clone/corpus simplement créé dans /tmp ou /var/tmp de
l'hôte peut être invisible dans l'unité. Préparer un chemin jetable accessible
hors de ces répertoires et hors de /home, par exemple sous
/opt/eidolon-validation-IDENTIFIANT ; ne pas assouplir les protections pour
contourner un mauvais placement. Ce montage nécessite un accès administrateur
et ne doit pas installer l'unité permanente ni relancer son installateur.

Par HTTP sur cette instance :

1. GET /sources sans authentification : 401.
2. GET authentifié : 200 et formulaire CSRF ; le jeton reste hors argv/logs.
3. POST d'un TXT synthétique de deux lignes : 200, original byte-identique,
   metadata valides, aucune Information créée automatiquement.
4. POST d'extraction explicite : 200, texte/paragraphes attendus.
5. Nouvelle lecture et nouvel upload du même original : lecture sans écriture,
   original conservé ; pas de duplication du bundle.
6. POST avec CSRF invalide et POST non authentifié : refus, empreintes inchangées.

Critères : permissions source compatibles avec l'utilisateur du service,
provenance exacte, audits/readiness valides, absence de secret dans argv,
contenu synthétique seulement. Contrôler aussi arrêt/reprise de **cette unité
jetable** ; service actif dashboard, MCP, Cloudflare et Ollama inchangés.
Conserver un journal statistique sans corps privés ; arrêter/retirer uniquement
les ressources jetables identifiées à la fin de l'essai.

## 4. Reboot VM — étape différée

Enabled et reprise après SIGKILL ne prouvent pas le démarrage après reboot.
Cette étape interrompt tous les services : elle reste hors des missions isolées
actuelles. La prévoir lors d'une fenêtre choisie par toytoy, après contrôle de
sauvegarde et accès de secours à la VM.

Avant : date, enabled/active, ports, commit disque et PID/date du dashboard,
état MCP/Cloudflare. Après : nouveau boot-id, service démarré automatiquement,
bon utilisateur/arguments sans afficher les secrets, ports attendus, HTTP 401
sans auth/200 avec, nouvelle date de mesure dashboard, accès au canal et audits
readiness. Ne pas lancer une migration ou une IA pour déclarer le boot réussi.

## Compte rendu attendu

| Contrôle | État initial | État final | Preuve | Limite |
| --- | --- | --- | --- | --- |
| Restauration synthétique | À exécuter | À renseigner | Empreintes/audits | Pas une restauration du corpus privé |
| Upload cloisonné | À exécuter | À renseigner | HTTP/statistiques/audits | Unité jetable, différences consignées |
| Reboot réel | Différé | À renseigner | Boot-id/service/HTTP | Interruption globale à planifier |

Un contrôle impossible reste NON TESTÉ, avec sa cause. Aucun PASS déduit d'un
autre contrôle ou d'un nombre global de tests.
