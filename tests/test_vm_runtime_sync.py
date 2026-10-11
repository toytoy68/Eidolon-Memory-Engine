# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_vm_runtime_sync.py
# Description : Validate operator VM execution bounds and fixed targets.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
import unittest
from services.collaboration.vm_gateway import dispatch, LIMIT
from services.collaboration.vm_client import VMClient

class RuntimeTests(unittest.TestCase):
    def test_execute_roundtrip(self):
        result = dispatch({"action":"execute","command":"printf eidolon-ok"}, {})
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["stdout"], "eidolon-ok")
        self.assertFalse(result["timed_out"])
    def test_output_is_bounded(self):
        result = dispatch({"action":"execute","command":"python3 -c 'print(\"x\" * 70000)'"}, {})
        self.assertEqual(len(result["stdout"]), LIMIT)
        self.assertTrue(result["truncated"])
    def test_reject_invalid_requests(self):
        for request in [{"action":"execute","command":""},
                        {"action":"execute","command":False},
                        {"action":"execute","command":"x"*6001},
                        {"action":"execute","command":"id","extra":True}]:
            with self.subTest(request_keys=list(request)), self.assertRaises(ValueError):
                dispatch(request, {})
    def test_only_operator_targets(self):
        class FakeClient(VMClient):
            def invoke(self, target, payload, **kwargs):
                return target, payload
        client = FakeClient({})
        for target in ("core", "memory"):
            self.assertEqual(client.execute(target,"id")[0],target)
        with self.assertRaises(ValueError):
            client.execute("other","id")
