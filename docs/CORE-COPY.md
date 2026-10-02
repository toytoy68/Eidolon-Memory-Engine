# Transfert explicite d’un arbre core arrêté

Ce transfert vers une **destination neuve** conserve les octets de `memory/` :
Informations actuelles, Threads/actions/révisions, Events, journaux complets,
reçus compacts et audits humains, parents de routage, échéances et suppressions,
dossiers et notes situés dans cet arbre. Il n’exécute aucune commande et ne
convertit aucun format legacy. Un mélange legacy/core doit suivre une politique
de conversion séparée ; le convertisseur historique conserve ses refus.

Arrêter les écrivains en source et en destination ; maintenir cet arrêt jusqu’au
résultat final. Le contrôle détecte les changements observés, sans remplacer cet
arrêt. Utiliser deux racines distinctes, sans lien symbolique, et un parent de
destination existant. Une destination déjà présente, même vide, est refusée.

```bash
python -B -m core.migration.core_copy --source SOURCE_ARRETEE --destination DESTINATION_NEUVE
python -B -m core.migration.core_copy --source SOURCE_ARRETEE --destination DESTINATION_NEUVE --apply
```

L’aperçu READY est sans écriture. L’application sérialise les demandes par verrou
sur le parent, prépare `.<destination>.core-copy-v1/tree`, vérifie les SHA256 de
chaque fichier, les formats, la readiness et les liens Thread/Information, puis
publie par renommage Linux atomique sans remplacement. Une destination apparue
entre-temps est conservée. Les états FAILED, les opérations incomplètes, les
formats inconnus, les liens symboliques et les fichiers spéciaux bloquent.
PENDING_DELETE et les échéances SCHEDULED valides restent en attente ; aucune
approbation ni exécution automatique. Les états terminaux restent identiques.

Après interruption, relancer exactement la même commande. Le plan conservé et
chaque fichier déjà copié sont comparés à la source ; seuls les éléments manquants
sont ajoutés. Un fichier divergent, une entrée inconnue ou un plan différent
bloque sans purge. Après publication, UNCHANGED exige le même manifeste source,
le reçu `core-copy-report.json` exact et la destination conforme. Toute divergence
bloque. La préparation et son plan restent conservés comme preuve.

Les verrous techniques `.write.lock` ne sont pas copiés. Aucun code, configuration,
secret, `.git` ou fichier hors de `memory/` n’est transféré. Des dossiers/notes
configurés en dehors de cet arbre exigent une sauvegarde séparée explicitement
vérifiée. Les permissions d’origine ne sont pas reproduites ; choisir et vérifier
les droits de la destination avant adoption. Les octets canoniques, historiques
et notes sont conservés sans reconstruire les vues.

Preuves du 03/10 : 42 cas synthétiques, quatre arrêts de processus, concurrence et
refus de remplacement ; suite VM complète 1429 tests réussis. Cela ne démontre
ni l’adoption par des services, ni le transfert d’un corpus réel, ni une coupure
électrique. L’activation et une migration entre formats restent des tâches
séparées. L’API de publication nécessite `renameat2(RENAME_NOREPLACE)` ; son
absence bloque au lieu de publier avec une garantie moindre.
