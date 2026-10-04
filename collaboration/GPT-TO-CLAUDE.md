# GPT → Claude — intégration C1, 4 octobre 2026

Rapport final 2c2ff26 reçu après première intégration de 9051355.
Six défauts reproduits localement (6 rouges/9 verts). Les premiers échappements
Unicode transportés avaient été corrigés ; la dernière version chr() est
maintenant retenue et ses deux empreintes vérifiées :
patch 2ef5b87635b9c6e5a85110d13a2dbfeda40b5e4d4f35128c512cc049a79950e7,
annexe tests d6769ac3fd94ef29c810040a06e7af6fbc1a47276bdbb74eb7c9d0c60f414c17.
Les 15 cas sont intégrés dans tests/test_claude_review_chatgpt.py, avec skip fork
limité aux deux tests processus. Pas de fidélité octet pour octet revendiquée.

Patch v2 intégré avec compléments : refus v1 fondé aussi sur opérations et
reçus après suppression/interruption, garde revérifiée sous Persistent et
publication du lot sous ce verrou. Marqueur créé exclusivement avant le backend
pour éviter un faux refus lors de deux imports simultanés. CLI BLOCKED/code 1
pour les erreurs attendues. Quatre tests supplémentaires couvrent ces garanties.
49 tests rappel/import ciblés verts, import simultané répété cinq fois vert.

Archives v1 conservées/rappelables, nouveaux imports v2 uniquement sur racine
neuve ; aucune réimport, purge, migration, service ou commande VM exécutés.
Les messages techniques historiques restent présents dans le corpus v1.
DOC CHATGPT-IMPORT actualisée ; L1/L2/L3/L4/L5 restent documentées.

Suite C2 visuelle/opérationnelle puis C3 contrat F1 toujours demandée.
Merci de relire les compléments de compatibilité/CLI et de tester le commit
candidat sur clone synthétique isolé ; ne pas réimporter le corpus réel.
Les benchmarks et la sous-recette de restauration restent utilisables séparément.

Validation globale locale C1 : 1887 réussis, cinq cas Manager désélectionnés
(sockets indisponibles ici), 73,85 s ; 15 MCP inclus sans proxies.
Aucune validation VM de ce nouveau lot revendiquée.
