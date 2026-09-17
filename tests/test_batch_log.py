"""Tests for Indexer batch.log and location labels."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from util.batch_log import (
    BATCH_LOG_FILENAME,
    EVENT_COMPLETE_BATCH,
    EVENT_OPEN_BATCH,
    append_batch_log,
    batch_location_label,
    current_user,
    log_batch_move,
    read_batch_log,
)


def test_location_label_job_folder():
    assert batch_location_label(Path("SCANS") / "BATCH001") == "SCANS"


def test_location_label_in_progress():
    assert (
        batch_location_label(Path("SCANS") / "_in_progress" / "BATCH001")
        == "_in_progress"
    )


def test_location_label_qc():
    assert batch_location_label(Path("SCANS") / "_qc" / "BATCH001") == "_qc"


def test_location_label_qc_in_progress():
    assert (
        batch_location_label(Path("SCANS") / "_qc" / "_in_progress" / "BATCH001")
        == "_qc/_in_progress"
    )


def test_location_label_complete():
    assert batch_location_label(Path("SCANS") / "_complete" / "BATCH001") == "_complete"


def test_current_user_from_getpass(monkeypatch):
    monkeypatch.setattr("util.batch_log.getpass.getuser", lambda: "tcowman")
    assert current_user() == "tcowman"


def test_current_user_falls_back_to_env(monkeypatch):
    def _raise():
        raise OSError("no login")

    monkeypatch.setattr("util.batch_log.getpass.getuser", _raise)
    monkeypatch.setenv("USERNAME", "fromenv")
    monkeypatch.delenv("USER", raising=False)
    assert current_user() == "fromenv"


def test_current_user_unknown_when_empty(monkeypatch):
    monkeypatch.setattr("util.batch_log.getpass.getuser", lambda: "")
    monkeypatch.setenv("USERNAME", "")
    monkeypatch.setenv("USER", "")
    assert current_user() == "unknown"


def test_append_batch_log_writes_header_then_row(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("util.batch_log.getpass.getuser", lambda: "alice")
    dest = tmp_path / "batch"
    dest.mkdir()
    when = datetime(2026, 9, 17, 15, 32, 1, tzinfo=timezone(timedelta(hours=1)))
    append_batch_log(
        dest,
        EVENT_OPEN_BATCH,
        "SCANS",
        "_in_progress",
        when=when,
    )
    text = (dest / BATCH_LOG_FILENAME).read_text(encoding="utf-8")
    assert text.splitlines() == [
        "Datetime\tUser\tEvent\tPrevious location\tNew location",
        "2026-09-17T15:32:01+01:00\talice\tOpen Batch\tSCANS\t_in_progress",
    ]


def test_append_batch_log_does_not_repeat_header(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("util.batch_log.getpass.getuser", lambda: "alice")
    dest = tmp_path / "batch"
    dest.mkdir()
    when = datetime(2026, 9, 17, 16, 10, 44, tzinfo=timezone(timedelta(hours=1)))
    append_batch_log(dest, EVENT_OPEN_BATCH, "SCANS", "_in_progress", when=when)
    append_batch_log(
        dest,
        EVENT_COMPLETE_BATCH,
        "_in_progress",
        "_qc",
        when=when,
    )
    lines = (dest / BATCH_LOG_FILENAME).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert lines[0].startswith("Datetime")
    assert lines[2].endswith("Complete Batch\t_in_progress\t_qc")


def test_log_batch_move_open_from_job_folder(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("util.batch_log.getpass.getuser", lambda: "bob")
    job = tmp_path / "SCANS"
    dest = job / "_in_progress" / "BATCH001"
    dest.mkdir(parents=True)
    source = job / "BATCH001"
    log_batch_move(source, dest, EVENT_OPEN_BATCH)
    lines = (dest / BATCH_LOG_FILENAME).read_text(encoding="utf-8").splitlines()
    assert lines[1].endswith("Open Batch\tSCANS\t_in_progress")


def test_log_batch_move_complete_indexing_to_qc(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("util.batch_log.getpass.getuser", lambda: "alice")
    job = tmp_path / "SCANS"
    source = job / "_in_progress" / "BATCH001"
    dest = job / "_qc" / "BATCH001"
    dest.mkdir(parents=True)
    log_batch_move(source, dest, EVENT_COMPLETE_BATCH)
    lines = (dest / BATCH_LOG_FILENAME).read_text(encoding="utf-8").splitlines()
    assert lines[1].endswith("Complete Batch\t_in_progress\t_qc")


def test_log_batch_move_open_from_qc(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("util.batch_log.getpass.getuser", lambda: "qcuser")
    job = tmp_path / "SCANS"
    source = job / "_qc" / "BATCH001"
    dest = job / "_qc" / "_in_progress" / "BATCH001"
    dest.mkdir(parents=True)
    log_batch_move(source, dest, EVENT_OPEN_BATCH)
    lines = (dest / BATCH_LOG_FILENAME).read_text(encoding="utf-8").splitlines()
    assert lines[1].endswith("Open Batch\t_qc\t_qc/_in_progress")


def test_log_batch_move_complete_qc_direct_to_complete(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("util.batch_log.getpass.getuser", lambda: "qcuser")
    job = tmp_path / "SCANS"
    source = job / "_qc" / "BATCH001"
    dest = job / "_complete" / "BATCH001"
    dest.mkdir(parents=True)
    log_batch_move(source, dest, EVENT_COMPLETE_BATCH)
    lines = (dest / BATCH_LOG_FILENAME).read_text(encoding="utf-8").splitlines()
    assert lines[1].endswith("Complete Batch\t_qc\t_complete")


def test_log_batch_move_complete_qc_in_progress_to_complete(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("util.batch_log.getpass.getuser", lambda: "qcuser")
    job = tmp_path / "SCANS"
    source = job / "_qc" / "_in_progress" / "BATCH001"
    dest = job / "_complete" / "BATCH001"
    dest.mkdir(parents=True)
    log_batch_move(source, dest, EVENT_COMPLETE_BATCH)
    lines = (dest / BATCH_LOG_FILENAME).read_text(encoding="utf-8").splitlines()
    assert lines[1].endswith("Complete Batch\t_qc/_in_progress\t_complete")


def test_read_batch_log_missing_file_is_empty(tmp_path: Path):
    assert read_batch_log(tmp_path / "nope") == []


def test_read_batch_log_returns_data_rows(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("util.batch_log.getpass.getuser", lambda: "alice")
    dest = tmp_path / "batch"
    dest.mkdir()
    when = datetime(2026, 9, 17, 15, 32, 1, tzinfo=timezone(timedelta(hours=1)))
    append_batch_log(dest, EVENT_OPEN_BATCH, "SCANS", "_in_progress", when=when)
    append_batch_log(
        dest,
        EVENT_COMPLETE_BATCH,
        "_in_progress",
        "_qc",
        when=when,
    )
    rows = read_batch_log(dest)
    assert rows == [
        ("2026-09-17T15:32:01+01:00", "alice", "Open Batch", "SCANS", "_in_progress"),
        ("2026-09-17T15:32:01+01:00", "alice", "Complete Batch", "_in_progress", "_qc"),
    ]

