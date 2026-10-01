# Diagnostics de revue du patch Claude

À exécuter depuis le dépôt avec Python et ses dépendances (`python -B`).
Toutes les données sont synthétiques et supprimées à la sortie. Aucun fichier
source n'est modifié. Comparer la base `0c89ce7` et la proposition appliquée
isolément ; voir [le rapport](../REVUE-CLAUDE-2026-10-01.md).

```python
from pathlib import Path
from tempfile import TemporaryDirectory
import json
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.information.writes import FilesystemInformationWrites
from core.migration.inventory import inventory
from core.migration.converter import convert
from core.operations.errors import OperationConflict
from tools.generate_scenario import generate

with TemporaryDirectory(prefix='claude-review-') as directory:
    root=Path(directory)
    history=root/'receipt/memory/history'
    backend=FilesystemBackend(root/'receipt/memory/persistent',history)
    writes=FilesystemInformationWrites(backend)
    def create(number):
        return writes.create(Memory(f'info-{number}',content='probe'),operation_id=f'op-{number}',event_id=f'event-{number}',actor='audit',timestamp='2026-10-01T00:00:00Z')
    create(1); writes.compact('op-1')
    receipt=writes.journal.receipt_path('op-1')
    value=json.loads(receipt.read_text());value['format_version']=999
    receipt.write_text(json.dumps(value))
    try:
        create(2); outcome='ALLOWED'
    except OperationConflict:
        outcome='BLOCKED'
    print(json.dumps({'case':'unknown_receipt_version_before_new_write','result':outcome}))
    for case,relative in [('unknown_file','memory/history/unrecognized.json'),('nested_unknown_family','memory/history/operations/thread-status-v1/future-v9/op.json')]:
        source=root/case
        path=source/relative;path.parent.mkdir(parents=True);path.write_text('{broken')
        print(json.dumps({'case':case,'needs_review':inventory(source)['needs_review']}))
    fixture=root/'fixture';generate(fixture,count=50)
    source=fixture/'legacy';state=source/'memory/history/pending-delete/retired.json'
    state.parent.mkdir(parents=True);state.write_text(json.dumps({'information_id':'retired','status':'DELETED'}))
    destination=root/'converted';report=convert(source,destination)
    print(json.dumps({'case':'rejection_after_conversion','converted':report['converted'],'rejections':report['rejected'],'active_files':len(list((destination/'memory/persistent').glob('*.md')))}))
    # Observe only synthetic paths when an ancestor is a link.
    try:
        from core.migration.inventory import unknown_history_entries
    except ImportError:
        pass
    else:
        linked=root/'linked';(linked/'memory').mkdir(parents=True)
        outside=root/'outside';(outside/'events/private-marker').mkdir(parents=True)
        (linked/'memory/history').symlink_to(outside,target_is_directory=True)
        print(json.dumps({'case':'unknown_scanner_symlink_ancestor','entries':unknown_history_entries(linked)}))
```

Sorties du candidat observées : nouvelle écriture ALLOWED avec reçu version 999 ;
`needs_review=[]` pour le fichier inconnu et la sous-famille imbriquée ; 50
Informations écrites avec un rejet opérationnel ; la fonction complémentaire
énumère `memory/history/events/private-marker` malgré l'ancêtre symbolique.
Sur la base, le premier cas est BLOCKED ; les deux omissions d'inventaire
existent déjà ; la conversion écrit les 50 Informations sans rejet ; la fonction
complémentaire n'existe pas. Le diagnostic de migration utilise un reçu minimal
synthétique, non validé : il mesure la position du contrôle dans l'algorithme,
pas l'import d'un reçu complet. Le test fourni par Claude couvre ce dernier.
