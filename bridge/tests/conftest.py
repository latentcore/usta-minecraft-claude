import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from usta.blockdb import BlockDB, set_db  # noqa: E402

DB = BlockDB.from_file(ROOT / "tests" / "data" / "blockdb-26.3.json.gz")
set_db(DB)


@pytest.fixture
def db():
    return DB
