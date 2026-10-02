"""Analyses must not fill the disk with bytes that hold no information, and a full disk is said in plain words.

A service on a modest volume failed its next analysis with "OSError: [Errno 28] No space left on device" after
a few dozen readings. Each reading wrote its one-sheet files twice, left its native diagnostics uncompressed
when a run was cut short, and a killed run left its working directory in /tmp.
"""
import os
import sys
import time

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))


def test_a_sheet_copy_becomes_a_link_to_the_same_bytes(tmp_path):
    from app.disk_space import link_sheet_copies
    (tmp_path / "sheets" / "0").mkdir(parents=True)
    (tmp_path / "quantities.json").write_text('{"rows": [1, 2, 3]}')
    (tmp_path / "sheets" / "0" / "quantities.json").write_text('{"rows": [1, 2, 3]}')
    (tmp_path / "physical-pipes.json").write_text('{"a": 1}')
    (tmp_path / "sheets" / "0" / "physical-pipes.json").write_text('{"a": 2}')      # differs: left alone
    saved = link_sheet_copies(str(tmp_path))
    a, b = (tmp_path / "quantities.json").stat(), (tmp_path / "sheets" / "0" / "quantities.json").stat()
    assert saved > 0 and a.st_ino == b.st_ino
    assert (tmp_path / "sheets" / "0" / "quantities.json").read_text() == '{"rows": [1, 2, 3]}'
    assert (tmp_path / "sheets" / "0" / "physical-pipes.json").read_text() == '{"a": 2}'
    assert link_sheet_copies(str(tmp_path)) == 0                                    # a second pass finds nothing


def test_only_old_working_directories_of_this_service_are_swept(tmp_path, monkeypatch):
    import tempfile
    from app import disk_space
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    old = tmp_path / "vvs-detector-cache-abc"; old.mkdir(); (old / "x.pkl").write_bytes(b"0" * 100)
    fresh = tmp_path / "vvs-native-def"; fresh.mkdir()
    other = tmp_path / "someone-elses"; other.mkdir()
    past = time.time() - 3 * 3600
    os.utime(old, (past, past)); os.utime(other, (past, past))
    assert disk_space.sweep_temp() == 100
    assert not old.exists() and fresh.exists() and other.exists()


def test_a_nearly_full_disk_is_refused_in_plain_words(tmp_path, monkeypatch):
    from app import disk_space
    monkeypatch.setattr(disk_space, "free_bytes", lambda path: 10 * 1024 * 1024)
    monkeypatch.setattr(disk_space, "reclaim", lambda root: {})
    with pytest.raises(OSError) as e:
        disk_space.ensure_room(str(tmp_path), str(tmp_path / "results"))
    assert "Disken" in str(e.value) and "10 MB ledigt" in str(e.value)
    monkeypatch.setattr(disk_space, "free_bytes", lambda path: 10 * 1024 ** 3)
    disk_space.ensure_room(str(tmp_path), str(tmp_path / "results"))                # room enough: nothing said


def test_when_space_runs_out_only_older_runs_of_the_same_drawing_give_way(tmp_path, monkeypatch):
    import datetime as dt
    from types import SimpleNamespace
    from app import disk_space
    import app.db as db_module
    import app.storage as storage_module
    jobs = []
    for drawing, n in (("d1", 4), ("d2", 1)):
        for k in range(n):
            key = f"results/{drawing}/{k}"
            (tmp_path / key).mkdir(parents=True)
            (tmp_path / key / "quantities.json").write_text("x" * 100)
            jobs.append(SimpleNamespace(drawing_id=drawing, result_key=key, status="COMPLETED",
                                        finished_at=dt.datetime(2026, 9, 1 + k), started_at=None))

    class Q:
        def filter(self, *a):
            return self
        def all(self):
            return jobs

    class S:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def query(self, model):
            return Q()
        def commit(self):
            pass
    monkeypatch.setattr(db_module, "SessionLocal", lambda: S())
    monkeypatch.setattr(storage_module, "storage", SimpleNamespace(path=lambda key: str(tmp_path / key)))
    assert disk_space.remove_superseded_runs(keep=2) == 200
    kept = sorted(j.result_key for j in jobs if j.result_key)
    assert kept == ["results/d1/2", "results/d1/3", "results/d2/0"]        # the two newest, and the only run of d2
    assert not (tmp_path / "results/d1/0").exists() and (tmp_path / "results/d1/3").exists()


def test_a_disk_still_full_after_reclaim_gives_up_older_runs_but_keeps_the_newest(tmp_path, monkeypatch):
    from app import disk_space
    monkeypatch.setattr(disk_space, "free_bytes", lambda path: 0)
    monkeypatch.setattr(disk_space, "reclaim", lambda root: {})
    kept = []
    monkeypatch.setattr(disk_space, "remove_superseded_runs", lambda keep: kept.append(keep) or 0)
    monkeypatch.setattr(disk_space, "remove_detector_cache", lambda root: 0)
    with pytest.raises(OSError):
        disk_space.ensure_room(str(tmp_path), str(tmp_path / "results"))
    assert kept == [1]                                     # the newest completed run of every drawing stays


def test_reclaim_does_not_touch_an_active_detection(tmp_path, monkeypatch):
    from app import disk_space, diagnostic_storage
    active = tmp_path / "drawing" / "active"
    frozen = tmp_path / "drawing" / "frozen"
    active.mkdir(parents=True)
    frozen.mkdir(parents=True)
    (frozen / "freeze-manifest.json").write_text('{}')
    monkeypatch.setattr(disk_space, "sweep_temp", lambda: 0)
    monkeypatch.setattr(disk_space, "remove_failed_results", lambda: 0)
    visited = []
    monkeypatch.setattr(disk_space, "link_sheet_copies", lambda p: visited.append(p) or 0)
    monkeypatch.setattr(diagnostic_storage, "compress_native_diagnostics", lambda p: visited.append(p) or 0)
    disk_space.reclaim(str(tmp_path))
    assert visited == [str(frozen), str(frozen)]


def test_an_administrator_can_clear_older_runs_and_the_detector_cache(tmp_path, monkeypatch):
    from app import disk_space
    calls = {}
    monkeypatch.setattr(disk_space, "reclaim", lambda root: {"temp": 0})
    monkeypatch.setattr(disk_space, "remove_superseded_runs", lambda keep: calls.setdefault("keep", keep) and 500)
    cache = tmp_path / "cache" / "native"
    old = cache / "project1" / ("a" * 64); old.mkdir(parents=True); (old / "result.pkl.gz").write_bytes(b"0" * 300)
    fresh = cache / "project2" / ("b" * 64); fresh.mkdir(parents=True); (fresh / "result.pkl.gz").write_bytes(b"0" * 7)
    past = time.time() - 3 * 3600
    os.utime(old, (past, past))
    out = disk_space.clean_up(str(tmp_path), str(tmp_path / "results"), str(cache))
    assert calls["keep"] == 1                                       # the newest run of every drawing stays
    assert out["detector_cache"] == 300 and not old.exists() and fresh.exists()
    assert "free_before" in out and "free_after" in out
