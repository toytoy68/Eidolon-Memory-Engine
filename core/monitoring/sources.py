# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/monitoring/sources.py
# Description : Source-library HTML and bounded upload parsing, separate from memory ingestion.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Source-library HTML and bounded upload parsing, separate from memory ingestion."""
from email import policy
from email.parser import BytesParser
from html import escape
from secrets import compare_digest
from urllib.parse import quote

from core.sources.store import MAX_BYTES

MAX_REQUEST = MAX_BYTES + 32768


def parse_upload(content_type, data, csrf):
    if (not isinstance(content_type, str) or len(content_type) > 512
            or '\r' in content_type or '\n' in content_type or len(data) > MAX_REQUEST):
        raise ValueError('invalid upload envelope')
    message = BytesParser(policy=policy.default).parsebytes(
        b'Content-Type: ' + content_type.encode('ascii') + b'\r\nMIME-Version: 1.0\r\n\r\n' + data)
    if message.defects or message.get_content_type() != 'multipart/form-data' or not message.is_multipart():
        raise ValueError('multipart upload required')
    fields = {}
    filename = None
    for part in message.iter_parts():
        name = part.get_param('name', header='content-disposition')
        if (part.defects or part.is_multipart() or part.get_content_disposition() != 'form-data'
                or name not in {'file', 'title', 'author', 'csrf'} or name in fields):
            raise ValueError('invalid or repeated upload field')
        raw = part.get_payload(decode=True)
        if not isinstance(raw, bytes):
            raise ValueError('invalid upload payload')
        if name == 'file':
            filename = part.get_filename()
            fields[name] = raw
        else:
            if len(raw) > 4096 or part.get_filename() is not None:
                raise ValueError('invalid upload text field')
            fields[name] = raw.decode('utf-8')
    if (set(fields) != {'file', 'title', 'author', 'csrf'} or not filename
            or not compare_digest(fields['csrf'].encode(), csrf.encode())):
        raise ValueError('upload form expired or incomplete')
    return dict(content=fields['file'], original_name=filename,
                title=fields['title'], author=fields['author'])


def shell(title, body):
    return ('<!doctype html><html lang="fr"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{escape(title)}</title><style>'
            'body{font:16px system-ui;max-width:950px;margin:auto;padding:2rem;background:#101827;color:#eef3fa}'
            'a{color:#8bd8ff}section{background:#1d2b3e;padding:1rem;margin:1rem 0;border-radius:12px}'
            'label{display:block;margin:.8rem 0}input{max-width:100%;padding:.5rem}button{padding:.7rem}'
            'pre{white-space:pre-wrap;overflow-wrap:anywhere}</style></head><body>'
            '<a href="/">Tableau de bord</a>' + f'<h1>{escape(title)}</h1>' + body + '</body></html>')


def render_ai_error(code, identity):
    status, message = {
        'BUSY': (409, 'Une analyse est déjà en cours. Attendez sa fin puis réessayez.'),
        'UNAVAILABLE': (503, 'Le moteur IA local ne répond pas. Réessayez plus tard ou demandez sa vérification.'),
        'MODEL_MISSING': (503, 'Le modèle choisi est absent du moteur local. Demandez sa vérification.'),
        'SOURCE_SUPPORT': (422, 'La proposition ne contient pas de citation exacte et identifiable dans le passage. Elle a été écartée. Vous pouvez réessayer ou passer à un autre paragraphe.'),
        'PASSAGE_TOO_LONG': (422, 'Ce paragraphe dépasse la taille autorisée pour une analyse. Choisissez un autre numéro de départ.'),
    }.get(code, (422, 'La réponse du modèle est incomplète ou illisible. Vous pouvez relancer l’analyse.'))
    page = shell('Analyse non terminée', '<p role="alert">'+escape(message)+'</p>'
                 '<p>Votre source est conservée. Aucun souvenir n’a été créé par cette analyse.</p>'
                 f'<p><a href="/source/text?id={quote(identity)}">Revenir au texte pour reprendre</a></p>')
    return status, page


def _source_form(csrf, record=None):
    record = record or {}
    title = escape(record.get('title', ''), quote=True)
    author = escape(record.get('author', ''), quote=True)
    button = 'Reprendre la conservation' if record else 'Conserver la source'
    return (f'<form action="/sources" method="post" enctype="multipart/form-data">'
            f'<input type="hidden" name="csrf" value="{escape(csrf, quote=True)}">'
            '<label>Fichier DOCX, PDF, TXT ou Markdown · 10 Mio maximum '
            '<input type="file" name="file" accept=".docx,.pdf,.txt,.md" required></label>'
            f'<label>Titre <input name="title" maxlength="512" value="{title}" required></label>'
            f'<label>Auteur <input name="author" maxlength="256" value="{author}"></label>'
            f'<button type="submit">{button}</button></form>')


def render_sources(records, *, csrf=None, result=None, pending=(), issues=(), warnings=(), information=()):
    body = ('<p>Les originaux sont conservés entiers. Ajouter une source ne transforme pas '
            'automatiquement son texte en souvenirs.</p>')
    if result:
        body += '<p role="status">' + ('Détail validé dans la mémoire, avec sa référence source.' if result == 'DETAIL_ACCEPTED' else 'Source ajoutée.' if result == 'ADDED' else 'Cette source est déjà conservée ; sa fiche reste inchangée.') + '</p>'
    if csrf is not None:
        body += '<section><h2>Ajouter un fichier source</h2>' + _source_form(csrf) + '</section>'
    else:
        body += '<p>Ajout de sources désactivé sur ce tableau de bord.</p>'
    if pending or issues:
        body += '<p role="status">Une source demande une reprise ou une vérification. Les validations en mémoire restent bloquées tant que ces anomalies ne sont pas résolues.</p>'
    for record in pending:
        body += ('<section><h2>Conservation en attente</h2>'
                 f'<p>{escape(record["title"])} · {escape(record["author"])}<br>'
                 f'Fichier attendu : {escape(record["original_name"])} · {record["size"]} octets</p>'
                 '<p>Reprendre avec le même fichier et les mêmes titre, auteur et nom. La date initiale sera conservée.</p>')
        if csrf is not None:
            body += _source_form(csrf, record)
        body += '</section>'
    for issue in issues:
        body += ('<section><h2>Vérification nécessaire</h2>'
                 '<p>Cette source ne peut pas être utilisée. Les autres sources valides restent consultables. Aucune suppression automatique n’est effectuée.</p>'
                 f'<details><summary>Détails pour la vérification</summary><p>{escape(issue["path"])}<br>{escape(issue["reason"])}</p></details></section>')
    body += render_reference_warnings(warnings)
    if information:
        body += '<p>Des extractions anciennes restent libres, sans engagement automatique :</p><ul>'
        for item in information:
            body += f'<li>uncommitted_extraction : <code>{escape(item["source_id"])}</code></li>'
        body += '</ul>'
    body += '<h2>Sources conservées</h2><ul>'
    for record in records:
        body += (f'<li><a href="/source?id={quote(record["source_id"])}">{escape(record["title"])}</a> '
                 f'· {escape(record["author"])} · {record["size"]} octets</li>')
    body += '</ul>' if records else '<li>Aucune source pour le moment.</li></ul>'
    return shell('Sources', body)


def render_source(record, *, csrf=None, has_extraction=False, warnings=()):
    identity = record['source_id']
    body = ('<a href="/sources">Retour aux sources</a><section>'
            f'<p>Auteur : {escape(record["author"])}<br>Fichier : {escape(record["original_name"])}'
            f'<br>Ajouté le {escape(record["added_at"])}<br>Taille : {record["size"]} octets</p>'
            f'<p>Référence de source : <code>{identity}</code></p>'
            f'<p><a href="/source/original?id={quote(identity)}">Télécharger le fichier original</a></p>'
            '</section>')
    if has_extraction:
        body += f'<p><a href="/source/text?id={quote(identity)}">Consulter le texte extrait</a></p>'
    elif record['original_name'].lower().endswith('.pdf'):
        body += '<p>Original PDF conservé. Extraction du texte PDF non disponible dans cette version.</p>'
    elif csrf is not None:
        body += (f'<form action="/source/extract" method="post">'
                 f'<input type="hidden" name="csrf" value="{escape(csrf, quote=True)}">'
                 f'<input type="hidden" name="id" value="{identity}">'
                 '<button>Extraire le texte pour préparer les détails à valider</button></form>')
    body += render_reference_warnings(warnings)
    return shell(record['title'], body)


def render_extraction(record, extraction, *, csrf=None, ai_enabled=False, page=1):
    visible = [(index, text) for index, text in enumerate(extraction['paragraphs'], 1) if text.strip()]
    total_pages = max(1, (len(visible) + 39) // 40)
    if type(page) is not int or not 1 <= page <= total_pages:
        raise ValueError('invalid extraction page')
    selected = visible[(page-1)*40:page*40]
    paragraphs = ''.join(f'<li value="{index}"><pre>{escape(text)}</pre></li>'
                         for index, text in selected)
    body = (f'<a href="/source?id={record["source_id"]}">Retour à la source</a>'
            '<p>Texte extrait : aucun souvenir créé. Les propositions IA devront être validées.</p>'
            '<p>Les paragraphes vides sont masqués ; les numéros de référence sont conservés.</p>'
            f'<p>Page {page} / {total_pages} · {len(visible)} paragraphes non vides</p>')
    if csrf is not None and ai_enabled and selected:
        body += (f'<form action="/source/propose" method="post">'
                 f'<input type="hidden" name="csrf" value="{escape(csrf, quote=True)}">'
                 f'<input type="hidden" name="id" value="{record["source_id"]}">'
                 f'<label>Commencer au paragraphe <input type="number" name="start" min="1" max="{len(extraction["paragraphs"])}" value="{selected[0][0]}" required></label>'
                 '<p>L’IA analyse un passage à la fois. Les propositions restent à valider.</p>'
                 '<button>Proposer des détails avec l’IA locale</button></form>')
    elif csrf is not None and not ai_enabled:
        body += '<p>Analyse IA locale non configurée pour ce tableau de bord.</p>'
    links = []
    if page > 1:
        links.append(f'<a href="/source/text?id={record["source_id"]}&amp;page={page-1}">Page précédente</a>')
    if page < total_pages:
        links.append(f'<a href="/source/text?id={record["source_id"]}&amp;page={page+1}">Page suivante</a>')
    navigation = '<nav aria-label="Pages du texte"><p>'+' · '.join(links)+'</p></nav>' if links else ''
    body += navigation + (f'<ol>{paragraphs}</ol>' if selected else '<p>Aucun texte non vide à afficher.</p>') + navigation
    body += (f'<details><summary>Références de l’extraction</summary><p>Version : {escape(extraction["extractor"])} '
             f'· Empreinte : {extraction["text_sha256"]}</p></details>')
    return shell(record['title'] + ' — texte extrait', body)


def render_proposals(record, proposals, tokens, csrf):
    skipped = proposals.get('skipped_paragraphs', [])
    status = 'Passage non analysé' if skipped else 'Passage analysé'
    body = (f'<a href="/source/text?id={record["source_id"]}">Retour au texte</a>'
            f'<p>{status} : paragraphes {proposals["first_paragraph"]} à {proposals["last_paragraph"]}. '
            f'IA locale : {escape(proposals["model"])}. Aucun souvenir créé avant validation.</p>')
    for item in skipped:
        body += (f'<p>Paragraphe {item["paragraph"]} non analysé : {item["characters"]} caractères, '
                 'au-delà de la limite de 6000. Son texte reste conservé intégralement. '
                 'Vous pouvez poursuivre au passage suivant.</p>')
    for item, token in zip(proposals['details'], tokens):
        body += (f'<section><p>Paragraphe {item["paragraph"]}</p><blockquote>{escape(item["quote"])}</blockquote>'
                 '<form action="/source/accept" method="post">'
                 f'<input type="hidden" name="csrf" value="{escape(csrf, quote=True)}">'
                 f'<input type="hidden" name="review" value="{escape(token, quote=True)}">'
                 '<label>Détail proposé — à corriger si nécessaire '
                 f'<textarea name="detail" rows="4" cols="70" maxlength="1000" required>{escape(item["detail"])}</textarea></label>'
                 '<p>Ce détail sera enregistré comme une interprétation non vérifiée, avec sa source.</p>'
                 '<button>Valider ce détail dans la mémoire</button></form></section>')
    if not proposals['details']:
        body += '<p>Aucun détail proposé pour ce passage.</p>'
    if proposals['next_paragraph'] is not None:
        body += (f'<form action="/source/propose" method="post">'
                 f'<input type="hidden" name="csrf" value="{escape(csrf, quote=True)}">'
                 f'<input type="hidden" name="id" value="{record["source_id"]}">'
                 f'<input type="hidden" name="start" value="{proposals["next_paragraph"]}">'
                 f'<p>Passage suivant : paragraphe {proposals["next_paragraph"]}. '
                 'Validez les détails souhaités avant de quitter cette page ; les propositions ne sont pas enregistrées.</p>'
                 '<button>Analyser le passage suivant</button></form>')
    else:
        body += '<p>Fin du document : aucun passage suivant à analyser.</p>'
    body += '<p>Pour refuser une proposition, ne pas la valider et revenir au texte.</p>'
    return shell('Détails à valider', body)


def render_reference_warnings(warnings):
    if not warnings:
        return ''
    body = '<section><h2>Références à vérifier</h2><p>Ces avertissements ne bloquent pas la mémoire. Aucun détail n’est modifié automatiquement.</p><ul>'
    for item in warnings:
        body += (f'<li><code>{escape(item["information_id"])}</code> · source : '
                 f'{escape(str(item["source_id"]))} · paragraphe : {escape(str(item["paragraph"]))}'
                 f'<br>source_reference_mismatch : {escape(", ".join(item["mismatches"]))}</li>')
    return body + '</ul></section>'
