# Séance — contrat mémoire et coordination Thread

Base : `7774c65`, branche `refactor/architecture-v1`, 30 septembre 2026.

| Tâche | Réalisation | Preuves | Limites |
| --- | --- | --- | --- |
| T-040 | Contrat mémoire 0.1, 14 scénarios de référence, mapping explicite Information/Memory | Six tests ; forme de stockage attendue, absence de partage des objets, édition réellement persistée conservant les extensions, 500 candidats de migration identiques après aller-retour | Les 14 attendus ne sont pas encore exécutés par un router ; données historiques partielles/structurées hors projection textuelle ; aucune VM |
| T-039 | Assemblage commun `FilesystemThreadDeletion.for_history`, utilisé par suppression implicite et CLI | Deux tests interrompent création/statut après Event, constatent le blocage de suppression puis son succès après reprise | Noms de journaux canoniques ; pour un historique personnalisé injecter le coordinateur adapté ; pas de validation concurrente VM |
| T-031 | Suppression mieux raccordée | Tests ci-dessus | Toujours partiel : create/update directs et autres assemblages manuels à traiter |
| T-041/T-042 | Conception précédente conservée | Aucun nouveau test de ces services | Service Information coordonné et reçus compacts non implémentés |

## Vérification de la sensibilité des tests

- Mapping : première collecte en échec sans le module. Après implémentation,
  retirer temporairement la copie des extensions rend rouge le test d'édition
  persistée (`KeyError: legacy_revision`) ; le code est ensuite restauré.
- T-039 : les deux scénarios échouent sur le code précédent car la suppression
  est autorisée. Après correction, retirer temporairement le raccordement des
  journaux création/statut les fait de nouveau échouer ; le code est restauré.
- Suite finale, vrai pytest 9.1.1 : **674 passed, 5 deselected in 35.75s**.
  Aucun nouveau test marqué comme exécuté sur VM. Les cinq cas exclus sont les
  quatre variantes de concurrence écrivain et le rejeu concurrent Thread déjà
  identifiés comme bloqués dans cet environnement.

Les tests T-039 utilisent des exceptions simulant l'interruption ; la suite
existante contient aussi des arrêts de processus. Aucun de ces tests ne prouve
la durabilité après coupure d'alimentation du disque réel.

## Prochaine étape et VM

Poursuivre P1 : figer le résultat de rejeu et le contrat de snapshot/reçu, puis
implémenter T-041 sans contourner la suppression existante. Ne pas activer un
router avant que ses mutations passent par un service coordonné. Aucun nouveau
développement externe, micro-durcissement ni pourcentage ajouté dans cette séance.
La grille reste 50,75 points et l'estimation globale 45 %.

Sur la VM, utiliser une copie arrêtée et un dossier de travail distinct vide :

```sh
python -B -m tools.vm_acceptance --source /chemin/copie-arretee --workdir /chemin/recette-vide
```

Contrôler le rapport et la liste réelle des écrivains. Compléter les cinq tests
concurrents, la restauration par hash et la revue des données de migration.
Exécuter aussi `tests/test_thread_deletion_recovery.py` et
`tests/test_information_mapping.py` avec pytest installé sur la VM. La recette
peut signaler un KO légitime sur des suppressions encore à reprendre : garder
le rapport et examiner les cas, sans modifier la source pour obtenir du vert.
