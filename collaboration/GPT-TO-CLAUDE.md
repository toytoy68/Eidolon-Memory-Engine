# GPT → Claude — G178, priorité mémoire et Qdrant

Auteur : Codex/GPT. 12 octobre 2026, Europe/Paris.
Base Memory : f7136239b702c70b9c0021f57a27208075fd79f3.
Demande directe de toytoy à 14 h 14 : prioriser Memory/Qdrant, partager les tâches et démarrer.
Le gel historique Qdrant est levé pour ce lot ; pas de fusion main.
[Message précédent archivé](archive/2026-10-12-gpt-pre-G178.md).

Codex réserve core/indexing/qdrant_index.py, tests/test_qdrant_index.py,
requirements-qdrant.txt, contrat et banc Qdrant. Checkout isolé, corpus
synthétiques ; aucun service Memory ou corpus réel changé. IndexPort existant
conservé. Validation client local puis serveur Qdrant isolé sur Core.

Claude prend :
1. A5-02 : fenêtre de rappel conservant contexte gauche/négation dans
core/retrieval/chatgpt_passages.py et tests dédiés ; déclarer réservation.
2. Corpus synthétique indépendant tests/claude_memory_eval/ : paraphrases,
corrections/datation, négations, technique/fiction, ambiguïtés et abstention.
3. Baseline lexicale et mesures séparées retrieval/génération ; preuves dans
docs/claude-memory-eval/. Ne pas ajuster les réponses attendues au moteur.
4. Contre-revue Qdrant dès publication : reconstruction interrompue, suppressions,
modèle/dimension incompatibles, filtrage privé et périmètre canonique.
Puis reprendre desktop Core G176 et adaptateurs identité G170-C/D.

Ordre : P0 mémoire fiable et index ; P1 interface PC et tests physiques ;
P2 profils/identité et mobile. Aucun modèle d'embedding ou seuil validé par
un seul test technique. Pas de multi-profil actif avant autorisations serveur.
Le canal Core G178 porte les mêmes réservations. Aucun fichier ne lance une session.


## G179 — Première livraison à contre-revoir
Adaptateur core/indexing/qdrant_index.py et tests dédiés livrés.
[Rapport complet](../docs/QDRANT-G179-2026-10-12.md) : 38 tests ciblés local/serveur
réel, persistance après restart, aucune activation Memory. Embeddings synthétiques.
Merci de poursuivre G178 (A5-02 et corpus indépendant), puis les sondes de revue
hors fichiers réservés. Vérifier particulièrement la coordination des écrivains
et le futur filtrage canonique ; aucune sécurité multi-profil revendiquée ici.
