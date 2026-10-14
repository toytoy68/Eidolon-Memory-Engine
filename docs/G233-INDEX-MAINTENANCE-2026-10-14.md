# G233 — Arriérés et orchestration durable, 14 octobre 2026

Auteur : Codex/GPT. Suite demandée jusqu’au bout par toytoy à 22 h 36 Europe/Paris.
Base Memory : `0c23815fd25ceefa69614e06fc89c0466d52fdf8`.

## Livraison et portée

Les deux étapes G232 sont implémentées : consommation paginée des gros arriérés,
puis raccordement des scanners et du worker dans `IndexMaintenance`.
L’API exécute une étape explicite par appel de l’hôte. Elle ne crée aucun thread,
timer, cron, service, modèle ni configuration réseau. L’activation sur le serveur
reste une opération distincte de cette qualification isolée.

## Journal : passages finis, sans famine derrière les revues

`JournalUpsertWorker.run_page(after=0, through=None, limit=100)` capture une borne
haute de séquence et parcourt les intentions en attente par clé croissante.
Une page contient au plus 999 intentions ; l’arriéré total peut dépasser 999.
Les lignes terminales ou compactées ne décalent pas un offset : il n’y en a pas.
La borne haute utilise la dernière séquence allouée, conservée après compactage.

Les nouvelles écritures au-delà de la borne attendent un passage suivant. Une
intention DELETE, interdite, périmée, incohérente, illisible ou avec horodatage
invalide reste en attente pour revue mais laisse avancer ce passage. Elle sera
réexaminée au passage suivant. Une panne de l’index conserve en revanche la ligne
incertaine au curseur et demande un report ; une indisponibilité persistante de
l’adaptateur peut toujours suspendre le travail.

Une récupération INTENT passe à PUBLISHED ; un passage ultérieur l’indexe.
PASS_EXHAUSTED signifie fin de ce passage, jamais file vide. `run_once()` conserve
son ancien contrat : file trop grande = TRUNCATED, horodatage invalide = REFUSED,
sans effet. Le nouveau mode paginé traite séparément les horodatages invalides.

Correctif concret découvert pendant les essais : une `InvalidMemory` produite
par un Markdown malformé interrompait le worker avant la ligne saine suivante.
Elle devient désormais une intention UNVERIFIED conservée pour revue. L’inventaire
canonique distingue ses erreurs de source (`CanonicalSnapshotUnavailable`) des
erreurs de contexte/checkpoint, qui restent des refus explicites.

## Cycle durable

`IndexMaintenance` lie trois checkpoints SQLite distincts au journal physique,
à la racine canonique physique, à l’alias, au modèle, aux profils et à la politique.
Il conserve l’étape, la borne, le curseur, le prochain instant admissible, le
résultat précédent et les motifs de revue du journal. Un contexte modifié ou
des chemins liés au même fichier sont refusés.

Chaque tour effectue, en appels séparés :

1. Un premier passage fini du worker, avec sa borne enregistrée avant ses effets.
2. Un second passage fini pour les publications récupérées au précédent.
3. Une page du scanner canonique, ou sa vérification finale.
4. Une page du scanner inverse lorsque le canon est terminé ou bloqué sans progrès.
5. Un bilan : nouveau tour, CYCLE_COMPLETE, ou REVIEW_REQUIRED.

Les scanners gardent leurs propres checkpoints. Le scanner inverse attend la
progression canonique pour éviter de classer inutilement en revue les intentions
qui viennent d’être récupérées. Une file saturée uniquement par des revues mène
à REVIEW_REQUIRED ; elle n’entraîne ni boucle de remplissage ni clôture forcée.

Une source malformée ou un budget d’inventaire dépassé produit
SOURCE_REQUIRES_REVIEW, avec `inventory_completed=False`. Les lignes saines déjà
journalisées sont traitées ; le cycle ne prétend pas avoir terminé cet inventaire.
Une limite du scanner inverse est également signalée comme nécessitant une revue.

Une bascule de génération détectée avant une étape recommence les deux parcours.
Les effets précèdent la validation du checkpoint du contrôleur. Une interruption
peut donc rejouer une étape, mais les reprises existantes vérifient les points et
les intentions, et ne ré-encodent pas un effet déjà confirmé.

## Conditions et délais

Valeurs par défaut : fenêtre **04 h–08 h Europe/Paris**, au moins **30 minutes
sans activité** et **30 minutes depuis le démarrage**, charge déclarée acceptable
par l’hôte. Ces conditions sont cumulatives ; le redémarrage n’autorise pas une
maintenance hors fenêtre. Les dates doivent porter un fuseau ; l’horloge ne doit
pas reculer par rapport au dernier appel exécuté.

L’activité, le démarrage et la charge sont fournis par un appelant de confiance.
Le composant ne mesure pas lui-même CPU/GPU, sessions utilisateur ou uptime.
La charge inconnue ou autre chose que True reporte le travail. Un verrou occupé
répond BUSY avec une heure de reprise suggérée ; aucune écriture de progression
n’est faite sans verrou. Une panne/incompatibilité d’index conserve un report
SQLite de 30 secondes par défaut. Aucun appel ne dort sous verrou.

Après un cycle terminé ou nécessitant une revue, le suivant devient admissible
après 300 secondes par défaut, puis repasse les conditions horaires/activité.
Des appels intermédiaires répondent WAITING. Le contrôleur ne lance pas lui-même
le prochain appel : cette responsabilité reste à l’hôte qui l’intégrera.

## Utilisation par un hôte de confiance

```python
from core.indexing.maintenance import IndexMaintenance

maintenance = IndexMaintenance(
    cycle_checkpoint, journal,
    canonical_checkpoint=canonical_checkpoint,
    orphan_checkpoint=orphan_checkpoint,
    canonical_root=canonical_root, index=configured_index,
    authorize=authorize, profile_id=profile,
    expected_profile_id=expected_profile, expected_model_id=model,
)
report = maintenance.tick(
    at=current_aware_datetime,
    last_activity=last_observed_activity,
    boot_at=observed_boot_time,
    load_ok=observed_load_is_acceptable,
)
historical = maintenance.status()
journal_reviews = maintenance.reviews(after=0, limit=100)
fresh_orphan_review = maintenance.orphans.review_page(after=-1, limit=100)
```

L’hôte doit respecter les reports et fournir des observations fraîches avant
chaque nouvel appel. Il choisit explicitement l’index et les embeddings ; aucun
modèle n’est téléchargé ou deviné. Les trois checkpoints doivent être privés et
séparés du journal. Une configuration incompatible exige de nouveaux checkpoints.

`status()` expose le dernier état historique sans contacter l’index. `reviews()`
pagine les raisons historiques et retire celles dont l’intention n’est plus en
attente ; ses verdicts ne sont pas des autorisations. La revue d’orphelins garde
la revalidation G232. Aucune de ces API ne supprime ou n’abandonne une intention.

## Preuves exécutées

- Trois tests initialement rouges pour les nouvelles API, puis verts.
- Un quatrième test rouge expose le blocage sur Markdown malformé ; il passe
  après correction et vérifie la poursuite de la ligne saine.
- **246 tests ciblés réussis avec `-W error`**, puis **40 tests propres à G233**
  après le dernier cas BUSY ; lots chevauchants, non additionnables.
- Arriéré réel SQLite de **1005 intentions DELETE à revoir et une ligne saine** :
  ligne saine indexée, motifs de revue paginés et conservés par le contrôleur.
- Documents sans événements retrouvés par le scanner, publication, indexation,
  fin de cycle, puis découverte d’un nouveau document au cycle périodique suivant.
- Arrêt réel (`os._exit(73)`) après effet Qdrant/journal et avant checkpoint du
  contrôleur : réouverture SQLite/Qdrant sur disque, reprise sans nouvel embedding.
- Perte simulée du commit du contrôleur après une page canonique : un seul événement,
  reprise jusqu’à la fin ; panne partielle d’index : curseur à la ligne incertaine.
- Droits révoqués/rétablis, file saturée de revues, nouvelle arrivée pendant une
  passe, changement de génération avant la clôture, concurrence, fenêtre/activité/
  démarrage/charge, horloge reculée, contexte remplacé et checkpoint incohérent.
- CI complète Memory, ciblée Qdrant et intégration Core : à confirmer sur les
  révisions publiées. Les tests utilisent Markdown, SQLite et Qdrant local réels
  avec vecteurs synthétiques ; aucun corpus privé ni serveur de production.

## Limites et J2 restant

CYCLE_COMPLETE rapporte un cycle d’observations sans revue ni intention encore
visible au bilan. Il n’est pas une transaction distribuée ni une preuve permanente
de synchronisation : des écritures après une observation attendent un cycle suivant.
Les écrivains de sources, droits et alias doivent respecter la coordination commune.

Les pages sont bornées en nombre, pas en durée réseau absolue. Les captures G231
initiale/finale lisent encore l’inventaire complet sous verrou dans leurs budgets
(100000 entrées, 8 Mio/fichier, 256 Mio au total). L’adaptateur réseau doit avoir
ses délais configurés par l’hôte. Un flux continu d’écritures ou une source
constamment modifiée peut empêcher un cycle de finir ; les appels restent explicites.

Restent hors de cette livraison : activation d’un service hôte avec ses mesures
réelles de charge/activité, qualification serveur Qdrant et corpus/modèles réels,
coût des verrous, contrat historique complet et identité du découpeur, contre-revue
indépendante puis recette VM/PC. La suppression effective reste désactivée.
Aucune fusion main, modification du corpus réel ou installation sur VM.
