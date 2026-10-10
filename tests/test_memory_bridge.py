"""Synthetic tests for the experimental Memory Bridge, no real memory accessed."""
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from services.memory_bridge import make_handler, validate_request


class FakeRecall:
    def recall(self, **kwargs):
        from dataclasses import dataclass
        @dataclass
        class Result:
            query: str
            items: tuple = ()
        return Result(kwargs["query"])


class BridgeTests(unittest.TestCase):
    def test_reject_invalid_contract(self):
        valid = dict(query="test", mode="operational", max_items=5, max_chars=4000, max_item_chars=800)
        self.assertEqual(validate_request(valid), valid)
        for change in ({"mode": "historical"}, {"max_items": True}, {"query": ""}, {"max_chars": 999999}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_request({**valid, **change})

    def test_auth_and_loopback_recall(self):
        token = "synthetic-token-" + "x" * 40
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(FakeRecall(), token))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/v1/recall"
            data = json.dumps(dict(query="test", mode="operational", max_items=5,
                                   max_chars=4000, max_item_chars=800)).encode()
            with self.assertRaises(HTTPError) as denied:
                urlopen(Request(url, data=data, method="POST"), timeout=2)
            self.assertEqual(denied.exception.code, 401)
            with urlopen(Request(url, data=data, method="POST",
                                 headers={"Authorization": "Bearer " + token}), timeout=2) as response:
                result = json.load(response)
            self.assertEqual(result["schema"], "eidolon-memory-recall/1")
            self.assertEqual(result["result"]["query"], "test")
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
