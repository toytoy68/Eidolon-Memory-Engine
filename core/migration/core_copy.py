# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/migration/core_copy.py
# Description : Verified transfer of a stopped core memory tree to a fresh destination.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Verified transfer of a stopped core memory tree to a fresh destination.

This copies bytes, never executes journals or converts legacy formats. Both
writers must remain stopped throughout preview, copying and publication.
"""
from __future__ import annotations

import argparse
import ctypes
from hashlib import sha256
import json
import os
from pathlib import Path
import stat

from core.backend.errors import BackendError
from core.backend.filesystem import FilesystemBackend
from core.migration.converter import _atomic_bytes
from core.migration.inventory import inventory
from core.operations.readiness import check_readiness
from core.persistence import exclusive_write, has_symlink_component
from core.threads.link_audit import audit_links

REPORT = 'core-copy-report.json'


def _checkpoint(stage, path=None):
    """Interruption boundary used by process-level acceptance tests."""


def _manifest(root):
    files, directories = {}, []
    def visit(path):
        mode = path.lstat().st_mode
        relative = path.relative_to(root).as_posix()
        if stat.S_ISDIR(mode):
            directories.append(relative)
            for child in sorted(path.iterdir()):
                visit(child)
        elif stat.S_ISREG(mode):
            if path.name != '.write.lock':
                files[relative] = sha256(path.read_bytes()).hexdigest()
        else:
            raise ValueError(f'unsafe memory entry: {relative}')
    visit(root / 'memory')
    return {'files': files, 'directories': sorted(directories)}


def _validate_core(root):
    if not (root / 'memory/persistent').is_dir():
        raise ValueError('source is not an initialized core tree')
    formats = inventory(root)
    if any(kind.startswith('legacy_') for counts in formats['categories'].values() for kind in counts):
        raise ValueError('legacy formats require explicit conversion before core copy')
    for path in sorted((root / 'memory/persistent').glob('*.md')):
        memory = FilesystemBackend._deserialize(path.read_text(encoding='utf-8'))
        if memory.information_id != path.stem:
            raise ValueError(f'Information identity mismatch: {path.name}')
    if not check_readiness(root)['ready']:
        raise ValueError('core readiness blocks transfer')
    if audit_links(root)['issues']:
        raise ValueError('invalid Thread or Information links')


def _paths(source, destination):
    source, destination = Path(source).absolute(), Path(destination).absolute()
    if has_symlink_component(source) or has_symlink_component(destination):
        raise ValueError('source or destination contains a symbolic link')
    if (source == destination or source in destination.parents
            or destination in source.parents):
        raise ValueError('source and destination must be separate trees')
    if not source.is_dir() or not destination.parent.is_dir():
        raise ValueError('source and destination parent must already exist')
    stage = destination.parent / ('.' + destination.name + '.core-copy-v1')
    if stage == source or source in stage.parents or stage in source.parents:
        raise ValueError('staging would overlap source')
    return source, destination, stage


def _plan(source, destination):
    manifest = _manifest(source)
    _validate_core(source)
    return {'format_version': 1, 'source': str(source),
            'destination': str(destination), 'manifest': manifest}


def _json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode('utf-8')


def _completed(destination, plan):
    if not destination.exists():
        return False
    if not destination.is_dir() or (destination / REPORT).is_symlink():
        raise ValueError('destination already exists without a verified copy')
    if json.loads((destination / REPORT).read_text()) != plan:
        raise ValueError('destination copy receipt differs from current source')
    if set(p.name for p in destination.iterdir()) != {'memory', REPORT}:
        raise ValueError('destination contains unexpected entries')
    if _manifest(destination) != plan['manifest']:
        raise ValueError('published destination differs from recorded copy')
    _validate_core(destination)
    return True


def _stage_valid(stage, plan):
    if has_symlink_component(stage) or not stage.is_dir():
        raise ValueError('unsafe staging directory')
    if set(p.name for p in stage.iterdir()) - {'plan.json', 'tree'}:
        raise ValueError('unknown staging entry')
    if (stage / 'plan.json').is_symlink():
        raise ValueError('unsafe staging plan')
    if json.loads((stage / 'plan.json').read_text()) != plan:
        raise ValueError('staging plan differs from current source')
    tree = stage / 'tree'
    if tree.exists() or tree.is_symlink():
        if has_symlink_component(tree) or not tree.is_dir():
            raise ValueError('unsafe staging tree')
        for path in tree.rglob('*'):
            mode = path.lstat().st_mode
            relative = path.relative_to(tree).as_posix()
            if stat.S_ISDIR(mode):
                if relative not in plan['manifest']['directories']:
                    raise ValueError('unexpected staging directory')
            elif stat.S_ISREG(mode):
                if relative == REPORT:
                    if json.loads(path.read_text()) != plan:
                        raise ValueError('divergent staging receipt')
                elif (relative not in plan['manifest']['files']
                      or sha256(path.read_bytes()).hexdigest() != plan['manifest']['files'][relative]):
                    raise ValueError('divergent or unexpected staging file')
            else:
                raise ValueError('unsafe staging entry')


def _report(status, plan, stage):
    return {'status': status, 'source': plan['source'],
            'destination': plan['destination'], 'files': len(plan['manifest']['files']),
            'staging': str(stage), 'issues': []}


def _blocked(exc):
    return {'status': 'BLOCKED', 'issues': [{'reason': str(exc)}]}


def inspect_core_copy(source, destination):
    try:
        source, destination, stage = _paths(source, destination)
        plan = _plan(source, destination)
        if _completed(destination, plan):
            return _report('UNCHANGED', plan, stage)
        if stage.exists() or stage.is_symlink():
            _stage_valid(stage, plan)
        return _report('READY', plan, stage)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, BackendError) as exc:
        return _blocked(exc)


def _publish(tree, destination):
    """Linux atomic rename with NOREPLACE; never replace an intervening tree."""
    libc = ctypes.CDLL(None, use_errno=True)
    rename = getattr(libc, 'renameat2', None)
    if rename is None:
        raise ValueError('atomic no-replace directory publication is unavailable')
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(tree), -100, os.fsencode(destination), 1):
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), str(destination))
    descriptor = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _copy_may_be_in_progress(source, destination):
    """A staging or destination tree beside an existing writer lock may belong to a cooperative copier."""
    try:
        _, destination, stage = _paths(source, destination)
        lock = destination.parent / '.write.lock'
        return ((stage.exists() or destination.exists())
                and lock.is_file() and not lock.is_symlink())
    except (OSError, ValueError):
        return False


def copy_core(source, destination):
    preview = inspect_core_copy(source, destination)
    if preview['status'] == 'UNCHANGED':
        return preview
    # An unlocked preview can observe another copier's staging in flight: decide it under the lock.
    if preview['status'] == 'BLOCKED' and not _copy_may_be_in_progress(source, destination):
        return preview
    try:
        source, destination, stage = _paths(source, destination)
        with exclusive_write(destination.parent):
            plan = _plan(source, destination)
            if _completed(destination, plan):
                return _report('UNCHANGED', plan, stage)
            if stage.exists() or stage.is_symlink():
                _stage_valid(stage, plan)
            else:
                stage.mkdir(mode=0o700)
                _atomic_bytes(stage / 'plan.json', _json_bytes(plan))
            _checkpoint('after_plan')
            tree = stage / 'tree'
            tree.mkdir(mode=0o700, exist_ok=True)
            for relative in plan['manifest']['directories']:
                (tree / relative).mkdir(mode=0o700, exist_ok=True)
            for relative, digest in plan['manifest']['files'].items():
                target = tree / relative
                data = (source / relative).read_bytes()
                if sha256(data).hexdigest() != digest:
                    raise ValueError('source changed during copy')
                if not target.exists():
                    _atomic_bytes(target, data)
                _checkpoint('after_file', relative)
            _stage_valid(stage, plan)
            if _manifest(tree) != plan['manifest'] or _manifest(source) != plan['manifest']:
                raise ValueError('source or staging changed during copy')
            _validate_core(tree)
            _atomic_bytes(tree / REPORT, _json_bytes(plan))
            _checkpoint('before_publication')
            if _manifest(source) != plan['manifest'] or _manifest(tree) != plan['manifest']:
                raise ValueError('source or staging changed before publication')
            _publish(tree, destination)
            _checkpoint('after_publication')
            return _report('COPIED', plan, stage)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, BackendError) as exc:
        return _blocked(exc)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    report = (copy_core if args.apply else inspect_core_copy)(args.source, args.destination)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(report['status'] == 'BLOCKED')


if __name__ == '__main__':
    raise SystemExit(main())
