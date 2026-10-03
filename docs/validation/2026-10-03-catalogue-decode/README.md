# Catalogue : décodage unique, double contrôle des octets — 3 octobre 2026

Base code `17c644e`, comparaison de l’ancienne classe catalogue extraite de
`e49caa7` contre la classe modifiée. Le script utilise les dépendances communes
du checkout courant ; ce n’est pas une comparaison de deux piles complètes.
Une projection filtrée est capturée après validation de chaque source par le
manifeste. Seules les métadonnées déjà publiées dans le catalogue sont retenues,
pas les corps ni extensions privées. Le second read_bytes et le contrôle SHA256
restent obligatoires avant traitement des reçus et publication.

Deux nouveaux cas : 1 rouge avant correction (deux décodages au lieu d’un),
1 contrôle conservé du refus d’une source modifiée entre les lectures.
67 ciblés verts ; **1727 réussis en 37,99 s**, 15 tests MCP exclus.
Aucun cache inter-commandes, aucun nouveau format canonique/index, aucun gain
de lecture disque revendiqué et aucun entretien du roman utilisateur.

Mesure VM : deux corpus synthétiques indépendants (100 et 300 Informations),
chaque arbre arrêté partagé par les deux classes. Trois snapshots complets par
variante, avec readiness réelle, instrumentés pour compter _deserialize.
À 100 : 200 → 100 décodages, médianes 0,008386 → 0,007176 s.
À 300 : 600 → 300 décodages, médianes 0,018615 → 0,016109 s.
Les six empreintes de snapshot sont identiques pour chaque taille. Il s’agit
de tmpfs chaud, pas de latence disque physique ni d’une mesure sous charge Core.
Le petit corpus n’a ni Thread ni historique d’opérations ; les tests couvrent
séparément appartenance projet, suppression, corruption et publications.

run.py conserve les chemins de cette recette VM (checkout /opt et extraction
sous /tmp/eidolon-maintenance-comparison-20261003) ; adapter ces chemins avant
une reproduction ailleurs. comparison.json contient échantillons et empreintes,
pytest.txt le journal général ; manifest.json protège ces trois artifacts.
