# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : services/remember_bridge.py
# Description : Profile-bound explicit write adapter, durable replay through canonical journal
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Only the separately authenticated Core write principal may call this adapter.

One endpoint serves one operator-selected isolated canonical root. The actor is
fixed at startup, never selected by the remote request. Existing journals own
idempotency and incomplete-operation recovery; HTTP failure is an unknown effect.
"""
from pathlib import Path
import re
from core.backend.filesystem import FilesystemBackend
from core.information.writes import FilesystemInformationWrites
from core.information.remember import apply, prepare
from core.persistence import has_symlink_component


class RememberValidationError(ValueError):
    """A request rejected before constructing a writer; never an execution failure."""


class RememberEndpoint:
    def __init__(self, root, profile):
        self.root = Path(root).absolute()
        if (type(profile) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", profile)
                or has_symlink_component(self.root)
                or not all((self.root / "memory" / name).is_dir() for name in ("persistent", "history"))):
            raise ValueError("existing isolated canonical root and profile required")
        from services.profile_binding import require_binding
        require_binding(self.root, profile)
        self.profile = profile

    def __call__(self, request):
        if (type(request) is not dict or set(request) != {"command", "approved_sha256"}
                or type(request["command"]) is not dict
                or request["command"].get("actor") != self.profile):
            raise RememberValidationError("invalid profile-bound write")
        try:
            expected = prepare(request["command"])[2]
            if type(request["approved_sha256"]) is not str or request["approved_sha256"] != expected:
                raise ValueError("approval mismatch")
        except (ValueError, TypeError, OverflowError) as exc:
            raise RememberValidationError("invalid reviewed write") from exc
        def writer():
            from services.profile_binding import require_binding
            require_binding(self.root, self.profile)
            if has_symlink_component(self.root):
                raise ValueError("canonical root changed")
            return FilesystemInformationWrites(FilesystemBackend(
                self.root / "memory/persistent", self.root / "memory/history"))
        receipt = apply(request["command"], approved_sha256=request["approved_sha256"], make_writer=writer)
        return {"state": "COMMITTED", "sha256": request["approved_sha256"], "receipt": receipt}
