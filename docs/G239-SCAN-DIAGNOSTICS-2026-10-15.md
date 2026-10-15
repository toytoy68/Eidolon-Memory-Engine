# G239 — Incompatibilité distincte d'une panne d'index

Codex/GPT, 15 octobre 2026. Base G238
`6e7ef5c65c397ee85c0d777f69677c51dbbbb2c6`.

Le rapport G234 signalait que les scanners transformaient encore un descripteur
incompatible en INDEX_UNAVAILABLE. ReconciliationScan, OrphanScan (scan et revue)
et IndexMaintenance conservent désormais le type IndexIncompatible et rapportent
INDEX_INCOMPATIBLE. Une vraie erreur de transport reste INDEX_UNAVAILABLE.
Les messages internes de l'adaptateur ne sont pas ajoutés au rapport.

Ce changement de diagnostic ne permet aucun effet supplémentaire. Dans le scanner
canonique, le préfixe déjà traité reste enregistré ; la ligne incertaine reste au
curseur. Dans le scanner inverse, aucune observation de la page partielle n'est
publiée. La revue retourne zéro candidat sur incompatibilité. Le contrôleur garde
le motif dans son checkpoint avec le même report borné ; il ne migre, réétiquette
ou reconstruit pas automatiquement l'index. Après une correction explicite du
contexte, les appels suivants recontrôlent la compatibilité avant reprise.

Preuves : 13 scénarios rouges avant correction et 3 témoins de panne réseau déjà
verts ; **133 tests scanners/maintenance réussis** après correction (5,56 s).
Le harnais d'une sonde a été ajusté avant correction : une page de deux éléments
pouvait ne contenir qu'un document plus le descripteur ; trois éléments incluent
les deux documents visés. L'échec INDEX_UNAVAILABLE au lieu d'INDEX_INCOMPATIBLE
est ensuite reproduit sur cette sonde avant modification du code.

Cas : schéma, projection ou modèle persisté incompatibles ; erreur au milieu
d'une page, vérification finale et revue d'orphelin ; réparation explicite puis
convergence. Le test serveur HTTP vérifie maintenant aussi ce diagnostic du
contrôleur. Le workflow ciblé inclut les nouveaux tests et leurs chemins de
déclenchement G236/G237/G239. CI du lot à confirmer.

## G238 serveur : résultat réel confirmé

[Workflow 38662940807](https://github.com/toytoy68/Eidolon-Memory-Engine/actions/runs/38662940807),
job 116188206027 : archive officielle vérifiée (`qdrant.tar.gz: OK`), puis
**9 tests réussis en 13,17 s avec -W error**, client 1.15.1, serveur 1.15.4,
Python 3.13/Linux. Aucun modèle réel, corpus privé, VM ou déploiement.
Le rapport G238 conserve le périmètre exact : la réponse perdue y est simulée
après un acquittement réel ; un proxy coupant réellement la réponse reste à tester.
La qualification d'un arriéré >1000 sur HTTP reste également distincte du test
local Claude déjà réussi. Ce sont les deux dernières validations Codex prévues
pour cette plage de travail, sans modification de politique d'activation.
