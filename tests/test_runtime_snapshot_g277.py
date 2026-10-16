# ==========================================================
# Projet      : Eidolon Core / Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : test_runtime_snapshot_g277.py
# Description : Same-metadata rewrites must not pass snapshot verification
# Standard    : Eidolon Presentation Standard v1
# ==========================================================
import pytest
from core import runtime_json as snap


def test_rewrite_detected_independently_of_timestamp_resolution(tmp_path, monkeypatch):
    path=tmp_path/'config.json';path.write_bytes(b'{"value":"A"}');path.chmod(0o600)
    monkeypatch.setattr(snap,'_version',lambda st:(st.st_dev,st.st_ino,st.st_size))
    assert snap.read_json_snapshot(str(tmp_path),'config.json',max_bytes=64)=={'value':'A'}
    monkeypatch.setattr(snap,'_after_read',lambda:path.write_bytes(b'{"value":"B"}'))
    with pytest.raises(snap.SnapshotRefused,match='SNAPSHOT_CHANGED'):
        snap.read_json_snapshot(str(tmp_path),'config.json',max_bytes=64)
