import os

os.environ.update(
    WEAZEL_ENVIRONMENT="test", WEAZEL_AUTH_MODE="password",
    WEAZEL_DATABASE_URL=os.environ.get("WEAZEL_TEST_DATABASE_URL", "postgresql+psycopg2://weazel:weazel_dev@127.0.0.1:5432/weazel_test"),
    WEAZEL_JWT_SECRET="test-secret-test-secret-test-secret-123", WEAZEL_AI_PROVIDER="mock",
)

import bcrypt  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app import models as m  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.security import create_access_token, login_limiter  # noqa: E402
from app.seed import seed_defaults  # noqa: E402

PW_HASH = bcrypt.hashpw(b"correct horse battery", bcrypt.gensalt(rounds=4)).decode()
ROOT = os.path.join(os.path.dirname(__file__), "..")


@pytest.fixture(scope="session", autouse=True)
def schema():
    """The test schema is built by the real Alembic migration, so every run also tests the migration."""
    cfg = Config(os.path.join(ROOT, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(ROOT, "alembic"))
    with engine.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def clean_db(schema):
    with engine.begin() as c:
        names = [r[0] for r in c.execute(text("select tablename from pg_tables where schemaname='public' and tablename <> 'alembic_version'"))]
        c.execute(text("TRUNCATE " + ", ".join(names) + " RESTART IDENTITY CASCADE"))
    with SessionLocal() as s:
        seed_defaults(s)
    login_limiter.reset()
    yield


@pytest.fixture
def db():
    with SessionLocal() as s:
        yield s


@pytest.fixture
def client():
    return TestClient(app)


def make_user(db, name: str, role: str | None, email: str | None = None, **kw) -> m.User:
    r = db.query(m.Role).filter_by(key=role).one() if role else None
    u = m.User(display_name=name, email=email or f"{name.lower().replace(' ', '.')}@weazel.test", password_hash=PW_HASH,
               role_id=r.id if r else None, source="local", **kw)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def auth(u: m.User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(u.id, u.token_version)}"}


class World:
    def __init__(self, db):
        self.db = db
        self.intern = make_user(db, "Ivy Intern", "intern")
        self.jo = make_user(db, "Jo Journalist", "journalist")
        self.jane = make_user(db, "Jane Journalist", "journalist")
        self.senior = make_user(db, "Sam Senior", "senior_journalist")
        self.editor = make_user(db, "Ed Editor", "editor")
        self.editor2 = make_user(db, "Eve Editor", "editor")
        self.inv_editor = make_user(db, "Ines Investigator", "investigative_editor")
        self.eic = make_user(db, "Chief One", "editor_in_chief")
        self.eic2 = make_user(db, "Chief Two", "editor_in_chief")
        self.admin = make_user(db, "Root Admin", "system_admin")
        self.stub = make_user(db, "No Role", None)

    def h(self, user) -> dict:
        self.db.refresh(user)
        return auth(user)


@pytest.fixture
def w(db):
    return World(db)
