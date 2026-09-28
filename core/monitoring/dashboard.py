"""Minimal authenticated, read-only HTML dashboard for the engine host."""

from __future__ import annotations

import argparse
import base64
import binascii
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
from secrets import compare_digest
from urllib.parse import parse_qs, quote, urlsplit

from core.monitoring.files import DIRECTORIES, PAGE_SIZE, list_documents, read_document
from core.monitoring.metrics import collect_metrics
from core.monitoring.overview import overview


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
    return f"{value / (1024 ** 3):.2f} GiB"


def render_dashboard(metrics: dict, state: dict) -> str:
    ram = metrics["ram_bytes"]
    volume = metrics["volume_bytes"]
    data = metrics["engine_data"]

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
td:last-child{{text-align:right}}small{{color:#bfd0e1}}strong{{color:#9fe5bf}}</style></head>
<body><h1>Eidolon Memory Engine</h1><p><a href="/files">Parcourir les fichiers Markdown</a></p>
<p>Machine : <strong>{escape(str(metrics['host']))}</strong><br>
<small>Mesuré le {escape(str(metrics['measured_at']))} UTC · rafraîchissement 30 s</small></p>
<main><section><h2>RAM hôte</h2><p>Utilisée : {_size(ram['used'])}<br>Disponible : {_size(ram['available'])}<br>
Total : {_size(ram['total'])}</p></section>
<section><h2>Volume des données</h2><p>Utilisé : {_size(volume['used'])}<br>Libre : {_size(volume['free'])}<br>
Total : {_size(volume['total'])}</p><small>{escape(str(metrics['data_path']))}</small></section>
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


def handler_factory(engine_root: Path, token: str):
    class DashboardHandler(BaseHTTPRequestHandler):
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
                body = page.encode("utf-8")
            except (OSError, ValueError, KeyError, TypeError):
                self.send_error(404, "Page or document unavailable")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'")
            self.end_headers()
            self.wfile.write(body)

    return DashboardHandler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Authenticated read-only HTML dashboard")
    parser.add_argument("--root", type=Path, required=True, help="Engine root containing memory/")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: loopback)")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    token = os.environ.get("EIDOLON_DASHBOARD_TOKEN", "")
    if not token:
        parser.error("EIDOLON_DASHBOARD_TOKEN must be set")
    if not args.root.is_dir():
        parser.error("engine root is not a directory")
    server = ThreadingHTTPServer((args.host, args.port), handler_factory(args.root, token))
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
