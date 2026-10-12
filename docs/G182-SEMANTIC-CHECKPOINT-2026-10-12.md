# G182 — Passages canoniques et première évaluation d'embeddings réels
Auteur : Codex/GPT. Date : 12/10/2026, Europe/Paris.
Base Memory : deff13647a8a5db7ee856966092fc91acf6c1cf4.
Statut : code ciblé testé ; résultats de suite et mesure sémantique EN ATTENTE.

## Implémentation
- archive_chunks.py découpe les messages user/assistant en morceaux verbatim
  bornés (1200 caractères, chevauchement jusqu'à 160 par défaut). Aucun mélange
  entre messages ou branches ; aucun classement épistémique déduit du texte.
- Les références ne stockent que message_index/start/end. Aucun hash individuel
  du texte ni copie de corps n'est ajouté au payload de Qdrant dans le banc.
- Le rappel canonique accepte une référence de passage issue d'un index choisi
  par du code de confiance. Révision et filtres G181 restent appliqués.
- Le texte et sa provenance sont relus depuis le Markdown courant. La sélection
  ne nécessite plus un mot commun avec la question pour ce chemin explicite.
- Références invalides refusées ; positions finales ajustées après budget de
  caractères/tokens. Contexte gauche partiel et marqueurs omis signalés.
- Le défaut lexical et la politique passage v3 restent inchangés.

## Preuves effectivement obtenues
Worktree isolé : /home/toytoy/eidolon-worktrees/memory-g182.
- Avant création du module : échec de collecte attendu (module absent).
- Après création, avant raccordement : 2 tests d'intégration rouges et 17 verts.
- Après raccordement : 76 tests ciblés réussis en 0,88 s.
- git diff --check : sans erreur.
La suite complète a été lancée ; sa fin n'a pas encore été récupérée.
Ne pas compter une suite verte à partir de son seul lancement.

## Modèle installé et protocole figé
Téléchargement vérifié sur Core via /api/tags :
- qwen3-embedding:0.6b ; 639150858 octets.
- Digest ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d.
- Ollama 0.32.15.
Le protocole impose num_gpu=0, num_thread=2, num_ctx=2048, dimensions=1024,
truncate=false et une instruction de requête fixe en anglais. Les documents
n'ont pas ce préfixe. Le digest est vérifié avant/après chaque lot ; il n'y a
ni téléchargement implicite ni acceptation silencieuse d'un tag modifié.
Le banc vérifie size_vram=0 avant ses questions ; cette vérification n'est pas
encore confirmée par le résultat final. Aucun changement de pilote NVIDIA.

Le script tests/claude_memory_eval/run_semantic.py utilise exclusivement le
corpus synthétique figé de Claude (30 documents / 27 questions), le Qdrant
de recette sur 127.0.0.1:16333 et Ollama sur 127.0.0.1:11434.
Il crée sa collection unique, stocke des passages, effectue le rappel par
ContextualRecall et conserve extraits/références/scores/latence. Les références
attendues restent inchangées. Aucun seuil d'abstention n'est choisi après coup.
La collection est supprimée dans finally si le processus termine normalement.
Ce producteur de candidats est un banc expérimental, pas l'adaptateur durable
de passages ni la synchronisation de production.

## Incident et reprise du checkpoint
Le premier lancement du banc a échoué avant indexation : Qdrant n'écoutait
pas encore (course au démarrage). Après /readyz réussi, second lancement.
Ensuite la liaison Eidolon Collaboration est devenue indisponible :
vm_execute, vm_diagnostic et get_exchange_status ont retourné des erreurs.
Les journaux distants existent, mais aucun résultat sémantique n'est annoncé.

À récupérer avant décision de modèle ou déploiement :
- /home/toytoy/eidolon-validation/memory-g182/full-suite.log
- /home/toytoy/eidolon-validation/memory-g182/semantic2.log
- /home/toytoy/eidolon-validation/memory-g182/semantic-qwen3.json, s'il existe.
Services temporaires : eidolon-memory-g182-suite (limite 240 s),
eidolon-memory-g182-semantic2 (limite 600 s), eidolon-qdrant-g182.
L'arrêt du serveur Qdrant temporaire reste à confirmer/exécuter une fois
l'accès revenu ; il écoute seulement en loopback. Aucun service Memory actif
n'a été reconfiguré, aucun corpus privé indexé par ce banc.

Commandes de reprise après lecture des journaux : vérifier les états, lire le
résultat existant, ne pas relancer aveuglément un benchmark déjà terminé.
Arrêter le Qdrant temporaire et décharger uniquement qwen3-embedding:0.6b
après la mesure. Ne jamais arrêter le modèle de dialogue pour ce nettoyage.

## Limites ouvertes
Le découpage garantit offsets et bornes, pas conservation complète du sens.
Une négation dans une phrase précédente reste hors de son heuristique.
Un mot très long peut être coupé pour respecter la borne ; Unicode est conservé
verbatim mais pas nécessairement la totalité d'un graphème dans chaque chunk.
Les 30 documents du corpus ne constituent pas une validation de gros historiques,
de branches réelles ou d'un corpus privé multi-profil.
Une édition directe sans incrément de révision peut rendre un classement et ses
positions obsolètes ; le texte retourné reste canonique courant, pas historique.
Reste à construire l'index durable par passages, la synchronisation, le filtrage
d'accès par profil et le branchement bridge après qualification de pertinence.
Aucune activation en production, aucun gain de rappel encore revendiqué.

## Sources techniques consultées le 12/10/2026
- https://huggingface.co/Qwen/Qwen3-Embedding-0.6B
  (séparation instruction de requête/documents, dimensions).
- https://ollama.com/library/qwen3-embedding:0.6b
  (modèle distribué et appel embeddings).
- https://docs.ollama.com/api/embed
  (lots d'entrées et refus de troncature).
Les recommandations externes ne remplacent pas la mesure locale.
