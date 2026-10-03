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
python -m core.monitoring.dashboard --root /opt/eidolon-memory-engine
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
