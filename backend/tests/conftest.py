import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp()) / "test.db"
os.environ["GPI_DATABASE_URL"] = f"sqlite:///{_tmp.as_posix()}"
os.environ["GPI_SECRET_KEY"] = "test"
os.environ["GPI_REGISTRATION"] = "invite"

import pytest  # noqa: E402

from gpi import models  # noqa: E402,F401
from gpi.db import Base, engine, session_scope  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    from gpi.pipeline.brand import seed_rules
    with session_scope() as s:
        seed_rules(s)
    yield
