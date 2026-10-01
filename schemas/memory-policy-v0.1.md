# Contrat fonctionnel mémoire 0.1

Statut au 01/10 : planificateur pur v0.1 exécutable dans
`core/routing/policy.py`, sur qualification déclarée. Mapping dans
`core/information/mapping.py`. Dossiers, activation et ordonnanceur restent
à implémenter (T-044 à T-046) ; les plans ne sont pas exécutés automatiquement.

## 1. Frontières et vocabulaire

L'entrée du moteur est une information qualifiée, pas un flux vidéo ou une
commande de mouvement. L'extraction de plusieurs informations depuis une
phrase relève du producteur ; le moteur peut recevoir un groupe lié. Le
producteur conserve l'origine de ses annotations, notamment une proposition
de LLM. Une qualification incomplète reste à examiner ; aucune valeur n'est
inventée pour rendre l'entrée admissible.

La source distingue auteur, système immédiat, méthode et date d'observation.
Le rôle administrateur sert à l'autorisation de commande ; il ne confirme pas
la vérité de son contenu. Une décision, une opinion, une hypothèse et une
observation ne se convertissent pas implicitement en FACT.

La confirmation s'applique à une affirmation dans son contexte déclaré.
Des contextes incompatibles peuvent justifier deux conclusions différentes.
Leur relation CONTRADICTS n'entraîne pas automatiquement REFUTED. Si les
conditions ne sont pas connues, l'applicabilité est UNKNOWN ; si les deux
affirmations divergent dans le même contexte, conserver le conflit.

## 2. Représentation cible, additive

Le format documentaire core reste 0.2. Ce contrat utilise les champs existants,
avec un espace de qualification versionné dans les métadonnées ; il ne change
pas les lecteurs du backend. Les clés sont conservées même si un ancien
consommateur ne les interprète pas.

| Chemin dans Memory | Sens et forme cible |
| --- | --- |
| metadata.type, epistemic_status, operational_state, confidence, importance, retention | Étiquettes existantes, conservées séparément |
| metadata.context | Mode/domaines, IDs projet/lieu/sujet connus, contexte de discussion |
| metadata.context.scope | Objet de conditions explicites : `subject_id`, `place_id`, `project_id` et `conditions` (clés/valeurs exactes dans ce premier contrat) |
| metadata.qualification | Objet `{version: "0.1", nature: ..., horizon: ..., qualified_by: ...}` ; absence signifie non qualifié |
| provenance | Source, auteur, méthode, chaîne de dérivation et références connues ; aucun rôle inféré depuis le texte |
| temporal | Dates observées/créées et bornes d'applicabilité, avec fuseau lorsqu'elles sont présentes |
| verification.evidence | Références soutenant ou contredisant l'affirmation |
| metadata.triggers | Déclencheurs déclarés ; aucune exécution destructrice implicite |

Natures initiales : TECHNICAL, REFLECTION, SPATIAL_LAYOUT, MOBILE_PRESENCE,
OBSTACLE, ACTION_REPORT, PROJECT_INTENT, CONDITIONAL_CLAIM. Elles complètent
le type, sans remplacer le statut épistémique. Horizons : IMMEDIATE, NEAR_TERM,
LONG_TERM, UNKNOWN. Horizon et rétention ne donnent aucune autorisation d'effacer.
`qualified_by` identifie la source de la qualification ; ce n'est pas une preuve.

Le contexte de requête est fourni séparément du contexte conservé. Pour cette
version, une condition exacte absente de la requête donne UNKNOWN, une valeur
différente donne OUT_OF_SCOPE, toutes les conditions connues correspondantes
donnent MATCH. Les intervalles numériques, synonymes et inférences de contexte
restent hors du comparateur initial. L'absence de scope ne signifie jamais
qu'une information est universelle.

## 3. Plan du router de référence

Le plan, versionné `memory-policy/0.1`, conserve identités et révisions sources,
la version des règles et des raisons explicites. Il décide séparément :

- persistance : STORE, UPDATE, NONE ou REVIEW ;
- disponibilité : HIGH, INTERMEDIATE ou LOW (projections sur une même identité) ;
- rattachement : CREATE_OR_LINK, LINK, NONE ou REVIEW ;
- applicabilité : MATCH, OUT_OF_SCOPE, UNKNOWN, EXPIRED ou UNRESOLVED ;
- action future : aucune, réexamen ou réactivation déclarée ;
- statut épistémique transmis, sans promotion fondée sur source/rôle/confiance.

NONE signifie aucun nouvel enregistrement durable de cette entrée, pas
suppression d'un enregistrement existant. UPDATE exige une cible connue et
sa révision ; un rapprochement incertain produit REVIEW. Les décisions de
conservation viennent d'une politique explicite et de la tâche, pas seulement
d'une détection de mots. Un lieu ou projet absent ne doit pas être inventé.

Un objet mobile aperçu n'est pas enregistré durablement par défaut dans le
profil de référence sans tâche de suivi. Une observation significative pour
une tâche peut l'être. Un obstacle contourné reste à revérifier : il n'est pas
considéré retiré. Une disposition des pièces est une connaissance stable
candidate, pas une vérité automatiquement confirmée par la caméra.

## 4. Dossier et disponibilité

Un projet identifié demande un dossier Markdown vivant et une fiche
intermédiaire. Chercher une identité existante avant création ; rattachement
ambigu → REVIEW. Le résumé référence les IDs/révisions et distingue texte
calculé et décisions humaines. Une correction invalide ou reconstruit les
vues dérivées ; la copie du résumé ne devient pas une seconde vérité.

HIGH contient le contexte actuel borné ; INTERMEDIATE prépare une reprise
probable ou datée ; LOW conserve le durable. Un catalogue reconstructible rend
également LOW repérable. Une échéance échue au redémarrage reste à traiter avec
un identifiant de déclenchement stable, sans doubler les actions déjà accusées.
La mémoire propose la reprise ; le moteur ne commande pas le robot directement.

## 5. Conservation et oubli

Éviction de HIGH, expiration de validité, archivage et suppression sont
distincts. Une observation historique peut être conservée avec applicabilité
EXPIRED. Aucun délai fixe par espèce/objet n'est décrété ; les durées et la
preuve de disparition sont des paramètres de profil à définir avant activation.

L'effacement exige une autorisation explicite et un plan couvrant références,
dossiers, catalogue, index, journaux et politique des sauvegardes. Les opérations
inachevées gardent leurs snapshots jusqu'à résolution. Après succès, un reçu
compact peut remplacer le snapshot selon le contrat T-042 livré dans `information-write-receipt-v1.md` ; aucun
effacement technique ne doit supprimer les garanties de rejeu ou ressusciter
une donnée supprimée. L'exécution de cette politique n'est pas livrée ici.

## 6. Correspondance exécutable Information ↔ Memory

| Information | Memory |
| --- | --- |
| information_id, revision, content | Même champ, sans allocation de révision |
| type, epistemic_status, operational_state, confidence, importance, retention | metadata, valeurs textuelles des Enum |
| context, triggers | metadata.context, metadata.triggers |
| provenance | provenance |
| time | temporal |
| evidence | verification.evidence |
| relations | relations |

`information_from_memory(memory)` exige des étiquettes explicites pour les
six Enum. Elle refuse le contenu structuré car le modèle Information actuel
est textuel. Elle ne modifie pas la source et ne la classe pas. Une métadonnée
optionnelle absente donne une vue vide, sans inventer une preuve.

`information_to_memory(information, original=memory)` préserve les extensions
de metadata/verification et l'absence des champs optionnels restés vides.
Pour une édition d'objet lu, fournir **toujours** l'original : sans lui la
fonction construit un nouvel objet et ne possède pas ses extensions. Les
objets sont copiés en profondeur ; les IDs doivent désigner la même identité.
Ces fonctions ne remplacent ni le service coordonné ni le contrat du backend.

Le service `FilesystemInformationWrites` alloue révision 1 à la création métier.
Un import utilise son chemin distinct : la projection conserve la révision
historique, comme le convertisseur actuel. Aucun Event CREATED historique
n'est ajouté et aucune mémoire partiellement étiquetée n'est complétée par
défaut ; ces cas restent à décider dans le rapport de migration.

## 7. Scénarios de référence et limites

`tests/fixtures/memory-policy-v0.1.json` contient les attendus métier de T-043
et T-046. `tests/test_memory_policy.py` convertit les exemples en objets Memory
et contexte de routage et vérifie la partie planification des 14 scénarios.
Le scénario programmé ne vérifie ni la durabilité du déclencheur ni le nombre
d'activations après rejeu : ces obligations restent T-046. La forme compacte
reste un jeu de préconditions, pas une nouvelle API d'ingestion.

Les tests `tests/test_information_mapping.py` vérifient séparément le mapping,
une édition réellement persistée avec extensions et le retour identique des
500 candidats synthétiques à la migration. Le corpus ne prouve ni la politique
de routage ni la compatibilité de toutes les données historiques de la VM.
