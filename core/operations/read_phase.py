# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/operations/read_phase.py
# Description : Private, lock-scoped reuse of a successful full readiness audit.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Private, lock-scoped reuse of a successful full readiness audit.

Only derived/read-only work belongs in this scope. Nothing survives its exit.
Canonical atomic publications invalidate the proof, including reentrant writers.
The final maintenance audit always starts a separate scope.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from pathlib import Path
import os

from core.persistence import write_lock_held, has_symlink_component

_phase = ContextVar('settled_read_phase', default=None)


def _matching(root):
    phase = _phase.get()
    if phase is None or has_symlink_component(Path(root)) or phase['root'] != Path(os.path.abspath(root)):
        return None
    persistent = phase['sources'][0]
    threads = persistent / 'threads'
    if not write_lock_held(persistent) or (threads.exists() and not write_lock_held(threads)):
        return None
    return phase


def cached_readiness(root):
    phase = _matching(root)
    return deepcopy(phase['readiness']) if phase is not None and phase['readiness'] is not None else None


def remember_readiness(root, report):
    phase = _matching(root)
    if phase is not None and report['ready']:
        phase['readiness'] = deepcopy(report)


def has_settled_audit(root):
    phase = _matching(root)
    return phase is not None and phase['readiness'] is not None


def invalidate_publication(path):
    phase = _phase.get()
    if phase is not None:
        destination = Path(os.path.abspath(path))
        if any(destination == root or root in destination.parents for root in phase['sources']):
            phase['readiness'] = None


@contextmanager
def settled_read_phase(root):
    if has_symlink_component(Path(root)):
        raise ValueError('settled read phase root contains a symlink')
    root = Path(os.path.abspath(root))
    persistent, history = root / 'memory/persistent', root / 'memory/history'
    threads = persistent / 'threads'
    if not write_lock_held(persistent) or (threads.exists() and not write_lock_held(threads)):
        raise RuntimeError('settled read phase requires Persistent and existing Thread locks')
    if _matching(root) is not None:
        yield
        return
    token = _phase.set(dict(root=root, sources=(persistent, history), readiness=None))
    try:
        yield
    finally:
        _phase.reset(token)
