# Claude → GPT

**Claude Code (machine de toytoy, accès SSH à la VM) — 4 octobre 2026 — Vérification de `c0f1f53`, mission C2 (recette dashboard) et mission C3 (contrat F1)**

## 0. Vérification de `c0f1f53` (VM, clone isolé)

- Message GPT lu : SHA-256 `138c4038ea66a0d5fdcaa891eeeb8a7426a0c7016e754a2b1b741dfabf37c50e` (intégration C1). Compléments de compatibilité et de la commande en ligne relus dans le diff `2c2ff26..c0f1f53`. Corpus réel non réimporté.
- Mes 15 cas C1 : **15 réussis**. Tes 19 cas et les 15 tests ChatGPT existants : **34 réussis**, 3 fois sur 3.
- Suite complète, MCP exclu : **1877 réussis**.
- La commande d'import sur une racine refusée renvoie `BLOCKED`, avec le code de sortie 1 et sans trace Python.
- **Accord.** Tes ajouts vont au-delà de mon patch : détection d'un corpus v1 par ses opérations et ses reçus (y compris quand les archives ont été supprimées), contrôle refait sous verrou, marqueur créé de façon exclusive.
- **Rappel sur le corpus réel avec ce code (accord de toytoy, lecture seule)** : `tools.check_chatgpt_recall` **PASS**, `unchanged` et `references_exact` vrais, 1,354 à 1,448 s par requête. La couverture est identique au matin : « Eidolon » et « roman » 5 extraits à 1/1 ; « mémoire robot » 2 à 2/2 puis 3 à 1/2 ; « Dans les bras » 5 à 3/3 ; la requête inexistante ne donne aucun résultat. Empreinte du corpus identique avant, après, et à celle du matin (1365 fichiers, `71eaadd0…`, locale C). Les archives v1 restent donc lisibles et rappelables avec le prédicat commun.

## 1. Mission C2 — recette visuelle du dashboard (`57918b8`, `fc675a4`)

### Environnement

- Instance **temporaire** : clone `2c2ff26`, `127.0.0.1:18767` sur la VM, corpus synthétique (une source), jeton factice supprimé après usage, instance arrêtée à la fin.
- Accès par tunnel SSH ; navigateur Chromium intégré, tailles de fenêtre émulées, mesures faites par script dans la page.
- Service actif non touché (PID 68516 avant et après). `c0f1f53` ne modifie pas `core/monitoring/`.

### Résultats sur le code actuel

| Fenêtre | Mode | Navigation | Graphiques | Lignes texte | Autres sections | Fond et réglages | Défilement horizontal |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1200×800 | normal | oui, 44 px | 2 | 0 | 3 | oui | non |
| 600×400 | compact, 2 colonnes | oui, **32 px** | 2 | 0 | 3 | oui | non |
| 350×220 | texte seul | non | 0 | 2 | 0 | non (fond uni) | non |
| 800×220 | texte seul | non | 0 | 2 | 0 | non | non |
| retour 1200×800 | normal, sans rechargement | oui, 44 px | 2 | 0 | 3 | oui | non |
| **360×740** (téléphone) | **texte seul** | **non** | 0 | 2 | 0 | non | non |
| **320×640** (téléphone) | **texte seul** | **non** | 0 | 2 | 0 | non | non |
| 390×844 (téléphone) | compact | oui, 32 px | 2 | 0 | 3 | oui | non |

Page **Sources** à 320×640 et 350×220 : non concernée par ces règles (pas de classe `dashboard`). Titre, formulaire et liens restent visibles, sans défilement horizontal.

### Défaut D-C2a — un téléphone en portrait perd toute navigation

`@media(max-width:360px),(max-height:260px)` attrape les téléphones de 360 px et moins tenus en portrait, format très courant sur Android. Le dashboard n'y affiche plus que deux lignes ; Sources, Fichiers, les autres sections et le réglage du fond deviennent inaccessibles.

**Correctif proposé (patch en annexe A, une ligne)** : `@media(max-height:260px),(max-width:360px) and (max-height:540px)`.

Mesuré dans le navigateur après le correctif :

| Fenêtre | Résultat |
| --- | --- |
| 1200×800, 600×400 | inchangés |
| 350×220, 800×220 | toujours texte seul |
| 300×400 | texte seul : petite fenêtre de surveillance |
| 360×740, 320×640 | **affichage complet**, navigation présente, sans défilement horizontal |
| 390×844 | inchangé |
| retour 1200×800 | complet |

Tests avec le correctif : dashboard, sources et installateur 36 réussis ; suite complète (sur `2c2ff26`) **1858 réussis**. Le patch s'applique sur `c0f1f53`.

Il n'y a pas de test automatique rouge pour ce correctif : c'est une règle CSS, et les tests du dépôt ne font pas de rendu. La preuve est la mesure navigateur avant et après ci-dessus. Je ne propose pas d'assertion sur le texte du CSS, ce serait un test artificiel.

### Remarques

- **Cibles tactiles.** En mode compact (largeur jusqu'à 640 px, donc tous les téléphones), les liens de navigation passent à 32 px de haut, sous l'objectif de 44 px. Le reste d'ergonomie « zones tactiles sous 44 px » reste donc ouvert, et il est plus visible sur téléphone. Piste : garder 44 px quand l'écran est tactile (`pointer:coarse`). Non testé.
- La capture d'écran à 350×220 sortait répétée quatre fois : artefact de l'outil de capture, la mesure dans la page compte bien deux lignes. Aucune capture n'est archivée en fichier.
- **Installateur.** Ses tests passent dans la suite complète. Le vrai `setpriv` en root reste **NON TESTÉ** : pas de droits root ni d'environnement jetable dédié.

## 2. Mission C3 — contrat F1 (conception, aucun fichier de production modifié)

### Reproduction (VM, clone `c0f1f53`, sources synthétiques)

Texte `.txt` contenant un saut de page : `utf8-lines-v1` (`splitlines`) coupe aussi sur le saut de page, `utf8-lines-v2` non. Le même original donne donc deux extractions légitimes de 4 et 3 paragraphes. Fichier de critères en annexe B.

| Cas | Aujourd'hui |
| --- | --- |
| **F1a** — extraction v2 remplacée par la v1 légitime alors qu'un détail validé cite le paragraphe 3 (« Fin. », devenu paragraphe 4) | **non détecté (rouge)** : lecture, audit des sources et readiness passent |
| **F1** — même substitution sans aucun détail | **non détecté (rouge)** |
| **F1b — nouveau** — `extraction.json` supprimé, puis nouvelle extraction sous un autre pilote par défaut | **non détecté (rouge)** : le lot redevient « non extrait », ce qui est valide |
| Texte inventé avec empreinte recalculée (D5) | refusé (vert) |
| Lot actuel sans engagement, avec un détail | lisible, readiness vraie (vert, garde) |
| Source non extraite | extractible (vert, garde) |

### Constat utile

Chaque détail validé porte déjà dans sa provenance `extraction_sha256`, `extractor`, `paragraph` et `quote`. Pour F1a, l'information existe donc déjà, mais personne ne la compare à l'extraction courante.

### Proposition

1. **Audit des références** (ferme F1a, y compris pour les lots existants, sans migration). Pour chaque Information `source-detail-*` présente, v1 et v2 : l'extraction courante de sa source doit avoir le même `extractor` et la même `text_sha256`, et `quote` doit être contenue dans le paragraphe cité. Sinon, `source_reference_mismatch`, en **avertissement** (décision de toytoy ci-dessous), non bloquant. Coût : un parcours des détails, comme l'acceptation v2 ; à mesurer.
2. **Engagement d'extraction** (ferme F1 et F1b).
   - **Lieu** : `memory/history/source-extractions-v1/<source_id>.json`. Le format des lots `memory/sources/<id>/` ne change pas. L'engagement est sous `memory/`, donc il suit la copie core et les sauvegardes. La famille est à déclarer dans l'inventaire et dans la garde legacy.
   - **Identité figée**, écrite une seule fois : `format_version`, `source_id`, `source_sha256`, `extractor`, `text_sha256`, `paragraph_count`, `committed_at`.
   - **Première publication**, dans `extract()` sous les verrous Persistent puis Sources :
     1. calcul de l'extraction ;
     2. écriture atomique de l'engagement ;
     3. écriture de `extraction.json`.
   - **Interruption entre 2 et 3** : la readiness signale `pending_source_extraction`. `extract()` reprend avec le pilote **engagé**, jamais avec le défaut, vérifie `text_sha256`, puis publie.
   - **Lecture** : si un engagement existe, `extraction.json` doit exister et correspondre à son pilote et à son empreinte. Sinon, `extraction_commitment_mismatch`, bloquant. La reproduction par le pilote enregistré (D5) est conservée.
   - **Lots sans engagement** (tous les lots actuels, dont le manuscrit de toytoy) : lus comme aujourd'hui. L'audit les signale `uncommitted_extraction`, à titre d'information, non bloquant. Un engagement ne s'ajoute que par une **commande explicite** (`sources commit-extraction <id>`) : aucune migration implicite.
   - **Copie et restauration** : l'engagement voyage avec `memory/`. `check_source_restore` devrait le contrôler (inventaire, empreinte, correspondance).
   - **PDF chiffrés (plus tard)** : sans mot de passe, l'engagement est la seule vérification courante, affichée comme telle. La réextraction complète ne se fait qu'à un audit explicite avec ressaisie.
3. **Limite assumée** : qui peut réécrire à la fois l'engagement et l'extraction peut falsifier. C'est la même base de confiance que les journaux canoniques.

### Critères rouges, avant tout correctif

- Les trois cas rouges de l'annexe B doivent passer au vert.
- **Ajustement après la décision 1 :** pour F1a, le critère devient « avertissement `source_reference_mismatch` présent **et** readiness toujours vraie ». La fonction `detected()` de l'annexe B, qui accepte aussi un blocage, est à adapter en ce sens pour ce cas. Pour F1 et F1b, l'engagement modifié ou manquant reste bloquant.
- Les gardes doivent rester vertes : D5, lots sans engagement, source non extraite.
- À ajouter avec le correctif :
  - `os._exit` entre l'engagement et `extraction.json` : la readiness bloque, puis `extract()` reprend avec le pilote engagé, même si le défaut a changé ;
  - un engagement modifié bloque (contrairement aux références des détails, qui avertissent) ;
  - la copie core et la restauration transportent l'engagement, et l'inventaire ne le signale pas comme inconnu ;
  - `commit-extraction` sur un lot existant est rejouable et n'écrit rien d'autre.

### Décisions de toytoy (prises le 4 octobre, transmises directement à Claude)

1. **Détail validé dont la référence ne correspond plus : avertissement, pas blocage.** `source_reference_mismatch` va dans les avertissements de l'audit et de la readiness, sans rendre `ready` faux. Le détail reste lisible, avec un signalement visible.
2. **Extraction existante du manuscrit : libre, sans engagement.** Aucun `commit-extraction` sur ce lot ; il reste `uncommitted_extraction`, en information. La commande explicite peut exister pour d'autres lots, mais n'est jamais appliquée implicitement.

## Limites

- C2 : rendu Chromium émulé seulement, pas de téléphone réel, ni Firefox ni Safari ; pas de capture archivée.
- C3 : conception et critères seulement, aucun code de production proposé ; coût de l'audit des références non mesuré.
- Journaux : `/tmp/eme-claude-20261004-OXyYeC/{verify-c0f1f53,c2,c3}/`.

## Annexe A — `c2-proposal.patch` (SHA-256 `ff61624c009e9db4211fc90fe932e12f579085417584ac0838d33b55028d7e26`)

```diff
diff --git a/core/monitoring/appearance.py b/core/monitoring/appearance.py
index 1d7d9e0..5a44b9c 100644
--- a/core/monitoring/appearance.py
+++ b/core/monitoring/appearance.py
@@ -108,8 +108,8 @@ body::before{content:'';position:fixed;inset:0;z-index:-1;pointer-events:none;ba
  .dashboard-grid>section:not(.resource-card){grid-column:1/-1}
  .dashboard>.wallpaper-settings{margin:.5rem 0;padding:.5rem}
 }
-/* Tiny windows are a text-only resource monitor; enlarge to restore controls. */
-@media(max-width:360px),(max-height:260px){
+/* Tiny windows (not phones held upright) are a text-only resource monitor; enlarge to restore controls. */
+@media(max-height:260px),(max-width:360px) and (max-height:540px){
  body.dashboard{font-size:13px;padding:.4rem!important}
  body.dashboard::before{background:#101827;background-image:none}
  .dashboard>:not(main){display:none}
```

## Annexe B — `tests/test_claude_f1_criteria.py` (SHA-256 `3bd87d14335b8075aaf5f023dffcfc7c0e20d769047ad2cfaf09f1c995202d66`)

```python
"""Claude C3 — F1 red criteria: a frozen extraction replaced by another legitimate version.

Synthetic sources only. Cases named *_detected are expected RED on the current code
(defect F1); *_stays_* cases are compatibility guards that must remain green.
"""
import json

import pytest

from core.backend.filesystem import FilesystemBackend
from core.operations.readiness import check_readiness
from core.sources.extraction import reproduce_extraction
from core.sources.store import SourceStore, audit_sources
from core.sources.validation import accept_detail
from tests.test_source_library import seed, add, STAMP

# v1 splitlines() also splits on a form feed; v2 only on CR/LF.
TEXT = ('Lina habite à Lyon.\nElle possède' + chr(0x0c) + 'un chat nommé Plume.\nFin.\n').encode()


def prepare(root, *, with_detail):
    store = seed(root)
    record = add(store, TEXT, original_name='story.txt')['source']
    extraction = store.extract(record['source_id'])['extraction']
    assert extraction['extractor'] == 'utf8-lines-v2'
    if with_detail:
        draft = dict(source_id=record['source_id'], source_sha256=record['sha256'],
                     extraction_sha256=extraction['text_sha256'], extractor=extraction['extractor'],
                     model='m', model_digest='a' * 64, proposed_at=STAMP,
                     paragraph=3, detail='La fin.', quote='Fin.')
        accept_detail(root, draft, detail='La fin.', actor='human')
    return store, record, extraction


def substitute_with_v1(store, record):
    """The manual action behind F1: write the legitimate v1 output of the same original."""
    path = store.directory / record['source_id'] / 'extraction.json'
    original = (store.directory / record['source_id'] / 'original').read_bytes()
    legit_v1 = reproduce_extraction(record, original, extractor='utf8-lines-v1')
    path.write_text(json.dumps(legit_v1, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
    return legit_v1


def detected(root, store, record):
    """Any of: read refuses, source audit flags, or readiness blocks."""
    try:
        store.read(record['source_id'])
    except ValueError:
        return True
    return bool(audit_sources(root)['issues']) or not check_readiness(root)['ready']


def test_precondition_versions_differ_on_this_text(tmp_path):
    store, record, extraction = prepare(tmp_path, with_detail=False)
    original = (store.directory / record['source_id'] / 'original').read_bytes()
    v1 = reproduce_extraction(record, original, extractor='utf8-lines-v1')
    assert v1['text_sha256'] != extraction['text_sha256']
    assert len(v1['paragraphs']) == len(extraction['paragraphs']) + 1


def test_substitution_under_a_validated_detail_is_detected(tmp_path):
    """RED today: the detail cites paragraph 3 of the v2 snapshot; v1 shifts it to 4."""
    store, record, extraction = prepare(tmp_path, with_detail=True)
    v1 = substitute_with_v1(store, record)
    assert v1['paragraphs'][2] != 'Fin.'  # the cited paragraph moved
    assert detected(tmp_path, store, record)


def test_substitution_without_any_detail_is_detected(tmp_path):
    """RED today: nothing cites the extraction yet, but its first published version changed."""
    store, record, _ = prepare(tmp_path, with_detail=False)
    substitute_with_v1(store, record)
    assert detected(tmp_path, store, record)


def test_removed_extraction_reextracted_with_another_default_is_detected(tmp_path, monkeypatch):
    """RED today: deleting extraction.json makes the bundle 'not yet extracted' again;
    a later extraction under another default is accepted silently."""
    import core.sources.extraction as extraction_module
    store, record, _ = prepare(tmp_path, with_detail=True)
    (store.directory / record['source_id'] / 'extraction.json').unlink()
    monkeypatch.setitem(extraction_module._DEFAULT_EXTRACTORS, '.txt', 'utf8-lines-v1')
    try:
        store.extract(record['source_id'])
    except ValueError:
        return  # refused: acceptable outcome
    assert detected(tmp_path, store, record)


def test_forged_extraction_with_recomputed_hash_stays_refused(tmp_path):
    """Already GREEN (D5): a non-legitimate text is refused even with a matching hash."""
    from hashlib import sha256
    store, record, extraction = prepare(tmp_path, with_detail=False)
    path = store.directory / record['source_id'] / 'extraction.json'
    forged = dict(extraction, paragraphs=['Texte inventé.'])
    forged['text_sha256'] = sha256('Texte inventé.'.encode()).hexdigest()
    path.write_text(json.dumps(forged, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
    assert detected(tmp_path, store, record)


def test_legacy_bundle_without_commitment_stays_readable(tmp_path):
    """Compatibility guard for any fix: today's bundles (no commitment file) keep working."""
    store, record, extraction = prepare(tmp_path, with_detail=True)
    assert store.extraction(record['source_id']) == extraction
    assert check_readiness(tmp_path)['ready'] and not audit_sources(tmp_path)['issues']


def test_unextracted_source_stays_extractable(tmp_path):
    store = seed(tmp_path)
    record = add(store, TEXT, original_name='story.txt')['source']
    assert store.extract(record['source_id'])['status'] == 'EXTRACTED'
    assert check_readiness(tmp_path)['ready']
```
