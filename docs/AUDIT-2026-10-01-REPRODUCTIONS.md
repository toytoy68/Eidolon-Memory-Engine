# Reproductions des constats A-01 à A-03

Audit du 01/10, code `a779c9d`. Exécuter le bloc Python depuis le dépôt avec
l'environnement contenant les dépendances (`python -B`). Il crée uniquement
des données synthétiques sous un TemporaryDirectory puis les retire.
Ce diagnostic constate les défauts actuels ; ce n'est pas un test affirmant
que ce comportement est souhaité, ni une recette VM. Un correctif futur doit
inverser ces constats dans ses tests de régression.

```python
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import os
import shutil
import subprocess
import sys

from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.events.filesystem import FilesystemEventRepository
from core.migration.converter import convert
from core.migration.inventory import inventory
from core.operations.filesystem import FilesystemOperationRepository
from core.operations.models import OperationStatus
from core.operations.thread_status import FilesystemThreadOperations
from core.threads.models import Thread, ThreadStatus
from core.threads.storage import ThreadStorage
from tools.generate_scenario import generate

with TemporaryDirectory(prefix="memory-audit-") as directory:
    root = Path(directory)

    # A-01 : état FAILED autorisé, omis du rapport CLI.
    engine = root / "gate"
    engine.mkdir()
    history = engine / "memory/history"
    storage = ThreadStorage(engine / "memory/persistent")
    storage.create(Thread(
        "t", "Title", "Objective",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    ))
    operations = FilesystemOperationRepository(history / "operations/thread-status-v1")
    service = FilesystemThreadOperations(
        storage, FilesystemEventRepository(history / "events/thread-status-v1"), operations,
    )

    def interrupted(operation):
        raise RuntimeError("audit: stop before APPLYING")

    service._resume = interrupted
    try:
        service.change_status("t", ThreadStatus.VALIDATED,
                              previous_revision=1, operation_id="op", event_id="e")
    except RuntimeError:
        pass
    operations.update(replace(operations.get("op"), status=OperationStatus.FAILED))
    result = subprocess.run(
        [sys.executable, "-B", "-m", "core.operations.cli", "recover-all"],
        env=dict(os.environ, MEMORY_ENGINE_ROOT=str(engine)),
        text=True, capture_output=True, check=False,
    )
    print("A-01", json.dumps({
        "exit": result.returncode,
        "report": json.loads(result.stdout),
        "persisted_status": operations.get("op").status.value,
    }))

    # A-02 : famille ignorée par l'inventaire des formats.
    source = root / "inventory"
    journal = source / "memory/history/operations/thread-delete-v1"
    journal.mkdir(parents=True)
    (journal / "broken.json").write_text("{broken", encoding="utf-8")
    print("A-02", json.dumps({"needs_review": inventory(source)["needs_review"]}))

    # A-03 : reçu valide produit par le core, ajouté à une source mixte.
    fixture = root / "fixture"
    generate(fixture, count=50)
    source = fixture / "legacy"
    receipts = source / "memory/history/pending-delete"
    receipts.mkdir(parents=True)
    producer = FilesystemBackend(root / "seed/memory/persistent", root / "seed/memory/history")
    producer.store(Memory("retired", content="test"))
    producer.delete_request("retired", "audit", "synthetic", 1, "delete-retired")
    producer.approve_delete("retired", "delete-retired")
    shutil.copy2(producer.pending_delete_root / "retired.json", receipts / "retired.json")
    destination = root / "converted"
    report = convert(source, destination)
    target = FilesystemBackend(destination / "memory/persistent", destination / "memory/history")
    target.store(Memory("retired", content="reused"))
    print("A-03", json.dumps({
        "rejected": report["rejected"],
        "archived": (destination / "archive/history/pending-delete/retired.json").exists(),
        "recreated": target.get("retired") is not None,
    }))
```

Sortie observée ici :

```text
A-01 {"exit": 0, "report": {"creations": {}, "status_changes": {}, "deletions": {}, "information-writes": {}}, "persisted_status": "FAILED"}
A-02 {"needs_review": []}
A-03 {"rejected": [], "archived": true, "recreated": true}
```

Le cas A-01 injecte une interruption par exception et une transition explicite
vers FAILED ; ce n'est pas un crash de VM ni la preuve d'une production
spontanée de cet état. A-03 utilise une source mixte synthétique, pas les données
de l'utilisateur. Les correctifs restent T-048/T-021 dans la TODO.
