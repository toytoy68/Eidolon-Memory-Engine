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
