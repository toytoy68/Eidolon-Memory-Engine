# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : vm_workspace.py
# Description : Workspaces Git et jobs de tests isolés, sans shell appelant.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Trusted host controller. Only core/*.py can change; no production corpus is copied."""
from contextlib import contextmanager
import fcntl
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import resource
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import time
import uuid

MAX_PATCH = 131072
MAX_FILE = 65536
MAX_LOG = 262144
TIMEOUT = 180
ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'}
SUPPORT = {'tools/__init__.py', 'tools/generate_scenario.py',
           'tools/vm_acceptance.py', 'tools/writer_inventory.py'}


def snapshot_path(path):
    return path.parts[0] in ('core', 'tests', 'schemas') or str(path) in SUPPORT


SUITES = {
    'unit': ['tests/test_filesystem_backend.py', 'tests/test_information_writes.py',
             'tests/test_lexical_ranking.py'],
    'routing': ['tests/test_routing_execution.py', 'tests/test_routing_outcomes.py',
                'tests/test_routing_existing_information.py', 'tests/test_routing_new_project.py',
                'tests/test_routing_information_only.py'],
    'recall': ['tests/test_contextual_recall.py', 'tests/test_recall_payload.py',
               'tests/test_context_assembly.py', 'tests/test_lexical_ranking.py'],
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def relative(value):
    if not isinstance(value, str) or not value or len(value) > 240:
        raise ValueError('Invalid path')
    parts = value.split('/')
    if any(not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*', p) or p in ('.', '..') for p in parts):
        raise ValueError('Invalid path')
    return PurePosixPath(value)


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{32}', value):
        raise ValueError('Invalid identifier')
    return value


def regular_bytes(root, name, limit=MAX_FILE):
    """Descriptor walk rejects links, special files and concurrent path replacement."""
    parts = relative(name).parts
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        child = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(child, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
                raise ValueError('Regular unlinked file required')
            data = stream.read(limit + 1)
            if len(data) > limit:
                raise ValueError('File too large')
            return data
    finally:
        os.close(fd)


def atomic_json(path, data):
    temp = path.with_name(path.name + '.new')
    with temp.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def lock(path):
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError('Unsafe lock')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Workspace busy') from None
        yield fd
    finally:
        os.close(fd)


def parse_patch(patch):
    """Strict unified diff for existing UTF-8 files; no create/delete/rename or git extensions."""
    if not isinstance(patch, str) or len(patch.encode()) > MAX_PATCH:
        raise ValueError('Patch too large')
    lines = patch.splitlines(keepends=True)
    result = {}
    index = 0
    while index < len(lines):
        if not lines[index].startswith('--- a/') or index + 1 >= len(lines):
            raise ValueError('Expected unified diff')
        name = lines[index][6:].rstrip('\n')
        path = relative(name)
        if path.parts[0] != 'core' or len(path.parts) < 2 or path.suffix != '.py':
            raise ValueError('Protected path')
        if name in result or lines[index + 1] != '+++ b/' + name + '\n':
            raise ValueError('Duplicate or renamed path')
        index += 2
        hunks = []
        while index < len(lines) and not lines[index].startswith('--- a/'):
            match = re.fullmatch(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n', lines[index])
            if not match:
                raise ValueError('Invalid hunk')
            old, old_count, new, new_count = (int(match[1]), int(match[2] or 1), int(match[3]), int(match[4] or 1))
            index += 1
            body = []
            consumed = added = 0
            while consumed < old_count or added < new_count:
                if index >= len(lines) or lines[index][:1] not in (' ', '+', '-') or not lines[index].endswith('\n'):
                    raise ValueError('Invalid hunk body')
                line = lines[index]
                consumed += line[0] in (' ', '-')
                added += line[0] in (' ', '+')
                body.append(line)
                index += 1
                if consumed > old_count or added > new_count:
                    raise ValueError('Invalid hunk counts')
            hunks.append((old, old_count, new, new_count, body))
        if not hunks:
            raise ValueError('Empty diff')
        result[name] = hunks
    if not result or len(result) > 64:
        raise ValueError('Invalid patch')
    return result


def apply_hunks(data, hunks):
    lines = data.decode('utf-8').splitlines(keepends=True)
    out = []
    cursor = 0
    for old, old_count, new, new_count, body in hunks:
        start = old - 1 if old_count else old
        if start < cursor or start > len(lines):
            raise ValueError('Overlapping or invalid hunk')
        out.extend(lines[cursor:start])
        if (new - 1 if new_count else new) != len(out):
            raise ValueError('Invalid new position')
        cursor = start
        for line in body:
            if line[0] in (' ', '-'):
                if cursor >= len(lines) or lines[cursor] != line[1:]:
                    raise ValueError('Patch context mismatch')
                cursor += 1
            if line[0] in (' ', '+'):
                out.append(line[1:])
    out.extend(lines[cursor:])
    data = ''.join(out).encode('utf-8')
    if len(data) > MAX_FILE:
        raise ValueError('Patched file too large')
    return data


class Workspaces:
    def __init__(self, configuration, config_path=None):
        self.repo = Path(configuration['repo']).resolve(strict=True)
        self.state = Path(configuration['state'])
        self.runtime = Path(configuration['runtime'])
        self.config_path = config_path
        if not self.state.is_absolute() or self.state == self.repo or self.repo in self.state.parents:
            raise ValueError('State must be outside source')
        self.state.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.state.is_symlink() or self.state.stat().st_mode & 0o077:
            raise ValueError('Private state required')
        for directory in ('workspaces', 'jobs'):
            (self.state / directory).mkdir(mode=0o700, exist_ok=True)
            if (self.state / directory).is_symlink():
                raise ValueError('Unsafe state')

    def workspace(self, value):
        root = self.state / 'workspaces' / identifier(value)
        if root.is_symlink() or not root.is_dir():
            raise ValueError('Unknown workspace')
        return root

    def metadata(self, root):
        return json.loads(regular_bytes(root, 'metadata.json', 1048576))

    def tree(self, root, meta):
        name = identifier(meta['generation'])
        tree = root / name
        if tree.is_symlink() or not tree.is_dir():
            raise ValueError('Unsafe generation')
        return tree

    def manifest(self, tree):
        hashes = {}
        for directory, dirs, files in os.walk(tree, followlinks=False):
            for name in dirs:
                if (Path(directory) / name).is_symlink():
                    raise ValueError('Symlink directory')
            for name in files:
                path = str((Path(directory) / name).relative_to(tree))
                hashes[path] = digest(regular_bytes(tree, path, 1048576))
        return hashes

    def verify(self, tree, meta):
        hashes = self.manifest(tree)
        if hashes != meta['hashes']:
            raise ValueError('Workspace integrity mismatch')
        return hashes

    def create(self, revision):
        if not isinstance(revision, str) or not re.fullmatch('[0-9a-f]{40}', revision):
            raise ValueError('Exact full Git commit required')
        with lock(self.state / 'allocation.lock'):
            if len(list((self.state / 'workspaces').iterdir())) >= 32:
                raise ValueError('Workspace quota reached')
            argv = ['/usr/bin/git', '--no-replace-objects', '-c', 'core.hooksPath=/dev/null',
                    '-c', 'safe.directory=' + str(self.repo), '-C', str(self.repo)]
            resolved = subprocess.run(argv + ['rev-parse', '--verify', revision + '^{commit}'],
                                      capture_output=True, check=True, timeout=10, env=ENV).stdout.decode().strip()
            if resolved != revision:
                raise ValueError('Exact commit required')
            # Exact blobs, ignoring export-subst/ignore attributes and the working tree.
            listing = subprocess.run(argv + ['ls-tree', '-rz', revision, '--', 'core', 'tests', 'schemas', *sorted(SUPPORT)],
                                     capture_output=True, check=True, timeout=10, env=ENV).stdout
            if len(listing) > 2 * 1024 * 1024:
                raise ValueError('Tree too large')
            entries = []
            for record in listing.split(b'\0'):
                if not record:
                    continue
                header, name = record.split(b'\t', 1)
                mode, kind, oid = header.decode().split()
                path = relative(name.decode('utf-8'))
                if not snapshot_path(path) or mode not in ('100644', '100755') or kind != 'blob':
                    raise ValueError('Snapshot links/special files forbidden')
                entries.append((path, oid))
            if not entries or len(entries) > 8192:
                raise ValueError('Snapshot quota exceeded')
            sizes = subprocess.run(argv + ['cat-file', '--batch-check'],
                input=''.join(oid + '\n' for _, oid in entries).encode(),
                capture_output=True, check=True, timeout=10, env=ENV).stdout.decode().splitlines()
            if len(sizes) != len(entries):
                raise ValueError('Invalid Git object listing')
            total = 0
            for (_, oid), record in zip(entries, sizes):
                fields = record.split()
                if len(fields) != 3 or fields[:2] != [oid, 'blob']:
                    raise ValueError('Invalid Git object')
                size = int(fields[2])
                total += size
                if size < 0 or size > 1048576 or total > 16 * 1024 * 1024:
                    raise ValueError('Snapshot quota exceeded')
            with __import__('tempfile').TemporaryFile() as stream:
                subprocess.run(argv + ['cat-file', '--batch'],
                    input=''.join(oid + '\n' for _, oid in entries).encode(),
                    stdout=stream, stderr=subprocess.DEVNULL, check=True, timeout=20, env=ENV)
                if stream.tell() > 32 * 1024 * 1024:
                    raise ValueError('Snapshot too large')
                stream.seek(0)
                workspace_id, generation = uuid.uuid4().hex, uuid.uuid4().hex
                root = self.state / 'workspaces' / workspace_id
                tree = root / generation
                root.mkdir(mode=0o700)
                tree.mkdir(mode=0o700)
                try:
                    total = 0
                    for path, oid in entries:
                        fields = stream.readline(128).decode().strip().split()
                        if len(fields) != 3 or fields[:2] != [oid, 'blob']:
                            raise ValueError('Invalid Git object')
                        size = int(fields[2])
                        total += size
                        if size < 0 or size > 1048576 or total > 16 * 1024 * 1024:
                            raise ValueError('Snapshot quota exceeded')
                        data = stream.read(size)
                        if len(data) != size or stream.read(1) != b'\n':
                            raise ValueError('Truncated Git blob')
                        if hashlib.sha1(b'blob ' + str(size).encode() + b'\0' + data).hexdigest() != oid:
                            raise ValueError('Corrupt Git blob')
                        dest = tree / path
                        dest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                        with dest.open('xb') as output:
                            output.write(data)
                        dest.chmod(0o600)
                    hashes = self.manifest(tree)
                    suites = {name: files for name, files in SUITES.items()
                              if all(p in hashes for p in files) and (name == 'unit' or SUPPORT <= hashes.keys())}
                    meta = {'base_revision': revision, 'generation': generation, 'hashes': hashes, 'suites': suites}
                    atomic_json(root / 'metadata.json', meta)
                    return {'workspace_id': workspace_id, 'base_revision': revision,
                            'suites': suites, 'modifiable': 'existing core/**/*.py', 'trust': 'UNVERIFIED'}
                except BaseException:
                    shutil.rmtree(root)
                    raise

    def read(self, workspace_id, path):
        root = self.workspace(workspace_id)
        if not snapshot_path(relative(path)):
            raise ValueError('Protected path')
        with lock(root / 'workspace.lock'):
            meta = self.metadata(root)
            tree = self.tree(root, meta)
            data = regular_bytes(tree, path)
            if digest(data) != meta['hashes'].get(path):
                raise ValueError('Integrity mismatch')
            return {'content': data.decode('utf-8'), 'sha256': digest(data), 'bytes': len(data), 'trust': 'UNVERIFIED'}

    def patch(self, workspace_id, patch, expected_hashes):
        hunks = parse_patch(patch)
        if not isinstance(expected_hashes, dict) or set(expected_hashes) != set(hunks):
            raise ValueError('Hashes required for every affected file, exactly')
        root = self.workspace(workspace_id)
        with lock(root / 'workspace.lock'):
            meta = self.metadata(root)
            tree = self.tree(root, meta)
            self.verify(tree, meta)
            # Capture checked bytes through descriptor walks, never follow paths in copytree.
            captured = {name: regular_bytes(tree, name, 1048576) for name in meta['hashes']}
            if {name: digest(data) for name, data in captured.items()} != meta['hashes']:
                raise ValueError('Workspace changed during capture')
            changes = {}
            # Validate ALL old hashes and ALL hunks before even staging a write.
            for name, pieces in hunks.items():
                if name not in captured or len(captured[name]) > MAX_FILE:
                    raise ValueError('Existing bounded code file required')
                data = captured[name]
                if expected_hashes[name] != digest(data):
                    raise ValueError('Stale SHA-256')
                changes[name] = apply_hunks(data, pieces)
            generation = uuid.uuid4().hex
            staged = root / generation
            try:
                staged.mkdir(mode=0o700)
                for name, data in {**captured, **changes}.items():
                    dest = staged / relative(name)
                    dest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    with dest.open('xb') as stream:
                        stream.write(data)
                        stream.flush()
                        os.fsync(stream.fileno())
                    dest.chmod(0o600)
                hashes = self.manifest(staged)
                # Single publication point; interruption before this keeps the old tree active.
                atomic_json(root / 'metadata.json', {**meta, 'generation': generation, 'hashes': hashes})
            except BaseException:
                if staged.exists():
                    shutil.rmtree(staged)
                raise
            shutil.rmtree(tree)
            return {'workspace_id': workspace_id, 'hashes': {p: hashes[p] for p in changes},
                    'code_sha256': digest(json.dumps({p:h for p,h in hashes.items() if p.startswith('core/')}, sort_keys=True).encode()),
                    'snapshot_sha256': digest(json.dumps(hashes, sort_keys=True).encode())}

    def sandbox(self, tree):
        if not Path('/usr/bin/bwrap').is_file() or not self.runtime.is_dir():
            raise ValueError('Isolation unavailable')
        return ['/usr/bin/bwrap', '--unshare-all', '--unshare-user', '--unshare-cgroup',
                '--disable-userns', '--assert-userns-disabled', '--new-session', '--die-with-parent',
                '--cap-drop', 'ALL', '--clearenv', '--ro-bind', str(self.runtime), '/',
                '--proc', '/proc', '--dev', '/dev', '--size', '1342177280', '--tmpfs', '/tmp',
                '--ro-bind', str(tree), '/workspace', '--chdir', '/workspace',
                '--setenv', 'HOME', '/tmp', '--setenv', 'TMPDIR', '/tmp',
                '--setenv', 'LANG', 'C.UTF-8', '--setenv', 'PYTHONPATH', '/deps:/workspace', '--setenv', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD', '1']

    def probe(self, tree):
        result = subprocess.run(self.sandbox(tree) + ['--', '/usr/bin/python3.13', '-I', '-S', '-c',
            'import os; assert not os.path.exists("/opt"); assert not os.path.exists("/home"); '
            'assert not os.path.exists("/run"); assert os.environ.get("HOME")=="/tmp"'],
            capture_output=True, timeout=10, env=ENV)
        if result.returncode:
            raise ValueError('Isolation unavailable')

    def start(self, workspace_id, suite):
        root = self.workspace(workspace_id)
        with lock(self.state / 'allocation.lock'), lock(root / 'workspace.lock') as fd:
            meta = self.metadata(root)
            if not isinstance(suite, str) or suite not in meta['suites']:
                raise ValueError('Unknown suite')
            tree = self.tree(root, meta)
            hashes = self.verify(tree, meta)
            self.probe(tree)  # Fail closed BEFORE reporting an accepted job.
            jobs = list((self.state / 'jobs').iterdir())
            if len(jobs) >= 128:
                raise ValueError('Job quota reached')
            active = sum(json.loads(regular_bytes(job, 'status.json'))['state'] == 'running' for job in jobs)
            if active >= 4:
                raise ValueError('Active job quota reached')
            if self.config_path is None:
                raise ValueError('Worker configuration required')
            job_id = uuid.uuid4().hex
            job = self.state / 'jobs' / job_id
            job.mkdir(mode=0o700)
            status = {'job_id': job_id, 'workspace_id': workspace_id, 'suite': suite,
                      'state': 'running', 'started_at': time.time(), 'timeout_seconds': TIMEOUT,
                      'code_sha256': digest(json.dumps({p: h for p, h in hashes.items() if p.startswith('core/')}, sort_keys=True).encode()),
                      'snapshot_sha256': digest(json.dumps(hashes, sort_keys=True).encode()),
                      'base_revision': meta['base_revision'], 'exit_code': None, 'truncated': False}
            atomic_json(job / 'status.json', status)
            (job / 'output.log').touch(mode=0o600)
            try:
                subprocess.Popen(['/usr/bin/python3', '-I', str(Path(__file__).resolve()),
                    '--worker', str(self.config_path), job_id, str(fd)], pass_fds=(fd,),
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    env=ENV, start_new_session=True)
            except BaseException:
                atomic_json(job / 'status.json', {**status, 'state': 'failed', 'exit_code': -1})
                raise
            # Child inherits flock's open description and holds it until cleanup completes.
            return status

    def status(self, job_id, offset=0, limit=16000):
        identifier(job_id)
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 16000:
            raise ValueError('Invalid pagination')
        job = self.state / 'jobs' / job_id
        if job.is_symlink():
            raise ValueError('Unsafe job')
        status = json.loads(regular_bytes(job, 'status.json'))
        data = regular_bytes(job, 'output.log', MAX_LOG)
        chunk = data[offset:offset + limit]
        if status['state'] == 'running' and time.time() > status['started_at'] + TIMEOUT + 30:
            status = {**status, 'state': 'worker_lost', 'exit_code': None}
        return {**status, 'log': chunk.decode('utf-8', 'replace'),
                'log_base64': base64.b64encode(chunk).decode('ascii'), 'offset': offset,
                'next_offset': offset + len(chunk), 'log_bytes': len(data),
                'has_more': offset + len(chunk) < len(data), 'trust': 'UNVERIFIED'}


def limits():
    for kind, value in ((resource.RLIMIT_CPU, 120), (resource.RLIMIT_AS, 1073741824),
                        (resource.RLIMIT_FSIZE, 8388608), (resource.RLIMIT_NOFILE, 128),
                        (resource.RLIMIT_NPROC, 128), (resource.RLIMIT_CORE, 0)):
        resource.setrlimit(kind, (value, value))


def trusted_config(path):
    info = Path(path).lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise ValueError('Root-owned configuration required')
    config = json.loads(Path(path).read_text())['workspaces']
    runtime = Path(config['runtime'])
    if runtime.is_symlink() or not runtime.is_dir():
        raise ValueError('Runtime unavailable')
    for directory, dirs, files in os.walk(runtime, followlinks=False):
        for item in [Path(directory)] + [Path(directory) / n for n in dirs + files]:
            info = item.lstat()
            if info.st_uid != 0 or info.st_mode & 0o022 or not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                raise ValueError('Unsafe runtime')
    return config


def worker(config_path, job_id, fd):
    engine = Workspaces(trusted_config(config_path), config_path)
    job = engine.state / 'jobs' / identifier(job_id)
    status = json.loads(regular_bytes(job, 'status.json'))
    process = None
    try:
        # Verify inherited lock, never unlock it until all sandbox descendants are gone.
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        root = engine.workspace(status['workspace_id'])
        meta = engine.metadata(root)
        tree = engine.tree(root, meta)
        hashes = engine.verify(tree, meta)
        if digest(json.dumps(hashes, sort_keys=True).encode()) != status['snapshot_sha256']:
            raise ValueError('Snapshot changed')
        files = meta['suites'][status['suite']]
        code = 'import sys; sys.path[:0]=["/deps", "/workspace"]; import pytest; raise SystemExit(pytest.main(sys.argv[1:]))'
        argv = engine.sandbox(tree) + ['--', '/usr/bin/python3.13', '-I', '-S', '-B', '-c', code,
                '-p', 'no:cacheprovider', '--basetemp=/tmp/pytest', '-q', '-s', *files]
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, env=ENV, start_new_session=True, preexec_fn=limits)
        deadline = time.monotonic() + TIMEOUT
        logged = 0
        timed_out = False
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        with (job / 'output.log').open('ab', buffering=0) as log:
            while selector.get_map() or process.poll() is None:
                if time.monotonic() >= deadline:
                    timed_out = True
                    os.killpg(process.pid, signal.SIGKILL)
                    break
                if not selector.get_map():
                    time.sleep(0.05)
                for key, _ in selector.select(timeout=0.2):
                    data = os.read(key.fd, 8192)
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    kept = data[:MAX_LOG - logged]
                    log.write(kept)
                    logged += len(kept)
                    if len(kept) < len(data):
                        status['truncated'] = True
        selector.close()
        exit_code = process.wait(timeout=10)
        status.update(state='timed_out' if timed_out else 'completed', exit_code=exit_code)
    except BaseException:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)
        status.update(state='failed', exit_code=-1)
    finally:
        status['finished_at'] = time.time()
        atomic_json(job / 'status.json', status)
        os.close(fd)


def dispatch(request, config_path):
    if not isinstance(request, dict) or request.get('target') != 'memory':
        raise ValueError('Only memory is permitted')
    action = request.get('action')
    schemas = {
        'workspace_create': {'base_revision'}, 'workspace_read_file': {'workspace_id', 'path'},
        'workspace_apply_patch': {'workspace_id', 'patch', 'expected_hashes'},
        'tests_start': {'workspace_id', 'suite'}, 'tests_status': {'job_id', 'offset', 'limit'},
    }
    if action not in schemas or set(request) != schemas[action] | {'action', 'target'}:
        raise ValueError('Invalid request')
    engine = Workspaces(trusted_config(config_path), config_path)
    if action == 'workspace_create':
        return engine.create(request['base_revision'])
    if action == 'workspace_read_file':
        return engine.read(request['workspace_id'], request['path'])
    if action == 'workspace_apply_patch':
        return engine.patch(request['workspace_id'], request['patch'], request['expected_hashes'])
    if action == 'tests_start':
        return engine.start(request['workspace_id'], request['suite'])
    return engine.status(request['job_id'], request['offset'], request['limit'])


if __name__ == '__main__':
    if len(sys.argv) == 5 and sys.argv[1] == '--worker':
        worker(sys.argv[2], sys.argv[3], int(sys.argv[4]))
    else:
        raise SystemExit(2)
