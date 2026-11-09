"""Importer tests. The MySQL-backed ones read the real legacy schema (legacy_schema.sql) loaded with tests/fixtures/legacy_seed.sql
into a local MariaDB; they are skipped when that server is not running."""
import copy
import os

import pytest
from sqlalchemy import func, select, text

from app import models as m
from app.legacy.importer import DictSource, ImportConflict, MySQLSource, import_legacy, verify_legacy
from tests.conftest import make_user

MYSQL_URL = os.environ.get("WEAZEL_LEGACY_TEST_URL", "mysql+pymysql://weazel_ro:ro_dev@127.0.0.1:3306/qbcore")


@pytest.fixture(scope="module")
def mysql_source():
    try:
        src = MySQLSource(MYSQL_URL)
        rows = src.rows("rp_articles")
    except Exception as e:  # pragma: no cover
        pytest.skip(f"legacy MySQL/MariaDB not reachable: {e}")
    assert rows, "legacy fixture not loaded (see tests/fixtures/legacy_seed.sql)"
    return src


@pytest.fixture
def staff(db):
    # authors that exist on the platform; "Twin Name" is ambiguous on purpose
    make_user(db, "Jo Journalist", "journalist")
    make_user(db, "Ed Editor", "editor")
    make_user(db, "Ivy Intern", "intern")
    make_user(db, "Twin Name", "journalist", email="twin1@weazel.test")
    make_user(db, "Twin Name", "journalist", email="twin2@weazel.test")


def counts(db):
    return {t: db.scalar(select(func.count()).select_from(getattr(m, c))) for t, c in
            [("articles", "Article"), ("comments", "ArticleComment"), ("likes", "ArticleLike"), ("investigations", "Investigation"), ("entries", "InvestigationEntry")]}


def test_import_from_real_mysql_preserves_everything(db, staff, mysql_source):
    rep = import_legacy(db, mysql_source)
    assert counts(db) == {"articles": 7, "comments": 3, "likes": 3, "investigations": 5, "entries": 6}  # orphans excluded, see below
    t = rep.tables
    assert t["article_comments"].skipped_orphans == [4] and t["article_likes"].skipped_orphans == [4]  # nothing dropped silently
    # ids, authorship, timestamps
    a1 = db.get(m.Article, 1)
    assert a1.title == "Braquage à Vinewood" and "☕" in a1.body and "« Aucun blessé »" in a1.body  # accents, guillemets, emoji intact
    assert a1.status == "published" and a1.created_at.isoformat() == "2026-01-10T09:30:00+00:00" and a1.published_at == a1.created_at
    assert a1.author.display_name == "Jo Journalist" and a1.legacy_author_name is None
    assert a1.category.key == "crime" and a1.cover_image_url == "https://cdn.example/img/1.png"
    # statuses
    assert db.get(m.Article, 3).status == "draft" and db.get(m.Article, 4).status == "submitted"
    assert db.get(m.Article, 5).status == "draft" and any("rp_articles 5" in w for w in rep.warnings)
    assert "sports" in rep.categories_created and db.get(m.Article, 5).category.key == "sports"  # unknown category kept, not forced
    # ambiguous and missing authors are kept as text, never guessed
    assert db.get(m.Article, 6).author_id is None and db.get(m.Article, 6).legacy_author_name == "Twin Name"
    assert db.get(m.Article, 7).author_id is None and db.get(m.Article, 7).legacy_author_name is None
    # hostile image URL refused but reported
    assert db.get(m.Article, 6).cover_image_url is None and any("rp_articles 6" in w for w in rep.warnings)
    # comments and likes
    assert db.get(m.ArticleComment, 3).comment == "<script>alert(1)</script>"  # stored as data; rendering escapes
    assert db.get(m.ArticleComment, 2).comment == "Merci pour l'info 🙏"
    assert {(l.article_id, l.citizen_id) for l in db.scalars(select(m.ArticleLike))} == {(1, "CIT001"), (1, "CIT002"), (2, "CIT001")}


def test_dossiers_and_entries_mapping(db, staff, mysql_source):
    rep = import_legacy(db, mysql_source)
    d = {i.id: i for i in db.scalars(select(m.Investigation))}
    assert d[1].reference == "WZ-LEG-0001" and d[1].classification == "standard" and d[1].status == "open"
    assert d[2].classification == "confidential"  # legacy "private" becomes the strictest class, never looser
    assert d[3].status == "concluded" and d[3].closed_at is not None and d[3].classification == "standard"  # "public" has no equivalent: standard
    assert d[4].is_archived and d[4].status == "archived"
    assert d[5].status == "open" and d[5].inv_type == "general" and d[5].legacy_meta["legacy_type"] == "investigation" and d[5].legacy_meta["source_event_id"] == 7
    assert any("rp_dossiers 5" in w for w in rep.warnings)
    # creators become leads through stub accounts keyed by citizenid (no login, no role, no permissions)
    stub = db.scalar(select(m.User).where(m.User.citizen_id == "REP1"))
    assert stub.source == "legacy" and stub.role_id is None and stub.password_hash is None and stub.email is None
    assert db.get(m.InvestigationParticipant, (2, stub.id)).access == "lead"
    assert rep.stub_users_created == 2  # REP1 and REP2
    e = {x.id: x for x in db.scalars(select(m.InvestigationEntry))}
    assert [e[i].verification for i in (1, 2, 3)] == ["rumour", "confirmed", "denial"]
    assert e[6].verification == "unverified_claim" and any("rp_dossier_entries 6" in w for w in rep.warnings)  # unknown type never upgraded to a trusted state
    assert e[3].restricted is True and e[1].restricted is False  # legacy "police" visibility stays restricted
    assert e[1].source_ref is None and e[2].source_ref == "Témoin A"
    assert e[2].legacy_meta["image_path"] == "uploads/a.png" and e[2].legacy_meta["caption"] == "Photo du dock" and e[3].legacy_meta["escalated"] is True
    assert db.get(m.User, e[2].author_id).display_name == "Jo Journalist" and e[2].event_date.isoformat() == "2026-01-05T12:00:00+00:00"


def test_imported_private_dossier_is_not_visible_to_staff_on_the_platform(db, staff, mysql_source, client):
    import_legacy(db, mysql_source)
    from tests.conftest import auth
    editor = db.scalar(select(m.User).where(m.User.display_name == "Ed Editor"))
    r = client.get("/api/v1/investigations", headers=auth(editor)).json()
    refs = {i["reference"] for i in r["items"]}
    assert "WZ-LEG-0002" not in refs and "WZ-LEG-0001" in refs
    assert client.get("/api/v1/investigations/2", headers=auth(editor)).status_code == 404


def test_rerun_is_idempotent_and_dry_run_writes_nothing(db, staff, mysql_source):
    dry = import_legacy(db, mysql_source, dry_run=True)
    assert dry.dry_run and counts(db)["articles"] == 0
    assert db.scalar(select(func.count()).select_from(m.User).where(m.User.source == "legacy")) == 0
    first = import_legacy(db, mysql_source)
    before = counts(db)
    again = import_legacy(db, mysql_source)
    assert counts(db) == before
    assert all(t.inserted == 0 and t.updated == 0 for t in again.tables.values())
    assert first.tables["rp_articles"].inserted == 7 and again.tables["rp_articles"].unchanged == 7


def test_new_rows_are_picked_up_and_source_edits_refresh_unmodified_rows(db, staff):
    from tests.test_legacy_import import SAMPLE
    src = DictSource(copy.deepcopy(SAMPLE))
    import_legacy(db, src)
    src.data["rp_articles"][0]["title"] = "Titre corrigé côté MySQL"
    src.data["rp_articles"].append({"id": 20, "title": "Nouveau", "content": "c", "author": "Jo Journalist", "image": None, "created_at": "2026-02-01 10:00:00", "status": "published", "category": "crime"})
    rep = import_legacy(db, src)
    assert rep.tables["rp_articles"].updated == 1 and rep.tables["rp_articles"].inserted == 1
    assert db.get(m.Article, 1).title == "Titre corrigé côté MySQL" and db.get(m.Article, 20) is not None


def test_platform_edits_are_never_overwritten_by_a_rerun(db, staff):
    src = DictSource(copy.deepcopy(SAMPLE))
    import_legacy(db, src)
    art = db.get(m.Article, 1)
    art.title, art.platform_modified = "Edited on the platform", True
    db.commit()
    src.data["rp_articles"][0]["title"] = "Changed again in MySQL"
    rep = import_legacy(db, src)
    assert db.get(m.Article, 1).title == "Edited on the platform"
    assert rep.tables["rp_articles"].skipped_modified == [1]
    assert verify_legacy(db, src)["tables"]["rp_articles"]["modified_on_platform_ids"] == [1]


def test_id_collision_with_native_record_aborts_without_writing(db, staff):
    native = m.Article(id=1, title="Native article", body="b", status="draft", platform_modified=True)
    db.add(native)
    db.commit()
    with pytest.raises(ImportConflict):
        import_legacy(db, DictSource(copy.deepcopy(SAMPLE)))
    assert db.get(m.Article, 1).title == "Native article"
    assert db.scalar(select(func.count()).select_from(m.Article)) == 1  # the whole import rolled back


def test_sequences_continue_after_import(db, staff, mysql_source, client):
    import_legacy(db, mysql_source)
    from tests.conftest import auth
    jo = db.scalar(select(m.User).where(m.User.display_name == "Jo Journalist"))
    new = client.post("/api/v1/articles", headers=auth(jo), json={"title": "After migration", "body": "b"}).json()
    assert new["id"] == 8  # the next id follows the highest imported id, no collision
    inv = client.post("/api/v1/investigations", headers=auth(jo), json={"title": "New case"}).json()
    assert inv["id"] == 6


def test_verification_report_detects_loss_and_tampering(db, staff, mysql_source):
    import_legacy(db, mysql_source)
    ok = verify_legacy(db, mysql_source)
    assert ok["ok"] is True
    assert ok["tables"]["rp_articles"]["source_rows"] == 7 and ok["tables"]["rp_articles"]["present"] == 7
    assert ok["tables"]["article_comments"]["orphans_in_source"] == [4]
    db.execute(text("DELETE FROM investigation_entries WHERE id = 2"))
    db.execute(text("UPDATE articles SET legacy_hash = 'tampered' WHERE id = 3"))
    db.commit()
    bad = verify_legacy(db, mysql_source)
    assert bad["ok"] is False
    assert bad["tables"]["rp_dossier_entries"]["missing_ids"] == [2] and bad["tables"]["rp_articles"]["content_mismatch_ids"] == [3]


def test_importer_only_reads_mysql(mysql_source):
    # the account used here has SELECT only, so any write attempt would raise; also the importer API has no write path
    with pytest.raises(Exception):
        with mysql_source.engine.begin() as c:
            c.execute(text("DELETE FROM rp_articles"))
    assert len(mysql_source.rows("rp_articles")) == 7
    with pytest.raises(ValueError):
        mysql_source.rows("players")  # only the five known tables can be read


SAMPLE = {
    "rp_articles": [{"id": 1, "title": "Titre", "content": "Texte", "author": "Jo Journalist", "image": None, "created_at": "2026-01-10 09:30:00", "status": "published", "category": "crime"}],
    "article_comments": [], "article_likes": [], "rp_dossiers": [], "rp_dossier_entries": [],
}
