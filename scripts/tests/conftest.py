import pytest


@pytest.fixture(autouse=True)
def _git_reads_no_machine_config(monkeypatch, tmp_path_factory):
    """Every git a test runs reads no system or user config, so a test passes on any machine as on
    CI: Apple's git names a new repo's first branch main, and a user's hooks or signing would
    run."""
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path_factory.mktemp("git") / "config"))
    for who in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{who}_NAME", "t")
        monkeypatch.setenv(f"GIT_{who}_EMAIL", "t@t")
