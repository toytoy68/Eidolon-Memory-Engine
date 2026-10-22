# G291 — Banc de 50 questions et isolation des tests

## Objectif

Séparer le classement des documents, la pertinence réelle, la capacité de répondre et la véracité. **30 questions positives** (deux formulations pour chacune des quinze fiches de veille IA) et **20 questions négatives** (questions fictives, futures ou sans preuve connue). Les négatives sont des questions sans réponse attendue **dans ce jeu de fiches**, pas la preuve qu'aucun autre document du corpus général ne peut y répondre. Le résultat de Qdrant ne suffit pas à déclarer une hallucination.

Jeu : `tests/evaluation/memory-50-questions-v1.json`. Lanceur en lecture seule : `tools/evaluation/run_memory_50.py`. Les réponses sont contrôlées par identité canonique, rang et limites de taille, sans divulguer le contenu des souvenirs. Rapports JSON locaux dans le répertoire de validation G288.

## Architecture d'isolation recommandée

**Niveau 1 — venv + pytest** : isoler les dépendances Python; ne protège pas les fichiers, processus, sockets, GPU ou réseau. Utiliser les versions épinglées et les umask attendus, en évitant le venv de production.

**Niveau 2 — Qdrant jetable + corpus temporaire** : chaque test destructif possède son serveur enfant, son port loopback, sa clé et ses répertoires temporaires, avec nettoyage après exécution. C'est déjà disponible via `tests/qdrant_server_fixture.py` et le binaire Qdrant 1.15.4; **ne jamais utiliser le port de production 26333** pour les tests de corruption/reprise. Limiter RAM/CPU, interdire l'accès réseau externe si le scénario le permet.

**Niveau 3 — VM Proxmox dédiée** : utile pour panne du noyau, disque, système de fichiers, tests de sécurité ou d'isolation forte. Plus coûteuse en RAM/stockage et administration. À provisionner seulement pour ces scénarios; aucune nouvelle VM créée dans G291.

Le banc actuel interroge `127.0.0.1:18765/v1/recall` en lecture seule pour les 50 questions, avec une clé de lecture déjà existante. Il ne modifie ni Memory Bridge, ni les fiches canoniques, ni l'index Qdrant. Les tests destructifs restent confinés au Qdrant jetable.

## Critères de validation

- Zéro erreur HTTP ou contrat et aucune mutation canonique.
- Top1/top5 rapportés séparément pour les 30 positives; latence médiane et distribution à documenter.
- Les 20 négatives mesurent la présence de candidats, **pas l'abstention de Core**, qui exige un test de génération/réponse distinct avec références.
- Pour calibrer une décision automatique, constituer un corpus **indépendant** avec questions négatives proches, contradictions, reformulations sans mots-clés et annotations humaines; séparation entraînement/validation, taux de faux refus et faux accords.
- La bêta Core/Memory reste prioritaire. Pas de seuil de production adopté à partir des seules 50 questions.

## Résultats de la première campagne réelle

Le 22 octobre 2026, 50 requêtes HTTP authentifiées vers le bridge local ont été exécutées séquentiellement. **29/30 positives au rang 1 et dans le top 5, zéro erreur HTTP, latence médiane 4102,2 ms**. La question `positive-06-2` (« Quel moteur d’inférence propose des mécanismes de service pour plusieurs agents ? ») n'a pas ramené la fiche vLLM attendue dans le top 5 : question générique/ambiguë qui attire des documents Eidolon voisins. Il faut conserver cet échec et examiner l'ambiguïté, pas réécrire la question pour gonfler le score.

Les **20/20 négatives ont reçu cinq candidats**, ce qui ne prouve pas que Core hallucinerait. Surtout, le premier score d'une négative monte à **0,659** : il chevauche des scores positifs. **Un seuil universel fondé sur le score vectoriel est donc explicitement déconseillé.** Il faut un évaluateur de suffisance des preuves, des annotations indépendantes et un test de la réponse générée.

Les SHA-256 de **205 fichiers canoniques** sont inchangés entre la capture effectuée pendant le début de la campagne et sa fin; aucun fichier de mémoire n'a été modifié pendant le contrôle observé. Le rapport complet, sans contenu de souvenirs ni jetons, est local : `/home/toytoy/eidolon-validation/g288/memory-50-g291.json`.
