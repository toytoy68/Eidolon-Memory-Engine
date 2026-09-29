# Assemblage de contexte — première interface interne

`core.retrieval.ContextAssembler` reçoit un backend conforme à `MemoryBackend`
et une requête textuelle. Il retourne une structure contenant des extraits de
contenu, les identifiants Information, leurs révisions, les scores fournis par
la recherche et un indicateur de troncature. Il ne crée pas de prompt et n'écrit
aucun fichier.

Les limites par défaut sont 5 Informations, 4 000 caractères de contenu au
total et 1 000 caractères par Information. Les limites comptent les caractères
Python, **pas les tokens d'un modèle**. Les résultats conservent l'ordre du
backend ; les contenus absents ou non textuels sont ignorés, ainsi que les
identifiants répétés. Un appelant ne doit pas interpréter ce résultat comme un
instantané cohérent si des fichiers changent pendant la recherche.

Cette interface est un point de départ vérifié sur les fichiers core. La
pertinence, les filtres d'accès, le rendu sûr pour un modèle, le budget en
tokens, la sélection épistémique et la recherche Qdrant reconstructible restent
à définir avant l'intégration à Eidolon Core. Aucun texte récupéré ne doit être
interprété comme une instruction du moteur.
