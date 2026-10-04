# Mesures pour le futur tableau de bord

La commande suivante mesure **la machine qui l'exécute** et le volume où se
trouve l'arborescence de données :

```sh
python -m core.monitoring.metrics --root /chemin/vers/eidolon-memory-engine
```

Elle renvoie en JSON l'hôte, l'heure UTC, le chemin mesuré, la RAM de l'hôte
(`MemTotal` et `MemAvailable` sous Linux), l'espace total/utilisé/libre du
volume et le nombre/la taille logique des fichiers sous `memory/`. La RAM
`used` est `MemTotal - MemAvailable` : ce n'est pas la consommation du seul
processus Memory Engine. La taille du moteur ne compte qu'une fois les liens
physiques et ignore les liens symboliques ; elle peut différer de l'espace
réellement alloué sur disque (compression, blocs, instantanés). L'index Qdrant
externe n'est pas inclus. Le scan récursif peut prendre du temps sur un grand
ensemble de fichiers : une interface devra rafraîchir les mesures à intervalle
raisonnable et signaler toute erreur de lecture.

Cette commande n'ouvre pas le contenu des mémoires et n'écrit rien. Elle ne
constitue pas encore une API réseau ni une interface graphique. Sur un bureau
distinct de la VM, l'exécuter localement mesurerait **le bureau** ; pour afficher
le serveur il faudra plus tard un adaptateur distant authentifié.

Pour les statuts du moteur, la commande suivante lit les Threads core 0.2 et
les opérations de changement de statut dans leurs journaux isolés :

```sh
python -m core.monitoring.overview --root /chemin/vers/eidolon-memory-engine
```

Elle compte les Threads par statut et les opérations `PREPARED`/`APPLYING` en
attente. Les documents core 0.1, inconnus ou malformés sont signalés par leur
chemin dans `needs_review`, sans afficher leur contenu. Ce n'est ni une lecture
transactionnelle de plusieurs fichiers ni un indicateur des anciens journaux
CLI. Un relevé pendant une écriture peut être provisoire : le tableau de bord
devra afficher l'heure et rafraîchir après reprise.

## Première page HTML

Le serveur intégré fournit une page de synthèse en lecture seule à la racine
`/`. Il exige un mot de passe transmis par variable d'environnement, puis une
authentification HTTP Basic (identifiant `eidolon`). Exemple local :

```sh
export EIDOLON_DASHBOARD_TOKEN='un-secret-long-et-aleatoire'
.venv/bin/python -m core.monitoring.dashboard --root /opt/eidolon-memory-engine
```

Ouvrir `http://127.0.0.1:8766/` sur la machine serveur. Sur la VM 110 indiquée
à l'adresse locale `192.168.1.110`, après validation, lancer avec
`--host 192.168.1.110` puis ouvrir `http://192.168.1.110:8766/` depuis le PC
principal, si le pare-feu l'autorise. **HTTP Basic sur HTTP ne
chiffre pas le mot de passe** ; pour un accès régulier au-delà d'un réseau local
de confiance, placer un proxy HTTPS authentifié devant le service. Ne pas
publier le port sur Internet. La valeur du secret ne doit pas être committée.

La page de synthèse est rafraîchie toutes les 30 secondes. Le lien « Parcourir
les fichiers Markdown » donne une liste paginée de `working`, `information`,
`threads`, `events`, `thread-events` et `reviews`. Un document est affiché en
texte échappé, sans exécuter son HTML et sans possibilité de modification.
Seuls les noms de fichiers `.md` simples des répertoires autorisés sont acceptés ;
les liens symboliques sont ignorés et l'aperçu est limité à 1 MiB par fichier.
Les opérations JSON et les fichiers hors de ces répertoires ne sont pas exposés.

Aucun navigateur ni socket réseau n'a encore été testé dans l'environnement de
développement. Aucun service systemd ni lancement automatique n'est installé.


## Bibliothèque de sources et validation de détails

Le dashboard comprend désormais Sources : consultation et téléchargement
authentifiés des originaux. Ajouter `--allow-source-upload` pour permettre
leur dépôt explicite ; `--local-ai-model qwen3:0.6b` active les propositions de
détails par le moteur Ollama local dédié (port 11435). Seule la validation
humaine crée une Information. [Parcours, formats, sauvegarde et limites](SOURCE-LIBRARY.md).

Les tests HTTP loopback du 03/10 sont exécutés sur ports éphémères et corpus
synthétiques : les limites historiques ci-dessus concernant l’absence de
test socket décrivent la première livraison. Aucun navigateur/LAN/corpus réel,
service dashboard permanent ni HTTPS dashboard nouvellement installé. Le port
par défaut 8766 est distinct du service MCP actif sur 8765.

Le 03/10/2026, le dashboard a été activé sur `192.168.1.110:8766` avec
l’environnement `.venv` du projet, dépôt de sources et Qwen3 0.6B activés.
Les accès authentifiés à `/` et `/sources` ont été vérifiés ; l’accès depuis
le PC a également été constaté dans les journaux. Le lancement reste manuel.
Un premier envoi a échoué car le Python système ne disposait pas de PyYAML :
aucun original n’avait été écrit. Le dossier temporaire vide a été conservé
hors bibliothèque dans `tmp/dashboard`, puis le serveur relancé avec `.venv`.
Les dépendances de publication sont désormais chargées avant toute création
de dossier temporaire ; une dépendance manquante produit une réponse HTTP 500.
Les 23 tests ciblés d’import et de bibliothèque passent, dont cette régression.

L’option « Personnaliser le fond d’écran » permet de choisir une image JPG,
PNG ou WebP de 2 Mo maximum et de régler son assombrissement. L’image et le
réglage restent dans le stockage local du navigateur, pour cette adresse ;
ils ne sont ni envoyés à la VM ni intégrés à la mémoire. Si le stockage est
indisponible ou plein, un message indique que le choix reste temporaire.
Le bouton de réinitialisation rétablit le fond uni. Le script de personnalisation
est autorisé par son empreinte CSP, sans autoriser les autres scripts intégrés.

## Lanceur utilisant l’environnement du projet

`scripts/run-dashboard.sh` fonctionne depuis n’importe quel répertoire et
utilise toujours `.venv/bin/python` à la racine du checkout. Il transmet les
options du dashboard, conserve le mode loopback/lecture seule par défaut et
exige toujours EIDOLON_DASHBOARD_TOKEN. Il ne génère ni ne publie de secret.
Exemple après définition privée de cette variable :

```sh
scripts/run-dashboard.sh --host 192.168.1.110 --port 8766 \
  --allow-source-upload --local-ai-model qwen3:0.6b
```

Avant d’ouvrir le port, le mode upload charge désormais les dépendances de
publication et refuse le démarrage avec une indication d’environnement si elles
manquent. Le lanceur n’installe aucun service, ne choisit pas un autre port,
ne termine aucun processus existant et ne démarre pas Ollama. Vérifier le port
et les commandes actives avant de le lancer. Sur la VM, il a été utilisé pour
relancer uniquement le dashboard identifié ; `/` et `/sources` répondent 200.
Un nouveau test rouge avant lot vérifie le refus avant création du serveur,
sans modification du corpus ; dix tests dashboard/HTTP passent après correction.

## Lisibilité mobile et fonds volumineux — après revue Claude

Les références longues et noms de fichiers peuvent revenir à la ligne ; champs
et zones de texte restent dans leur conteneur, grille adaptée aux petites largeurs.
Des surfaces sombres derrière texte/liens assurent leur lisibilité même quand
l’utilisateur réduit l’assombrissement sur une image claire ; liens/boutons ont
une hauteur de cible de 44 px. Les index des paragraphes conservent leur place.

L’image de fond sélectionnée (toujours 2 Mo maximum) est désormais redimensionnée
à 1920×1080 maximum et encodée en JPEG dans un canevas local avant stockage,
avec limite d’URL data inférieure à celle constatée par Claude sous Chromium.
Les fonds déjà enregistrés au-delà de cette limite sont adaptés à leur prochain
chargement. Le fichier d’origine sur le PC n’est pas modifié, aucune image n’est
transmise à la VM. L’actualisation utilise le script CSP autorisé et se suspend
quand la personnalisation est ouverte ou l’onglet masqué. Sans JavaScript,
l’actualisation automatique et les préférences locales ne fonctionnent pas.

17 tests dashboard/HTTP passent, empreinte CSP recalculée automatiquement.
Vérification de rendu en navigateur réel de ce nouveau lot demandée à Claude :
aucun Chromium/Playwright disponible sur cette VM, aucun résultat navigateur
précédent attribué à cette modification. Les mesures de contraste et le défaut
de grande URL data proviennent de sa revue cloud `5e8c161`.

## Tableau de bord compact — 4 octobre 2026

À la demande de toytoy, la page principale se compacte automatiquement quand
la fenêtre fait au plus 640 px de large **ou** 540 px de haut. Les cartes mémoire
et espace disque restent côte à côte, avec cercles, titres et marges réduits.
Les informations secondaires restent sous les jauges, accessibles par défilement ;
elles ne sont pas supprimées. La ligne machine/date est masquée dans cette vue.
La navigation et le réglage de fond restent accessibles. Les autres pages ne
changent pas de densité ; la vue large conserve ses cartes ordinaires.

19 tests dashboard/sources verts. Vérification visuelle réelle **en attente** :
Playwright présent mais aucun navigateur installé ; téléchargement Chromium
inutilisable dans cet environnement. Recette sur VM : mettre la branche à jour,
relancer le dashboard, recharger `/`, puis réduire la fenêtre à environ 400×300,
320×320 et 600×400 pixels ; vérifier jauges côte à côte, valeurs lisibles,
absence de défilement horizontal, accès aux autres cartes par défilement vertical,
puis agrandir à 1000×800. Tester aussi le fond personnalisé et le zoom 200 %.

## Vue minimale texte — 4 octobre 2026

En dessous de 360 px de largeur **ou** 260 px de hauteur utile du navigateur,
la page principale affiche seulement deux lignes : Mémoire et Espace disque,
avec utilisé / total et pourcentage. Jauges, fond personnalisé, navigation et
cartes secondaires sont masqués ; agrandir la fenêtre rétablit la vue et ses
réglages. Aucun changement de données ou de préférences enregistrées.

19 tests existants dashboard/sources verts ; rendu de ce nouveau mode à vérifier
sur le navigateur VM, notamment à 600×220 et 320×320 pixels utiles.
La capture de toytoy à 09 h 47 confirme la vue compacte précédente : deux
jauges lisibles côte à côte après reprise du processus, et non ce mode texte.
