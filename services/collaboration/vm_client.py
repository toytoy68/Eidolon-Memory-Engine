# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : services/collaboration/vm_client.py
# Description : Fixed-target client for the read-only SSH gateway.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Operator configuration selects hosts and keys; callers cannot supply commands."""
import base64
import json
import subprocess
import tempfile


class VMClient:
    def __init__(self, targets):
        self.targets = targets

    def invoke(self, target, payload):
        if target not in self.targets:
            raise ValueError("Unknown VM")
        settings = self.targets[target]
        encoded = base64.b64encode(json.dumps(payload).encode()).decode()
        argv = ["/usr/bin/ssh", "-F", "/dev/null", "-T", "-o", "BatchMode=yes",
                "-o", "StrictHostKeyChecking=yes", "-o", "IdentitiesOnly=yes",
                "-o", "ConnectTimeout=5", "-o", "ClearAllForwardings=yes",
                "-o", "UserKnownHostsFile=" + settings["known_hosts"],
                "-i", settings["key"], settings["destination"], "eidolon-read-v1 " + encoded]
        with tempfile.TemporaryFile() as output:
            result = subprocess.run(argv, stdout=output, stderr=subprocess.DEVNULL, timeout=45)
            output.seek(0)
            data = output.read(400001)
        if result.returncode or len(data) > 400000:
            raise ValueError("VM gateway unavailable or request rejected")
        response = json.loads(data)
        if not response.get("ok"):
            raise ValueError("VM gateway request rejected")
        return {"target": target, **response["result"]}

    def diagnostic(self, target):
        return self.invoke(target, {"action": "diagnostic"})

    def read(self, target, root, path):
        return self.invoke(target, {"action": "read", "root": root, "path": path})
