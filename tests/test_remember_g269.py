# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : tests/test_remember_g269.py
# Description : Reviewed remember preview, replay and conflict evidence
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
from copy import deepcopy
import pytest
from core.information.remember import prepare,apply,main
from core.backend.filesystem import FilesystemBackend
from core.information.writes import FilesystemInformationWrites
from core.operations.errors import OperationConflict

def command():
    return dict(schema="eidolon-remember/1",request_id="weekend-1",actor="operator",
                timestamp="2026-10-17T12:00:00+02:00",text="Une observation synthétique.")

def test_idempotent_remember_and_changed_retry(tmp_path):
    backend=FilesystemBackend(tmp_path/"memory/persistent",tmp_path/"memory/history")
    factory=lambda: FilesystemInformationWrites(backend)
    raw=command();digest=prepare(raw)[2]
    first=apply(raw,approved_sha256=digest,make_writer=factory)
    assert first==apply(raw,approved_sha256=digest,make_writer=factory)
    saved=backend.get(first["information_id"])
    assert saved.content==raw["text"] and saved.metadata["epistemic_status"]=="UNVERIFIED"
    changed={**raw,"text":"Another"}
    with pytest.raises(OperationConflict):
        apply(changed,approved_sha256=prepare(changed)[2],make_writer=factory)
    assert backend.get(first["information_id"]).content==raw["text"]

def test_mismatch_has_no_writer():
    calls=[]
    with pytest.raises(ValueError):
        apply(command(),approved_sha256="a"*64,make_writer=lambda:calls.append(1))
    assert calls==[]

@pytest.mark.parametrize("key,value",[("text",""),("text","x"*16001),("actor","a/b"),
    ("request_id","../x"),("timestamp","2026-10-17"),("schema","other")])
def test_bad_commands(key,value):
    raw=command();raw[key]=value
    with pytest.raises(ValueError):prepare(raw)

def test_preview_does_not_create_root(tmp_path,capsys):
    import json
    path=tmp_path/"remember.json";path.write_text(json.dumps(command()))
    assert main(["--input",str(path)])==0
    result=json.loads(capsys.readouterr().out)
    assert result["state"]=="PREVIEW" and len(result["sha256"])==64
    assert not (tmp_path/"memory").exists()
