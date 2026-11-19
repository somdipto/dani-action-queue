"""
Shared pytest fixtures.

Sets DAQ_DB_PATH and DAQ_ALLOWLIST_PATH to temp files so tests are fully isolated.
"""
import json
import os
import pytest

from app.db import init_db


@pytest.fixture(autouse=True, scope="session")
def _temp_db(tmp_path_factory):
    db_file = tmp_path_factory.mktemp("db") / "test_queue.db"
    os.environ["DAQ_DB_PATH"] = str(db_file)
    allowlist_file = tmp_path_factory.mktemp("cfg") / "allowlist.json"
    allowlist_file.write_text(json.dumps(["echo", "date", "ls"]))
    os.environ["DAQ_ALLOWLIST_PATH"] = str(allowlist_file)
    init_db(str(db_file))
    yield
