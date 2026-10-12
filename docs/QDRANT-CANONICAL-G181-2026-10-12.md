# G181 — Candidats Qdrant relus par le rappel canonique
Auteur : Codex/GPT. Date : 12/10/2026, Europe/Paris.
Base : 03157fcaf7ca901325583544c5e2c62a07eb4ee6, refactor/architecture-v1.

## Changement livré
ContextualRecall accepte un index optionnel et une borne candidate_limit
(100 par défaut, maximum 1000). Sans index, le parcours lexical est inchangé.
L'objet index est fourni par du code de confiance, pas par une requête utilisateur.

Un appel index fournit un lot borné d'identités, scores et révisions.
Le lot est validé avant adoption ; résultat mal formé ou panne remontent en
erreur, sans repli lexical silencieux. Les doublons sont ignorés.
Chaque identité est relue depuis le backend Markdown choisi ; absence et
révision différente sont exclues et comptées. Aucun corps, provenance ou état
épistémique n'est accepté depuis l'index. Un nouvel appel relit le canonique.

Les filtres existants de ContextualRecall restent appliqués avant le budget
d'extrait : projet, disponibilité, applicabilité, expiration, réfutation,
remplacement et suppression en attente. Le mode historique reste explicite.
Les limites caractères/tokens restent celles de ContextAssembler.
Le score de candidat et les métadonnées d'index sont identifiés séparément
du contenu canonique ; ce score ne prouve ni vérité ni pertinence suffisante.

## Usage programmatique isolé
```python
reader = ContextualRecall(canonical_backend, index=configured_qdrant_index,
                          candidate_limit=100)
bundle = reader.recall(query, query_scope=trusted_scope, at=explicit_timestamp)
```
Backend et alias doivent déjà être sélectionnés pour le périmètre autorisé.
query_scope est un filtre d'applicabilité, PAS une authentification utilisateur.
Ce lot ne met en place aucun droit multi-profil et ne modifie pas le bridge.

## Vérifications exécutées sur Core
Worktree isolé : /home/toytoy/eidolon-worktrees/memory-g181.
Données synthétiques uniquement ; aucun corpus Memory actif modifié.
- Avant implémentation : 24 échecs des nouvelles attentes, 1 contrôle lexical réussi.
- Tests ciblés : 43 réussis en 1,29 s.
- Suite complète : 2087 réussis, 12 sous-tests réussis en 68,36 s.
- Vrai Qdrant 1.15.4, HTTP loopback : 3 scénarios réussis en 1,70 s
  (filtres/extrait, retard de révision puis upsert explicite, orphelin/suppression).
- git diff --check : sans erreur. Serveur Qdrant temporaire arrêté.
Journaux : /home/toytoy/eidolon-validation/memory-g181/
(red.log, targeted.log, full-suite.log, qdrant-server.log).

## Limites et suite
- Aucun déploiement du rappel vectoriel de production. Embeddings des tests
  synthétiques ; aucun gain sémantique mesuré par ce lot.
- Le contrôle de révision ne détecte pas une édition directe conservant la
  révision ; le contenu est cependant toujours relu dans le Markdown courant.
  Le classement peut alors être périmé. Les verrous protègent les writers
  coopérants, pas les écritures externes qui les ignorent.
- Le query index a lieu sous les verrous canoniques. Le client doit avoir
  un timeout adapté (3 s dans les tests Qdrant) ; pas de garantie de délai
  pour un adaptateur injecté arbitraire.
- Le top-K borné peut être épuisé par des candidats exclus. Un résultat vide
  n'établit pas l'absence de réponse dans tout le corpus.
- Les archives ChatGPT gardent leur sélection lexicale de passage :
  un document trouvé sémantiquement sans chevauchement lexical peut ne pas
  fournir d'extrait. Découpage/indexation par passages encore nécessaires.
- Pas de seuil d'abstention improvisé à partir du cosinus. Le corpus figé G180
  reste la référence d'évaluation ; résultats G180 non remesurés ici.
- InMemoryIndex de référence ne fournit pas encore les révisions dans ranking ;
  ce parcours exige un index à révisions, notamment QdrantIndex G180.
Prochain lot : passages d'archives et embeddings réels évalués, puis
synchronisation incrémentale et raccordement bridge avec périmètres autorisés.
