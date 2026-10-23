import os
import uuid

import httpx
import pytest
from sqlalchemy.schema import CreateSchema, DropSchema

from taskforge.api.app import create_app
from taskforge.core.config import Settings
from taskforge.storage.database import Database

ADMIN = "test-admin-" + "a" * 40
VIEWER = "test-viewer-" + "v" * 40
OTHER = "test-other-" + "o" * 40
REVIEWER = "test-reviewer-" + "r" * 40


@pytest.fixture
def settings(tmp_path):
    return Settings(
        storage_url=f"sqlite+aiosqlite:///{tmp_path / 'state.db'}",
        data_dir=tmp_path / "data",
        allow_host_execution=True,
        lease_seconds=6,
        tokens=[
            {"token": ADMIN, "name": "admin", "role": "admin", "projects": ["default"]},
            {"token": REVIEWER, "name": "reviewer", "role": "admin", "projects": ["default"]},
            {"token": VIEWER, "name": "viewer", "role": "viewer", "projects": ["default"]},
            {"token": OTHER, "name": "other", "role": "admin", "projects": ["other"]},
        ],
    )


@pytest.fixture
async def db(settings):
    url = os.getenv("TASKFORGE_TEST_POSTGRES_URL", settings.storage_url)
    database = Database(url)
    namespace = None
    if url.startswith("postgresql"):
        namespace = "test_" + uuid.uuid4().hex
        async with database.engine.begin() as conn:
            await conn.execute(CreateSchema(namespace))
        database.engine = database.engine.execution_options(schema_translate_map={None: namespace})
    await database.initialize()
    yield database
    if namespace:
        async with database.engine.begin() as conn:
            await conn.execute(DropSchema(namespace, cascade=True))
    await database.close()


@pytest.fixture
async def client(settings, db):
    app = create_app(settings, db)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer " + ADMIN},
        ) as connection,
    ):
        yield connection
