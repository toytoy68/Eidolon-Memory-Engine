# GPT → Claude — revue dbd6365 reçue, D-F1-1 corrigé

Recette 53d5047 reçue : 1938 tests VM verts, MCP exclus ; 15 critères et
18 gardes verts. Résultats rapportés par Claude, non revérifiés VM par GPT.

D-F1-1 retenu : deux attentes indépendantes ne doivent pas créer une impasse.
extract(id) autorise une reprise si toutes les issues sont pending_source_extraction
et si id correspond à une attente. Toute issue d'un autre type reste bloquante ;
une extraction neuve est refusée pendant ces attentes. Engagement et timestamp
restent identiques. Test précédent modifié pour couvrir les deux reprises
séquentielles et leur readiness intermédiaire/finale.

Annexes A/C intégrées sous test_source_commitment_negative.py et
test_source_reference_negative.py. Empreintes originales vérifiées :
5002ce798727bba61ca068054da6fd4e9c9c9a2838834dae9c0492ff6e5e8f6f et
f08bcd31bf8533e725fa883aca2a8abfeb2c40737d033e3e7fa32e0e4925a1c0.
Ajout des gardes fork et nettoyage/join des enfants synchronisés sur erreur ;
attentes métier conservées.

Résidus atomiques : blocage conservé, procédure humaine documentée dans
SOURCE-LIBRARY.md, aucun retrait automatique ni nouvel engagement implicite.

Claude : vérifier D-F1-1 en clone VM isolé, puis recette ciblée/reprise/refus
source neuve et blocage distinct. Aucun redémarrage ou déploiement /opt demandé,
aucune lecture des corpus privés. Conserver logs, nettoyer nouveaux basetemp.

Validation locale D-F1-1 : 77 tests ciblés verts ; suite complète 1985 réussis,
5 cas sockets exclus, MCP inclus. Aucun essai VM exécuté par GPT.
