# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/claude_memory_eval/receipt_seen_store.py
# Description : Consommation durable EXPÉRIMENTALE des identifiants de bascule (Claude, G262-9)
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""EXPERIMENTAL, test-only. Kept apart from alias_switch_receipt.py, which stays pure (no file)."""
import os
import re
import stat

from tests.claude_memory_eval.alias_switch_receipt import ReceiptRefused, verify_receipt


class DirectorySeenStore:
    """EXPERIMENTAL durable consumption of switch ids: one empty file per id, created with O_EXCL.

    What it guarantees, and only that: on one local POSIX filesystem, among processes using this same
    directory, at most one consume() of an id succeeds, and a success survives a crash once it returned
    (file and directory fsync-ed). Not guaranteed: network filesystems, a directory that someone edits
    or deletes, ordering between different ids. Validation (verify_*) stays pure; consumption is this."""

    def __init__(self, directory):
        self.directory = os.fspath(directory)
        st = os.lstat(self.directory)
        if not stat.S_ISDIR(st.st_mode) or stat.S_IMODE(st.st_mode) & 0o022:
            raise ReceiptRefused("RECEIPT_STORE_UNSAFE")

    def consumed(self):
        return frozenset(n for n in os.listdir(self.directory) if re.fullmatch(r"[0-9a-f]{32}", n))

    def consume(self, receipt):
        """Verify (pure) against the durable set, then claim the id atomically. Returns the switch id."""
        switch_id = verify_receipt(receipt, seen_switch_ids=self.consumed())
        dir_fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            try:
                fd = os.open(switch_id, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                             0o600, dir_fd=dir_fd)
            except FileExistsError:
                raise ReceiptRefused("RECEIPT_REPLAYED") from None   # lost a concurrent race
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
        return switch_id
