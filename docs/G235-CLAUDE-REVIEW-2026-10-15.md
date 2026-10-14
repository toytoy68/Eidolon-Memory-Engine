# G235 — Traitement de la contre-revue Claude C179/C180

15 octobre 2026, Europe/Paris — Codex/GPT.
Base Memory : `29f9c7bde2e9eec517d5b9898c6d6c017172bc06`.
Code livré : `507fbb140676dab2b870b582733f0bd421a3b845`.
Revue reçue dans Core : `2dd8de86def61c811a0d4b6f0d53057c90cfe9c3`.

## Décisions et résultat

La contre-revue confirme les gardes de reprise, l'absence de suppression, les
arriérés sans famine et la revalidation des orphelins. Les conclusions de sabotage
d'OrphanScan sont rapportées par Claude, pas reproduites dans ce lot.
Les priorités Q1, W1/W2 et A08 sont traitées ; pas de refonte d'architecture.

### Q1 — Preuve après reconstruction corrigée

Reproduit avec le test Claude `test_a_rebuilt_generation_keeps_verifiable_provenance`
et `--runxfail` : échec, preuve absente. Le rebuild prend désormais le verrou
canonique avant celui de l'adaptateur, lit chaque Information via CanonicalReader,
compare son digest et sa révision au manifeste et construit ses points avec
la provenance complète dans la **nouvelle génération**, avant la bascule.
Il ne faut pas appeler `upsert_verified()` ici : cette méthode cible l'alias actif,
donc l'ancienne génération, et détruirait l'isolation de la reconstruction.

La comparaison finale du manifeste et les contrôles de génération/descripteur
restent en place. Les générations anciennes ou interrompues restent conservées.
La sonde Q1 devient une non-régression sans xfail, assertions identiques. La sonde
0036 vérifie maintenant que la maintenance ne ré-encode plus les points reconstruits
(5 écritures worker au total, pas 10). Les imports Claude originaux restent conservés
dans les patchs Core pour comparer l'avant/après.

Le digest est celui du **fichier canonique complet**, privé dans Qdrant, comme les
upserts vérifiés depuis G229 ; aucun hash du texte brut n'est ajouté aux candidats.
La sonde historique de confidentialité est adaptée au nouveau schéma et vérifie
l'absence du corps et de son hash brut. Les vecteurs et digests demeurent des données
privées dérivées ; cette distinction n'est pas une anonymisation.

### W1/W2 — Un seul worker applicatif, tests sur le vrai chemin

Suppression de `core/indexing/worker.py`, copie de la référence expérimentale.
Déplacement de l'ancien worker sans provenance vers
`tests/experimental_isolated_upsert.py`. Il n'existe plus dans le paquet applicatif.
`JournalUpsertWorker` est le worker journal ; `worker_upsert` est son opération
unitaire partagée, sous verrou et avec preuve. La référence et ses 19 scénarios
restent uniquement dans les tests, sans revendication de conformité du runtime.

La CI exécute explicitement les sondes 0033 sur le worker réel, Markdown réel et
Qdrant local. La suppression locale de chacun des deux gardes finaux a été essayée
indépendamment : retirer les droits fait échouer 2 sondes ; retirer le canon en fait
échouer 1. Le code original a été restauré octet pour octet ; aucun mutant publié.
Cela confirme indépendamment que ces tests détectent les régressions signalées.

### Contributions intégrées

Patchs Claude 0008, 0032–0036 : migrations/crash, passages, séparation
attente/revue, contrat réel, calibration v1/v2, générations et maintenance.
Le jeu v1 manquait dans notre branche ; importé intact depuis 0008, nécessaire au
contrôle de v2. Les empreintes figées, questions et réponses attendues sont inchangées.
Aucun benchmark sémantique ni seuil calibré à partir de ces nouveaux jeux.

Les sondes 0036 comprennent 1200 upserts sains et une mort réelle du processus
après écriture Qdrant mais avant INDEXED/checkpoint, avec reprise sans embedding.
14 tests Claude sur le vrai chemin ont été reproduits avant correction ; après
correction/import complet, **361 tests ciblés réussis et 5 xfail**, 14,08 s.
Les 5 xfail sont des exigences ouvertes, pas des réussites : signalement du retard
dans le rappel, passages de production, nettoyage des générations ratées, escalade
par âge S1, disparition de l'API delete Q2. Le nettoyage automatique demeure exclu
à ce stade ; ce xfail décrit une proposition historique, pas une autorisation.

## Points encore ouverts et ordre retenu

| Point | Décision |
| --- | --- |
| MT1 — saut d'horloge en avant | Constat accepté. Prévoir une remise à zéro explicite et auditée, avec redémarrage du cycle ; aucune correction silencieuse de last_at. Pas encore implémentée |
| MT3 — limite d'orphelins | Exposer une borne configurée par l'hôte, liée au contexte du checkpoint. Conserver le refus sans certification d'inventaire complet. Pas encore implémenté |
| S1 — ancienneté | Conserver pending distinct de stale ; définir et calibrer une alerte d'âge explicite avant changement. Aucun seuil inventé dans ce lot |
| Q2 — delete public | API héritée du contrat IndexPort, jamais appelée par le worker/cycle. Séparer ultérieurement le port administratif ; ne pas annoncer de suppression effective désactivée dans toute la bibliothèque |
| R1 — taille canonique | Borne du lecteur journal à expliciter avant hôte de production ; scanners déjà bornés |
| L1/L2 — cycles d'import | Dette reconnue, extractions ciblées ultérieures, aucune refonte urgente |

Le prochain lot de maintenance traite MT1/MT3 avant activation de l'hôte.
A08 est corrigé dans Core, détaillé dans PROJECT-STATUS et la réponse G235.
Les écarts historiques de contrat (revue DELETE séparée, délai WAIT absent,
gardes par intention) restent explicites : la matrice G234 n'est pas invalidée.
Aucun serveur, VM, corpus privé, suppression ou fusion main dans ce lot.

## Validation CI

| Validation sur code publié | Résultat |
| --- | --- |
| [Memory complet](https://github.com/toytoy68/Eidolon-Memory-Engine/actions/runs/38647247658) | **2567 réussis, 5 xfail et 12 sous-tests réussis**, 280,22 s |
| Contrat du vrai worker, même workflow | **35 réussis**, 2,61 s |
| [Qdrant et sondes Claude](https://github.com/toytoy68/Eidolon-Memory-Engine/actions/runs/38647247571) | **260 réussis, 1 xfail (Q2)**, 18,63 s |
| [Core avec Memory G235](https://github.com/toytoy68/Eidolon-Bootstrap-Framework/actions/runs/38647296057) | **1786 réussis, 7 ignorés et 1299 sous-tests réussis**, 347,34 s |

Core testé : `b8eadc04b2994c27df5d295ea796de4c39bfef68`.
Les comptes ciblés et complets se chevauchent ; ils ne s'additionnent pas.

Core : aucun avertissement pytest ; les 7 exclusions nécessitent numpy/ONNX/OpenCV et les modèles d’identité optionnels. Les avertissements Node des actions GitHub sont distincts. Trois workflows terminés avec succès.
