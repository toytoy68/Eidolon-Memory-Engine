from core.indexing.passages import split_passages, verify_passage
import pytest

def test_passages_reconstruct_exact_source():
    text = "Le serveur Eidolon fonctionne. " * 120
    chunks = split_passages("archive-01", 3, text, size=256, overlap=32)
    assert len(chunks) > 2
    assert chunks[0].start == 0
    assert chunks[-1].end == len(text)
    assert all(verify_passage(p, text) for p in chunks)
    assert len({p.passage_id for p in chunks}) == len(chunks)

def test_change_invalidates_passage():
    text = "a" * 400
    passage = split_passages("archive", 1, text, size=256)[0]
    assert not verify_passage(passage, "b" + text[1:])

def test_revision_changes_identity():
    a = split_passages("archive", 1, "a" * 256)[0]
    b = split_passages("archive", 2, "a" * 256)[0]
    assert a.passage_id != b.passage_id

@pytest.mark.parametrize("size,overlap", [(0,0),(128,128),(128,-1),(8193,1),(True,0)])
def test_invalid_chunking(size, overlap):
    with pytest.raises(ValueError):
        split_passages("archive",1,"text",size=size,overlap=overlap)

def test_empty_document_has_no_passage():
    assert split_passages("archive",1,"") == ()
