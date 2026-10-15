# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/qdrant_server_fixture.py
# Description : Own a disposable loopback Qdrant process; never use an external endpoint.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Opt-in transport fixture. Only this fixture's child PID is stopped or killed.

EIDOLON_TEST_QDRANT_BINARY must name an explicitly provisioned trusted binary.
CI verifies the pinned release archive before extraction. Data and config live
in pytest's private temporary directory. No Docker, service or model is used.
"""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time
from urllib.error import URLError, HTTPError
from urllib.request import Request, build_opener, ProxyHandler
import pytest


class DisposableQdrant:
    def __init__(self, binary, directory):
        self.binary = Path(binary).resolve(strict=True)
        self.directory = directory
        self.directory.mkdir(mode=0o700)
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        self.url = f'http://127.0.0.1:{port}'
        self.key = secrets.token_hex(32)
        self.process = None
        self.log = None
        self.opener = build_opener(ProxyHandler({}))
        self.config = self.directory/'server.yaml'
        # JSON is also valid YAML; all paths and the private API key are escaped.
        config = dict(log_level='WARN', telemetry_disabled=True, cluster=dict(enabled=False),
            storage=dict(storage_path=str(self.directory/'storage'), snapshots_path=str(self.directory/'snapshots'),
                         performance=dict(max_search_threads=2, optimizer_cpu_budget=1),
                         optimizers=dict(default_segment_number=1, max_optimization_threads=1),
                         hnsw_index=dict(max_indexing_threads=1)),
            service=dict(host='127.0.0.1', http_port=port, grpc_port=None, max_workers=2,
                         enable_cors=False, api_key=self.key))
        self.config.write_text(json.dumps(config))
        self.config.chmod(0o600)

    def start(self):
        if self.process is not None:
            raise RuntimeError('server is already owned')
        self.log = (self.directory/'server.log').open('ab')
        env = {k: v for k, v in os.environ.items() if not k.startswith('QDRANT__')}
        self.process = subprocess.Popen([str(self.binary), '--config-path', str(self.config)],
            cwd=self.directory, env=env, stdout=self.log, stderr=subprocess.STDOUT)
        deadline = time.monotonic()+25
        try:
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError('owned Qdrant exited during startup; inspect server.log')
                try:
                    request = Request(self.url+'/collections', headers={'api-key': self.key})
                    with self.opener.open(request, timeout=0.5) as response:
                        payload = json.load(response)
                    if payload.get('status') != 'ok':
                        raise RuntimeError('unexpected server readiness response')
                    # An unrelated open endpoint must not satisfy readiness.
                    try:
                        self.opener.open(Request(self.url+'/collections'), timeout=0.5).close()
                    except HTTPError as exc:
                        if exc.code not in (401, 403):
                            raise
                    else:
                        raise RuntimeError('server did not require its unique test credential')
                    with self.opener.open(Request(self.url+'/', headers={'api-key': self.key}), timeout=1) as response:
                        if json.load(response).get('version') != '1.15.4':
                            raise RuntimeError('unexpected Qdrant release')
                    if self.process.poll() is not None:
                        raise RuntimeError('owned Qdrant exited during readiness')
                    return
                except (URLError, TimeoutError, ConnectionError):
                    time.sleep(0.1)
            raise RuntimeError('owned Qdrant did not become ready within 25 seconds')
        except BaseException:
            self.stop()
            raise

    def stop(self, *, crash=False):
        if self.process is None:
            return
        try:
            if self.process.poll() is None:
                self.process.kill() if crash else self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        finally:
            self.log.close()
            self.process = self.log = None

    def client(self):
        from qdrant_client import QdrantClient
        # Header avoids the client's TLS recommendation for this owned loopback
        # fixture. No endpoint or credential from an application is accepted.
        return QdrantClient(url=self.url, headers={'api-key': self.key}, timeout=3,
                            check_compatibility=False, trust_env=False)


@pytest.fixture
def qdrant_server(tmp_path):
    binary = os.environ.get('EIDOLON_TEST_QDRANT_BINARY')
    if not binary:
        pytest.skip('explicit disposable Qdrant binary required; dedicated server CI runs these cases')
    server = DisposableQdrant(binary, tmp_path/'server')
    try:
        server.start()
        yield server
    finally:
        server.stop()
