# Échéances pass-local — 3 octobre 2026

Base `0b02f31`, deux cas paramétrés rouges avant correction ; 74 ciblés verts,
puis 42 ciblés après copie défensive du rapport. Version finale figée :
**1732 réussis en 38,36 s**, avec `.venv/bin/python -m pytest -q
--ignore=tests/test_collaboration_mcp.py` sur VM et corpus de tests indépendants.
15 tests MCP exclus, aucune recette d’entretien du corpus utilisateur.

Les tests comptent un appel _deadlines sur passe inactive dans les deux modes,
puis vérifient qu’une passe ultérieure à l’échéance relit et applique le trigger.
Un seul inventaire reste vérifié par les tests du lot précédent. Les rapports
conservent leur structure et séparent les objets de lecture par copie défensive.
Pas de cache entre passes, pas de nouvelle mesure de latence ni de suppression
des lectures des autres phases ; écrivains legacy et coupure hors garantie.

SHA256 pytest.txt : `166d423a904dc53affa4896ed7f31affccac9303f4b3909b42e601eefa6f303e`.
