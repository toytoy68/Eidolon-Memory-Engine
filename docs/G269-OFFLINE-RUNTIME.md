# G269 — runtime candidat, préparation hors VM

15/10/2026, Codex/GPT. C191 et patch 0067 reçus (auteur Claude conservé).

## Contrats livrés

- `services.memory_bridge --index-config /chemin/index.json` sélectionne explicitement un alias existant. Le défaut lexical reste compatible. Aucun repli silencieux si l’index sélectionné échoue ; 503 côté rappel. `--check-storage` refuse cette option, code 64, sans modèle/réseau.
- `python -m core.indexing.runtime --config /chemin/index.json check-config` est hors réseau. `status` observe Qdrant. `rebuild --persistent-root /copie/memory/persistent --stopped-copy [--create-alias]` modifie explicitement l’index dérivé ; ne l’utiliser que sur une copie arrêtée et un alias de recette.
- `projection=documents` : index documentaire et maintenance incrémentale existants. `projection=archive_passages` : adapter `QdrantPassageIndex`, projection durable distincte, archives par passages 1200/160 et documents ordinaires. Reconstruction complète uniquement. Aucun partage d’alias avec le worker documentaire.
- Embeddings Ollama local CPU, modèle/digest explicites, vérifiés avant/après chaque appel, aucune troncature silencieuse ; prétraitement de requête distinct. Le descriptor lie l’empreinte du modèle et le prétraitement. Aucun téléchargement.
- `python -m core.information.remember --input /chemin/remember.json` prépare un aperçu sans writer. Ajouter `--root /copie --approve-sha256 <empreinte de l’aperçu>` écrit via le journal existant. Rejouer les mêmes octets/identifiants après interruption ; ne jamais générer un nouvel identifiant pour contourner un conflit. Le souvenir est UNVERIFIED, pas une vérité confirmée. L’aperçu contient le texte : le conserver dans un emplacement privé.

## Limites

Code candidat testé sur données synthétiques, pas de qualification sémantique réelle. L’index de passages ne gère pas encore les mises à jour incrémentales ; le budget de candidats compte les passages, le rappel retient au plus un passage par document. Les générations anciennes/échouées restent conservées : aucun nettoyage automatique. `--stopped-copy` est une attestation opérateur, pas un gel du système de fichiers. Les alias exigent un writer unique.

Le pont reste en lecture seule fonctionnelle ; l’isolation UID/montage est à qualifier sur VM. Une configuration hôte doit se trouver dans une arborescence de confiance, non modifiable par un autre compte. Aucun secret Qdrant ou accès distant n’est ajouté : endpoints loopback seulement, sans proxy de l’environnement. Les délais sont des délais d’I/O, pas une garantie de temps total d’inférence.

La mémorisation est une commande opérateur locale ; le bouton/parcours conversationnel Core et l’authentification multi-profils ne sont pas encore raccordés. Aucun producteur automatique de reçus d’activité utilisateur n’est prétendu installé.

Dossier PC/VM commun : dépôt Core, `eidolon-core/weekend/2026-10-17/`.
