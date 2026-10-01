# Proposition — écritures Information coordonnées

Conception du 2026-09-30, mise à jour le 01/10 : **service et compaction v1
livrés en local, non validés sur VM**. Voir le contrat implémenté dans
[INFORMATION-WRITES.md](INFORMATION-WRITES.md). Synthèse de la revue croisée avec Claude et
toytoy. L'annexe reçue dans `eidolon_memory_engine_2026-09-30_maj2.zip` est
intégrée et harmonisée avec les décisions validées le 30/09 :
[conflits, reçus et reprise détaillés](DESIGN-INFORMATION-WRITES-DETAIL.md).
Les signatures et le schéma du reçu v1 sont maintenant documentés dans le
contrat livré ; les paragraphes de conception conservent leur contexte initial. Voir le [bilan d'architecture](MEMORY-ARCHITECTURE-2026-09-30.md).

## Problème et frontières

`FilesystemBackend.store/update` assurent verrous, contrôle des révisions et
publication atomique d'un fichier, sans coordonner Operation et Event.
`MemoryBackend` expose ces méthodes et le convertisseur utilise `store`.
Les supprimer ou les renommer privées casserait ce contrat.

Proposition : un service métier orchestre les écritures ; les primitives
restent nécessaires au stockage, à son contrat testé et à l'import isolé.
Recenser puis migrer les appelants métier. Le contrat ne doit pas dépendre
de la bonne volonté de chaque client pour construire tous les coordinateurs.
Un point d'assemblage commun doit garantir leur configuration complète.

Les Threads ne sont pas entièrement couverts : `ThreadStorage.create/update`
restent des primitives publiques sans Operation/Event. `delete` est journalisé,
et son coordinateur implicite consulte désormais les familles création/statut
canoniques via `for_history` (T-039 corrigé en local, non validé sur VM).
Étendre la coordination Information ne résout pas ces contournements à lui seul.

## Décisions retenues

| Décision | Orientation retenue pour la conception | Reste à spécifier |
| --- | --- | --- |
| D1 | Nouvelle Information métier à révision 1 ; mise à jour n → n+1 ; import distinct conservant les révisions historiques | Mapping textuel livré sous T-040 ; import sans faux événements et cas historiques ambigus avec T-021 |
| D2 | Event sans corps complet, métadonnées sélectionnées et empreinte ; snapshots conservés pendant la reprise ; compaction possible après succès | Format de reçu compact, politique et conditions de compaction, garanties de rejeu et suppression |
| D3 | Conserver le contrat bas niveau ; faire passer les mutations métier par un service coordonné ; préserver tests de stockage et ajouter tests de service | Inventaire des appelants et migration par étapes, contrat des primitives réservées à l'import/reprise |
| D4 | Aucun CREATED historique inventé ; préserver les archives ; trace d'import datée si utile | Format éventuel de trace et liens vers source/rapport de migration |
| D5 | Unification du journal de suppression ultérieure ; compatibilité et conflits à définir dès maintenant | Ordre de reprise commun, réservation d'identité, interaction avec liens et snapshots |
| D6 | Mapping textuel explicitement étiqueté livré ; snapshots du Memory complet, extensions comprises | Cas non couverts soumis à une politique d'import explicite |
| D7 | Annuler explicitement PENDING_DELETE avant une nouvelle modification métier | Implémenter et tester ce contrôle, absent de update actuellement |
| D8 | Conserver l'empreinte de commande dans le reçu compact v1, même après suppression de la cible ; aucune garantie de confidentialité | Normalisation précise ; futur effacement des empreintes avec contrat de rejeu distinct |
| D9 | Identité réservée après CANCELLED ; modification de la cible existante permise | Pas de changement de store ; cible absente = incohérence à examiner |

`INFORMATION_CREATE` et `INFORMATION_UPDATE` sont des types Operation proposés,
absents du code. `CREATED` et `UPDATED` existent déjà comme types Event.
Une création enregistrée ne signifie pas une information confirmée.

## Écriture et reprise proposées

1. Recevoir une commande identifiée : cible, révision attendue, données,
   provenance et identifiant d'opération. Figer les données variables, dont la
   date, dans le plan ; ne pas les recalculer lors du rejeu.
2. Sous les verrous appropriés, contrôler les opérations incompatibles,
   l'identité réservée et la révision. Préparer le snapshot après, et le
   snapshot avant pour une modification. Définir l'empreinte d'une commande
   normalisée et l'Event attendu, avec lien vers l'opération.
3. Publier durablement PREPARED puis APPLYING avant toute mutation métier.
4. Publier l'Information attendue, puis l'Event déterministe ; une identité
   Event existante avec un contenu différent est un conflit.
5. Marquer COMMITTED après vérification des sorties. Retourner un résultat
   minimal stable (identité/révisions/Event), compatible avec la compaction.

L'ordre existant pour la création Thread est Persistent → Thread → Operation
→ Event. Le futur service Information doit respecter un ordre global compatible
(Persistent puis, si nécessaire, Thread, puis Operation et Event). Les chemins
qui nécessitent plusieurs journaux doivent avoir un ordre entre ces journaux.
Cette proposition n'est pas une preuve d'absence d'interblocage : tracer les
prises de verrous et tester la concurrence avant de la valider.

| Interruption ou état observé | Reprise attendue à spécifier et tester |
| --- | --- |
| Avant PREPARED | Aucune mutation métier ; nouvelle tentative possible |
| PREPARED/APPLYING, fichier encore avant | Reprendre le plan exact, pas une nouvelle commande |
| Fichier après, Event absent | Reconnaître le snapshot après et écrire l'Event une fois |
| Fichier après, Event conforme, statut non COMMITTED | Finaliser le journal |
| Fichier ni avant ni après, ou Event incompatible | Bloquer sans écraser ; garder les éléments de reprise |
| COMMITTED puis état cible ayant évolué | Accuser la commande déjà exécutée sans restaurer l'ancien état |
| Même operation_id, autre commande | Conflit, y compris après compaction |

Un journal récupérable ne rend pas les lectures multi-fichiers atomiques.
Définir ce que voit un lecteur pendant APPLYING ; aucune promesse de transaction
globale n'est ajoutée par ce document.

## Conflits entre création, mise à jour et suppression

- Une opération inachevée réserve sa cible ; un nouveau chemin métier ne doit
  pas la contourner. Reprise ou résolution explicite avant commande incompatible.
- Une suppression commencée interdit la réécriture ou la recréation de la cible.
  Les identités réservées par un reçu de suppression restent protégées.
- Une nouvelle modification métier exige l'annulation explicite d'une demande
  PENDING_DELETE (D7). CANCELLED conserve l'identité et permet la modification
  de la cible existante (D9). Ces règles cibles ne sont pas toutes appliquées
  par les primitives actuelles ; leur raccordement appartient à T-041/T-031.
- Une suppression doit tenir compte des opérations Information et Thread qui
  réservent ou référencent la cible, en plus des liens persistés.
- Reprendre un ancien update ne doit jamais ressusciter une cible supprimée.
- La compaction ne doit pas supprimer les informations nécessaires à ces
  décisions ni permettre le contournement par une autre famille de journal.

La matrice cible détaillée et ses écarts avec le code sont dans l'annexe §5bis.
La compaction précède APPLYING_DELETE. Vérifier l'absence de plans contenant du
texte puis publier cet état sous le même verrou Persistent partagé avec les
écrivains ; ne pas laisser une nouvelle opération s'intercaler entre les deux.

## Snapshots, reçu compact et oubli

Pendant PREPARED/APPLYING, ou lorsqu'une reprise est bloquée, conserver les
snapshots tant que leur sort n'a pas été résolu explicitement. Le texte peut
être nécessaire même si sa durée d'utilité métier a expiré.

Après succès vérifié, proposer un reçu compact versionné conservant type et
identité de commande, cible, révisions, empreintes, identité Event et résultat
minimal. Le reçu reconnaît un rejeu et rejette une commande différente, sans
prétendre restituer l'ancien contenu. Un hash n'est pas un chiffrement et les
métadonnées du reçu doivent elles aussi avoir une politique de conservation.

La compaction est une transition de format récupérable, pas un effacement de
champs dans `OperationRecord` : les plans actuels sont requis par les modèles,
empreintes et reprises. Publier puis relire le reçu durable avant le retrait
du snapshot ; synchroniser aussi le répertoire après ce retrait. Si journal
et reçu coexistent, vérifier leur concordance ; une divergence bloque la
reprise, sans priorité automatique. Ne jamais retraiter un reçu compact comme
une opération à appliquer. Les conditions détaillées figurent à l'annexe §10.
Les empreintes restent conservées en v1 selon D8 ; les délais et un éventuel
protocole d'effacement ultérieur restent à spécifier.

Séparer : sortir de mémoire haute, expirer l'applicabilité, archiver et supprimer
le contenu. Une suppression complète doit recenser aussi dossiers, résumés,
catalogues, index, journaux, archives et sauvegardes ; ne pas promettre un
effacement global à partir du seul retrait du fichier Information. Ne pas
supprimer une preuve ou une réserve d'identité nécessaire à une reprise sans
résolution correspondante. L'historique métier conservant le corps est une
politique explicite distincte des besoins techniques du journal.

## Preuves requises avant livraison

- Contrat de création, mise à jour et import ; révisions et provenance conservées.
- Interruptions à chaque frontière, rejeu exact, commande différente sous le
  même identifiant, Event existant incompatible et cible ayant divergé.
- Conflits avec les familles Thread et suppressions Information, dont T-039.
- Compaction interrompue et reprise après redémarrage ; rejeu après compaction
  et après modification/suppression ultérieure de la cible.
- Aucune perte silencieuse de Reviews/Events historiques et aucun faux CREATED.
- Inventaire prouvant quels appelants métier passent réellement par le service.
- Chaque fonctionnalité/correctif a un test démontré rouge sans lui ; conserver
  aussi les tests du backend. Validation multiprocessus et disque réel sur VM
  séparée des simulations locales.

La première édition du 30/09 était uniquement documentaire (674 tests réussis
et 5 exclus rapportés). L'implémentation et les nouveaux tests du 01/10 sont
attestés dans [le rapport de séance](SESSION-2026-10-01.md). Ni la VM ni la
durabilité après coupure électrique ne sont validées. Un arrêt de processus
ne prouve ni un arrêt de VM ni une coupure physique.
