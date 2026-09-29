from dataclasses import replace
from pathlib import Path
import pytest
from core.backend.filesystem import FilesystemBackend
from core.backend.models import Memory
from core.backend.errors import InvalidMemory
from core.threads.storage import ThreadStorage, ThreadStorageError
from core.threads.models import Thread, ThreadAction

FIXTURES = Path(__file__).parent / "fixtures"
TEXT = "  Heading\n---\n## Metadata\n```json\n{broken}\n```\nUnicode: café 🚀\n  "


def test_memory_preserves_arbitrary_markdown_and_spaces(tmp_path):
    store = FilesystemBackend(tmp_path / "p", tmp_path / "h")
    memory = Memory("m", content=TEXT, metadata={"fence":"```", "nested":{"x":TEXT}})
    store.store(memory)
    assert store.get("m") == memory


def test_thread_preserves_title_objective_and_nested_fences(tmp_path):
    store = ThreadStorage(tmp_path)
    thread = Thread("t", TEXT, TEXT, context={"text":TEXT},
                    actions=[ThreadAction("a",TEXT,metadata={"text":TEXT})])
    store.create(thread)
    assert store.get("t") == thread
    changed = replace(thread, revision=2, objective=TEXT + "updated")
    store.update(changed, 1)
    assert store.get("t") == changed


@pytest.mark.parametrize("content", [None, {"nested":[1,True,"x"]}, ["a","b"], ""])
def test_memory_preserves_json_content_types(content):
    value = Memory("m", content=content)
    assert FilesystemBackend._deserialize(FilesystemBackend._serialize(value)) == value


def test_legacy_memory_remains_readable():
    value = FilesystemBackend._deserialize((FIXTURES / "memory-v01.md").read_text())
    assert value.information_id == "legacy"
    assert value.content == "Legacy content"


def test_legacy_thread_remains_readable():
    value = ThreadStorage._deserialize((FIXTURES / "thread-v01.md").read_text())
    assert value.thread_id == "legacy"
    assert value.objective == "Legacy objective"


def test_legacy_documents_reject_zero_revision():
    memory = (FIXTURES / "memory-v01.md").read_text().replace("revision: 1", "revision: 0")
    thread = (FIXTURES / "thread-v01.md").read_text().replace("revision: 1", "revision: 0")
    assert "revision: 0" in memory and "revision: 0" in thread
    with pytest.raises(InvalidMemory, match="revision"):
        FilesystemBackend._deserialize(memory)
    with pytest.raises(ThreadStorageError, match="revision"):
        ThreadStorage._deserialize(thread)


@pytest.mark.parametrize("store,value,error", [(ThreadStorage, Thread("t","title","objective"),ThreadStorageError),
                                              (FilesystemBackend, Memory("m",content="x"),InvalidMemory)])
def test_unknown_versions_and_trailing_payload_are_rejected(store, value, error):
    text = store._serialize(value)
    for bad in (text.replace("Version: 0.2", "Version: 9.9"), text + "extra"):
        with pytest.raises(error):
            store._deserialize(bad)


def test_thread_identity_mismatch_is_rejected(tmp_path):
    store = ThreadStorage(tmp_path)
    store.create(Thread("t","title","objective"))
    (store.threads_root / "renamed.md").write_text((store.threads_root / "t.md").read_text())
    with pytest.raises(ThreadStorageError):
        store.get("renamed")


def test_event_preserves_embedded_code_fences(tmp_path):
    from core.events.filesystem import FilesystemEventRepository
    from core.events.models import Event, EventType, Cause, CauseType
    repo = FilesystemEventRepository(tmp_path)
    event = Event("e",1,EventType.CREATED,information_id="m",cause=Cause(CauseType.OTHER,TEXT))
    repo.save(event)
    assert repo.get("e") == event
