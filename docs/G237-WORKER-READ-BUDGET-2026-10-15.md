# G237 — Lectures canoniques bornées du worker journal

Codex/GPT, 15 octobre 2026. Réponse à R1 de la contre-revue Claude.
Base : Memory G236 `8a93466038a80fbaaf3eadc136d139c9739c863e`.

`JournalUpsertWorker(..., max_file_bytes=8 * 1024 * 1024)` utilise désormais un
CanonicalReader borné pour toutes ses lectures, y compris INTENT→PUBLISHED,
lecture avant/après effet et récupération d'un accusé perdu. La limite porte
sur les octets du fichier Markdown complet, pas seulement son texte utilisateur.
La valeur par défaut reprend les 8 Mio du scanner canonique existant.

`IndexMaintenance(..., max_file_bytes=...)` transmet la même politique au worker
et au scanner canonique, et la lie au contexte du contrôleur. La valeur par
défaut conserve la représentation historique du contexte ; toute autre valeur
est inscrite et doit rester identique à la reprise. Modifier la politique d'un
contrôleur existant nécessite des checkpoints distincts, comme pour max_points.

Un fichier trop grand produit `CANONICAL_TOO_LARGE` et reste pending pour revue.
Il ne prouve ni absence ni corruption. Les lignes suivantes restent traitées,
la revue durable conserve ce motif, aucune clôture ni suppression n'est faite.
Si la taille augmente après un effet déjà exécuté, cet effet ne peut pas être
annulé : la ligne reste pending et sera réévaluée, sans INDEXED mensonger.

Le lecteur vérifie la taille avant lecture puis lit au plus limite+1 octets ;
une croissance concurrente ne permet pas une lecture sans borne. Chaque relecture
utilise la même limite. Les limites nulles, non entières, booléennes, négatives ou
hors de la capacité native de read sont refusées à la construction. La limite
exacte est acceptée. L'hôte reste responsable du choix d'un budget raisonnable.
Ce budget n'est pas une mesure de RSS : décodage, parsing et copies peuvent
consommer plusieurs fois la taille du fichier. Le budget global de snapshot
canonique reste distinct (256 Mio par défaut).

Le CanonicalReader général conserve son option historique non bornée pour les
autres appelants ; seul le worker journal impose systématiquement une borne.
L'API bas niveau apply_upsert accepte toujours un lecteur fourni par son appelant.
Aucune qualification du rebuild, du rappel ou des modèles réels n'est déduite
par extension de cette correction R1.

## Preuves

- 23 nouveaux tests rouges avant correction ; 2 cas supplémentaires rouges pour
  les entiers hors capacité read, puis corrigés : **25 nouveaux cas** au total.
- 116 tests worker/maintenance réussis avant ces deux cas supplémentaires ;
  61 tests lecteur/scanner/budgets réussis après correction complète.
- Deux vrais documents valides de plus de 8 Mio reproduisaient publication et
  indexation avant correction ; ils sont désormais refusés avant embedding.
- Croissance pendant read et après effet, limite exacte, reprise sans doublon,
  publication durable, état conservé et ligne saine suivante couverts.
- Tests ajoutés aux workflows Qdrant ciblé et contrat du vrai worker.
- Résultats CI à compléter après publication ; aucun test serveur ou VM déduit.

G236 est confirmé en CI : workflow Memory 38662055230, **2594 réussis, 5 xfail,
12 sous-tests**, 114,15 s ; contrat réel **35 réussis**, 1,38 s. Workflow Qdrant
38662055164 : **287 réussis, 1 xfail Q2**, 26,81 s. Périmètres chevauchants.

Claude a reçu dix tâches et les sources G236 pour ses contre-revues ; sa nouvelle
réponse n'est pas encore observée. Aucun runtime activé ni déploiement.
