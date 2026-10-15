# G270 — Profils, écriture explicite et passages incrémentaux

Codex/GPT, 15 octobre 2026. Suite de G269, sans déploiement ni corpus réel.

Le pont conserve son rappel par défaut. `--profile-id` exige une liaison préparée
par `python -m services.profile_binding --root ROOT --profile ID --apply`.
Le mode de vérification sans `--apply` ne crée rien. Un autre profil sur la même
racine est refusé. La liaison technique est en dehors des répertoires canoniques.
La racine doit être réellement isolée pour cette personne ; cette commande ne
sépare, ne déplace et ne nettoie aucun ancien corpus partagé.

`--remember-profile ID` (égal à `--profile-id`) active `/v1/remember` avec
`EIDOLON_MEMORY_WRITE_TOKEN`, obligatoirement distinct du jeton de rappel.
Les modes `--read-only-storage` et `--check-storage` excluent cette écriture.
La confirmation exacte et l'identité de personne relèvent du Core appairé ; le
pont n'accepte que l'acteur fixé au démarrage. L'écriture réutilise le journal
canonique, le reçu et l'identifiant stable de G269. Un refus HTTP peut cacher
un effet déjà commis : reprendre exclusivement la commande originale, jamais
inventer un nouveau request_id après une réponse perdue. Aucun texte de modèle
ne vaut confirmation. L'information reste OBSERVATION / UNVERIFIED.

`python -m core.indexing.runtime --config INDEX.json sync --persistent-root ROOT`
calcule seulement les vecteurs des documents ajoutés/modifiés. Les autres
vecteurs sont copiés vers une nouvelle génération. Inventaire canonique, copie
des vecteurs et contrôle final restent O(N) : **pas** une mise à jour O(1).
Les passages d'une archive changée sont remplacés ensemble. Le manifeste doit
rester identique avant publication et l'alias reste ancien sur toute erreur ou
reprise d'activité. Une synchronisation sans changement ne crée pas de génération.
Aucune génération ancienne ou échouée n'est supprimée. L'API du worker un-point
par document reste volontairement refusée pour cette projection ; Core utilise
le chemin de maintenance dédié. Un seul écrivain coopérant de l'alias est requis.

Les preuves sont les tests G270 et le test supplémentaire de reprise sur serveur
Qdrant réel. Les comptes, montages, modèles Ollama et performances nécessitent
la recette du week-end. La publication des sources n'active aucun service.
