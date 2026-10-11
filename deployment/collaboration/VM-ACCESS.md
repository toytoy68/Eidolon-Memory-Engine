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

## Fixed offline benchmark extension (11 October 2026)

An operator may install `install-vm-benchmark.sh` from a pinned commit on Memory.
It adds bounded file inventory and `vm_benchmark_start` / `vm_benchmark_status`.
The existing VM read scope gates these offline diagnostics: the client cannot
select commands, arguments, code, query text, models or source paths. The gateway
only enables execution when its root-owned configuration contains `benchmark`.
Core's gateway stays unchanged and rejects benchmark requests.

The launcher copies at most 64 MB / 10000 regular corpus files into temporary
storage, rejects symlinks, and executes the operator-owned benchmark using
Bubblewrap with all namespaces unshared, no network, read-only host filesystem,
hidden home/runtime directories, and only the disposable `/work` tree writable.
The existing hybrid runtime/model cache is mounted read-only at `/runtime`.
There is no network or unsandboxed fallback. One flock-protected job runs at a
time; wall/CPU limit 600 seconds, virtual address space 12 GiB, output/file-size
limits, two numerical threads, reduced scheduling priority. Results are saved in
`/var/lib/eidolon-vm/jobs`, not in application/corpus directories; 20 jobs maximum.
The worker has the privileges of toytoy, not root. After completion its source
snapshot and temporary logs are deleted. Status accepts only a generated UUID.

Comparison: lexical, factual-card selection, original router v3, corrected
experimental router, exact semantic cosine, RRF (20+20 candidates), optional
cached Cross-Encoder. All use the same factual-v2 corpus snapshot. Semantic
vectors are regenerated in RAM including factual cards; existing Qdrant index
and services are not changed. This is not a measurement of Qdrant latency.
Original v3 source is preserved byte-for-byte with a pinned SHA256; only audited
classifier/scoring nodes are used, not its import-time backend initialization.

The dataset contains 40 new formulations, 35 provisionally labelled against seven
operator factual cards, plus five unjudged wider/unknown queries. Metrics are
reference recall@5 and MRR@5, not answer accuracy or precision@5. No label comes
from per-query signals used for ranking. These labels are source-retrieval
checks, not verified ground truth about current hardware or VM allocation.
Gold corpus files remain UNVERIFIED/PENDING_REVIEW. Wider source judgements,
answer correctness and real temporal validity remain manual work. Model loading
and corpus embedding times are separate from query latency. Model/package
versions, snapshot SHA256 and selected provenance are returned.

Local validation covers ASGI OAuth scope enforcement, no arbitrary execution,
corpus-copy integrity, link/path rejection, sandbox command construction,
classification counterexamples and operational versus historical retrieval.
The local hosted environment blocks Bubblewrap's network namespace creation;
therefore no claim of an executed VM/sandbox/model benchmark is made before the
installer's same-user probe and actual MCP job complete on Memory.

Refreshing the connected app's tool inventory may be required after installation.
Keep OAuth permissions and app identity. Do not repeatedly reconnect if the new
tools are absent; inspect the developer app's tool-refresh control instead.
