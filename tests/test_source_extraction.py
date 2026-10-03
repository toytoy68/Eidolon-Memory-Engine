from io import BytesIO
from zipfile import ZipFile
from hashlib import sha256
import json

import pytest

from core.operations.readiness import check_readiness
from tests.test_source_library import seed, add
from tools.vm_acceptance import hashes


def docx(xml):
    result = BytesIO()
    with ZipFile(result, 'w') as archive:
        archive.writestr('word/document.xml', xml)
    return result.getvalue()


def test_docx_extracts_stable_paragraphs_preserving_original_and_memory(tmp_path):
    store = seed(tmp_path)
    data = docx('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
                '<w:p><w:r><w:t>Prologue &amp; été</w:t><w:tab/><w:t>suite</w:t></w:r></w:p>'
                '<w:p/><w:p><w:r><w:t>Chapitre 1</w:t><w:br/><w:t>Fin.</w:t></w:r></w:p>'
                '</w:body></w:document>')
    record = add(store, data)['source']
    original = store.read(record['source_id'])
    canonical = hashes(tmp_path / 'memory/persistent'), hashes(tmp_path / 'memory/history')
    result = store.extract(record['source_id'])
    assert result['status'] == 'EXTRACTED'
    extraction = result['extraction']
    assert extraction['paragraphs'] == ['Prologue & été\tsuite', '', 'Chapitre 1\nFin.']
    assert extraction['source_sha256'] == sha256(data).hexdigest()
    assert extraction['text_sha256'] == sha256('\n'.join(extraction['paragraphs']).encode()).hexdigest()
    assert store.extract(record['source_id'])['status'] == 'UNCHANGED'
    assert store.read(record['source_id']) == original
    assert (hashes(tmp_path / 'memory/persistent'), hashes(tmp_path / 'memory/history')) == canonical
    assert check_readiness(tmp_path)['ready']


def test_text_lines_are_numbered_without_html_execution(tmp_path):
    store = seed(tmp_path)
    identity = add(store, 'Été\r\n\r\n<script>texte</script>\n'.encode(), original_name='notes.md')['source']['source_id']
    result = store.extract(identity)['extraction']
    assert result['paragraphs'] == ['Été', '', '<script>texte</script>']
    assert result['extractor'] == 'utf8-lines-v1'


@pytest.mark.parametrize('name,data', [
    ('bad.docx', b'not a zip'), ('pdf.pdf', b'%PDF-synthetic'),
    ('bad.txt', b'\xff'), ('empty.md', b'  \n'),
    ('entity.docx', docx('<!DOCTYPE x [<!ENTITY value "hidden">]><x>&value;</x>')),
], ids=['bad-docx', 'pdf-not-supported', 'utf8', 'empty', 'xml-entity'])
def test_failed_extraction_preserves_source_without_partial_snapshot(tmp_path, name, data):
    store = seed(tmp_path)
    identity = add(store, data, original_name=name)['source']['source_id']
    before = hashes(tmp_path)
    with pytest.raises(ValueError):
        store.extract(identity)
    assert hashes(tmp_path) == before
    assert check_readiness(tmp_path)['ready']


def test_extraction_tampering_blocks_readiness_and_read(tmp_path):
    store = seed(tmp_path)
    identity = add(store, b'line one\nline two', original_name='test.txt')['source']['source_id']
    store.extract(identity)
    file = store.directory / identity / 'extraction.json'
    payload = json.loads(file.read_text())
    payload['paragraphs'][0] = 'changed'
    file.write_text(json.dumps(payload))
    assert not check_readiness(tmp_path)['ready']
    with pytest.raises(ValueError):
        store.extraction(identity)


def test_rehashed_invented_extraction_does_not_become_source_text(tmp_path):
    store = seed(tmp_path)
    identity = add(store, b'original evidence', original_name='source.txt')['source']['source_id']
    store.extract(identity)
    path = store.directory / identity / 'extraction.json'
    value = json.loads(path.read_text())
    value['paragraphs'] = ['invented evidence']
    value['text_sha256'] = sha256(b'invented evidence').hexdigest()
    path.write_text(json.dumps(value))
    assert not check_readiness(tmp_path)['ready']
    with pytest.raises(ValueError):
        store.read(identity)
