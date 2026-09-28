import base64

from core.monitoring.dashboard import authorized, render_dashboard


def basic(value):
    return "Basic " + base64.b64encode(value.encode()).decode()


def test_dashboard_requires_correct_credentials():
    assert authorized(basic("eidolon:secret"), "secret")
    assert not authorized(None, "secret")
    assert not authorized(basic("other:secret"), "secret")
    assert not authorized(basic("eidolon:wrong"), "secret")
    assert not authorized("Basic not-base64!", "secret")


def test_render_escapes_file_paths_and_hostnames():
    metrics = {
        "host": '<script>alert(1)</script>', "measured_at": "2026-09-28T00:00:00+00:00",
        "data_path": "/tmp/<bad>",
        "ram_bytes": {"total": 1024, "used": 512, "available": 512},
        "volume_bytes": {"total": 1024, "used": 512, "free": 512},
        "engine_data": {"files": 2, "bytes": 42, "symlinks_skipped": 0},
    }
    state = {
        "threads": {"statuses": {"<PROPOSED>": 1}, "needs_review": []},
        "thread_status_operations": {"statuses": {}, "needs_review": []},
        "pending_operations": 0,
    }

    html = render_dashboard(metrics, state)

    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;bad&gt;" in html
    assert "&lt;PROPOSED&gt;" in html
    assert "rafraîchissement 30 s" in html
