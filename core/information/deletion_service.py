# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/information/deletion_service.py
# Description : Application entry point for guarded Information deletion.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Application entry point for guarded Information deletion."""

from __future__ import annotations

from core.backend.errors import InformationDeletionBlocked
from core.backend.filesystem import FilesystemBackend
from core.threads.storage import ThreadStorage


class LinkedInformationDeletionService:
    """Compatibility facade; the filesystem backend now enforces the guard."""

    def __init__(self, backend: FilesystemBackend, threads: ThreadStorage) -> None:
        if backend.persistent_root.resolve() != threads.persistent_root.resolve():
            raise ValueError("Information and Thread stores must share a persistent root")
        self.backend = backend

    def approve_delete(self, information_id: str, operation_id: str):
        return self.backend.approve_delete(information_id, operation_id)
