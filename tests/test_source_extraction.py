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
    assert hashes(tmp_path / 'memory/persistent') == canonical[0]
    history = hashes(tmp_path / 'memory/history')
    commitment = 'source-extractions-v1/' + record['source_id'] + '.json'
    assert set(history) == set(canonical[1]) | {commitment}
    assert {k:v for k,v in history.items() if k != commitment} == canonical[1]
    assert check_readiness(tmp_path)['ready']


def test_text_lines_are_numbered_without_html_execution(tmp_path):
    store = seed(tmp_path)
    identity = add(store, 'Été\r\n\r\n<script>texte</script>\n'.encode(), original_name='notes.md')['source']['source_id']
    result = store.extract(identity)['extraction']
    assert result['paragraphs'] == ['Été', '', '<script>texte</script>']
    assert result['extractor'] == 'utf8-lines-v2'


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


def textbox_docx():
    inner='<w:p><w:r><w:t>Encadré : marée haute.</w:t></w:r></w:p>'
    return docx('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
        'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
        'xmlns:v="urn:schemas-microsoft-com:vml"><w:body><w:p><w:r><mc:AlternateContent>'
        '<mc:Choice Requires="wps"><wps:txbx><w:txbxContent>'+inner+'</w:txbxContent></wps:txbx></mc:Choice>'
        '<mc:Fallback><v:textbox><w:txbxContent>'+inner+'</w:txbxContent></v:textbox></mc:Fallback>'
        '</mc:AlternateContent></w:r><w:r><w:t>Maëlle relit son carnet.</w:t></w:r></w:p>'
        '</w:body></w:document>')


def test_docx_textbox_is_extracted_once_in_new_version(tmp_path):
    store=seed(tmp_path)
    record=add(store,textbox_docx(),original_name='textbox.docx')['source']
    result=store.extract(record['source_id'])['extraction']
    text='\n'.join(result['paragraphs'])
    assert text.count('marée haute')==1 and text.count('Maëlle relit')==1
    assert result['extractor']=='docx-paragraph-v2'
    assert check_readiness(tmp_path)['ready']


def test_docx_v1_snapshot_remains_exact_after_new_default(tmp_path, monkeypatch):
    import core.sources.extraction as module
    store=seed(tmp_path)
    data=textbox_docx()
    record=add(store,data,original_name='textbox.docx')['source']
    with monkeypatch.context() as patch:
        patch.setitem(module._DEFAULT_EXTRACTORS,'.docx','docx-paragraph-v1')
        old=store.extract(record['source_id'])['extraction']
    before=hashes(tmp_path)
    assert '\n'.join(old['paragraphs']).count('marée haute')==4
    assert store.extraction(record['source_id'])==old
    assert store.extract(record['source_id'])['status']=='UNCHANGED'
    assert module.extract_paragraphs(record,data)['extractor']=='docx-paragraph-v2'
    assert check_readiness(tmp_path)['ready'] and hashes(tmp_path)==before


def test_text_v2_counts_only_actual_newline_boundaries(tmp_path):
    store=seed(tmp_path)
    data='First\fpart\u2028continued\nSecond\r\nThird\rLast\n'.encode()
    record=add(store,data,original_name='newlines.txt')['source']
    result=store.extract(record['source_id'])['extraction']
    assert result['paragraphs']==['First\fpart\u2028continued','Second','Third','Last']
    assert result['extractor']=='utf8-lines-v2'
    assert check_readiness(tmp_path)['ready']


def test_utf8_v1_snapshot_remains_exact_with_new_line_default(tmp_path, monkeypatch):
    import core.sources.extraction as module
    store=seed(tmp_path)
    data='First\u2028continued\nSecond'.encode()
    record=add(store,data,original_name='newlines.txt')['source']
    with monkeypatch.context() as patch:
        patch.setitem(module._DEFAULT_EXTRACTORS,'.txt','utf8-lines-v1')
        frozen=store.extract(record['source_id'])['extraction']
    before=hashes(tmp_path)
    assert frozen['paragraphs']==['First','continued','Second']
    assert module.extract_paragraphs(record,data)['extractor']=='utf8-lines-v2'
    assert store.extraction(record['source_id'])==frozen
    assert check_readiness(tmp_path)['ready'] and hashes(tmp_path)==before
