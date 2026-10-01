"""Check persisted references before removing an Information."""

from __future__ import annotations

from pathlib import Path

from core.backend.errors import InformationDeletionBlocked, InvalidMemory
from core.threads.storage import ThreadStorage, ThreadStorageError
from core.operations.filesystem import FilesystemOperationRepository
from core.operations.models import OperationStatus, OperationType, ThreadCreatePlan
from core.operations.errors import InvalidOperationRecord
from core.persistence import has_symlink_component


def ensure_no_information_links(persistent_root: Path, information_id: str,
                                deserialize) -> None:
    """Block removal if another Information references the target.

    The caller holds the Persistent writer lock, shared by Information writes.
    """
    if persistent_root.is_symlink():
        raise InformationDeletionBlocked("Information directory is a symlink")
    for path in sorted(persistent_root.glob("*.md")):
        if path.is_symlink():
            raise InformationDeletionBlocked("Information scan contains a symlink")
        if path.stem == information_id:
            continue  # Its outgoing relations disappear with this Information.
        try:
            memory = deserialize(path.read_text(encoding="utf-8"))
            if memory.information_id != path.stem:
                raise ValueError("Information identity mismatch")
        except (OSError, UnicodeError, ValueError, TypeError, KeyError,
                AttributeError, InvalidMemory) as exc:
            raise InformationDeletionBlocked(
                "unreadable Information prevents safe deletion"
            ) from exc
        for relation in memory.relations:
            if not isinstance(relation, dict):
                raise InformationDeletionBlocked("invalid Information relation")
            target_id = relation.get("target_id")
            legacy_target = relation.get("target")
            if (target_id is not None and legacy_target is not None
                    and target_id != legacy_target):
                raise InformationDeletionBlocked("ambiguous Information relation target")
            target = target_id if target_id is not None else legacy_target
            if not isinstance(target, str) or not target:
                raise InformationDeletionBlocked("invalid Information relation target")
            if target == information_id:
                raise InformationDeletionBlocked(
                    f"Information is referenced by Information {memory.information_id}"
                )


def ensure_no_thread_links(threads_root: Path, information_id: str) -> None:
    """Fail closed on links or unreadable Threads; caller holds the writer lock."""
    if threads_root.is_symlink():
        raise InformationDeletionBlocked("Thread directory is a symlink")
    if threads_root.exists() and not threads_root.is_dir():
        raise InformationDeletionBlocked("Thread directory is not a directory")
    if not threads_root.is_dir():
        return
    for path in sorted(threads_root.glob("*.md")):
        if path.is_symlink():
            raise InformationDeletionBlocked("linked Thread scan contains a symlink")
        try:
            thread = ThreadStorage._deserialize(path.read_text(encoding="utf-8"))
            if thread.thread_id != path.stem:
                raise ValueError("Thread identity mismatch")
        except (OSError, UnicodeError, ValueError, TypeError, KeyError,
                AttributeError, ThreadStorageError) as exc:
            raise InformationDeletionBlocked(
                "unreadable Thread prevents safe Information deletion"
            ) from exc
        for relation in thread.relations:
            if not isinstance(relation, dict):
                raise InformationDeletionBlocked("invalid Thread relation")
            if relation.get("type") != "CONCERNS":
                continue
            target_id = relation.get("target_id")
            legacy_target = relation.get("target")
            if (target_id is not None and legacy_target is not None
                    and target_id != legacy_target):
                raise InformationDeletionBlocked("ambiguous Thread CONCERNS target")
            target = target_id if target_id is not None else legacy_target
            if not isinstance(target, str) or not target:
                raise InformationDeletionBlocked("invalid Thread CONCERNS target")
            if target == information_id:
                raise InformationDeletionBlocked(
                    f"Information is linked by Thread {thread.thread_id}"
                )


def ensure_no_pending_thread_creations(history_root: Path, information_id: str) -> None:
    """A prepared Thread link reserves its target before the Thread file exists."""
    root = history_root / "operations" / "thread-create-v1"
    if has_symlink_component(root):
        raise InformationDeletionBlocked("Thread creation journal contains a symlink")
    if not root.exists():
        return
    if not root.is_dir():
        raise InformationDeletionBlocked("Thread creation journal is not a directory")
    repository = FilesystemOperationRepository(root)
    for path in sorted(root.glob("*.json")):
        try:
            record = repository.get(path.stem)
        except (OSError, UnicodeError, ValueError, InvalidOperationRecord) as exc:
            raise InformationDeletionBlocked("unreadable Thread creation journal") from exc
        if (record is not None and record.operation_type is OperationType.THREAD_CREATE
                and record.status is not OperationStatus.COMMITTED
                and isinstance(record.plan, ThreadCreatePlan)
                and record.plan.information_id == information_id):
            raise InformationDeletionBlocked("pending Thread creation references Information")


def ensure_no_pending_thread_updates(history_root: Path, information_id: str) -> None:
    """Prepared project mutations reserve links in both persisted snapshots."""
    from core.operations.thread_update import read_operations
    from core.operations.models import ThreadUpdatePlan
    from core.operations.thread_status import plan_hash
    from core.operations.errors import OperationRepositoryError
    try:
        for record in read_operations(history_root / 'operations/thread-update-v1'):
            if (record.operation_type is not OperationType.THREAD_UPDATE
                    or type(record.plan) is not ThreadUpdatePlan
                    or plan_hash(record) != record.execution_plan_hash):
                raise InformationDeletionBlocked('invalid Thread update journal')
            if record.status is OperationStatus.COMMITTED:
                continue
            for text in (record.plan.before_state, record.plan.after_state):
                snapshot = ThreadStorage._deserialize(text)
                if information_id in ThreadStorage._concerns(snapshot):
                    raise InformationDeletionBlocked('pending Thread update references Information')
    except (OSError, ValueError, TypeError, ThreadStorageError, OperationRepositoryError) as exc:
        raise InformationDeletionBlocked('unreadable Thread update journal') from exc


def ensure_information_write_safety(history_root: Path, information_id: str,
                                    *, require_compacted: bool = False) -> None:
    """Called under Persistent: pending snapshots reserve targets and links.

    Approval also requires committed snapshots of the deleted identity to be
    compacted first. Unreadable plans fail closed, with no silent purge.
    """
    from core.routing.execution_journal import require_available
    from core.operations.errors import OperationConflict
    try:
        require_available(history_root, information_id=information_id)
    except OperationConflict as exc:
        raise InformationDeletionBlocked('pending routing execution reserves Information') from exc
    from core.backend.filesystem import FilesystemBackend
    from core.information.write_journal import InformationWriteJournal
    from core.operations.errors import OperationRepositoryError
    try:
        journal = InformationWriteJournal(history_root)
        for opid in journal.ids():
            entry = journal.read(opid)
            record = entry.operation if entry is not None else None
            if record is None:
                continue
            if record.target_id == information_id:
                if record.status is not OperationStatus.COMMITTED:
                    raise InformationDeletionBlocked('pending Information write requires recovery')
                if require_compacted:
                    raise InformationDeletionBlocked('compact Information write snapshots before deletion')
            if record.status is not OperationStatus.COMMITTED:
                after = FilesystemBackend._deserialize(record.plan.after_state)
                if any(r.get('target_id', r.get('target')) == information_id for r in after.relations):
                    raise InformationDeletionBlocked('pending Information write references target')
    except (OSError, UnicodeError, ValueError, TypeError, InvalidMemory, OperationRepositoryError) as exc:
        raise InformationDeletionBlocked('unreadable Information write journal') from exc
