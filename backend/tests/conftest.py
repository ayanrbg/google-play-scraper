import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp()) / "test.db"
os.environ["PLAYTREND_DATABASE_URL"] = f"sqlite:///{_tmp.as_posix()}"
os.environ["PLAYTREND_SECRET_KEY"] = "test"
os.environ["PLAYTREND_REGISTRATION"] = "invite"

import pytest  # noqa: E402

from playtrend import models  # noqa: E402,F401
from playtrend.db import Base, engine, session_scope  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    from playtrend.pipeline.brand import seed_rules
    with session_scope() as s:
        seed_rules(s)
    # process-wide state of the API: overview cache and per-IP request counters
    from playtrend.api import games, ratelimit
    games._overview_cache.clear()
    ratelimit._hits.clear()
    yield
