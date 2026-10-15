# G245 — Pont HTTP Memory borné, 15 octobre 2026

Codex/GPT. Base : Memory 22f6a70e674da1b9c3291806e7d9d88cf1da779b.

## Défauts reproduits et correction

L'ancien pont acceptait deux Content-Length, Transfer-Encoding et deux
Authorization : trois requêtes ambiguës ont réellement répondu HTTP 200 avant
modification. Les nouveaux cas ont été exécutés rouges avant code.

- `BoundedRecallServer` n'écoute que sur 127.0.0.1 ; huit connexions acceptées en
  traitement par défaut, limite hôte explicite de 1 à 32. Au-delà : 503 BUSY,
  fermeture, pas de nouveau thread de traitement ni de mise en file applicative.
- Une échéance monotone unique de trois secondes par défaut couvre ligne de
  requête, en-têtes et corps. Le lecteur applique le temps restant à chaque
  lecture réseau, y compris avec des octets envoyés au compte-gouttes. Une
  lecture du corps expirée produit 408 ; un en-tête expiré ferme la connexion.
- Un seul Authorization ASCII, un seul Content-Length décimal et aucun
  Transfer-Encoding. Corps borné à 4096 octets, doublons JSON/nombres non finis
  et requêtes blanches refusés. Erreur de profondeur du décodeur : 400 générique.
- Réponse JSON UTF-8 stricte, sans conversion implicite de valeurs arbitraires,
  sérialisée une seule fois et limitée à 128 Kio. Exception privée : 503 générique.
  Un client déconnecté ne provoque pas de seconde réponse ni de fuite de détail.
- La capacité est libérée même après erreur. Le verrou existant conserve un
  seul rappel à la fois. Le point d'entrée CLI utilise le serveur borné ; aucun
  endpoint d'écriture ou configuration Qdrant distante n'est ajouté.

## Validation exécutée

40 tests ciblés +5 sous-tests réussis avec `-W error` : en-têtes ambigus,
authentification, corps court/expiré/lent, en-têtes lents, saturation et reprise,
JSON invalide, données non sérialisables, limite UTF-8 et HTTP réel avec
ContextualRecall/Qdrant local. Le dernier trajet vérifie un rappel vide périmé,
une reconstruction concordante et une modification à révision inchangée exclue.
Les erreurs réseau restent des erreurs, sans repli lexical ni détail privé.

La suite générale GitHub inclut ce fichier de service dans ses déclencheurs.
Résultat complet G245 à confirmer. G244 Memory confirmé : 2686 réussis,
18 ignorés (exécutés dans la recette dédiée), 4 xfail, 12 sous-tests ;
18 scénarios serveur réussis et 52 worker. Qdrant ciblé G243 : 406 +1 xfail.

## Limites

L'échéance borne la **lecture HTTP**, pas une fonction recall déjà en cours ni
l'embedding. Le fournisseur doit conserver ses propres délais réseau. Un rappel
bloqué garde sa capacité ; aucun arrêt forcé de thread n'est présenté comme sûr.
La file TCP du système reste distincte des traitements applicatifs bornés.
Le sérialiseur reçoit des objets de confiance du fournisseur : la taille de la
réponse réseau n'est pas une garantie de consommation mémoire du fournisseur.
L'accès reste local/SSH existant ; aucune installation, tunnel ou activation
sur VM et aucun corpus privé utilisé. Aucun benchmark sémantique relancé.
