# F1 : contrats reçus et lot suivant

Compte rendu C3 4a85b81 et complément a6d546c, reçus le 4 octobre 2026.
Aucun engagement ou audit de référence nouveau n'est encore implémenté.

## Première tranche F1a : avertissement visible

Pour les détails source-detail v1/v2 présents, comparer la provenance à
l'extraction courante : source, pilote, empreinte, paragraphe et citation exacte.
Conserver les contrôles existants de validité des originaux/extractions.
Une substitution légitime qui rend une référence discordante doit produire
source_reference_mismatch dans warnings, séparé des issues bloquantes.
Readiness reste vraie si aucune autre anomalie ne bloque. Pas de réécriture,
suppression, correction automatique ou nouvelle acceptation du détail.

Affichage demandé : Sources et fiche concernée exposent identifiant du détail,
source, paragraphe et raison (pilote/empreinte/citation discordante). Aucun
texte du manuscrit ou du détail dans le signalement. Accueil : compteur et lien
Sources, visibles en compact ; texte seul : compteur seulement s'il tient,
sinon ne pas rendre la fenêtre de ressources inutilisable.

Critères : pas d'avertissement pour référence valide ; substitution légitime
avec détail = avertissement audit/readiness/UI et ready vrai ; corpus inchangé ;
rendu sans contenu privé. Les corruptions déjà bloquantes restent bloquantes.
Mesurer le coût du parcours et réutiliser l'extraction d'une même source dans
une inspection, sans cache entre inspections ni contournement de validation.

## Seconde tranche F1/F1b : engagement durable

Proposition Claude : memory/history/source-extractions-v1/<source_id>.json,
identité figée source/pilote/empreinte/nombre de paragraphes/date. Écriture de
l'engagement avant publication de l'extraction ; reprise explicite avec pilote
engagé après interruption ; engagement discordant ou extraction manquante
bloquants. Inventaire, garde legacy, copie core, backup/restore à raccorder.
Cette proposition exige des tests d'arrêt réel et de compatibilité avant code.

Lots existants sans engagement : restent lisibles, information non bloquante
uncommitted_extraction. Aucun engagement automatique du manuscrit ni migration.
Une éventuelle commande commit-extraction ne s'exécute que par choix explicite.
Les critères initiaux de Claude doivent être adaptés : F1a avertit, F1/F1b
sans engagement ne peuvent pas être rendus bloquants implicitement sur les lots
existants. Les cas bloquants doivent préparer un engagement explicite/nouveau.

## Répartition

GPT peut implémenter F1a puis demander une revue négative indépendante.
Claude : préciser/réviser les critères de la seconde tranche selon ces décisions,
préparer les cas compatibles/interruption/copie, sans engager le manuscrit.
Le scénario root setpriv, le téléphone réel, l'upload cloisonné et le reboot
restent des preuves opérationnelles distinctes, pas des garanties déduites de F1.
