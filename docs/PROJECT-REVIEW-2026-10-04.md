# Étude du projet — 4 octobre 2026

Base examinée : f3aaf3b, branche refactor/architecture-v1. Lecture des contrats,
TODO, code de validation et rapports reçus ; pas de nouvel audit VM complet.

| Domaine | Preuves disponibles | Travail prioritaire |
| --- | --- | --- |
| Stockage, reprise, concurrence | Tests unitaires et VM ; neuf gardes de morts de processus intégrées | Conserver readiness et verrous ; pas d'assouplissement implicite |
| Import et rappel ChatGPT | Corpus réel importé ; recette PASS, références exactes, 1824 tests VM sur 9819d6b | Revue indépendante des quatre commits ; pertinence sémantique non évaluée |
| Sources et détails | Originaux exacts, pilotes versionnés, validation humaine, identité v2 | Contrat F1 : extraction légitime substituable ; coût du scan des Informations |
| Dashboard | Jauges compactes confirmées ; service systemd installé selon rapport | Recette visuelle du mode texte et retour à grande fenêtre |
| Installateur | Transport environnement corrigé, quatre tests simulés verts | Vrai setpriv root et chemins de panne non validés opérationnellement |
| Parcours métier | Routage, projets, dossiers, catalogue, entretien et reprise partiellement livrés | Étendre les branches après réduction des incertitudes sources/exploitation |
| Performance | Lots/index/compaction mesurés ; lectures résiduelles linéaires | Mesurer validation source séparément avant cache/index ou ingestion intensive |

Le socle est suffisamment éprouvé pour poursuivre des essais contrôlés. Les
preuves ne suffisent pas à déclarer toute l'exploitation validée : reboot,
restauration complète au candidat, upload sous cloisonnement, IA locale réelle
et pertinence des réponses restent distincts. Un nombre de tests croissant
ne remplace pas une preuve de parcours utilisateur.

La priorité retenue est de réduire ces incertitudes avant d'ajouter une campagne
IA. Le coût des validations est mesurable sans décider les règles de purge ou
de déduplication sémantique. F1 exige un contrat durable et une compatibilité
explicite ; aucun changement de validation n'est engagé pendant la revue.

Répartition et critères : collaboration/GPT-TO-CLAUDE.md, missions C1 à C3.
GPT a livré le benchmark synthétique des détails : 18 points PASS, 58 tests
ciblés verts ; voir SOURCE-DETAIL-COST.md. Le rejeu évite le scan de compatibilité
mais conserve les contrôles globaux, donc son coût augmente aussi avec le corpus. Les corpus sont temporaires,
les rapports ne contiennent que mesures, identifiants factices et empreintes.
L'estimation globale 45 % reste gelée : cette étude ne redéfinit pas les poids.
