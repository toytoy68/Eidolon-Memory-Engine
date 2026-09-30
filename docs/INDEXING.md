# Index dérivé — manifeste de source

Le port `IndexPort` expose `upsert`, `delete`, `query`, `rebuild` et `status`.
`InMemoryIndex` fournit une implémentation de référence sans service externe :
il classe lexicalement et se reconstruit intégralement à partir des fichiers.
Il reste volontairement éphémère. `tests/contracts/index_port_contract.py`
définit les tests partagés : un autre adaptateur fournit simplement son
fixture `index` et hérite de `IndexPortContract`, sans changer ces tests.
`status().source_digest` désigne le dernier manifeste reconstruit ; toute
mutation incrémentale l'efface jusqu'à une nouvelle reconstruction. Ce port
ne branche pas encore les écritures métier sur un index.

`core.indexing.build_manifest(persistent_root)` lit les fichiers Information
core de `memory/persistent/*.md` sans écrire. Il renvoie, dans l'ordre des noms
de fichiers, l'identifiant, la révision et SHA-256 des octets du fichier, ainsi
qu'une empreinte globale calculée sur cette liste. Le corps privé n'est pas
inclus dans le manifeste.

Un document illisible, mal identifié ou symbolique bloque la construction.
`diff_manifests(ancien, courant)` prépare, sans écriture, la liste ordonnée des
IDs à ajouter/actualiser et à retirer. La comparaison refuse les doublons,
les entrées invalides et une empreinte globale incohérente ; cette empreinte
n'authentifie toutefois pas l'origine du manifeste.

Pour deux copies arrêtées, afficher seulement les comptes et empreintes :

```sh
python -m core.indexing.cli --root /chemin/vers/ancienne-copie \
  --compare-root /chemin/vers/nouvelle-copie
```

Chaque racine contient `memory/persistent/`. La commande ne crée ni verrou ni
fichier. Elle sort avec erreur si une source n'est pas lisible ou correctement
identifiée ; les contenus des Informations ne figurent pas dans le rapport.
Comparer deux manifestes permet de détecter qu'une source a changé, mais ne
prouve pas que Qdrant contient déjà la bonne projection : aucun index ni
connecteur Qdrant n'est implémenté ici. La lecture n'est pas un instantané
atomique en présence d'écrivains ; pour une reconstruction ou un contrôle de
migration, utiliser une copie arrêtée. La définition des points, des embeddings,
des filtres d'accès et du rattrapage après écriture reste à valider.
