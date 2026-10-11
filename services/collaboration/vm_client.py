# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : services/collaboration/vm_client.py
# Description : Bounded fixed-target SSH client for diagnostics and memory workspaces.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Operator configuration selects hosts and keys; callers cannot supply commands."""
import base64
import json
import subprocess
import os
import selectors
import time


def bounded_ssh(argv, data):
    """Bound stdin, stdout and wall time while preserving the fixed forced command."""
    process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    selector = selectors.DefaultSelector()
    output = bytearray()
    sent = 0
    deadline = time.monotonic() + 45
    try:
        os.set_blocking(process.stdout.fileno(), False)
        selector.register(process.stdout, selectors.EVENT_READ)
        if data:
            os.set_blocking(process.stdin.fileno(), False)
            selector.register(process.stdin, selectors.EVENT_WRITE)
        else:
            process.stdin.close()
        while selector.get_map() or process.poll() is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError("VM transport timeout")
            if not selector.get_map():
                time.sleep(min(0.05, remaining))
            for key, _ in selector.select(min(0.2, remaining)):
                if key.fileobj is process.stdin:
                    size = os.write(key.fd, data[sent:sent + 8192])
                    sent += size
                    if sent == len(data):
                        selector.unregister(process.stdin)
                        process.stdin.close()
                else:
                    block = os.read(key.fd, 8192)
                    if not block:
                        selector.unregister(process.stdout)
                    else:
                        if len(output) + len(block) > 400000:
                            raise ValueError("VM response too large")
                        output.extend(block)
        if process.wait(timeout=1):
            raise ValueError("VM gateway unavailable or request rejected")
        return bytes(output)
    finally:
        selector.close()
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()
        if not process.stdin.closed:
            process.stdin.close()


class VMClient:
    def __init__(self, targets):
        self.targets = targets

    def invoke(self, target, payload, *, workspace=False):
        if target not in self.targets:
            raise ValueError("Unknown VM")
        settings = self.targets[target]
        data = json.dumps(payload, ensure_ascii=True).encode()
        if workspace and len(data) > 200000:
            raise ValueError("Workspace request too large")
        encoded = base64.b64encode(data).decode()
        command = "eidolon-workspace-v1" if workspace else "eidolon-read-v1 " + encoded
        argv = ["/usr/bin/ssh", "-F", "/dev/null", "-T", "-o", "BatchMode=yes",
                "-o", "StrictHostKeyChecking=yes", "-o", "IdentitiesOnly=yes",
                "-o", "ConnectTimeout=5", "-o", "ClearAllForwardings=yes",
                "-o", "UserKnownHostsFile=" + settings["known_hosts"],
                "-i", settings["key"], settings["destination"], command]
        response = json.loads(bounded_ssh(argv, data if workspace else None))
        if not response.get("ok"):
            raise ValueError("VM gateway request rejected")
        return {"target": target, **response["result"]}

    def diagnostic(self, target):
        return self.invoke(target, {"action": "diagnostic"})

    def read(self, target, root, path):
        return self.invoke(target, {"action": "read", "root": root, "path": path})

    def inventory(self, target, root):
        return self.invoke(target, {'action': 'inventory', 'root': root})

    def benchmark_start(self, target):
        return self.invoke(target, {'action': 'benchmark_start'})

    def benchmark_status(self, target, job_id):
        return self.invoke(target, {'action': 'benchmark_status', 'job_id': job_id})

    def workspace_request(self, target, payload):
        if target != "memory":
            raise ValueError("Only memory is permitted")
        return self.invoke(target, {**payload, "target": "memory"}, workspace=True)

    def execute(self, target, command):
        if target not in {"core", "memory"}:
            raise ValueError("Execution is enabled only for core or memory")
        if not isinstance(command, str) or not command.strip() or len(command) > 6000:
            raise ValueError("Invalid command")
        return self.invoke(target, {"action": "execute", "command": command})
