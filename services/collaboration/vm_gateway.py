# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : services/collaboration/vm_gateway.py
# Description : Forced SSH gateway for diagnostics and isolated memory workspaces.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Fixed protocols only; workspace edits and tests use a trusted isolated controller."""
import base64
import hashlib
import json
import os
from pathlib import Path
import shlex
import stat
import re
import subprocess
import sys
import signal

LIMIT = 65536


def read_file(root, relative):
    path = Path(relative)
    if path.is_absolute() or not path.parts or any(p in (".", "..") or p.startswith(".") for p in path.parts):
        raise ValueError("Invalid relative path")
    if path.suffix not in {".py", ".md", ".json", ".txt", ".csv"}:
        raise ValueError("File type not allowed")
    # Walk with directory descriptors: reject symlinks and traversal, including races.
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[:-1]:
            next_descriptor = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        file_descriptor = os.open(path.parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
        with os.fdopen(file_descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > LIMIT:
                raise ValueError("Requires a regular file of at most 65536 bytes")
            data = stream.read(LIMIT + 1)
            if len(data) > LIMIT:
                raise ValueError("File too large")
        return {"content": data.decode("utf-8"), "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data), "mtime_ns": info.st_mtime_ns, "trust": "UNVERIFIED"}
    finally:
        os.close(descriptor)


def inventory(root):
    files = []
    for directory, dirs, names in os.walk(root, followlinks=False):
        current = Path(directory)
        dirs[:] = sorted(n for n in dirs if not n.startswith('.') and not (current / n).is_symlink()
                         and len((current / n).relative_to(root).parts) <= 5)
        for name in sorted(names):
            path = current / name
            info = path.lstat()
            if not name.startswith('.') and stat.S_ISREG(info.st_mode) and path.suffix in {'.py', '.md', '.json', '.txt', '.csv'}:
                files.append({'path': str(path.relative_to(root)), 'bytes': info.st_size})
                if len(files) == 500:
                    return {'files': files, 'truncated': True}
    return {'files': files, 'truncated': False}


def dispatch(request, roots, benchmark_config=None):
    if not isinstance(request, dict):
        raise ValueError("Object required")
    action = request.get("action")

    if action == "execute" and set(request) == {"action", "command"}:
        command = request["command"]
        if not isinstance(command, str) or not command.strip() or len(command) > 6000:
            raise ValueError("Invalid command")
        import tempfile
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            process = subprocess.Popen(
                ["/bin/bash", "-c", command],
                stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                start_new_session=True,
            )
            timed_out = False
            try:
                process.wait(timeout=25)
            except subprocess.TimeoutExpired:
                timed_out = True
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            out.seek(0)
            err.seek(0)
            stdout = out.read(LIMIT + 1)
            stderr = err.read(LIMIT + 1)
        return {
            "exit_code": process.returncode,
            "timed_out": timed_out,
            "stdout": stdout[:LIMIT].decode("utf-8", "replace"),
            "stderr": stderr[:LIMIT].decode("utf-8", "replace"),
            "truncated": len(stdout) > LIMIT or len(stderr) > LIMIT,
        }
    if action == "diagnostic" and set(request) == {"action"}:
        results = {}
        for name, argv in {
            "hostname": ["/usr/bin/hostname"],
            "kernel": ["/usr/bin/uname", "-sr"],
            "python": ["/usr/bin/python3", "--version"],
            "services": ["/usr/bin/systemctl", "list-units", "--type=service", "--all", "--no-pager", "eidolon*"],
        }.items():
            result = subprocess.run(argv, capture_output=True, timeout=10, env={"PATH": "/usr/bin:/bin", "LANG": "C"})
            results[name] = {"returncode": result.returncode, "stdout": result.stdout[:8192].decode("utf-8", "replace")}
        return {"diagnostic": results, "roots": {name: {"exists": Path(root).is_dir()} for name, root in roots.items()}}
    if action == "read" and set(request) == {"action", "root", "path"}:
        if request["root"] not in roots or not isinstance(request["path"], str):
            raise ValueError("Unknown root or invalid path")
        return read_file(roots[request["root"]], request["path"])
    if action == 'inventory' and set(request) == {'action', 'root'}:
        if request['root'] not in roots:
            raise ValueError('Unknown root')
        return inventory(roots[request['root']])
    if benchmark_config and (
        action == 'benchmark_start' and set(request) == {'action'}
        or action == 'benchmark_status' and set(request) == {'action', 'job_id'}
    ):
        runner = Path('/usr/local/lib/eidolon-vm/vm_benchmark.py')
        info = runner.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('Unsafe benchmark launcher')
        argv = ['/usr/bin/python3', '-I', str(runner),
                '--start' if action == 'benchmark_start' else '--status', str(benchmark_config)]
        if action == 'benchmark_status':
            if not isinstance(request['job_id'], str) or not re.fullmatch('[0-9a-f]{32}', request['job_id']):
                raise ValueError('Invalid job ID')
            argv.append(request['job_id'])
        result = subprocess.run(argv, capture_output=True, timeout=15,
                                env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
        if result.returncode or len(result.stdout) > 350000:
            raise ValueError('Benchmark unavailable')
        return json.loads(result.stdout)
    raise ValueError("Action not allowed")


def main():
    try:
        # Only an operator-owned configuration file can define accessible directories.
        config_path = Path(sys.argv[1])
        info = config_path.stat()
        if info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError("Configuration must be root-owned and not writable by group/others")
        configuration = json.loads(config_path.read_text())
        roots = configuration["roots"]
        command = shlex.split(os.environ.get("SSH_ORIGINAL_COMMAND", ""))
        if command == ["eidolon-workspace-v1"]:
            # A fixed protocol marker, never a shell command or caller-supplied argv.
            signal.alarm(10)
            data = sys.stdin.buffer.read(200001)
            signal.alarm(0)
            if len(data) > 200000:
                raise ValueError("Workspace request too large")
            module = Path(__file__).resolve().with_name('vm_workspace.py')
            module_info = module.lstat()
            parent_info = module.parent.stat()
            if (not stat.S_ISREG(module_info.st_mode) or module_info.st_uid != 0
                    or module_info.st_mode & 0o022 or parent_info.st_uid != 0
                    or parent_info.st_mode & 0o022):
                raise ValueError("Unsafe workspace controller")
            # Works under python -I; only the checked operator-owned sibling is imported.
            sys.path.insert(0, str(module.parent))
            import vm_workspace
            result = vm_workspace.dispatch(json.loads(data), config_path)
        else:
            if len(command) != 2 or command[0] != "eidolon-read-v1" or len(command[1]) > 8192:
                raise ValueError("Invalid gateway command")
            request = json.loads(base64.b64decode(command[1], validate=True))
            result = dispatch(request, roots, config_path if 'benchmark' in configuration else None)
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=True))
    except Exception:
        print(json.dumps({"ok": False, "error": "Gateway request rejected or unavailable"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
