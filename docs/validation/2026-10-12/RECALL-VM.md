# Validation VM et rappel mémoire — 12 octobre 2026

Sur la base 4fe0b85, 2011 tests réussis. Après report du runtime MCP :
2015 tests réussis, 8 sous-tests. Le reranking ajoute trois tests de garanties :
exclusion avant score des éléments réfutés/expirés/futurs, statut UNVERIFIED
et provenance conservés, budget de caractères, scores invalides refusés.

Évaluation sur une copie du corpus (171 informations), empreintes inchangées :
- 35 questions existantes : rappel à 5 lexical 71,43 %, reranking 94,29 %.
- 14 nouvelles paraphrases figées avant ce réglage : 35,71 % puis 57,14 %.
- MRR : 0,468 puis 0,838 ; paraphrases 0,208 puis 0,500.
- Temps moyen CPU du reranking 128 candidats : environ 3,5 secondes.

Ce gain mesure la présence d'une fiche attendue dans cinq résultats, pas
la justesse d'une réponse générée. Les 14 questions portent encore sur les sept
fiches factuelles. Aucune garantie générale de rappel, de vérité ou d'abstention.
Un score ne transforme jamais UNVERIFIED en CONFIRMED.
Les modèles sont chargés depuis le cache local, sans téléchargement.

Le bridge canonique est installé sur 127.0.0.1:18765 avec authentification.
Le raccordement SSH distant Core->Memory reste bloqué par la revue automatique.
Les configurations privées et clés ne sont pas versionnées.
Publication des nouveaux commits GitHub bloquée par la revue automatique,
qui exige l'autorisation du dépôt et du contenu exacts.
