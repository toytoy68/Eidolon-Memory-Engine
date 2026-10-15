# G238 — Recette du worker sur serveur Qdrant jetable

Codex/GPT, 15 octobre 2026. Base Memory G237
`096e7bcc81258cc50510e6b0fa9e0d85ebc3e7af`.

## Périmètre

Neuf scénarios du worker et de la maintenance utilisent un vrai serveur HTTP
Qdrant 1.15.4, un journal SQLite et des fichiers Markdown synthétiques. Le serveur
est un sous-processus possédé par le harnais, dans le dossier privé de pytest.
Il n'accepte aucune URL applicative. Un port loopback libre est choisi, gRPC et
cluster sont désactivés, la télémétrie est désactivée. Une clé aléatoire propre
au test évite de prendre un autre serveur local pour celui attendu. Seul le PID
créé par le harnais est arrêté ou tué ; les données de test sont jetables.

Le workflow télécharge l'archive Linux GNU officielle v1.15.4 et vérifie SHA-256
`8d0f3af71b4606581c6d4d943c0763aa7f368a7ee801b2f01e16ab2376e8f363`
avant extraction. Digest revérifié par l'API GitHub de la release officielle le
15/10, identique à celui de G179. Client épinglé à 1.15.1 via requirements-qdrant.
Configuration vérifiée contre config/config.yaml du tag serveur v1.15.4.
Ce choix reproduit la version déjà qualifiée en G179 ; ce n'est pas une
recommandation de version de production actuelle.

## Scénarios

1. Publications interrompues, cycle complet, rebuild avec provenance sans
   ré-encodage par la maintenance, puis réouverture après redémarrage.
2–3. Réponse perdue simulée après un vrai upsert HTTP acquitté : redémarrage
   propre et SIGKILL séparés ; reprise par relecture sans nouvel embedding.
4. Panne HTTP réelle (serveur arrêté), report durable puis reprise.
5. Descripteur incompatible : aucune publication d'INTENT.
6. Revue d'orphelin sous budget exact, aucune suppression avant/après restart.
7. Inventaire supérieur à sa borne : pas de faux CYCLE_COMPLETE.
8. Document au-dessus de la borne : revue et progression de la ligne saine.
9. Défaut d'horloge persistant au restart serveur, reprise auditée puis effet
   seulement au tick suivant.

La perte de réponse est injectée dans le client après réception de l'acquittement,
pas par un proxy réseau. SIGKILL qualifie un arrêt de processus, pas une coupure
électrique ni une transaction distribuée. Vecteurs synthétiques uniquement ;
aucune mesure sémantique, corpus privé, VM ou service existant.

## Exécution et preuves

`EIDOLON_TEST_QDRANT_BINARY=/chemin/vers/binaire-vérifié python -m pytest -q -rs
-W error tests/test_qdrant_server_maintenance_g238.py`.

Sans ce chemin explicitement fourni, les neuf cas sont ignorés avec motif. Le
workflow dédié le fournit après vérification de l'archive et exécute les tests
avec avertissements traités en erreurs. Un chemin fourni mais invalide échoue ;
il ne devient pas une exclusion silencieuse. Résultat JUnit et seuls logs serveur
conservés sept jours, pas les configurations contenant les clés temporaires.

Collecte initiale rouge (harnais absent), puis neuf cas correctement collectés et
explicitement ignorés ici, où aucun binaire serveur n'est disponible. **La recette
réelle n'est pas encore déclarée réussie : résultat CI à récupérer.** Ce lot
n'a pas de modification du code applicatif. Le canal MCP a été revérifié une
fois et renvoie encore une erreur interne ; aucune commande VM exécutée.

G237 est confirmé : Memory 38662413157, **2619 réussis, 5 xfail, 12 sous-tests**,
134,04 s ; vrai contrat worker **52 réussis**, 2,40 s. Qdrant 38662413171 :
**312 réussis, 1 xfail**, 55,61 s. Core épinglé G236, workflow 38662300287 :
**1786 réussis, 7 ignorés, 1299 sous-tests**, 250,09 s, aucun avertissement pytest.
