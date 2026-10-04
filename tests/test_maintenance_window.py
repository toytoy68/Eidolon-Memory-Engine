"""Timing eligibility remains separate from lock/readiness checks and execution."""
from datetime import datetime, time
import json
import pytest
from core.maintenance.window import preview_window
from tools.preview_maintenance_window import main


def preview(at, last_activity='2026-10-04T00:00:00Z', **overrides):
    fields = dict(at=datetime.fromisoformat(at), last_activity=datetime.fromisoformat(last_activity),
        start=time(4), end=time(8), zone='Europe/Paris', minimum_idle_minutes=30)
    fields.update(overrides)
    return preview_window(**fields)


@pytest.mark.parametrize('at,status', [
    ('2026-10-04T01:59:59Z','DEFERRED'), ('2026-10-04T02:00:00Z','ELIGIBLE'),
    ('2026-10-04T05:59:59Z','ELIGIBLE'), ('2026-10-04T06:00:00Z','DEFERRED'),
])
def test_window_start_included_and_end_excluded_in_paris(at, status):
    result = preview(at)
    assert result['status'] == status and not result['execution_performed']


@pytest.mark.parametrize('seconds,status', [(1799,'DEFERRED'), (1800,'ELIGIBLE')])
def test_elapsed_idle_boundary(seconds, status):
    from datetime import timedelta
    now = datetime.fromisoformat('2026-10-04T04:00:00+02:00')
    result = preview(now.isoformat(), last_activity=(now-timedelta(seconds=seconds)).isoformat())
    assert result['status'] == status and result['idle_seconds'] == seconds


def test_all_deferral_reasons_are_reported():
    result = preview('2026-10-04T10:00:00Z', last_activity='2026-10-04T09:59:00Z')
    assert result['reasons'] == ['OUTSIDE_WINDOW','ACTIVITY_RECENT']


@pytest.mark.parametrize('at,activity,seconds', [
    ('2026-10-25T02:45:00+01:00','2026-10-25T02:15:00+02:00',5400),
    ('2026-03-29T03:15:00+02:00','2026-03-29T01:45:00+01:00',1800),
])
def test_idle_uses_elapsed_time_across_dst(at, activity, seconds):
    result = preview(at, last_activity=activity, start=time(0), end=time(4))
    assert result['idle_seconds'] == seconds and result['status'] == 'ELIGIBLE'


@pytest.mark.parametrize('hour,status', [(21,'DEFERRED'),(22,'ELIGIBLE'),(1,'ELIGIBLE'),(2,'DEFERRED')])
def test_overnight_windows(hour, status):
    result = preview(f'2026-10-04T{hour:02}:00:00+02:00',
        last_activity='2026-10-03T00:00:00Z', start=time(22), end=time(2))
    assert result['status'] == status


@pytest.mark.parametrize('overrides', [
    {'at':datetime(2026,10,4)}, {'last_activity':datetime(2026,10,4)},
    {'last_activity':datetime.fromisoformat('2026-10-05T00:00:00Z')},
    {'minimum_idle_minutes':True}, {'minimum_idle_minutes':0},
    {'end':time(4)}, {'zone':'Unknown/Nowhere'},
])
def test_invalid_policy_or_activity_is_refused(overrides):
    fields = dict(at=datetime.fromisoformat('2026-10-04T02:00:00Z'),
        last_activity=datetime.fromisoformat('2026-10-04T00:00:00Z'),
        start=time(4), end=time(8), zone='Europe/Paris', minimum_idle_minutes=30)
    fields.update(overrides)
    with pytest.raises(ValueError):
        preview_window(**fields)


def test_cli_preview_never_touches_current_directory(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    args = ['--at','2026-10-04T04:00:00+02:00','--last-activity','2026-10-04T03:30:00+02:00',
        '--start','04:00','--end','08:00','--timezone','Europe/Paris','--minimum-idle-minutes','30']
    assert main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == 'ELIGIBLE' and not result['execution_performed']
    assert list(tmp_path.iterdir()) == []
