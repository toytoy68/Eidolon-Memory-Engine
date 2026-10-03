"""Versioned paragraph extraction, not semantic detail selection."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile, BadZipFile

MAX_TEXT_BYTES = 16 * 1024 * 1024
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def _extract_v1(record, original):
    """Frozen v1 semantics; new parsing rules require a separately named driver."""
    suffix = Path(record['original_name']).suffix.lower()
    if suffix in {'.txt', '.md'}:
        text = original.decode('utf-8-sig')
        paragraphs = text.splitlines()
        extractor = 'utf8-lines-v1'
    elif suffix == '.docx':
        try:
            with ZipFile(BytesIO(original)) as archive:
                if len(archive.infolist()) > 2000:
                    raise ValueError('DOCX contains too many entries')
                matching = [i for i in archive.infolist() if i.filename == 'word/document.xml']
                if len(matching) != 1 or matching[0].file_size > MAX_TEXT_BYTES:
                    raise ValueError('DOCX document XML is missing, duplicated or oversized')
                raw = archive.read(matching[0])
                if len(raw) > MAX_TEXT_BYTES:
                    raise ValueError('DOCX document XML is oversized')
            xml = raw.decode('utf-8-sig')
            if '<!DOCTYPE' in xml.upper() or '<!ENTITY' in xml.upper():
                raise ValueError('document XML declarations are not supported')
            document = ElementTree.fromstring(xml)
            paragraphs = []
            for paragraph in document.iter(W + 'p'):
                parts = []
                for element in paragraph.iter():
                    if element.tag == W + 't':
                        parts.append(element.text or '')
                    elif element.tag == W + 'tab':
                        parts.append('\t')
                    elif element.tag in {W + 'br', W + 'cr'}:
                        parts.append('\n')
                paragraphs.append(''.join(parts))
            extractor = 'docx-paragraph-v1'
        except (BadZipFile, KeyError, ElementTree.ParseError, RuntimeError) as exc:
            raise ValueError('DOCX text extraction unavailable') from exc
    else:
        raise ValueError('PDF originals can be preserved; PDF text extraction is not available in this version')
    text = '\n'.join(paragraphs)
    if not text.strip() or len(text.encode('utf-8')) > MAX_TEXT_BYTES or '\x00' in text:
        raise ValueError('source text is empty, invalid or oversized')
    return dict(format_version=1, extractor=extractor, source_sha256=record['sha256'],
                text_sha256=sha256(text.encode('utf-8')).hexdigest(), paragraphs=paragraphs)


_EXTRACTORS = {
    'utf8-lines-v1': ({'.txt', '.md'}, _extract_v1),
    'docx-paragraph-v1': ({'.docx'}, _extract_v1),
}
_DEFAULT_EXTRACTORS = {'.txt': 'utf8-lines-v1', '.md': 'utf8-lines-v1', '.docx': 'docx-paragraph-v1'}


def reproduce_extraction(record, original, *, extractor):
    """Verify a published snapshot using its recorded version, never the default."""
    if not isinstance(extractor, str) or extractor not in _EXTRACTORS:
        raise ValueError('unsupported frozen source extractor')
    suffixes, driver = _EXTRACTORS[extractor]
    if Path(record['original_name']).suffix.lower() not in suffixes:
        raise ValueError('source format differs from frozen extractor')
    result = driver(record, original)
    if result['extractor'] != extractor:
        raise ValueError('frozen extractor returned a different version')
    return result


def extract_paragraphs(record, original):
    """Select the current default for a new extraction only."""
    extractor = _DEFAULT_EXTRACTORS.get(Path(record['original_name']).suffix.lower())
    if extractor is None:
        raise ValueError('PDF originals can be preserved; PDF text extraction is not available in this version')
    return reproduce_extraction(record, original, extractor=extractor)


def validate_extraction(value, identity):
    keys = {'format_version', 'extractor', 'source_sha256', 'text_sha256', 'paragraphs'}
    if (not isinstance(value, dict) or set(value) != keys or type(value['format_version']) is not int
            or value['format_version'] != 1 or value['source_sha256'] != identity
            or not isinstance(value['extractor'], str) or value['extractor'] not in _EXTRACTORS
            or not isinstance(value['paragraphs'], list)
            or not all(isinstance(p, str) for p in value['paragraphs'])):
        raise ValueError('invalid source extraction')
    text = '\n'.join(value['paragraphs'])
    if (not text.strip() or '\x00' in text or len(text.encode('utf-8')) > MAX_TEXT_BYTES
            or sha256(text.encode('utf-8')).hexdigest() != value['text_sha256']):
        raise ValueError('extracted text differs from its snapshot')
    return value
