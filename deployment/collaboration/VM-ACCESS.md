# Accès VM MCP — première phase en lecture seule

État : code préparé, non déployé. Les connexions réelles depuis Work ne sont
pas encore validées. Le MCP conserve ses trois outils historiques par défaut.
L'activation explicite ajoute `vm_diagnostic` et `vm_read_file` ; elle ne donne
aucune capacité de shell, d'écriture, de benchmark ou de contrôle de services.
Les benchmarks seront ajoutés après examen de leurs scripts et isolation des
sorties dans un répertoire temporaire. Ne pas exécuter un script simplement
parce qu'il porte le nom de benchmark.

## Architecture et restrictions

Le compte MCP existant reste isolé avec `ProtectHome=yes`. Une nouvelle clé
privée reste dans `/var/lib/eidolon-collaboration/credentials`, accessible
uniquement au compte MCP. Ne pas réutiliser la clé GitHub. Les deux destinations
SSH sont fixées par l'opérateur ; aucun hôte ou commande n'est fourni par le LLM.

Sur chaque VM, installer `vm_gateway.py` sous un chemin détenu par root, par
exemple `/usr/local/lib/eidolon-vm/vm_gateway.py`, avec une configuration root
non modifiable par toytoy. La clé publique dédiée est autorisée avec cette
commande imposée dans le compte toytoy (qui possède les corpus) :

```
restrict,command="/usr/bin/python3 -I /usr/local/lib/eidolon-vm/vm_gateway.py /etc/eidolon-vm-gateway.json" ssh-ed25519 CLE_PUBLIQUE_DEDIEE
```

`restrict` interdit PTY et transferts SSH ; la commande imposée n'exécute jamais
`SSH_ORIGINAL_COMMAND` comme un shell. Elle accepte seulement le protocole
`eidolon-read-v1` et ses actions fixes. Ne pas remplacer les clés existantes.
La configuration et les scripts doivent être installés par l'opérateur avant
d'autoriser la clé. Toute modification du service MCP doit être approuvée.

Configuration passerelle VM110 (réduire les racines selon le besoin) :

```json
{"roots":{"tools":"/home/toytoy/eidolon-tools","hybrid":"/home/toytoy/eidolon-hybrid-lab","corpus":"/home/toytoy/eidolon-corpus-factual-v2-test"}}
```

Configuration passerelle Core :

```json
{"roots":{"source":"/opt/eidolon-core/bootstrap/eidolon-core/src/eidolon_core"}}
```

Vérifier l'existence du répertoire Core avant activation. Ne pas exposer les
répertoires de credentials, les sauvegardes, ni les fichiers d'environnement.
Les fichiers accessibles sont limités aux extensions .py/.md/.json/.txt/.csv,
aux chemins relatifs sans fichiers cachés, à 65536 octets. Les symlinks dans la
racine sont refusés par ouverture relative aux descripteurs de répertoire.
Les résultats portent `UNVERIFIED`, une empreinte SHA-256 et une date mtime ;
la date du fichier ne constitue pas une preuve de validité temporelle du fait.

## Configuration client MCP (root, lecture pour le compte MCP)

```json
{"targets":{"memory":{"destination":"toytoy@192.168.1.110","key":"/var/lib/eidolon-collaboration/credentials/vm_read_ed25519","known_hosts":"/var/lib/eidolon-collaboration/credentials/vm_known_hosts"},"core":{"destination":"toytoy@192.168.1.101","key":"/var/lib/eidolon-collaboration/credentials/vm_read_ed25519","known_hosts":"/var/lib/eidolon-collaboration/credentials/vm_known_hosts"}}}
```

Enregistrer les clés hôtes seulement après comparaison avec les sessions SSH
habituelles. La clé Core vérifiée le 11/10/2026 est
`SHA256:riG5M5w2V+7CuPEzZI/tcdn5cxvhFVHj8k7OTtx2k1Y` ; la clé VM110 reste
à vérifier. Ne pas utiliser StrictHostKeyChecking=no.

Définir `EIDOLON_VM_CONFIG=/etc/eidolon-collaboration/vm-access.json` dans
l'environnement du MCP après installation d'une nouvelle release vérifiée.
Conserver la release actuelle `/opt/eidolon-collaboration/release.19fiaQjj`
pour retour arrière. Aucun changement au tunnel ou à l'URL MCP n'est requis
par le code ; la connexion ChatGPT et le blocage Cloudflare restent à vérifier.

## Autorisation OAuth et recette

Configurer dans Auth0 la permission supplémentaire `eidolon:vm:read` pour
l'identité autorisée, sans l'attribuer automatiquement à tous les utilisateurs
historiques. Le token doit porter `eidolon:exchange` ET `eidolon:vm:read`.
Vérifier que le client demande ce scope ; sinon les outils VM restent refusés.

Avant tout redémarrage MCP : vérifier passerelles via la clé dédiée, absence
d'accès shell/PTY, refus des traversées et fichiers non autorisés. Faire une
copie de l'environnement et du lien de release. Après approbation, basculer
uniquement le MCP et le redémarrer ; ne toucher ni Core ni Memory Bridge.
Tester `tools/list`, rejet sans scope, diagnostic des deux VM, lecture de
`context_router_v3.py`, contrôle des hashes et journal d'audit. Rétablir
l'environnement et le lien précédents en cas d'échec. Aucun succès Work ne doit
être annoncé avant un appel MCP réel depuis la conversation.
