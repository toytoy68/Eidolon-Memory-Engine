# G180 — Intégration des quatre patchs Claude et correctifs, 12/10/2026

Auteur : Codex/GPT. Base Memory : 41854309ab212d5d732cbc7e8e551f2b4c11a08a.
Patchs Claude 0001–0004 lus depuis Core 13a60c6, appliqués par git am dans
un worktree isolé sur la VM Core. Aucun service/corpus Memory actif modifié.

## Livraison Claude intégrée

- A5-02 : politique de passage v3, contexte gauche et marqueurs omis.
- Corpus synthétique figé : 30 documents, 27 questions ; empreinte inchangée.
- Banc et résultats de rappel lexical, sans génération.
- Contre-revue Qdrant avec sondes indépendantes.
Les quatre patchs d'origine et leur attribution restent dans le dépôt Core ;
leurs commits git am sont conservés dans le worktree d'intégration.

## Contre-vérification et décisions Codex

**A5-02 : défaut supplémentaire corrigé.** L'expression régulière cherchait les
mots à partir d'une position située au milieu d'un mot ; elle considérait alors
le suffixe comme un nouveau mot. Deux cas rouges (budgets 18/24), puis verts :
recherche depuis le début de phrase, conservation des seules frontières
admissibles. Références et texte restent verbatim ; aucune paraphrase créée.

**Q4 : retrait de l'empreinte par texte.** Choix de l'alternative proposée par
Claude : payloads et résultats conservent ID/révision, plus de text_sha256.
Pas de clé HMAC à gérer dans cette première version. Le futur consommateur
doit relire le canonique et ses métadonnées ; la révision seule n'est pas une
preuve contre une modification directe d'un fichier. Vecteurs, manifeste et
index demeurent privés ; ceci ne promet pas leur anonymisation.
Les anciennes générations déjà créées ne sont pas purgées automatiquement :
leur retrait explicite reste requis si elles contiennent un ancien payload.
Ici les générations de recette ne contiennent que des données synthétiques.

**Q3 : provenance de fraîcheur explicite.** Chaque résultat porte source_digest
et index_freshness : FULL_REBUILD_SNAPSHOT ou UNVERIFIED_INCREMENTAL.
Un digest de reconstruction ne prouve pas que les fichiers sont restés
inchangés depuis. La revalidation canonique reste obligatoire.

**Q2 : migration par nouvel alias.** Un changement de modèle/prétraitement,
même à dimension identique, exige un nouvel alias explicitement créé.
Reconstruction/évaluation séparées, changement de configuration consommateur
seulement après validation, ancien alias gardé pour retour arrière.
Le remplacement implicite du modèle sur le même alias reste refusé.
La sonde a été adaptée à cette règle, plutôt que d'assouplir le contrôle.

Les trois xfail stricts sont devenus des tests ordinaires correspondant aux
solutions retenues. Leur version originale reste dans le patch 0004.
Q1 (collection disparue) a aussi été confirmé sur le serveur réel.

## Résultats reproduits

- Avant correctifs : 66 réussis, 3 xfail sur la sélection Claude/index/passages.
- Après correctifs : 71 ciblés réussis.
- Suite Memory complète : **2059 réussis, 12 subtests réussis, 64,19 s**.
  Aucun xfail, saut ou échec signalé. Exécution sur VM Core, corpus temporaires.
- Tests Qdrant et sondes Claude : **30 réussis, 10,56 s**, serveur Qdrant
  1.15.4 réel, client 1.15.1, vecteurs de hachage synthétiques.
- Serveur temporaire en loopback et arrêté après recette ; services Core
  et Memory de production non reconfigurés.

Les sondes Claude acceptent désormais EIDOLON_TEST_QDRANT_URL pour reproduire
le contrôle serveur ; le comportement local reste celui de leur fixture.
Cette adaptation du harnais a été vérifiée par les 30 tests serveur après
la suite complète. Elle ne modifie pas l'adaptateur ou le rappel.

Rejeu indépendant du corpus figé sur Core :
rappel@1 = 0,783 ; rappel@3/@5 = 0,826 ; 10/10 contrôles d'extraits ;
négation 3/3 ; paraphrases 1/5 ; abstention 0/4.
Latence de ce passage : médiane 6,42 ms, maximum 16,10 ms.
Ces mesures portent uniquement sur le rappel lexical, sans LLM et sur
27 questions synthétiques : aucun taux de fiabilité général n'en découle.

Preuves privées de recette sur Core :
/home/toytoy/eidolon-validation/memory-g180/
(full-suite.log, qdrant-server.log, baseline-vm.json, passage-red.log).
Un exemplaire synthétique du résultat de baseline est versionné à côté.

## Suite prioritaire

- Définir le découpage des archives et mesurer de vrais embeddings.
- Comparer sur le même corpus, sans modifier les réponses attendues.
- Traiter abstention et faits remplacés avant usage décisionnel.
- Synchronisation de l'index et revalidation canonique avant branchement bridge.
- Claude poursuit le dashboard PC G176, puis identité isolée G170.
Qdrant ne sert toujours pas la mémoire active après cette intégration.
