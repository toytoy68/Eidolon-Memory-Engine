# Audit indépendant Eidolon — 11 octobre 2026

## Accès réellement observés

Work → VM100 192.168.1.135 et VM110 192.168.1.110 : TCP 22, 5000 et 8766 renvoient Network is unreachable. Ces essais ne prouvent ni arrêt des VM ni état des services. Aucun service modifié.

HTTPS https://mcp.eidolon.re/mcp : GET non authentifié reçoit HTTP 403 Cloudflare, erreur 1010 browser_signature_banned, 2026-10-11T05:12:25Z. Ce résultat ne valide pas le transport MCP, Auth0 ou le serveur derrière Cloudflare. Aucun contournement du blocage tenté. Le plugin sélectionné ne fournit aucun outil Eidolon appelable dans cette session.

Le serveur MCP **publié** dans services/collaboration/server.py expose seulement read_gpt_message, write_claude_message et get_exchange_status. Aucun accès aux fichiers expérimentaux, shell ou état des VM. Ses lectures synchronisent Git et journalisent leur appel : elles ne sont pas sans effet disque. La version déployée demeure inconnue.

## Bases examinées

- Memory, refactor/architecture-v1 : 4fe0b85aecca0680acb92e555c3ebdb56847cbc0.
- Core, feat/eidolon-core-v0.1 : 02448ddc4024ff5dbf537f943cbd3d8421081d0f.
- Core : lecture des consignes et échanges; aucun changement ni test Core dans ce lot.
- Les résultats Claude C128/personnalité rapportés dans le contexte ne sont pas démontrés par cette base Core.
- context_router_v3.py, test_router_v3.py, corpus factual-v2 et laboratoire hybride absents des branches récupérées et de la recherche locale ciblée. Leur contenu et leurs performances ne sont pas audités.

Le score rapporté 27/30 = 90 % concerne la conformité aux étiquettes initiales. Il ne démontre pas la pertinence des souvenirs, leur provenance ou leur validité temporelle. Sans questions, labels, sorties et protocole, les trois écarts ne peuvent être qualifiés d’erreurs.

## Benchmark préparé

real-questions.json contient 40 questions indépendantes : matériel, infrastructure, mémoire, temporalité, provenance, absence de preuve. Elles ne réutilisent pas les 30 questions originales, qui sont indisponibles. Elles restent UNANNOTATED_NOT_SCORABLE : aucun identifiant/source attendu inventé depuis les souvenirs de conversation. Avant toute mesure réelle, annoter sur les Markdown figés : identifiants pertinents, révisions/empreintes, source, intervalle de validité, statut et abstention. Une réponse demandant un secret doit s’abstenir de le divulguer, même si un document l’a conservé.

synthetic-gold.json contient séparément 40 cas connus sur 32 Informations temporaires : huit sujets × direct, paraphrase, historique, UNVERIFIED, futur. Ces fixtures représentent un contrat artificiel, pas l’état de ton installation. Ne pas les importer dans les corpus réels.

Exécution depuis la racine Memory :

```sh
PYTHONPATH=. python tools/benchmark_independent_recall.py
python -m pytest -q tests/test_contextual_recall.py tests/test_lexical_ranking.py tests/test_recall_payload.py tests/test_memory_policy.py
```

Le script écrit seulement synthetic-results.json dans ce checkout et crée/détruit son propre dossier temporaire. Aucun paramètre ne pointe vers une VM ou un corpus canonique existant.

## Résultats réellement exécutés

| Mesure | Résultat |
|---|---:|
| Questions synthétiques | 40 |
| Rappel à 5, 32 cas avec cible attendue | 26/32 = 81,25 % |
| MRR sur ces 32 cas | 0,8125 |
| Questions directes | 8/8 |
| Paraphrases | 2/8 |
| Cibles historiques | 8/8 |
| Cibles UNVERIFIED | 8/8 |
| Abstention sur questions exclusivement futures | 0/8 |
| Violations des garanties contrôlées sur les résultats retournés | 0 |
| Empreintes corpus temporaire avant/après rappel | identiques |
| Tests existants ciblés | 79 réussis, 0 échec |

Latence médiane des médianes de trois répétitions : environ 6,12 ms sur le petit corpus temporaire de Work, setup et contrôles exclus. Pas de comparaison valable avec les 91,5 ms du routeur VM : environnement, corpus et opération différents. Trois répétitions ne constituent pas une distribution robuste; conserver les échantillons dans synthetic-results.json.

Les contrôles vérifient statut inchangé, provenance/temporalité/révision identiques au fixture, avertissement pour statut non confirmé et absence EXPIRED/OUT_OF_SCOPE en opérationnel. Ils ne prouvent pas authenticité des preuves ni état du système réel. La précision par question et les réponses complètes sont consignées dans le JSON. Un score de rappel seul cache les résultats hors cible.

## Comparaison disponible et limites

| Stratégie | Exécutée | Conclusion |
|---|---|---|
| lexical_v1 + politique publiée | Oui, synthétique | Bon rappel exact, paraphrases faibles, abstention insuffisante |
| Fiches factuelles / routeur VM v0.3 | Non | Fichiers et données manquants |
| MiniLM + fusion RRF | Non | Prototype et poids manquants |
| Cross-Encoder | Non | Prototype et poids manquants |

Aucune fausse équivalence entre politique contextuelle publiée et routeur expérimental v0.3. Aucun classement de stratégies non exécutées.

## Défauts et décisions

1. Six paraphrases ratées démontrent une limite de couverture lexicale, pas un défaut temporel. Ne pas ajouter une table de synonymes ajustée à ces huit questions ni promouvoir les suppositions.
2. Les huit requêtes futures excluent correctement la donnée pas encore valide, mais retournent les fiches actuelles/hypothèses du même sujet. La recherche partielle n’assure donc pas l’abstention. La politique publiée n’annonce pas de garantie de réponse : ce constat nécessite une décision de consommation/pertinence, pas un durcissement arbitraire du score lexical.
3. Un historique consulte les objets actuels conservés, pas toutes leurs anciennes révisions. Ne pas assimiler historical à une reconstruction complète à une date passée.
4. Aucun correctif au routeur v0.3 livré : source absente. Aucun code métier modifié sans défaut reproductible attribuable à ce code. Les seuls ajouts sont ce benchmark et ses preuves. Les 79 tests passent; les régressions du routeur restent inconnues faute de base comparable.

## Comparaison réelle à effectuer

Figer un snapshot des 171 Informations, SHA-256 par fichier et SHA du code; vérifier le compte 164 + 7. Annoter les 40 questions avant de régler les stratégies. Conserver un lot de réglage distinct de ce lot d’évaluation. Capturer classement brut et résultats après une **même** politique de temps/contexte/statut/provenance, pour isoler qualité de classement et sécurité. Ne jamais laisser un reranker promouvoir UNVERIFIED.

Mesurer rappel/precision à 1 et 5, MRR/nDCG sur jugements gradués, bonnes abstentions, provenance complète, sources réellement résolubles, révisions correctes, absence d’affirmation confirmée sans preuve, conflits/expirations, latences froides et chaudes (p50/p95), coût CPU/RAM et chargement des modèles séparé. Compter les doublons source pour ne pas favoriser les fragments répétés. Comparer les mêmes questions et mêmes budgets de sortie. Rapporter chaque régression, pas seulement la moyenne.

## Accès sécurisé proposé

Option immédiate sans accès distant : sur VM110, créer un export en lecture du routeur, du benchmark original avec sorties, des prototypes et d’un snapshot autorisé/anonymisé du corpus. Exclure clés, tokens, exports personnels non requis. Joindre manifeste SHA-256, versions Python/dépendances et configuration des modèles. Cela permet l’audit sans modifier les services.

Pour un pilotage réel : SSH via réseau privé autorisé et compte dédié sans sudo; pas de port SSH ou Qdrant ouvert publiquement. Vérifier les clés hôtes hors bande. Limiter écritures à un nouveau répertoire d’expériences et accès au corpus à une copie. La présence d’un VPN sur ton PC ne garantit pas que Work y soit raccordé.

Alternative MCP : après autorisation explicite de modifier/installer ce service, exposer uniquement diagnostic expurgé, lecture de chemins autorisés et lancement de benchmarks prédéfinis, avec authentification, scopes distincts, journaux expurgés, limites CPU/temps et sans shell arbitraire. Ne pas élargir implicitement le MCP de collaboration. La correction de Cloudflare doit être ciblée et autorisée, sans désactiver globalement sa protection. Aucun de ces changements n’a été effectué.

Priorité : accès aux preuves et politique de réponse fiable avant ajout d’algorithmes. La mission réelle reste partiellement bloquée par l’accès et les fichiers absents.
