# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : services/collaboration/vm_benchmark.py
# Description : Fixed offline benchmark jobs on disposable corpus snapshots.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Operator-owned launcher. No caller-selected command, file, model or query."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import uuid

RESULT_LIMIT = 250000
JOB_RE = re.compile(r"[0-9a-f]{32}")
SCRIPT = Path('/usr/local/lib/eidolon-vm/independent_benchmark.py')


def owned(path):
    info = Path(path).lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise ValueError('Requires root-owned, non-writable regular file')


def config(path):
    owned(path)
    data = json.loads(Path(path).read_text())['benchmark']
    for key in ('jobs', 'corpus', 'lab', 'repo'):
        p = Path(data[key])
        if not p.is_absolute() or p.is_symlink() or not p.is_dir():
            raise ValueError('Invalid operator path')
    owned(SCRIPT)
    if not Path('/usr/bin/bwrap').is_file():
        raise ValueError('Bubblewrap unavailable; refusing unsandboxed execution')
    return data


def save(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=True))
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def snapshot(source, destination):
    """Copy a bounded regular-file corpus; never follow filesystem links."""
    destination.mkdir()
    digest = hashlib.sha256()
    count = size = 0
    directories = 0
    def copy_directory(descriptor, relative, depth=0):
        nonlocal count, size, directories
        directories += 1
        if depth > 32 or directories > 10000:
            raise ValueError('Directory snapshot limit exceeded')
        for name in sorted(os.listdir(descriptor)):
            if name.startswith('.') or name == '__pycache__':
                continue
            info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            child = relative / name
            if stat.S_ISDIR(info.st_mode):
                nested = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                 dir_fd=descriptor)
                try:
                    (destination / child).mkdir(parents=True, exist_ok=True)
                    copy_directory(nested, child, depth + 1)
                finally:
                    os.close(nested)
                continue
            if not stat.S_ISREG(info.st_mode) or info.st_size > 2_000_000:
                raise ValueError('Invalid corpus file or symlink')
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
            with os.fdopen(fd, 'rb') as stream:
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode):
                    raise ValueError('Invalid corpus file')
                raw = stream.read(2_000_001)
                after = os.fstat(stream.fileno())
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise ValueError('Source changed during snapshot')
            size += len(raw)
            count += 1
            if size > 64_000_000 or count > 10000 or len(raw) > 2_000_000:
                raise ValueError('Corpus snapshot limit exceeded')
            target = destination / child
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            digest.update(str(child).encode() + b'\0' + hashlib.sha256(raw).digest())
    descriptor = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        copy_directory(descriptor, Path())
    finally:
        os.close(descriptor)
    return {'files': count, 'bytes': size, 'sha256': digest.hexdigest()}


def sandbox_argv(data, stage):
    return ['/usr/bin/bwrap', '--die-with-parent', '--new-session', '--unshare-all',
            '--cap-drop', 'ALL', '--ro-bind', '/', '/', '--proc', '/proc', '--dev', '/dev',
            '--tmpfs', '/home', '--tmpfs', '/run', '--tmpfs', '/tmp',
            '--ro-bind', data['lab'], '/runtime', '--bind', str(stage), '/work',
            '--ro-bind', str(SCRIPT.parent), '/benchmark-code', '--chdir', '/work',
            '--clearenv', '--setenv', 'PATH', '/usr/bin:/bin',
            '--setenv', 'HOME', '/work/home', '--setenv', 'LANG', 'C.UTF-8',
            '--setenv', 'PYTHONPATH', '/work/engine',
            '--setenv', 'PYTHONDONTWRITEBYTECODE', '1',
            '--setenv', 'HF_HUB_OFFLINE', '1', '--setenv', 'TRANSFORMERS_OFFLINE', '1',
            '--setenv', 'TOKENIZERS_PARALLELISM', 'false',
            '--setenv', 'OMP_NUM_THREADS', '2', '--setenv', 'MKL_NUM_THREADS', '2',
            '/runtime/.venv/bin/python', '/benchmark-code/independent_benchmark.py']


def limits():
    resource.setrlimit(resource.RLIMIT_CPU, (600, 600))
    resource.setrlimit(resource.RLIMIT_FSIZE, (2_000_000, 2_000_000))
    resource.setrlimit(resource.RLIMIT_AS, (12 * 1024**3, 12 * 1024**3))
    resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
    resource.setrlimit(resource.RLIMIT_NPROC, (128, 128))
    os.nice(10)


def worker(data, job):
    started = time.time()
    save(job / 'status.json', {'state': 'RUNNING', 'job_id': job.name})
    try:
        with tempfile.TemporaryDirectory(prefix='eidolon-benchmark-') as temporary:
            stage = Path(temporary)
            (stage / 'home').mkdir()
            provenance = snapshot(Path(data['corpus']), stage / 'corpus')
            (stage / 'engine').mkdir()
            engine_provenance = snapshot(Path(data['repo']) / 'core', stage / 'engine/core')
            process = None
            with tempfile.TemporaryFile() as log:
                process = subprocess.Popen(sandbox_argv(data, stage), stdout=log, stderr=log,
                                           start_new_session=True, preexec_fn=limits)
                try:
                    code = process.wait(timeout=600)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                    raise ValueError('Benchmark exceeded 600 seconds')
                log.seek(0)
                output = log.read(16000).decode('utf-8', 'replace')
            result = stage / 'result.json'
            if code or not result.is_file() or result.is_symlink() or result.stat().st_size > RESULT_LIMIT:
                raise ValueError(f'Isolated benchmark failed (code {code}): {output}')
            payload = json.loads(result.read_text())
            save(job / 'status.json', {'state': 'COMPLETED', 'job_id': job.name,
                 'elapsed_s': round(time.time() - started, 3), 'snapshot': provenance, 'engine_snapshot': engine_provenance,
                 'runner_sha256': hashlib.sha256(SCRIPT.read_bytes()).hexdigest(), 'result': payload})
    except Exception as exc:
        save(job / 'status.json', {'state': 'FAILED', 'job_id': job.name,
                                  'error': str(exc)[:16000]})


def start(data, configuration):
    jobs = Path(data['jobs'])
    fd = os.open(jobs / '.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        raise ValueError('A benchmark is already running')
    # Keep a bounded number of completed jobs. Never follow links when cleaning.
    old = sorted(p for p in jobs.iterdir() if JOB_RE.fullmatch(p.name) and p.is_dir() and not p.is_symlink())
    if len(old) >= 20:
        os.close(fd)
        raise ValueError('20 jobs retained; operator cleanup required')
    job = jobs / uuid.uuid4().hex
    job.mkdir(mode=0o700)
    save(job / 'status.json', {'state': 'QUEUED', 'job_id': job.name})
    try:
        subprocess.Popen(['/usr/bin/python3', '-I', str(Path(__file__).resolve()),
                          '--worker', str(configuration), job.name, str(fd)],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         pass_fds=(fd,), start_new_session=True)
    finally:
        os.close(fd)
    return {'state': 'QUEUED', 'job_id': job.name}


def status(data, identity):
    if not isinstance(identity, str) or not JOB_RE.fullmatch(identity):
        raise ValueError('Invalid job ID')
    job = Path(data['jobs']) / identity
    if job.is_symlink():
        raise ValueError('Invalid job directory')
    fd = os.open(job / 'status.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 350000:
            raise ValueError('Invalid status')
        return json.loads(stream.read(350001))


def main():
    data = config(sys.argv[2])
    if sys.argv[1] == '--worker' and len(sys.argv) == 5:
        if not JOB_RE.fullmatch(sys.argv[3]):
            raise ValueError('Invalid job')
        worker(data, Path(data['jobs']) / sys.argv[3])
        os.close(int(sys.argv[4]))
        return
    if sys.argv[1] == '--start' and len(sys.argv) == 3:
        result = start(data, sys.argv[2])
    elif sys.argv[1] == '--status' and len(sys.argv) == 4:
        result = status(data, sys.argv[3])
    else:
        raise ValueError('Invalid launcher arguments')
    print(json.dumps(result, ensure_ascii=True))


if __name__ == '__main__':
    main()
