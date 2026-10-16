# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/information/remember.py
# Description : Explicit reviewed memory command with durable idempotency
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
"""Explicit reviewed remembering through the operator CLI or authenticated bridge.
No inferred approval; the bridge adds its own profile and credential checks.

Preview validates a complete stable command without constructing a writer.
Apply requires the exact preview SHA-256, then delegates journaled idempotency
and conflict detection to FilesystemInformationWrites. Approval is local operator
intent, not an authorization token. No LLM text can invoke this command itself.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from datetime import datetime
import re
from core.runtime_json import read_json_snapshot
from core.backend.models import Memory
from core.information.writes import canonical_json


def prepare(raw):
    fields={"schema","request_id","actor","timestamp","text"}
    if type(raw) is not dict or set(raw)!=fields or raw.get("schema")!="eidolon-remember/1":
        raise ValueError("invalid remember command")
    for key in ("request_id","actor"):
        if type(raw[key]) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}",raw[key]):
            raise ValueError("invalid " + key)
    text=raw["text"]
    if type(text) is not str or not text.strip() or len(text)>16000 or "\0" in text:
        raise ValueError("invalid remember text")
    if type(raw["timestamp"]) is not str or len(raw["timestamp"])>40:
        raise ValueError("invalid timestamp")
    at=datetime.fromisoformat(raw["timestamp"])
    if at.tzinfo is None or at.year<2000:
        raise ValueError("timezone-aware timestamp required")
    ident="remember-"+raw["request_id"]
    memory=Memory(ident,content=text,metadata={"type":"OBSERVATION","epistemic_status":"UNVERIFIED",
        "operational_state":"ACTIVE","importance":"NORMAL","retention":"NORMAL"},
        provenance={"source":"explicit-operator-remember","actor":raw["actor"],"timestamp":raw["timestamp"]})
    command=dict(operation_id=ident,event_id="event-"+ident,actor=raw["actor"],timestamp=raw["timestamp"])
    digest=sha256(canonical_json(raw).encode()).hexdigest()
    return memory,command,digest


def apply(raw, *, approved_sha256, make_writer):
    memory,command,digest=prepare(raw)
    if type(approved_sha256) is not str or approved_sha256!=digest:
        raise ValueError("preview approval does not match command")
    return make_writer().create(memory,**command)


def main(argv=None):
    parser=argparse.ArgumentParser(description="Preview or explicitly persist one operator memory")
    parser.add_argument("--input",required=True,type=Path)
    parser.add_argument("--root",type=Path)
    parser.add_argument("--approve-sha256")
    args=parser.parse_args(argv)
    if (args.root is None)!=(args.approve_sha256 is None):
        parser.error("apply requires --root and --approve-sha256 together")
    effects="NONE"
    try:
        path=args.input.absolute()
        raw=read_json_snapshot(str(path.parent),path.name,max_bytes=128*1024)
        memory,command,digest=prepare(raw)
        if args.approve_sha256 is None:
            result={"state":"PREVIEW","sha256":digest,"information_id":memory.information_id,
                    "text":memory.content,"actor":command["actor"],"timestamp":command["timestamp"],
                    "epistemic_status":"UNVERIFIED"}
        else:
            def writer():
                nonlocal effects
                from core.backend.filesystem import FilesystemBackend
                from core.information.writes import FilesystemInformationWrites
                from core.persistence import has_symlink_component
                root=args.root.absolute()
                if has_symlink_component(root) or not (root/"memory/persistent").is_dir() or not (root/"memory/history").is_dir():
                    raise ValueError("existing canonical root required")
                effects="UNKNOWN"
                return FilesystemInformationWrites(FilesystemBackend(root/"memory/persistent",root/"memory/history"))
            receipt=apply(raw,approved_sha256=args.approve_sha256,make_writer=writer)
            result={"state":"COMMITTED","receipt":receipt,"sha256":digest}
        print(json.dumps(result,ensure_ascii=True,sort_keys=True))
        return 0
    except Exception:
        print(json.dumps({"state":"REFUSED_OR_INCOMPLETE","effects":effects}))
        return 2

if __name__=="__main__":
    raise SystemExit(main())
