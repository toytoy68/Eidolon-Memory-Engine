"""Authenticated dashboard; source additions and reviewed details are explicit opt-ins."""

from __future__ import annotations

import argparse
import base64
import binascii
from datetime import datetime, timezone
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
from secrets import compare_digest, token_urlsafe, token_bytes
from urllib.parse import parse_qs, quote, urlsplit
from zoneinfo import ZoneInfo

from core.monitoring.files import DIRECTORIES, PAGE_SIZE, list_documents, read_document
from core.monitoring.metrics import collect_metrics
from core.monitoring.overview import overview
from core.monitoring.appearance import decorate, SCRIPT_HASH
from core.sources.store import SourceStore
from core.sources.validation import seal, unseal, accept_detail
from core.sources.local_ai import LocalDetailAI, LocalAIError
from core.backend.errors import BackendError
from core.operations.errors import OperationRepositoryError
from core.monitoring.sources import MAX_REQUEST, parse_upload, render_sources, render_source, render_extraction, render_proposals
from core.monitoring.sources import render_ai_error


def authorized(header: str | None, token: str) -> bool:
    if not header or not header.startswith("Basic "):
        return False
    try:
        credentials = base64.b64decode(header[6:], validate=True).decode("utf-8")
    except (binascii.Error, UnicodeError, ValueError):
        return False
    username, separator, password = credentials.partition(":")
    return bool(separator and username == "eidolon" and compare_digest(password, token))


def _size(value: int) -> str:
    for divisor, unit in ((1024 ** 3, 'GiB'), (1024 ** 2, 'MiB'), (1024, 'KiB')):
        if value >= divisor:
            return f"{value / divisor:.2f} {unit}"
    return f"{value} octets"


def _measurement_time(value: str) -> str:
    local = datetime.fromisoformat(value).astimezone(ZoneInfo('Europe/Paris'))
    offset = local.strftime('%z')
    return local.strftime('%d-%m-%Y T %H:%M:%S ') + offset[:3] + ':' + offset[3:]


def render_dashboard(metrics: dict, state: dict) -> str:
    ram = metrics["ram_bytes"]
    volume = metrics["volume_bytes"]
    data = metrics["engine_data"]

    def chart(used, total, available, label):
        percent = max(0, min(100, used / total * 100)) if total > 0 else 0
        color = '#fb7185' if percent >= 90 else '#fbbf24' if percent >= 75 else '#8bd8ff'
        return (f'<div class="donut" role="img" aria-label="{escape(label)} : {percent:.1f} % utilisés" '
                f'style="background:conic-gradient({color} 0% {percent:.2f}%,#3b5369 {percent:.2f}% 100%)">'
                f'<div class="donut-center"><b>{percent:.1f} %</b><span>{_size(used)}</span>'
                '<small>utilisés</small></div></div>'
                f'<p class="capacity">Sur {_size(total)} au total<br><small>{_size(available)} disponibles</small></p>')

    def rows(counts):
        return "".join(f"<tr><td>{escape(str(name))}</td><td>{int(number)}</td></tr>"
                       for name, number in sorted(counts.items())) or "<tr><td colspan=2>Aucun</td></tr>"

    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="30"><title>Eidolon Memory Engine</title>
<style>body{{font:16px system-ui;background:#101827;color:#eef3fa;max-width:1000px;margin:auto;padding:2rem}}
h1{{color:#8bd8ff}}main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1rem}}
section{{background:#1d2b3e;border:1px solid #3b5369;border-radius:12px;padding:1rem}}
table{{width:100%;border-collapse:collapse}}td{{padding:.4rem;border-bottom:1px solid #3b5369}}
td:last-child{{text-align:right}}small{{color:#bfd0e1}}strong{{color:#9fe5bf}}
.donut{{width:190px;height:190px;border-radius:50%;margin:1.5rem auto;display:grid;place-items:center}}
.donut-center{{width:148px;height:148px;border-radius:50%;background:#1d2b3e;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:.3rem}}
.donut-center b{{font-size:2rem}}.capacity{{text-align:center;line-height:1.7}}a{{color:#8bd8ff}}</style></head>
<body><h1>Eidolon Memory Engine</h1><p><a href="/files">Parcourir les fichiers Markdown</a> · <a href="/sources">Sources</a></p>
<p>Machine : <strong>{escape(str(metrics['host']))}</strong><br>
<small>Mesuré le {escape(_measurement_time(str(metrics['measured_at'])))} UTC · rafraîchissement 30 s</small></p>
<main><section><h2>Mémoire de la VM</h2>{chart(ram['used'], ram['total'], ram['available'], 'Mémoire de la VM')}</section>
<section><h2>Espace disque</h2>{chart(volume['used'], volume['total'], volume['free'], 'Espace disque')}<small>{escape(str(metrics['data_path']))}</small></section>
<section><h2>Fichiers du moteur</h2><p>{int(data['files'])} fichiers · {_size(data['bytes'])} logiques<br>
Liens ignorés : {int(data['symlinks_skipped'])}</p></section>
<section><h2>Threads</h2><table>{rows(state['threads']['statuses'])}</table>
<small>À examiner : {len(state['threads']['needs_review'])}</small></section>
<section><h2>Opérations de statut</h2><table>{rows(state['thread_status_operations']['statuses'])}</table>
<p>En attente : <strong>{int(state['pending_operations'])}</strong></p>
<small>À examiner : {len(state['thread_status_operations']['needs_review'])}</small></section></main>
<p><small>Vue en lecture seule. Les journaux historiques et l'index Qdrant externe ne sont pas comptés.</small></p>
</body></html>"""


def render_files(root: Path, category: str | None, offset: int = 0) -> str:
    links = " · ".join(f'<a href="/files?category={quote(key)}">{escape(key)}</a>'
                       for key in DIRECTORIES)
    body = "<p>Sélectionner une catégorie.</p>"
    if category is not None:
        names = list_documents(root, category, offset)
        items = "".join(
            f'<li><a href="/view?category={quote(category)}&name={quote(name)}">'
            f'{escape(name)}</a></li>' for name in names
        ) or "<li>Aucun fichier sur cette page.</li>"
        next_link = (f'<a href="/files?category={quote(category)}&offset={offset + PAGE_SIZE}">'
                     "Page suivante</a>") if len(names) == PAGE_SIZE else ""
        previous = (f'<a href="/files?category={quote(category)}&offset={max(0, offset-PAGE_SIZE)}">'
                    "Page précédente</a>") if offset else ""
        body = f"<h2>{escape(category)}</h2><ul>{items}</ul><p>{previous} {next_link}</p>"
    return ("<!doctype html><html lang=fr><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            "<title>Fichiers Eidolon</title><style>body{font:16px system-ui;max-width:950px;"
            "margin:auto;padding:2rem;background:#101827;color:#eef3fa}a{color:#8bd8ff}"
            "li{margin:.5rem 0}</style></head><body><a href='/'>Tableau de bord</a>"
            f"<h1>Fichiers Markdown</h1><p>{links}</p>{body}</body></html>")


def render_document(category: str, name: str, content: str) -> str:
    return ("<!doctype html><html lang=fr><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            "<title>Document Eidolon</title><style>body{font:16px system-ui;max-width:1050px;"
            "margin:auto;padding:2rem;background:#101827;color:#eef3fa}a{color:#8bd8ff}"
            "pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#1d2b3e;padding:1rem}"
            "</style></head><body>"
            f'<a href="/files?category={quote(category)}">Retour aux fichiers</a>'
            f"<h1>{escape(name)}</h1><pre>{escape(content)}</pre></body></html>")


def handler_factory(engine_root: Path, token: str, *, allow_source_upload=False, local_ai=None):
    store = SourceStore(engine_root)
    csrf = token_urlsafe(32)
    review_secret = token_bytes(32)

    def library_page(result=None):
        inspection = store.inspect()
        return render_sources(inspection['sources'], pending=inspection['pending'],
                              issues=inspection['issues'], csrf=csrf if allow_source_upload else None,
                              result=result)
    class DashboardHandler(BaseHTTPRequestHandler):
        def _page(self, page, status=200):
            body = decorate(page).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; "
                             f"script-src 'sha256-{SCRIPT_HASH}'; img-src data:; "
                             "form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if not authorized(self.headers.get('Authorization'), token):
                self.send_error(401)
                return
            if self.path not in {'/sources', '/source/extract', '/source/propose', '/source/accept'} or not allow_source_upload:
                self.send_error(403, 'Source upload is disabled')
                return
            try:
                lengths = self.headers.get_all('Content-Length', [])
                if len(lengths) != 1 or self.headers.get('Transfer-Encoding'):
                    raise ValueError('bounded content length required')
                size = int(lengths[0])
                if not 0 < size <= MAX_REQUEST:
                    self.send_error(413, 'Source exceeds upload limit')
                    return
                self.connection.settimeout(10)
                raw = self.rfile.read(size)
                if len(raw) != size:
                    raise ValueError('incomplete upload')
                if self.path != '/sources':
                    if self.headers.get('Content-Type', '').split(';')[0] != 'application/x-www-form-urlencoded' or size > 65536:
                        raise ValueError('invalid source action form')
                    fields = parse_qs(raw.decode('utf-8'), strict_parsing=True)
                    if any(len(v) != 1 for v in fields.values()) or not compare_digest(fields.get('csrf', [''])[0], csrf):
                        raise ValueError('invalid source action request')
                    if self.path == '/source/accept':
                        if set(fields) != {'csrf', 'review', 'detail'}:
                            raise ValueError('incomplete detail validation')
                        review = unseal(fields['review'][0], review_secret)
                        result = accept_detail(engine_root, review, detail=fields['detail'][0], actor='dashboard-user')
                        self._page(library_page(result='DETAIL_ACCEPTED'))
                        return
                    if set(fields) != ({'csrf', 'id'} if self.path == '/source/extract' else {'csrf', 'id', 'start'}):
                        raise ValueError('incomplete source action')
                    identity = fields['id'][0]
                    record = store.read(identity)[0]
                    if self.path == '/source/extract':
                        extracted = store.extract(identity)['extraction']
                        self._page(render_extraction(record, extracted, csrf=csrf, ai_enabled=local_ai is not None))
                        return
                    if local_ai is None:
                        raise ValueError('local AI is not configured')
                    proposals = local_ai.propose(record, store.extraction(identity), start=int(fields['start'][0]))
                    proposed_at = datetime.now(timezone.utc).isoformat()
                    tokens = [seal(dict(source_id=identity, source_sha256=proposals['source_sha256'],
                        extraction_sha256=proposals['extraction_sha256'], extractor=proposals['extractor'],
                        model=proposals['model'], model_digest=proposals['model_digest'],
                        proposed_at=proposed_at, **item), review_secret) for item in proposals['details']]
                    self._page(render_proposals(record, proposals, tokens, csrf))
                    return
                upload = parse_upload(self.headers.get('Content-Type'), raw, csrf)
                result = store.add(**upload, added_at=datetime.now(timezone.utc).isoformat())
                self._page(library_page(result=result['status']))
            except LocalAIError as exc:
                status, page = render_ai_error(exc.code, fields['id'][0])
                self._page(page, status=status)
            except ImportError:
                self.log_error('Missing runtime dependency; launch using the project virtual environment')
                self.send_error(500, 'Dependance serveur manquante; contacter l administrateur.')
            except (OSError, ValueError, TypeError, KeyError, BackendError, OperationRepositoryError):
                self.send_error(400, 'Action non terminee; verifier le fichier, le formulaire et le moteur local. Une source deja conservee reste intacte.')

        def do_GET(self):
            if not authorized(self.headers.get("Authorization"), token):
                self.send_response(401)
                self.send_header("WWW-Authenticate", 'Basic realm="Eidolon Dashboard"')
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            try:
                url = urlsplit(self.path)
                if url.path == "/" and not url.query:
                    page = render_dashboard(collect_metrics(engine_root), overview(engine_root))
                elif url.path == '/sources' and not url.query:
                    page = library_page()
                elif url.path in {'/source', '/source/original', '/source/text'}:
                    query = parse_qs(url.query, keep_blank_values=True)
                    allowed = {'id', 'page'} if url.path == '/source/text' else {'id'}
                    if 'id' not in query or not set(query) <= allowed or any(len(values) != 1 for values in query.values()):
                        raise ValueError('one source identity required')
                    record, original = store.read(query['id'][0])
                    if url.path == '/source/original':
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/octet-stream')
                        self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + quote(record['original_name'], safe=''))
                        self.send_header('Content-Length', str(len(original)))
                        self.send_header('Cache-Control', 'no-store')
                        self.send_header('X-Content-Type-Options', 'nosniff')
                        self.end_headers()
                        self.wfile.write(original)
                        return
                    if url.path == '/source/text':
                        page = render_extraction(record, store.extraction(record['source_id']),
                                                 csrf=csrf if allow_source_upload else None, ai_enabled=local_ai is not None,
                                                 page=int(query.get('page', ['1'])[0]))
                    else:
                        page = render_source(record, csrf=csrf if allow_source_upload else None,
                                             has_extraction=(store.directory / record['source_id'] / 'extraction.json').exists())
                elif url.path == "/files":
                    query = parse_qs(url.query)
                    category = query.get("category", [None])[0]
                    offset = int(query.get("offset", ["0"])[0])
                    page = render_files(engine_root, category, offset)
                elif url.path == "/view":
                    query = parse_qs(url.query)
                    category = query["category"][0]
                    name = query["name"][0]
                    page = render_document(category, name,
                                           read_document(engine_root, category, name))
                else:
                    self.send_error(404)
                    return
            except (OSError, ValueError, KeyError, TypeError):
                self.send_error(404, "Page or document unavailable")
                return
            self._page(page)

    return DashboardHandler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Authenticated dashboard with optional source upload and human-reviewed AI details")
    parser.add_argument("--root", type=Path, required=True, help="Engine root containing memory/")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: loopback)")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument('--allow-source-upload', action='store_true', help='Enable explicit source additions; canonical memory remains separate')
    parser.add_argument('--local-ai-model', help='Explicit installed local Ollama model for detail proposals')
    parser.add_argument('--local-ai-url', default='http://127.0.0.1:11435', help='Dedicated loopback Ollama endpoint')
    args = parser.parse_args(argv)
    token = os.environ.get("EIDOLON_DASHBOARD_TOKEN", "")
    if not token:
        parser.error("EIDOLON_DASHBOARD_TOKEN must be set")
    if not args.root.is_dir():
        parser.error("engine root is not a directory")
    if args.allow_source_upload:
        try:
            from core.migration.converter import _atomic_bytes
            from core.migration.core_copy import _publish
        except ImportError:
            parser.error('Source upload dependencies unavailable; use .venv/bin/python or scripts/run-dashboard.sh')
    local_ai = LocalDetailAI(model=args.local_ai_model, endpoint=args.local_ai_url) if args.local_ai_model else None
    server = ThreadingHTTPServer((args.host, args.port), handler_factory(args.root, token, allow_source_upload=args.allow_source_upload, local_ai=local_ai))
    print(f"Eidolon dashboard listening on {args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
