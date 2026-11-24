"""Settings for every test.

Groot reads GROOT_MODEL, GROOT_COUNTRY and GROOT_BACKUPS from your own deadline_agent/.env when it starts.
An empty GROOT_MODEL set here wins over that file, so the tests always run
with the default model, whatever your own Groot is set to use.
"""

import os

os.environ["GROOT_MODEL"] = ""
os.environ["GROOT_COUNTRY"] = ""  # and Sydney time, whatever country your own .env sets
os.environ["GROOT_BACKUPS"] = ""  # and the usual backup models

import pytest


@pytest.fixture(autouse=True)
def never_touch_the_real_deadlines(tmp_path, monkeypatch):
    """Every test saves to a temporary deadlines file, so your real deadlines.json is never read or changed.

    Most test files also set their own temporary file. This is the safety net
    for any test that forgets: on 24 Nov 2026 one did, and saved a test
    deadline into the real file.
    """
    monkeypatch.setenv("DEADLINES_FILE", str(tmp_path / "safety-net-deadlines.json"))
