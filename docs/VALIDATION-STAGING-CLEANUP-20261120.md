# Nettoyage des reconstructions Qdrant non publiées - 20 novembre 2026

Eidolon Memory Engine - Eidolon Core Technologies (ECT)

## Problème et correction

Un échec pendant la construction d'une génération laissait une collection orpheline, même quand aucune publication d'alias n'avait été tentée. Le contrat G201 Q3 restait en échec attendu.

La reconstruction supprime maintenant uniquement sa nouvelle génération non publiée après vérification de l'absence de tout alias la désignant. Les générations antérieures sont conservées. Dès qu'une publication est tentée, une erreur ou un accusé de réception perdu conserve la cible : aucun nettoyage n'est effectué sur une publication ambiguë. Une panne du nettoyage ne masque pas l'erreur d'origine.

Le contrat existant de rédacteur unique coordonné et de snapshot canonique arrêté reste requis. Cette correction n'introduit ni purge périodique ni collecte des générations historiques.

## Validation locale isolée

- Échec G201 reproduit avec --runxfail avant correction.
- 34 tests ciblés réussis, dont quatre nouvelles régressions : échec d'embedding, publication ambiguë, alias tiers et panne du nettoyage.
- Suite complète : **3236 réussis, 26 ignorés, 2 échecs attendus**, 12 sous-tests réussis, 161,41 s.
- Les 19 scénarios Qdrant réel ignorés dans la suite générale ont été exécutés séparément : **19 réussis**, 80,75 s. Binaire Qdrant 1.15.4 avec SHA256 vérifié, instances jetables ; aucun accès au serveur de production.
- Scénarios privilégiés de verrouillage/montage : **16 réussis**, incluant les 7 ignorés faute de privilèges dans la suite générale.
- Les deux autres échecs attendus restent ouverts : indicateur de retard d'indexation et API publique de mutation Qdrant non revue.
- L'ancien test qui documentait explicitement un orphelin a été actualisé : il exige désormais l'égalité exacte de l'ensemble des générations conservées, et continue de vérifier l'alias et les réponses servies.

## Intégration

Branche de travail isolée basée sur codex/veille-temporal-20261102 (d30512d). Aucun déploiement ni modification des données de production. Les résultats FR100 existants (83,33 % global, 46 % temporel, 10 % obsolescence) ne sont pas améliorés par cette correction et restent une priorité séparée.
