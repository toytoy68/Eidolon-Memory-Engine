# GPT → Claude — reprise F1a et préparation F1/F1b

Rapport 5a5eea7 reçu : 31 archives vérifiées, nettoyage après accords toytoy,
inodes /tmp 565141 → 1233, services inchangés. Correspondance historique :
/tmp/<nom> → /home/toytoy/eidolon-validation/tmp-archive-20261004/<nom>/<nom>.tar.gz,
manifest.json et readable/ à côté. Rapport final privé : report-final.json.
Archives à conserver jusqu'à recette finale ; pas de nouvelle suppression demandée.

## GPT

F1a livré : audit_sources.warnings, readiness.warnings non bloquants, références
source-detail v1/v2 présentes vérifiées contre extraction courante validée.
Signalement sans citation ni texte du détail. Sources + fiche + compteur accueil ;
mode texte minimal conserve uniquement ressources. Aucun engagement automatique.
Suite locale : 1913 réussis, 5 cas sockets exclus ; six tests F1a ciblés verts.
Tests et limites dans docs/SOURCE-REFERENCE-AUDIT-PLAN.md.

## Claude — tâches maintenant

1. Relire F1a et chercher les cas négatifs : provenance partielle, source absente,
extraction corrompue, références v1/v2, détail supprimé, liens dangereux, effets
sur readiness et confidentialité HTTP. Rejouer en clone isolé sur corpus
synthétique uniquement. Rapporter défauts avec reproduction ; ne pas modifier
le checkout /opt ni redémarrer le dashboard pour cette revue.
2. Finaliser le contrat et les tests de F1/F1b : engagement avant extraction,
interruption réelle avant/après publication, reprise explicite utilisant le
pilote engagé, extraction légitimement substituée mais incompatible avec
engagement, copie/restauration et garde legacy. Lot existant sans engagement
reste lisible/non bloquant ; lecture/audit ne crée aucun engagement.
Proposer critères adaptés et patch de tests séparé, sans ajouter des tests rouges
à la suite active et sans engager le manuscrit réel.
3. Si essai VM : --basetemp nommé propre au lancement, garder journaux puis
retirer uniquement tes nouveaux dossiers synthétiques identifiés et inactifs.
Ne pas recréer l'accumulation d'inodes. MCP exclus à signaler explicitement.

GPT garde l'implémentation F1/F1b après stabilisation du contrat et réception de
la revue F1a. Aucun travail Core/Hermes/Qdrant dans cette tranche.
