# G250 — Âge inconnu, diagnostic honnête

Codex, 15 octobre 2026. Complément indépendant au module pur de Claude C182 ; le patch original 0039 est conservé.

Deux tests rouges démontraient que des dates connues mêlées à une date inconnue produisaient un âge maximal global non prouvé. `oldest_age_seconds` vaut maintenant `None` dès que `AGE_UNKNOWN` est présent. Le nombre `lagging` conserve les retards établis : une borne inférieure, pas un total exhaustif. Une intention connue en retard continue donc de produire `INDEX_LAGGING` ; une date inconnue ne masque pas cette preuve.

Le seuil reste fourni par l’hôte, aucune lecture d’horloge, aucun I/O, aucune activation. `worker_status` et son écart S1 historique ne sont pas modifiés. Deux régressions ajoutées au contrat CI ciblé ; validation complète distante à suivre dans le bilan de session.
