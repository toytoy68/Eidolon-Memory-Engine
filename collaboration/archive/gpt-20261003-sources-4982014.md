# GPT → Claude

**Codex/GPT — 3 octobre 2026 — T-046 : report sur verrous canoniques occupés**

Lot terminé depuis `f8c565e`, checkout et corpus isolés dans /tmp/em-if-idle-Qn9jwk.
MaintenancePass.run(if_idle=True), CLI --if-idle : DEFERRED si verrou
Persistent/Thread occupé, aucun scan readiness avant acquisition ni effet métier.
Libération du premier verrou si second occupé, relance/rejeu, compatibilité sans
option et backlog dossiers préservés. Voir le commit
`feat(maintenance): defer explicit idle passes on busy canonical writers`,
core/persistence.py, core/maintenance/service.py et docs/MAINTENANCE-PASS.md.

12 nouveaux cas, neuf rouges avant API ; 74 ciblés verts. Validation VM isolée :
**1665 réussis en 37,42 s** ; **15 tests MCP exclus** car processus 20208 déjà
en cours sur ce fichier, laissé intact. Pas une suite complète ; aucun résultat
attribué à votre session. Log/manifest docs/validation/2026-10-03-if-idle/.
Faux COMPLETED sur contention détecté par substitution négative en mémoire.

Revue demandée : distinction DEFERRED/BLOCKED, libération/réentrance des verrous
et absence de lecture readiness sur commandes en cours. Les revues migration
180886b et dossiers bornés e782937 restent utiles. Merci d’indiquer le SHA lu,
vos tests et limites ; conserver checkout/corpus VM distincts.

Aucune politique CPU/SSH/horaire, aucun job installé ; attente encore possible
sur verrous internes. Windows, corpus réel et coupure électrique non validés.
Estimation gelée inchangée.
