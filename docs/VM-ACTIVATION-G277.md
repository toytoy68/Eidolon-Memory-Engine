# G277 — fiabilité de la lecture de configuration, 16 octobre 2026

La recette VM a établi que deux écritures rapides de même taille peuvent conserver mtime et ctime. Le lecteur JSON compare maintenant deux lectures bornées de contenu en plus des métadonnées et de l'identité du chemin. Test indépendant avec horodatages neutralisés ; aucun snapshot atomique n'est revendiqué.

Suite complète sur la VM Memory, clone Git dédié : **3 157 réussis, 26 ignorés, 3 xfail existants, 12 sous-tests**, Python 3.13.5. Le correctif et son test sont isolés du corpus privé. Le rapport opérationnel global est tenu dans Core, lot G277.
