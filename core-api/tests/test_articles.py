from datetime import datetime, timedelta, timezone

from app import models as m

API = "/api/v1"
ART = {"title": "Harbour corruption", "body": "Line one.\nLine two.", "summary": "S", "category": "crime", "tags": ["Port", "port", "Crime "]}


def create(client, w, user=None, **over):
    r = client.post(f"{API}/articles", headers=w.h(user or w.jo), json={**ART, **over})
    assert r.status_code == 201, r.text
    return r.json()


def move(client, w, user, art_id, to, **kw):
    return client.post(f"{API}/articles/{art_id}/transition", headers=w.h(user), json={"to": to, **kw})


def to_approved(client, w, art_id, reviewer=None, approver=None):
    assert move(client, w, w.jo, art_id, "submitted").status_code == 200
    assert move(client, w, reviewer or w.editor, art_id, "in_review").status_code == 200
    r = move(client, w, approver or w.editor, art_id, "approved")
    assert r.status_code == 200, r.text


def test_full_lifecycle_with_history(client, w):
    a = create(client, w)
    assert a["status"] == "draft" and a["tags"] == ["port", "crime"] and a["author"] == "Jo Journalist"
    to_approved(client, w, a["id"])
    r = move(client, w, w.editor, a["id"], "published", destination="newsroom")
    assert r.status_code == 200 and r.json()["status"] == "published" and r.json()["published_at"]
    events = client.get(f"{API}/articles/{a['id']}/events", headers=w.h(w.editor)).json()
    assert [e["to_status"] for e in events if e["kind"] == "transition"] == ["submitted", "in_review", "approved", "published"]
    assert client.get(f"{API}/articles/{a['id']}/events", headers=w.h(w.jo)).status_code == 200  # the author sees the history


def test_author_cannot_review_or_approve_own_work_even_as_editor(client, w):
    a = create(client, w, user=w.editor)  # editor writes it
    assert move(client, w, w.editor, a["id"], "submitted").status_code == 200
    r = move(client, w, w.editor, a["id"], "in_review")
    assert r.status_code == 403 and "Independent" in r.json()["detail"]
    assert move(client, w, w.editor2, a["id"], "in_review").status_code == 200
    assert move(client, w, w.editor, a["id"], "approved").status_code == 403  # still not their own
    assert move(client, w, w.editor2, a["id"], "approved").status_code == 200


def test_assignee_is_not_independent(client, w):
    a = create(client, w)
    assert client.put(f"{API}/articles/{a['id']}/assignees", headers=w.h(w.editor), json={"user_ids": [w.editor2.id]}).status_code == 200
    move(client, w, w.jo, a["id"], "submitted")
    assert move(client, w, w.editor2, a["id"], "in_review").status_code == 403
    assert move(client, w, w.editor, a["id"], "in_review").status_code == 200


def test_unauthorised_roles_cannot_review_approve_publish(client, w):
    a = create(client, w)
    move(client, w, w.jo, a["id"], "submitted")
    for u in (w.intern, w.jane, w.senior):
        assert move(client, w, u, a["id"], "in_review").status_code in (403, 404)
    move(client, w, w.editor, a["id"], "in_review")
    for u in (w.intern, w.jane, w.senior, w.inv_editor):
        assert move(client, w, u, a["id"], "approved").status_code in (403, 404)  # 404: not even visible to that user
    move(client, w, w.editor, a["id"], "approved")
    for u in (w.intern, w.jane, w.senior, w.jo):
        assert move(client, w, u, a["id"], "published").status_code in (403, 404)
    assert client.get(f"{API}/articles/{a['id']}", headers=w.h(w.jo)).json()["status"] == "approved"  # nothing slipped through


def test_invalid_and_skipped_transitions_rejected(client, w):
    a = create(client, w)
    assert move(client, w, w.editor, a["id"], "published").status_code == 409
    assert move(client, w, w.editor, a["id"], "approved").status_code == 409
    assert move(client, w, w.jo, a["id"], "nonsense").status_code == 409


def test_request_changes_needs_feedback_and_author_can_revise(client, w):
    a = create(client, w)
    move(client, w, w.jo, a["id"], "submitted")
    move(client, w, w.editor, a["id"], "in_review")
    assert move(client, w, w.editor, a["id"], "revision_requested").status_code == 422
    r = move(client, w, w.editor, a["id"], "revision_requested", feedback=[{"field": "body", "comment": "Source the second claim"}])
    assert r.status_code == 200
    d = client.get(f"{API}/articles/{a['id']}", headers=w.h(w.jo)).json()
    assert d["can_edit"] is True
    ev = client.get(f"{API}/articles/{a['id']}/events", headers=w.h(w.jo)).json()
    assert ev[-1]["feedback"] == [{"field": "body", "comment": "Source the second claim"}]
    ok = client.patch(f"{API}/articles/{a['id']}", headers=w.h(w.jo), json={"expected_version": d["version"], "body": "Revised body", "change_note": "sourced"})
    assert ok.status_code == 200
    assert move(client, w, w.jo, a["id"], "submitted").status_code == 200


def test_edit_rules_by_state_and_person(client, w):
    a = create(client, w)
    v = a["version"]
    assert client.patch(f"{API}/articles/{a['id']}", headers=w.h(w.jane), json={"expected_version": v, "title": "hijack"}).status_code == 403
    assert client.patch(f"{API}/articles/{a['id']}", headers=w.h(w.intern), json={"expected_version": v, "title": "hijack"}).status_code in (403, 404)
    assert client.patch(f"{API}/articles/{a['id']}", headers=w.h(w.jo), json={"expected_version": v, "title": "Mine"}).status_code == 200
    move(client, w, w.jo, a["id"], "submitted")
    d = client.get(f"{API}/articles/{a['id']}", headers=w.h(w.jo)).json()
    assert client.patch(f"{API}/articles/{a['id']}", headers=w.h(w.jo), json={"expected_version": d["version"], "title": "late"}).status_code == 403  # author locked out while in review
    assert client.patch(f"{API}/articles/{a['id']}", headers=w.h(w.editor), json={"expected_version": d["version"], "title": "Edited by editor"}).status_code == 200
    d = client.get(f"{API}/articles/{a['id']}", headers=w.h(w.editor)).json()
    assert d["author"] == "Jo Journalist" and d["title"] == "Edited by editor"  # original author preserved


def test_assigned_senior_can_edit_but_unassigned_cannot(client, w):
    a = create(client, w)
    v = a["version"]
    assert client.patch(f"{API}/articles/{a['id']}", headers=w.h(w.senior), json={"expected_version": v, "title": "x"}).status_code in (403, 404)
    client.put(f"{API}/articles/{a['id']}/assignees", headers=w.h(w.editor), json={"user_ids": [w.senior.id]})
    d = client.get(f"{API}/articles/{a['id']}", headers=w.h(w.senior)).json()
    assert client.patch(f"{API}/articles/{a['id']}", headers=w.h(w.senior), json={"expected_version": d["version"], "title": "x"}).status_code == 200


def test_optimistic_concurrency(client, w):
    a = create(client, w)
    h = w.h(w.jo)
    assert client.patch(f"{API}/articles/{a['id']}", headers=h, json={"expected_version": a["version"], "title": "A"}).status_code == 200
    stale = client.patch(f"{API}/articles/{a['id']}", headers=h, json={"expected_version": a["version"], "title": "B"})
    assert stale.status_code == 409


def test_published_article_cannot_be_edited_only_corrected_with_history(client, w):
    a = create(client, w)
    to_approved(client, w, a["id"])
    move(client, w, w.editor, a["id"], "published")
    d = client.get(f"{API}/articles/{a['id']}", headers=w.h(w.editor)).json()
    for u in (w.jo, w.editor, w.admin):
        r = client.patch(f"{API}/articles/{a['id']}", headers=w.h(u), json={"expected_version": d["version"], "body": "silent edit"})
        assert r.status_code in (403, 409), u.display_name
    assert client.post(f"{API}/articles/{a['id']}/correct", headers=w.h(w.jo), json={"expected_version": d["version"], "note": "fix", "body": "x"}).status_code == 403
    r = client.post(f"{API}/articles/{a['id']}/correct", headers=w.h(w.editor), json={"expected_version": d["version"], "note": "Corrected the date", "body": "Line one.\nLine 2 corrected."})
    assert r.status_code == 200 and r.json()["status"] == "corrected" and r.json()["correction_note"] == "Corrected the date"
    revs = client.get(f"{API}/articles/{a['id']}/revisions", headers=w.h(w.editor)).json()
    assert [x["change_note"] for x in revs][-2].startswith("before correction")
    first, last = revs[0]["revision_no"], revs[-1]["revision_no"]
    diff = client.get(f"{API}/articles/{a['id']}/revisions/{first}/diff/{last}", headers=w.h(w.editor)).json()
    assert "body" in diff["changed_fields"] and diff["lines_removed"] >= 1 and diff["lines_added"] >= 1
    pub = client.get(f"{API}/public/articles/{a['id']}").json()
    assert pub["correction_note"] == "Corrected the date" and "corrected" in pub["body"]


def test_schedule_requires_future_time(client, w):
    a = create(client, w)
    to_approved(client, w, a["id"])
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    assert move(client, w, w.editor, a["id"], "scheduled", scheduled_for=past).status_code == 422
    assert move(client, w, w.editor, a["id"], "scheduled", scheduled_for=datetime.now().isoformat()).status_code == 422  # naive time refused
    future = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
    assert move(client, w, w.editor, a["id"], "scheduled", scheduled_for=future).status_code == 200
    assert client.get(f"{API}/public/articles", ).json()["total"] == 0  # scheduled is not public yet


def test_visibility_of_unpublished_articles(client, w):
    a = create(client, w)
    assert client.get(f"{API}/articles/{a['id']}", headers=w.h(w.intern)).status_code == 200 or True
    # intern has no article.read and is not involved -> invisible everywhere
    assert client.get(f"{API}/articles/{a['id']}", headers=w.h(w.intern)).status_code == 404
    ids = [x["id"] for x in client.get(f"{API}/articles", headers=w.h(w.intern)).json()["items"]]
    assert a["id"] not in ids
    assert client.get(f"{API}/articles?q=Harbour", headers=w.h(w.intern)).json()["total"] == 0
    assert client.get(f"{API}/search?q=Harbour", headers=w.h(w.intern)).json()["articles"] == []
    assert client.get(f"{API}/articles/{a['id']}", headers=w.h(w.jane)).status_code == 200  # journalists read the newsroom
    assert client.get(f"{API}/public/articles/{a['id']}").status_code == 404


def test_public_api_exposes_no_internal_data(client, w):
    a = create(client, w, internal_notes="SECRET NOTE", source_refs=[{"name": "Deep Throat"}])
    client.put(f"{API}/articles/{a['id']}/assignees", headers=w.h(w.editor), json={"user_ids": [w.jane.id]})
    to_approved(client, w, a["id"])
    move(client, w, w.editor, a["id"], "published")
    body = client.get(f"{API}/public/articles/{a['id']}").text
    listing = client.get(f"{API}/public/articles").text
    for leak in ("SECRET NOTE", "Deep Throat", "Jane Journalist", "internal_notes", "source_refs", "assignees"):
        assert leak not in body and leak not in listing, leak
    assert "Jo Journalist" in body


def test_internal_notes_visibility(client, w):
    a = create(client, w, internal_notes="for editors only")
    assert client.get(f"{API}/articles/{a['id']}", headers=w.h(w.jo)).json()["internal_notes"] == "for editors only"  # author
    assert client.get(f"{API}/articles/{a['id']}", headers=w.h(w.editor)).json()["internal_notes"] == "for editors only"
    assert client.get(f"{API}/articles/{a['id']}", headers=w.h(w.jane)).json()["internal_notes"] is None  # other journalist, not involved


def test_input_validation_and_url_safety(client, w):
    h = w.h(w.jo)
    assert client.post(f"{API}/articles", headers=h, json={**ART, "cover_image_url": "javascript:alert(1)"}).status_code == 422
    assert client.post(f"{API}/articles", headers=h, json={**ART, "cover_image_url": 'https://x.test/a" onerror="x'}).status_code == 422
    assert client.post(f"{API}/articles", headers=h, json={**ART, "category": "nope"}).status_code == 422
    assert client.post(f"{API}/articles", headers=h, json={**ART, "article_type": "nope"}).status_code == 422
    assert client.post(f"{API}/articles", headers=h, json={**ART, "title": ""}).status_code == 422
    assert client.post(f"{API}/articles", headers=h, json={**ART, "title": "x" * 300}).status_code == 422
    assert client.post(f"{API}/articles", headers=h, json={**ART, "title": "  \x00\x07  "}).status_code == 422
    assert client.get(f"{API}/articles?sort=password", headers=h).status_code == 422
    assert client.get(f"{API}/articles?status=hacked", headers=h).status_code == 422
    stored = client.post(f"{API}/articles", headers=h, json={**ART, "title": "<b>bold</b> & co"}).json()
    assert stored["title"] == "<b>bold</b> & co"  # stored verbatim; the UI renders text, never HTML


def test_search_filters_pagination_sorting(client, w):
    for i in range(25):
        create(client, w, title=f"Story {i:02d}", category="crime" if i % 2 else "politics")
    h = w.h(w.jo)
    first = client.get(f"{API}/articles?page_size=10&sort=title", headers=h).json()
    assert first["total"] == 25 and len(first["items"]) == 10 and first["items"][0]["title"] == "Story 00"
    assert len(client.get(f"{API}/articles?page_size=10&page=3&sort=title", headers=h).json()["items"]) == 5
    assert client.get(f"{API}/articles?category=crime", headers=h).json()["total"] == 12
    assert client.get(f"{API}/articles?q=story 1", headers=h).json()["total"] == 10
    assert client.get(f"{API}/articles?q=100%25", headers=h).json()["total"] == 0  # % is literal, not a wildcard
    assert client.get(f"{API}/articles?page_size=5000", headers=h).json()["page_size"] == 100
    assert client.get(f"{API}/articles?tag=port", headers=h).json()["total"] == 25


def test_autosave_and_recovery(client, w):
    a = create(client, w)
    h = w.h(w.jo)
    assert client.put(f"{API}/articles/{a['id']}/autosave", headers=h, json={"base_version": a["version"], "payload": {"body": "unsaved words", "evil": "x"}}).status_code == 200
    got = client.get(f"{API}/articles/{a['id']}/autosave", headers=h).json()["autosave"]
    assert got["payload"] == {"body": "unsaved words"} and got["stale"] is False
    assert client.get(f"{API}/articles/{a['id']}/autosave", headers=w.h(w.jane)).json()["autosave"] is None  # private to the user
    assert client.put(f"{API}/articles/{a['id']}/autosave", headers=w.h(w.jane), json={"base_version": 1, "payload": {"body": "x"}}).status_code == 403
    client.patch(f"{API}/articles/{a['id']}", headers=h, json={"expected_version": a["version"], "title": "Saved"})
    assert client.get(f"{API}/articles/{a['id']}/autosave", headers=h).json()["autosave"] is None  # cleared by a real save


def test_linked_investigation_not_revealed_in_article(client, w):
    secret = client.post(f"{API}/investigations", headers=w.h(w.jo), json={"title": "Secret case", "classification": "confidential"}).json()
    a = create(client, w)
    assert client.put(f"{API}/articles/{a['id']}/investigations/{secret['id']}", headers=w.h(w.jo)).status_code == 200
    mine = client.get(f"{API}/articles/{a['id']}", headers=w.h(w.jo)).json()
    assert [i["title"] for i in mine["investigations"]] == ["Secret case"]
    other = client.get(f"{API}/articles/{a['id']}", headers=w.h(w.editor)).json()
    assert other["investigations"] == []  # editors can read the article but not know about the confidential case
    b = create(client, w, user=w.editor)
    assert client.put(f"{API}/articles/{b['id']}/investigations/{secret['id']}", headers=w.h(w.editor)).status_code == 404
    assert client.put(f"{API}/articles/{b['id']}/investigations/9999", headers=w.h(w.editor)).status_code == 404  # same answer as a real hidden case
