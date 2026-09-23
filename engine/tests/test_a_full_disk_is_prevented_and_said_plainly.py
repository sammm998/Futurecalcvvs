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
