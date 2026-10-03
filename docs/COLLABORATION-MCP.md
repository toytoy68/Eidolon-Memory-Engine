# Eidolon Collaboration — serveur MCP distant

## État et contrat

Implémentation du canal décidée par toytoy dans « Connecter GitHub à Claude »,
le 3 octobre 2026. Le serveur est indépendant du Memory Engine ; aucune donnée
mémoire ni fonction métier n'est modifiée. L'historique ECHANGES.md reste intact.

Surface MCP : `read_gpt_message()`, `write_claude_message(message)`,
`get_exchange_status()`. Aucun shell ou chemin fourni par l'appelant. Branche
imposée `refactor/architecture-v1`, origine imposée au dépôt toytoy68, HTTPS ou
SSH GitHub. Message non vide, sans NUL, UTF-8 strict, 32768 octets maximum.
Le corps HTTP est borné à 65536 octets ; un JSON fortement échappé peut atteindre
cette limite avant celle du message.

Chaque opération prend un verrou Linux `flock` non bloquant partagé par les
instances utilisant le même répertoire d'état, vérifie checkout autonome,
branche, origine de lecture/écriture, fichiers suivis et chemins sans symlink,
refuse les modifications suivies ou non suivies, récupère la branche distante,
refuse tout commit local non publié/divergence et fait `git pull --ff-only`.
Une modification distante pendant la synchronisation impose une relance.
Les lectures synchronisent aussi ; statut `ready=false` en cas de blocage Git.
Les fichiers ignorés par Git ne sont pas un indicateur de saleté ; aucun
opérateur ne doit modifier ce checkout pendant que le service fonctionne.

Une écriture archive les octets de la réponse précédente sous un UUID, remplace
atomiquement le fichier actif, ajoute seulement ces deux chemins, commite et
pousse explicitement la branche. Les hooks et signatures Git automatiques sont
désactivés pour les commandes du service. Aucun merge, reset ou push forcé.
La publication est annoncée seulement après vérification de la référence distante.
Les anciennes réponses ne sont jamais écrasées ; les archives peuvent croître.
Aucun archivage global d'ECHANGES.md ni ordonnanceur automatique ajouté.

## Authentification

Streamable HTTP via SDK officiel MCP 1.30.0, ligne 1.x maintenue et dépendance
épinglée ; JWT RS256 via PyJWT. Le serveur refuse de démarrer sans URLs HTTPS et
liste explicite des identités OAuth autorisées. Pas de mode anonyme.
Il publie la découverte RFC 9728 à
`/.well-known/oauth-protected-resource/mcp` et renvoie un challenge 401 vers
cette découverte. Le fournisseur OAuth est séparé : ce service n'est pas un
serveur de connexion ou d'émission des tokens.

Configurer chez le fournisseur : Authorization Code + PKCE S256, métadonnées
OAuth, client Claude (enregistrement dynamique ou client préenregistré),
redirections Claude déclarées par sa documentation, émission de JWT RS256 avec
`iss`, `aud` **égal exactement à l'URL publique /mcp**, `sub`, `iat`, `exp`,
et `scope` comprenant `eidolon:exchange`. Le fournisseur doit accepter la
ressource MCP demandée et délivrer cette audience. Un fournisseur qui ne sait
pas émettre ces claims nécessite une adaptation testée du vérificateur.

La signature vient du JWKS configuré par l'opérateur, jamais d'une URL reçue
avec le token. Vérification de l'expiration, de l'émetteur, de l'audience, du
scope et de la liste `sub` autorisée. Un compte du même fournisseur mais absent
de cette liste ne peut pas utiliser le canal. Les tokens et credentials Git
ne figurent pas dans les résultats MCP ou dans le journal d'audit.

Références primaires :
[SDK MCP : autorisation](https://github.com/modelcontextprotocol/python-sdk/blob/v1.x/docs/authorization.md),
[connecteurs distants Claude](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp).
La connexion Claude Web passe par l'infrastructure Anthropic : une adresse LAN
ou le port local seul ne suffit pas. Un PAT GitHub n'est pas un identifiant
client OAuth et ne doit jamais être collé dans Claude.

## Installation sur la VM

Les modèles sont dans `deployment/collaboration/`. Ne pas activer le service
avant d'avoir renseigné le domaine, le fournisseur et le compte autorisé.
Prérequis : Python >= 3.10, Git, compte système dédié, Caddy installé, DNS public
et ports 80/443 joignables depuis Internet. Garder 8765 local uniquement.

1. Créer le compte système `eidolon-collaboration`, sans connexion interactive,
   avec domicile `/var/lib/eidolon-collaboration`. Créer `app/` dans
   `/opt/eidolon-collaboration`, et `repo/`, `state/`, `credentials/` dans
   `/var/lib/eidolon-collaboration`. Le code et le venv sont possédés par root,
   les trois répertoires d'état appartiennent au compte du service, mode 0700.
2. Copier le code **du commit publié validé** dans `app/` (clone de lecture ou
   archive Git). Créer `/opt/eidolon-collaboration/venv` puis installer
   `requirements-collaboration.txt`. Conserver le code du service séparé de
   son checkout modifiable : une réponse Git ne change pas le programme actif.
3. Fournir une clé de déploiement GitHub dédiée, autorisée en écriture pour ce
   dépôt seulement, dans `credentials/github_ed25519`, mode 0600. Vérifier les
   clés hôtes GitHub par leur source officielle avant de remplir `known_hosts` ;
   ne pas désactiver StrictHostKeyChecking. Ne pas réutiliser la clé personnelle
   de l'opérateur. La clé GitHub permet techniquement plus que les deux fichiers ;
   la restriction de chemins est réalisée par le service, pas par GitHub.
4. Sous le compte du service, avec `GIT_SSH_COMMAND` du modèle d'environnement,
   cloner `git@github.com:toytoy68/Eidolon-Memory-Engine.git`, branche
   `refactor/architecture-v1`, dans `repo/`. Vérifier arbre propre et accès
   distant sans afficher de credential. Ce checkout est réservé au MCP.
5. Copier `environment.example` vers `/etc/eidolon-collaboration/environment`,
   possédé par root, mode 0600. Remplacer les trois URLs et l'identité OAuth ;
   aucune clé privée ne doit être écrite dans le dépôt. Copier l'unité systemd
   vers `/etc/systemd/system/eidolon-collaboration.service`.
6. Adapter `Caddyfile.example` au domaine public et l'intégrer à la configuration
   Caddy existante. Le proxy conserve Authorization et Host ; aucune journalisation
   d'en-têtes sensibles. La découverte OAuth est publique, `/mcp` exige un token.
   Valider Caddy et l'unité systemd, puis démarrer le service et le proxy.
7. Vérifier sans token : `/mcp` répond 401 avec `WWW-Authenticate`, découverte
   OAuth répond 200, issuer/resource correspondent. Avec une session autorisée,
   vérifier les trois outils et `ready=true`, puis un aller-retour Claude réel.

Commandes après préparation des comptes, chemins et configurations :

```bash
/opt/eidolon-collaboration/venv/bin/python -m pip install -r /opt/eidolon-collaboration/app/requirements-collaboration.txt
sudo systemd-analyze verify /etc/systemd/system/eidolon-collaboration.service
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl daemon-reload
sudo systemctl enable --now eidolon-collaboration
sudo systemctl reload caddy
```

Dans Claude : Paramètres → Connecteurs → ajouter un connecteur personnalisé,
nom « Eidolon Collaboration », URL `https://<domaine>/mcp`, connexion OAuth au
compte autorisé. Si le fournisseur exige un client préenregistré, renseigner
ses champs client OAuth ; aucun PAT GitHub. La configuration de ce fournisseur
et le consentement dans le compte Claude restent des étapes humaines tant
qu'aucun accès à ces comptes n'est disponible.

## Audit et reprise

`state/audit.jsonl` : date UTC, démarrage/appel d'outil et identité OAuth,
UUID, taille/hash du message, commit local, publication ou échec ; aucun corps
ou token. Les étapes d'écriture sont flush/fsync avant progression. stdout/stderr
vont au journal systemd. Ces journaux sont locaux et ne constituent pas une
preuve d'inviolabilité ; sauvegarde et rotation relèvent de l'opérateur.
L'historique Git porte le contenu exact et l'UUID.

Si commit/push/réseau/audit échoue, une erreur indique que la publication n'est
pas confirmée. Une coupure peut laisser une archive/fichier temporaire ou un
commit local. **Ne pas renvoyer automatiquement la réponse.**

Arrêter le service, lire l'audit et examiner status/diff/log et la branche
distante depuis le checkout dédié. Si le commit existe et est déjà distant,
confirmer sa présence avant relance. S'il est propre, en avance seulement et
pas distant, publier **ce même commit** après revue. Si le distant a avancé,
réconcilier manuellement sur une branche de travail en conservant réponse et
archive, puis synchroniser le checkout réservé. Si l'écriture n'est pas
commitée, examiner les fichiers avant de terminer ou annuler cette opération.
Ne jamais effacer aveuglément les preuves avec un reset. Le service refuse
les nouvelles écritures tant que son checkout est sale ou en avance/divergence.

Le verrou protège les instances du service, pas des commandes humaines Git
lancées hors de ce protocole. Un push Git concurrent peut légitimement faire
échouer une réponse : c'est un blocage à résoudre, pas une fusion automatique.
Une même réponse envoyée volontairement deux fois après succès produit deux
commits : les trois outils n'offrent pas de clé d'idempotence fournie par Claude.

## Validation et limites

Tests : clones temporaires avec remote bare réel, publication/archives CRLF et
Unicode, limites UTF-8/octets, branches/origines imposées, état sale/divergent,
verrou entre instances, push rejeté et reprise du même commit ; JWT signés et
requêtes MCP HTTP ASGI, découverte, outils exacts et accès refusés.

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q tests/test_collaboration_exchange.py tests/test_collaboration_mcp.py
```

Les tests HTTP asynchrones nécessitent un environnement permettant les réveils
asynchrones et sockets locaux (restrictions sandbox observées sur cette VM).
Les fixtures ne contactent pas GitHub ou un fournisseur OAuth public.
Validation HTTPS/DNS, émission OAuth réelle et session Claude Web ne sont pas
couvertes par ces tests. Les modèles sont préparés ; aucun service permanent
ni endpoint public ne doit être annoncé actif avant cette recette.

Résultat du 03/10/2026 sur la VM : **1643 réussis en 38,02 s**, dont 37 nouveaux
cas de collaboration. Le client MCP officiel a également été connecté sur HTTP
loopback à un serveur réel, avec dépôt/remote bare isolés : trois outils, lecture,
publication et statut contrôlés. Neutraliser le push ou le vérificateur OAuth
fait échouer les tests correspondants. `pip check` cohérent. Syntaxe systemd
validée sur une copie dont ExecStart pointe vers le Python existant ; le chemin
de déploiement du modèle n'existe pas encore. Caddy n'est pas installé, son
modèle n'a pas pu être validé avec l'exécutable. Aucun service permanent activé.
