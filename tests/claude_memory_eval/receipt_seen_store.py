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

    Guaranteed, and only that: on one local POSIX filesystem, among processes using this same directory
    (same inode as at construction), at most one consume() of an id succeeds; a returned success has the
    mark and the directory entry fsync-ed. Not guaranteed: network filesystems, ordering between ids, a
    directory that someone edits by hand. G266-6: a failure AFTER the mark was created is reported as
    RECEIPT_CONSUMED_UNCONFIRMED (consumed, durability unknown); the mark is never removed, so any retry
    sees RECEIPT_REPLAYED and the id can never be consumed twice."""

    _DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC

    def __init__(self, directory):
        self.directory = os.fspath(directory)
        try:
            fd = os.open(self.directory, self._DIR)
        except OSError:
            raise ReceiptRefused("RECEIPT_STORE_UNSAFE") from None    # absent, not a directory, or a link
        try:
            st = os.fstat(fd)
            self._check(st)
            self.identity = (st.st_dev, st.st_ino)
        finally:
            os.close(fd)

    @staticmethod
    def _check(st):
        if not stat.S_ISDIR(st.st_mode) or stat.S_IMODE(st.st_mode) & 0o022:
            raise ReceiptRefused("RECEIPT_STORE_UNSAFE")

    def _open(self):
        try:
            fd = os.open(self.directory, self._DIR)
        except OSError:
            raise ReceiptRefused("RECEIPT_STORE_CHANGED") from None
        st = os.fstat(fd)
        if (st.st_dev, st.st_ino) != self.identity:
            os.close(fd)
            raise ReceiptRefused("RECEIPT_STORE_CHANGED")           # replaced since construction
        try:
            self._check(st)                                         # rights may have changed since
        except ReceiptRefused:
            os.close(fd)
            raise
        return fd

    def consumed(self):
        fd = self._open()
        try:
            return frozenset(n for n in os.listdir(fd) if re.fullmatch(r"[0-9a-f]{32}", n))
        finally:
            os.close(fd)

    def consume(self, receipt):
        """Verify (pure) against the durable set, then claim the id atomically. Returns the switch id."""
        dir_fd = self._open()
        try:
            seen = frozenset(n for n in os.listdir(dir_fd) if re.fullmatch(r"[0-9a-f]{32}", n))
            switch_id = verify_receipt(receipt, seen_switch_ids=seen)
            try:
                fd = os.open(switch_id, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                             0o600, dir_fd=dir_fd)
            except FileExistsError:
                raise ReceiptRefused("RECEIPT_REPLAYED") from None   # lost a concurrent race
            # From here the mark EXISTS. Any failure is ambiguous, never a plain error, never undone.
            try:
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
                os.fsync(dir_fd)
            except OSError:
                raise ReceiptRefused("RECEIPT_CONSUMED_UNCONFIRMED") from None
        finally:
            os.close(dir_fd)
        return switch_id
