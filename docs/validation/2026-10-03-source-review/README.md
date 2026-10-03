# Correctifs après revue Claude — 3 octobre 2026

Code `be8eed7`, suite générale VM : **1742 réussis en 38,51 s**, avec
`.venv/bin/python -m pytest -q --ignore=tests/test_collaboration_mcp.py`.
15 cas MCP exclus, donc pas de suite complète revendiquée. Les preuves rouges
et ciblées de chaque lot restent dans ECHANGES.md et les contrats.

Lots inclus : pagination, D1 signature privée/citation obligatoire,
D2/D3 bibliothèque disponible sans relâcher audit ni purger les temporaires,
D5 drivers figés, D8 Basic UTF-8, mobile/fonds locaux. D3 diagnostic UI : aucune
réparation implicite du lot invalide. D5 conserve les pilotes v1 à l’identique.
Le nouveau lot mobile/fond n’a pas été essayé en navigateur sur cette VM ;
recette Chromium demandée à Claude. Ses anciens essais cloud ne constituent
pas une validation de ce nouveau lot. API HTTP live / et /sources : 200,
Basic erroné Unicode : 401 ; audit sources réel 1 source, aucune anomalie.
Aucun détail accepté par GPT et aucun original utilisateur modifié dans la recette.

SHA256 pytest.txt : `ce19e55a85212cdcc83f9dd260a1bf38ca92f8f9691f00b62a6bdcebccda0ef9`.
