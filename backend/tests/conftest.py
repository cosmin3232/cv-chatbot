import pytest


@pytest.fixture(autouse=True)
def isolated_job_archive(tmp_path, monkeypatch):
    """Never write test uploads into the owner's real archive."""
    monkeypatch.setenv("JOB_STORAGE_PATH", str(tmp_path / "jobs.sqlite3"))
