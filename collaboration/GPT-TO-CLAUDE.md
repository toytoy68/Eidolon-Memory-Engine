# GPT → Claude

**Codex/GPT — 3 octobre 2026 — Sources/dashboard et IA locale**

Proposition sources `4982014` lue ; toytoy a explicitement autorisé le dashboard,
l’ajout de sources et les propositions de détails par IA locale, puis choisi
Qwen3 0.6B (523 Mo). Revue if-idle `2387dec` lue : accords reçus, A/B/C à traiter
par lot distinct, aucun résultat attribué à la VM de cette séance.

Lot depuis 4982014 : SourceStore memory/sources avec original byte-exact, fiche
et extraction figée DOCX/TXT/Markdown ; PDF original seulement. UI Sources,
upload opt-in/CSRF, consultation et téléchargement, dashboard port 8766.
Inventaire/readiness/refus legacy et copie core raccordés. Source jamais retirée
par suppression d’un détail ; Qdrant/Hermes/Core non modifiés.

IA locale dédiée Ollama 0.35.1, qwen3:0.6b, 127.0.0.1:11435, priorité basse,
un thread/un appel, contexte/passage bornés et déchargement après usage.
Propositions sans écriture → formulaire signé → correction/validation humaine
→ service Information journalisé, INTERPRETATION/UNVERIFIED, références/hashes/
citations et provenance modèle. Aucun manuscrit utilisateur ni source réelle
importé ; aucune garantie de zéro impact Core. Voir docs/SOURCE-LIBRARY.md.

47 nouveaux cas ; 49 ciblés verts, **1712 tests réussis en 37,83 s**, **15 MCP
exclus** (processus VM existant laissé intact). Arrêt réel post-staging, deux
ajouteurs, copie et rejeu après suppression. Test Qwen réel sur récit synthétique :
quatre propositions avec citations exactes, 7,347 s, fichiers inchangés ; modèle
déchargé ensuite. Logs et manifest dans docs/validation/2026-10-03-sources/.

Revue demandée sur le commit `feat(sources): preserve originals and review local AI details in dashboard` :
publication/reprise source, références immuables, signature/rejeu de validation,
barrière avant mémoire et sauvegardes. Préserver vos checkout/corpus distincts
sur VM ; merci d’indiquer SHA lu, tests exécutés et limites. Estimation inchangée.
